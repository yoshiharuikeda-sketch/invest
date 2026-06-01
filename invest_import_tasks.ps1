# Task re-registration script (ASCII only - task names loaded from file)
$log = "C:\Users\tropi\invest_import_result.txt"
"[$(Get-Date)] Start" | Out-File $log -Encoding utf8

# Load task names from UTF-8 file (avoids encoding issue in this script)
$names = [System.IO.File]::ReadAllLines(
    'C:\Users\tropi\task_names.txt',
    [System.Text.Encoding]::UTF8
) | Where-Object { $_ -match '\S' }

$xmlFiles = @(
    'C:\Users\tropi\task_invest_login.xml',
    'C:\Users\tropi\task_invest_signal.xml',
    'C:\Users\tropi\task_invest_open.xml',
    'C:\Users\tropi\task_invest_close.xml',
    'C:\Users\tropi\task_invest_fills.xml',
    'C:\Users\tropi\task_invest_shutdown.xml',
    'C:\Users\tropi\task_invest_report.xml'
)

for ($i = 0; $i -lt $names.Count; $i++) {
    $name    = $names[$i]
    $xmlPath = $xmlFiles[$i]

    # Delete existing task
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue

    # Import from XML (all files are UTF-8, strip encoding declaration for compatibility)
    $xml    = [System.IO.File]::ReadAllText($xmlPath, [System.Text.Encoding]::UTF8)
    $xml    = $xml -replace '\s*encoding="[^"]*"', ''
    $result = Register-ScheduledTask -TaskName $name -Xml $xml -Force 2>&1
    if ($?) {
        $msg = "[OK] $name -> $($xmlFiles[$i])"
    } else {
        $msg = "[NG] $name : $result"
    }
    $msg | Add-Content $log -Encoding utf8
    Write-Host $msg
}

# Verify actions
"`n--- Action check ---" | Add-Content $log -Encoding utf8
foreach ($name in $names) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        $line = "$name -> $($t.Actions[0].Execute)"
        $line | Add-Content $log -Encoding utf8
        Write-Host $line
    }
}

Write-Host "`nDone. Log: $log" -ForegroundColor Cyan
