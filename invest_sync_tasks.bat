@echo off
chcp 65001 > nul
setlocal
SET SRC=G:\My Drive\Claude Code\Invest\invest_import_tasks.ps1
SET DST=C:\Users\tropi\invest_import_tasks.ps1
IF NOT EXIST "%SRC%" (echo [NG] Source not found: %SRC% & exit /b 1)
copy /Y "%SRC%" "%DST%" > nul
IF %ERRORLEVEL% NEQ 0 (echo [NG] Copy failed & exit /b 1)
echo [OK] Synced invest_import_tasks.ps1 to %DST%
echo Next: run invest_import_tasks.bat as Administrator
