param(
    [string]$ReportPath,
    [switch]$Test
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ProjectRoot "state\config.local.json"
$PasswordPath = Join-Path $ProjectRoot "state\gmail_app_password.dpapi"

try {
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { throw "Local email configuration is missing." }
    if (-not (Test-Path -LiteralPath $PasswordPath -PathType Leaf)) { throw "Encrypted Gmail App Password is missing; run configure_email.ps1." }
    if (-not $Test -and -not $ReportPath) { throw "Pass -ReportPath or -Test." }

    $Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $Email = $Config.email_notifications
    if (-not $Email.enabled) { throw "Email notifications are not enabled." }

    $SecurePassword = ConvertTo-SecureString -String (Get-Content -LiteralPath $PasswordPath -Raw)
    $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    try {
        $PlainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
        $Message = [System.Net.Mail.MailMessage]::new()
        $Message.From = [System.Net.Mail.MailAddress]::new([string]$Email.sender)
        $Message.To.Add([string]$Email.recipient)
        $Message.SubjectEncoding = [Text.Encoding]::UTF8
        $Message.BodyEncoding = [Text.Encoding]::UTF8
        $Message.IsBodyHtml = $false

        if ($Test) {
            $Message.Subject = "하루 생활꿀팁 자동화 이메일 알림 테스트"
            $Message.Body = "테스트 메일입니다. 자동화 실행 결과가 이 주소로 발송됩니다."
        } else {
            $Report = Get-Content -LiteralPath $ReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $ReleaseLabel = if ($Report.slot -eq "manual") { "요청에 따른 즉시 게시" } elseif ($Report.slot -eq "pm") { "오후 7시" } else { "오전 7시" }
            $StatusLabel = switch ($Report.status) {
                "scheduled" { "성공: YouTube 공개 예약 완료" }
                "published" { "성공: YouTube 즉시 공개 완료" }
                "cancelled" { "취소: 소재 3회 제작 후 최종 검수 미통과" }
                "skipped" { "건너뜀" }
                "failed" { "실패" }
                default { [string]$Report.status }
            }
            $Lines = @(
                "날짜: $($Report.date) (한국 시간)",
                "회차: $ReleaseLabel",
                "결과: $StatusLabel",
                "단계: $($Report.stage)"
            )
            if ($Report.title) { $Lines += "제목: $($Report.title)" }
            if ($Report.topic) { $Lines += "주제: $($Report.topic)" }
            if ($Report.scheduled_publish_at_kst) { $Lines += "공개 예약: $($Report.scheduled_publish_at_kst)" }
            if ($Report.url) { $Lines += "YouTube: $($Report.url)" }
            if ($Report.reason) { $Lines += "사유: $($Report.reason)" }
            if ($Report.email_notification -eq "failed") { $Lines += "주의: 결과 메일 발송에도 실패했습니다. PC의 work/mailbox/logs/email.log를 확인하세요." }
            $Message.Subject = "생활꿀팁 실행 결과 - $($Report.date) $ReleaseLabel - $($Report.status)"
            $Message.Body = $Lines -join [Environment]::NewLine
        }

        $Smtp = [System.Net.Mail.SmtpClient]::new("smtp.gmail.com", 587)
        $Smtp.EnableSsl = $true
        $Smtp.Timeout = 30000
        $Smtp.Credentials = [System.Net.NetworkCredential]::new([string]$Email.sender, $PlainPassword)
        $Smtp.Send($Message)
        $Message.Dispose()
        $Smtp.Dispose()
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
        Remove-Variable PlainPassword,SecurePassword -ErrorAction SilentlyContinue
    }
    Write-Output "Email sent."
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
