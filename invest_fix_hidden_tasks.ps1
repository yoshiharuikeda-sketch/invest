# Re-register close/fills/report tasks to launch hidden (no cmd console) via wscript+VBS.
# Task action change needs admin. Run in an ELEVATED PowerShell:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\tropi\invest_fix_hidden_tasks.ps1"
$names = [System.IO.File]::ReadAllLines('C:\Users\tropi\task_names.txt',
                                        [System.Text.Encoding]::UTF8) | Where-Object { $_ -match '\S' }
# task_names.txt order: 0=login 1=signal 2=open 3=close 4=fills 5=shutdown 6=report
$idx  = @(3, 4, 6)
$xmls = @('task_invest_close.xml', 'task_invest_fills.xml', 'task_invest_report.xml')
for ($i = 0; $i -lt $idx.Count; $i++) {
    $name = $names[$idx[$i]]
    $path = "C:\Users\tropi\$($xmls[$i])"
    $xml  = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8) -replace '\s*encoding="[^"]*"', ''
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    $r = Register-ScheduledTask -TaskName $name -Xml $xml -Force
    $t = Get-ScheduledTask -TaskName $name
    Write-Host ("OK: {0}  Action={1} {2}" -f $t.TaskName, $t.Actions[0].Execute, $t.Actions[0].Arguments)
}
Write-Host "Done. close/fills/report は非表示(VBS)起動になりました。"
