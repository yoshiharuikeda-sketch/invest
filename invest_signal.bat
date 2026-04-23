@echo off
call "%~dp0run_daily.bat" signal

call "%~dp0run_daily.bat" sync
