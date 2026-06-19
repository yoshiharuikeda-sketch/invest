# =====================================================================
# invest_setup_tasks.ps1 -- single source of truth for the trading tasks
# English only (PowerShell 5.1 reads PS1 as CP932; non-ASCII breaks parsing).
#
# 9-task layout, all launched by .bat directly (no hidden VBS):
#   AM : login_am 08:45 -> signal 08:50 -> open 09:00 -> shutdown_am 09:10
#   PM : login_pm 15:20 -> close 15:25 -> fills 15:32 -> report 15:35 -> shutdown_pm 15:40
#
# Run from an ELEVATED PowerShell. The G: drive is not mapped under admin,
# but we only register the bat PATH STRING (no G: access needed), so run the
# C: copy:
#   powershell -ExecutionPolicy Bypass -File C:\Users\tropi\invest_setup_tasks.ps1
#
# Behavior: delete every existing invest task, then register the 9 (idempotent via -Force).
# =====================================================================
$ErrorActionPreference = 'Stop'
$LOG = 'C:\Users\tropi\invest_setup_tasks.log'
function Log($m){ ((Get-Date -Format 'HH:mm:ss') + '  ' + $m) | Tee-Object -FilePath $LOG -Append }
Remove-Item $LOG -ErrorAction SilentlyContinue

$DIR = 'G:\My Drive\Claude Code\Invest'
$SID = 'S-1-5-21-2752900438-3444082329-101990108-1001'
$DOW = @('Monday','Tuesday','Wednesday','Thursday','Friday')

# --- 1) delete existing invest tasks (matched by name or by action path) ---
$jp = [char]0x6295  # CJK '投' (avoid literal non-ASCII in PS1 which CP932 corrupts)
$existing = Get-ScheduledTask | Where-Object {
    $act = ($_.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' '
    ($_.TaskName -match 'invest') -or ($act -match 'Claude Code\\Invest') -or ($_.TaskName -match $jp)
}
foreach ($t in $existing) {
    try { Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false; Log "deleted: $($t.TaskName)" }
    catch { Log "DELETE FAIL: $($t.TaskName) : $($_.Exception.Message)" }
}

# --- 2) principal: run as tropi in the interactive session ---
try { $principal = New-ScheduledTaskPrincipal -UserId $SID -LogonType Interactive }
catch { $principal = New-ScheduledTaskPrincipal -UserId 'tropi' -LogonType Interactive }

# --- 3) the 9 tasks ---
#   Wake  = WakeToRun (wake the PC from sleep for this task)
#   Swa   = StartWhenAvailable (run late on next boot if the scheduled time was missed)
#   Limit = ExecutionTimeLimit in minutes. login_pm stays resident until 15:42 (keep-awake), so longer.
$tasks = @(
  @{ Name='invest_login_am';     Time='08:45'; Bat='invest_login.bat';    Wake=$true;  Swa=$false; Limit=60 },
  @{ Name='invest_signal';       Time='08:50'; Bat='invest_signal.bat';   Wake=$false; Swa=$false; Limit=10 },
  @{ Name='invest_open';         Time='09:00'; Bat='invest_open.bat';     Wake=$false; Swa=$false; Limit=10 },
  @{ Name='invest_shutdown_am';  Time='09:10'; Bat='invest_shutdown.bat'; Wake=$true;  Swa=$true;  Limit=10 },
  @{ Name='invest_login_pm';     Time='15:20'; Bat='invest_login.bat';    Wake=$true;  Swa=$false; Limit=60 },
  @{ Name='invest_close';        Time='15:25'; Bat='invest_close.bat';    Wake=$true;  Swa=$false; Limit=10 },
  @{ Name='invest_fills';        Time='15:32'; Bat='invest_fills.bat';    Wake=$true;  Swa=$false; Limit=10 },
  @{ Name='invest_report';       Time='15:35'; Bat='invest_report.bat';   Wake=$true;  Swa=$false; Limit=10 },
  @{ Name='invest_shutdown_pm';  Time='15:40'; Bat='invest_shutdown.bat'; Wake=$true;  Swa=$true;  Limit=10 }
)

foreach ($t in $tasks) {
    $action  = New-ScheduledTaskAction -Execute (Join-Path $DIR $t.Bat)
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DOW -At $t.Time
    # Desktop on AC: clear all battery restrictions (so a UPS misdetect never blocks a task).
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes $t.Limit)
    $settings.WakeToRun          = [bool]$t.Wake
    $settings.StartWhenAvailable = [bool]$t.Swa
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Log ("registered: {0,-20} {1} -> {2}  Wake={3} Swa={4}" -f $t.Name,$t.Time,$t.Bat,$t.Wake,$t.Swa)
}
Log "DONE"
