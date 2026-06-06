@echo off
REM === DRY検証期間中（2026-06-08〜）: 実決済せず DRY RUN。検証終了後は "close" に戻す ===
call "%~dp0run_daily.bat" dry_close

call "%~dp0run_daily.bat" sync
