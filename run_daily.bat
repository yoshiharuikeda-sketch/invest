@echo off
chcp 65001 > nul
setlocal
SET PYTHONIOENCODING=utf-8
SET PATH=C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64;%PATH%
FOR /F "usebackq tokens=1,* delims==" %%i IN ("G:\My Drive\Claude Code\Invest\.env_windows") DO SET "%%i=%%j"
IF "%1"=="login"    python "G:\My Drive\Claude Code\Invest\kabu_autologin.py"
IF "%1"=="shutdown" python "G:\My Drive\Claude Code\Invest\kabu_autologin.py" --mode shutdown
IF "%1"=="signal" python "G:\My Drive\Claude Code\Invest\daily_signal.py" >> "G:\My Drive\Claude Code\Invest\log_signal.txt" 2>&1 
IF "%1"=="open"   python "G:\My Drive\Claude Code\Invest\kabu_order.py" --value %PORTFOLIO_VALUE% --execute >> "G:\My Drive\Claude Code\Invest\log_order.txt" 2>&1
IF "%1"=="close"  python "G:\My Drive\Claude Code\Invest\kabu_order.py" --close --value %PORTFOLIO_VALUE% --execute >> "G:\My Drive\Claude Code\Invest\log_order.txt" 2>&1
IF "%1"=="dry"     python "G:\My Drive\Claude Code\Invest\kabu_order.py" --value %PORTFOLIO_VALUE%
IF "%1"=="monitor" python "G:\My Drive\Claude Code\Invest\monitor_agent.py"
