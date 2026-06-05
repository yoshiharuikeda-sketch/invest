# Re-register ONLY the auto-shutdown task with robust settings
# (StartWhenAvailable + WakeToRun + run on battery). ASCII only.
# Run this in your own session:  powershell -ExecutionPolicy Bypass -File invest_fix_shutdown_task.ps1
$xmlPath = 'C:\Users\tropi\task_invest_shutdown.xml'
$name = ([System.IO.File]::ReadAllLines('C:\Users\tropi\task_names.txt',[System.Text.Encoding]::UTF8) |
         Where-Object { $_ -match '\S' })[5]
Write-Host "Target task: $name"
$xml = [System.IO.File]::ReadAllText($xmlPath, [System.Text.Encoding]::UTF8) -replace '\s*encoding="[^"]*"',''
Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
$r = Register-ScheduledTask -TaskName $name -Xml $xml -Force
$t = Get-ScheduledTask -TaskName $name
$s = $t.Settings
Write-Host "Registered: $($t.TaskName)  State=$($t.State)"
Write-Host ("  StartWhenAvailable        = " + $s.StartWhenAvailable)
Write-Host ("  WakeToRun                 = " + $s.WakeToRun)
Write-Host ("  DisallowStartIfOnBatteries= " + $s.DisallowStartIfOnBatteries)
Write-Host ("  StopIfGoingOnBatteries    = " + $s.StopIfGoingOnBatteries)
