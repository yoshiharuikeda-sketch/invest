# Re-register invest_afternoon_login with the re-login moved 15:10 -> 15:20
# (closer to the 15:25 close, to minimize trade-session staleness -> Code:10016).
# Task change needs admin. Run in an ELEVATED PowerShell:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\tropi\invest_fix_afternoon_login.ps1"
$xmlPath = 'C:\Users\tropi\task_invest_afternoon_login.xml'
$name = 'invest_afternoon_login'
$xml = [System.IO.File]::ReadAllText($xmlPath, [System.Text.Encoding]::UTF8) -replace '\s*encoding="[^"]*"',''
Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
$r = Register-ScheduledTask -TaskName $name -Xml $xml -Force
$t = Get-ScheduledTask -TaskName $name
Write-Host "Registered: $($t.TaskName)  State=$($t.State)"
Write-Host ("  Trigger = " + (($t.Triggers | ForEach-Object { $_.StartBoundary }) -join ', '))
Write-Host ("  WakeToRun = " + $t.Settings.WakeToRun + "  DisallowStartIfOnBatteries = " + $t.Settings.DisallowStartIfOnBatteries)
