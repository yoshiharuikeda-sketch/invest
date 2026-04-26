# Invest task registration - all tasks defined inline (no G: drive needed, safe for admin mode)
# Run as Administrator

$log = "C:\Users\tropi\invest_import_result.txt"
"[$(Get-Date)] Start task registration" | Out-File $log -Encoding utf8

$vbsLogin    = "`"G:\My Drive\Claude Code\Invest\invest_login_hidden.vbs`""
$vbsShutdown = "`"G:\My Drive\Claude Code\Invest\invest_shutdown_hidden.vbs`""
$batSignal   = "G:\My Drive\Claude Code\Invest\invest_signal.bat"
$batOpen     = "G:\My Drive\Claude Code\Invest\invest_open.bat"
$batClose    = "G:\My Drive\Claude Code\Invest\invest_close.bat"
$batMonitor  = "G:\My Drive\Claude Code\Invest\invest_monitor.bat"

$settings  = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$tasks = @(
    @{ Name="invest_login";            At="08:45"; Exe="wscript.exe"; Arg=$vbsLogin    },
    @{ Name="invest_signal";           At="08:50"; Exe=$batSignal;    Arg=""            },
    @{ Name="invest_open";             At="09:00"; Exe=$batOpen;      Arg=""            },
    @{ Name="invest_morning_shutdown"; At="09:10"; Exe="wscript.exe"; Arg=$vbsShutdown },
    @{ Name="invest_afternoon_login";  At="15:10"; Exe="wscript.exe"; Arg=$vbsLogin    },
    @{ Name="invest_close";            At="15:25"; Exe=$batClose;     Arg=""            },
    @{ Name="invest_shutdown";         At="15:30"; Exe="wscript.exe"; Arg=$vbsShutdown }
)

foreach ($t in $tasks) {
    $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $t.At

    if ($t.Arg -ne "") {
        $action = New-ScheduledTaskAction -Execute $t.Exe -Argument $t.Arg
    } else {
        $action = New-ScheduledTaskAction -Execute $t.Exe
    }

    Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue
    $result = Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
              -Settings $settings -Principal $principal -Force 2>&1

    if ($?) {
        $msg = "[OK] $($t.Name) at $($t.At)"
    } else {
        $msg = "[NG] $($t.Name) : $result"
    }
    $msg | Add-Content $log -Encoding utf8
    Write-Host $msg
}

"`n--- Registered tasks ---" | Add-Content $log -Encoding utf8
foreach ($t in $tasks) {
    $task = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($task) {
        $line = "$($t.Name) -> $($task.Actions[0].Execute) $($task.Actions[0].Arguments)"
        $line | Add-Content $log -Encoding utf8
        Write-Host $line
    }
}

Write-Host "`nDone. Log: $log" -ForegroundColor Cyan
