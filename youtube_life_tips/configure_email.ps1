$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateRoot = Join-Path $ProjectRoot "state"
$ConfigPath = Join-Path $StateRoot "config.local.json"
$PasswordPath = Join-Path $StateRoot "gmail_app_password.dpapi"
$MailerPath = Join-Path $ProjectRoot "send_result_email.ps1"

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "state/config.local.json is missing. Complete the YouTube channel setup first."
}

$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Email = $Config.email_notifications
if (-not $Email) {
    $Email = [pscustomobject]@{
        enabled = $false
        sender = "appleap385@gmail.com"
        recipient = "aaz0919@naver.com"
        password_file = "state/gmail_app_password.dpapi"
    }
    $Config | Add-Member -NotePropertyName email_notifications -NotePropertyValue $Email
}

Write-Host "Enter the Gmail App Password for $($Email.sender). Input is hidden."
Write-Host "Use the 16-character app password without spaces; this is not your Google account password."
$SecurePassword = Read-Host "Gmail App Password" -AsSecureString
if ($SecurePassword.Length -lt 16) {
    throw "The entered value is too short for a Gmail App Password. No email setting was changed."
}

New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
$EncryptedPassword = ConvertFrom-SecureString -SecureString $SecurePassword
[System.IO.File]::WriteAllText($PasswordPath, $EncryptedPassword, [System.Text.Encoding]::ASCII)
$Email.enabled = $true
$Email.sender = "appleap385@gmail.com"
$Email.recipient = "aaz0919@naver.com"
$Email.password_file = "state/gmail_app_password.dpapi"
$Json = $Config | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ConfigPath, $Json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

Write-Host "Sending a test message to $($Email.recipient)..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $MailerPath -Test
if ($LASTEXITCODE -ne 0) {
    throw "The test email failed. The encrypted password is saved locally; check the app password and try again."
}
Write-Host "Email notifications are enabled and the test message was accepted by Gmail SMTP."
