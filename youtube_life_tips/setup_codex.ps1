$ErrorActionPreference = "Stop"

$InstallRoot = if ($env:LIFETIPS_CODEX_HOME) { $env:LIFETIPS_CODEX_HOME } else { "D:\Tools\Codex" }
$Codex = Get-ChildItem -LiteralPath $InstallRoot -Filter "codex.exe" -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\bin\\codex\.exe$" } |
    Select-Object -First 1
if (-not $Codex) { throw "Codex CLI was not found under '$InstallRoot'. Install it there or set LIFETIPS_CODEX_HOME." }

function Invoke-CodexCli([string]$Arguments) {
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $Codex.FullName
    $StartInfo.Arguments = $Arguments
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo
    [void]$Process.Start()
    $Stdout = $Process.StandardOutput.ReadToEnd()
    $Stderr = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()
    $Result = @{ ExitCode = $Process.ExitCode; Output = ($Stdout + $Stderr).Trim() }
    $Process.Dispose()
    return $Result
}

$VersionResult = Invoke-CodexCli "--version"
if ($VersionResult.ExitCode -ne 0 -or $VersionResult.Output -notmatch "^codex-cli ") {
    throw "Invalid Codex CLI executable: $($VersionResult.Output)"
}
$LoginResult = Invoke-CodexCli "login status"
if ($LoginResult.ExitCode -ne 0 -or $LoginResult.Output -notmatch "Logged in using ChatGPT") {
    throw "The current Windows user's Codex CLI must be signed in using ChatGPT. Result: $($LoginResult.Output)"
}

Write-Host "Using the existing Codex CLI: $($Codex.FullName)"
Write-Host "$($VersionResult.Output); $($LoginResult.Output)"
Write-Host "The daily workflow uses this external CLI and does not depend on a project-local copy."
