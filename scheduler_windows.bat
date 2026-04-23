@echo off
REM ============================================================
REM Windowsタスクスケジューラへの登録スクリプト
REM 管理者権限で実行してください
REM
REM 自動実行スケジュール:
REM   08:55  シグナル確認（DRY RUN）
REM   09:00  寄付き発注
REM   15:25  引成決済
REM ============================================================

SET PROJECT_DIR=%~dp0
SET PYTHON=python

REM --- 08:55 シグナル確認 ---
SCHTASKS /CREATE /TN "投資戦略_シグナル確認" ^
  /TR "cmd /c \"%PROJECT_DIR%run_windows.bat\" dry >> \"%PROJECT_DIR%log_signal.txt\" 2>&1" ^
  /SC WEEKLY /D MON,TUE,WED,THU,FRI ^
  /ST 08:55 /F
echo シグナル確認タスクを登録しました (08:55)

REM --- 09:00 寄付き発注 ---
SCHTASKS /CREATE /TN "投資戦略_寄付き発注" ^
  /TR "cmd /c \"%PROJECT_DIR%run_windows.bat\" open >> \"%PROJECT_DIR%log_order.txt\" 2>&1" ^
  /SC WEEKLY /D MON,TUE,WED,THU,FRI ^
  /ST 09:00 /F
echo 寄付き発注タスクを登録しました (09:00)

REM --- 15:25 引成決済 ---
SCHTASKS /CREATE /TN "投資戦略_引成決済" ^
  /TR "cmd /c \"%PROJECT_DIR%run_windows.bat\" close >> \"%PROJECT_DIR%log_order.txt\" 2>&1" ^
  /SC WEEKLY /D MON,TUE,WED,THU,FRI ^
  /ST 15:25 /F
echo 引成決済タスクを登録しました (15:25)

echo.
echo ========================================
echo タスクスケジューラへの登録が完了しました
echo ========================================
echo 登録されたタスク一覧:
SCHTASKS /QUERY /TN "投資戦略*"
pause
