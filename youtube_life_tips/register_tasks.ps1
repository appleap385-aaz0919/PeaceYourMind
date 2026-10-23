$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$MailboxScript = Join-Path $ProjectRoot "codex_mailbox.py"
$WatcherTaskName = "Life Tips - Mailbox Watcher"
$DailyTaskName = "Life Tips - Daily Queue"
$PythonLauncher = (Get-Command py.exe -ErrorAction Stop).Source
$PythonExe = (& $PythonLauncher -3 -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Python 3 could not be resolved from the py launcher." }

$TimeZone = Get-TimeZone
if ($TimeZone.Id -ne "Korea Standard Time") {
    throw "Set the Windows time zone to Korea Standard Time before registering the 03:00/07:00 schedule."
}

Write-Host "Checking Codex, renderer, OAuth, and the separate YouTube channel..."
$DoctorOutput = & $PythonExe $MailboxScript doctor --require-youtube 2>&1
$DoctorExitCode = $LASTEXITCODE
$DoctorOutput | ForEach-Object { Write-Host $_ }
if ($DoctorExitCode -ne 0) {
    throw "Readiness check failed. Configure this project's own channel ID and OAuth files, then run this script again. No tasks were registered."
}

$PythonDirectory = Split-Path -Parent $PythonExe
$PythonwExe = Join-Path $PythonDirectory "pythonw.exe"
if (-not (Test-Path -LiteralPath $PythonwExe)) { $PythonwExe = $PythonExe }
$UserId = "$env:USERDOMAIN\$env:USERNAME"
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$WatcherAction = New-ScheduledTaskAction -Execute $PythonwExe `
    -Argument "`"$MailboxScript`" watch --poll-seconds 2" -WorkingDirectory $ProjectRoot
$DailyAction = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument "`"$MailboxScript`" enqueue --today" -WorkingDirectory $ProjectRoot
$WatcherTrigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$DailyTrigger = New-ScheduledTaskTrigger -Daily -At "3:00AM"
$WatcherSettings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable:$false -WakeToRun:$false `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$DailySettings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable:$false -WakeToRun:$false `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $WatcherTaskName -Action $WatcherAction -Trigger $WatcherTrigger `
    -Principal $Principal -Settings $WatcherSettings -Description "Low-memory local Codex life-tips mailbox watcher." -Force | Out-Null
Register-ScheduledTask -TaskName $DailyTaskName -Action $DailyAction -Trigger $DailyTrigger `
    -Principal $Principal -Settings $DailySettings -Description "Queues today's life-tips short at 03:00 Korea time; missed starts are skipped." -Force | Out-Null

Write-Host "Registered '$WatcherTaskName' (starts at your Windows logon)."
Write-Host "Registered '$DailyTaskName' (daily at 03:00 Korea time; no catch-up after a missed start)."
Write-Host "The workflow stops accepting uploads at 06:30 so a completed video can be scheduled for 07:00."
