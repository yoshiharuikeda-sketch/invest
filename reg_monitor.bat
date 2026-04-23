@echo off
setlocal
chcp 65001 > nul

SET LOG="G:\My Drive\Claude Code\Invest\reg_monitor_result.txt"
echo [%DATE% %TIME%] 開始 > %LOG%

REM スペースを含むパスに対応するため明示的にダブルクォートを付ける
SET BAT="G:\My Drive\Claude Code\Invest\run_daily.bat"
echo BAT=%BAT% >> %LOG%

SCHTASKS /DELETE /TN "invest_monitor_morning" /F >> %LOG% 2>&1
SCHTASKS /DELETE /TN "invest_monitor_evening" /F >> %LOG% 2>&1

SCHTASKS /CREATE /TN "invest_monitor_morning" /TR "%BAT% monitor" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:05 /F >> %LOG% 2>&1
IF %ERRORLEVEL% EQU 0 (echo [OK] morning >> %LOG%) ELSE (echo [NG] morning ERRORLEVEL=%ERRORLEVEL% >> %LOG%)

SCHTASKS /CREATE /TN "invest_monitor_evening" /TR "%BAT% monitor" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:32 /F >> %LOG% 2>&1
IF %ERRORLEVEL% EQU 0 (echo [OK] evening >> %LOG%) ELSE (echo [NG] evening ERRORLEVEL=%ERRORLEVEL% >> %LOG%)

echo. >> %LOG%
echo --- 登録確認 --- >> %LOG%
SCHTASKS /QUERY /FO TABLE /NH >> %LOG% 2>&1

echo 完了。結果: %LOG%
pause
