# Register the one-time "close remaining positions" task for Monday 08:55.
# Task creation needs admin. Run in an ELEVATED PowerShell BEFORE Monday 08:55:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\tropi\invest_register_close_remaining.ps1"
$xmlPath = 'C:\Users\tropi\task_invest_close_remaining.xml'
$name = 'invest_close_remaining'
$xml = [System.IO.File]::ReadAllText($xmlPath, [System.Text.Encoding]::UTF8) -replace '\s*encoding="[^"]*"',''
Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
$r = Register-ScheduledTask -TaskName $name -Xml $xml -Force
$t = Get-ScheduledTask -TaskName $name
$i = $t | Get-ScheduledTaskInfo
Write-Host "Registered: $($t.TaskName)  State=$($t.State)"
Write-Host ("  Trigger    = " + (($t.Triggers | ForEach-Object { $_.StartBoundary }) -join ', '))
Write-Host ("  NextRun    = " + $i.NextRunTime)
Write-Host ("  Action     = " + $t.Actions[0].Execute)
Write-Host ""
Write-Host "NOTE: This is a ONE-TIME task. After it runs Monday, remove it with:"
Write-Host '  Unregister-ScheduledTask -TaskName invest_close_remaining -Confirm:$false'
