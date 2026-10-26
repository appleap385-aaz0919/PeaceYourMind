$ErrorActionPreference = "Stop"

$TaskNames = @("Life Tips - Daily Queue", "Life Tips - Evening Queue", "Life Tips - Mailbox Watcher")
foreach ($TaskName in $TaskNames) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed '$TaskName'."
    } else {
        Write-Host "'$TaskName' is not registered."
    }
}
