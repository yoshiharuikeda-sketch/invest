@echo off
setlocal
chcp 65001 > nul

echo ============================================================
echo   自動スリープ解除 / 自動スリープ セットアップ
echo   ※ 管理者として実行してください
echo ============================================================
echo.

REM 管理者権限チェック
net session > nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [NG] 管理者権限がありません。
    echo.
    echo このファイルを右クリック → 「管理者として実行」してください。
    pause
    exit /b 1
)

echo [OK] 管理者権限を確認しました
echo.

REM ---- 08:40 スリープ解除タスク ----
powershell -Command ^
  "$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c echo wake';" ^
  "$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '08:40';" ^
  "$s = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 1);" ^
  "Unregister-ScheduledTask -TaskName '投資戦略_スリープ解除' -Confirm:$false -ErrorAction SilentlyContinue;" ^
  "Register-ScheduledTask -TaskName '投資戦略_スリープ解除' -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force | Out-Null;" ^
  "Write-Host '[OK] 08:40 スリープ解除タスクを登録しました'"

REM ---- 15:35 自動スリープタスク ----
powershell -Command ^
  "$a = New-ScheduledTaskAction -Execute 'rundll32.exe' -Argument 'powrprof.dll,SetSuspendState 0,1,0';" ^
  "$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '15:35';" ^
  "$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1);" ^
  "Unregister-ScheduledTask -TaskName '投資戦略_自動スリープ' -Confirm:$false -ErrorAction SilentlyContinue;" ^
  "Register-ScheduledTask -TaskName '投資戦略_自動スリープ' -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force | Out-Null;" ^
  "Write-Host '[OK] 15:35 自動スリープタスクを登録しました'"

echo.

REM ---- スリープ解除タイマーを Windows で有効化 ----
echo スリープ解除タイマーを有効化しています...
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 > nul 2>&1
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 > nul 2>&1
powercfg /setactive SCHEME_CURRENT > nul 2>&1
echo [OK] スリープ解除タイマーを有効化しました
echo.

REM ---- 高速スタートアップを無効化（スリープ解除の安定性向上）----
echo 高速スタートアップを無効化しています...
powercfg /hibernate off > nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f > nul 2>&1
echo [OK] 高速スタートアップを無効化しました
echo.

REM ---- Windows Update 自動再起動の抑止 ----
echo Windows Update の自動再起動を抑止しています...

REM ログオン中ユーザーがいる場合は自動再起動しない
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f > nul 2>&1

REM アクティブ時間を 08:00-20:00 に設定（この時間帯は再起動しない）
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart /t REG_DWORD /d 8 /f > nul 2>&1
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd   /t REG_DWORD /d 20 /f > nul 2>&1

REM 再起動を通知のみにする（自動実行しない）
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v AUOptions /t REG_DWORD /d 2 /f > nul 2>&1

echo [OK] Windows Update の自動再起動を抑止しました
echo      アクティブ時間: 08:00-20:00（この時間帯は再起動しません）
echo.

echo ============================================================
echo   [OK] セットアップ完了
echo ============================================================
echo.
echo   【スケジュール】
echo     08:40  スリープ解除（PCが自動で起動）
echo     08:41  kabuステーション自動ログイン
echo     08:50  シグナル計算
echo     09:00  寄付き発注
echo     15:25  引成決済
echo     15:30  kabuステーション終了
echo     15:35  自動スリープ
echo.
echo   【Windows Update 抑止】
     08:00-20:00 はアクティブ時間として自動再起動しません
     ログオン中は自動再起動しません（通知のみ）
     ※ 週末など取引のない時間に手動で再起動してください
echo.
echo   【重要: 追加で必要な設定】
echo.
echo   1. kabuステーション(R) を自動起動に設定する
echo      kabuステーション(R) を起動 → スタートアップに登録
echo      または以下を実行:
echo      タスクスケジューラ → ログオン時に kabuStation.exe を起動
echo.
echo   2. Windows の自動ログインを設定する（任意）
echo      netplwiz を実行 → パスワード不要でログイン
echo.
echo   3. PCをシャットダウンではなく「スリープ」で待機させる
echo      スタートメニュー → 電源 → スリープ
echo.
pause
