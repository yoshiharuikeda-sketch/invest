@echo off
chcp 65001 > nul
setlocal
SET SRC_DIR=G:\My Drive\Claude Code\Invest
SET DST_DIR=C:\Users\tropi

REM ps1 script
copy /Y "%SRC_DIR%\invest_import_tasks.ps1" "%DST_DIR%\invest_import_tasks.ps1" > nul || (echo [NG] invest_import_tasks.ps1 & exit /b 1)
echo [OK] invest_import_tasks.ps1

REM task names
copy /Y "%SRC_DIR%\task_names.txt" "%DST_DIR%\task_names.txt" > nul || (echo [NG] task_names.txt & exit /b 1)
echo [OK] task_names.txt

REM XML files
FOR %%F IN (
    task_invest_login.xml
    task_invest_signal.xml
    task_invest_open.xml
    task_invest_close.xml
    task_invest_fills.xml
    task_invest_shutdown.xml
    task_invest_report.xml
) DO (
    copy /Y "%SRC_DIR%\%%F" "%DST_DIR%\%%F" > nul || (echo [NG] %%F & exit /b 1)
    echo [OK] %%F
)

echo.
echo Sync complete. Next: run invest_import_tasks.bat as Administrator
