@echo off
REM === DRY検証期間中（2026-06-08〜）: 実発注せず DRY RUN。検証終了後は "open" に戻す ===
call "%~dp0run_daily.bat" dry_open

call "%~dp0run_daily.bat" sync
