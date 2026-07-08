@echo off
chcp 65001 > nul
setlocal
SET PYTHONIOENCODING=utf-8
SET PATH=C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64;%PATH%
FOR /F "usebackq tokens=1,* delims==" %%i IN ("G:\My Drive\Claude Code\Invest\.env_windows") DO SET "%%i=%%j"
IF "%1"=="login"    python "G:\My Drive\Claude Code\Invest\kabu_autologin.py" 2>> "C:\Users\tropi\log_login_stderr.txt"
IF "%1"=="shutdown" python "G:\My Drive\Claude Code\Invest\kabu_autologin.py" --mode shutdown
IF "%1"=="sleep"    python "G:\My Drive\Claude Code\Invest\invest_sleep.py"
IF "%1"=="signal" python "G:\My Drive\Claude Code\Invest\daily_signal.py" >> "G:\My Drive\Claude Code\Invest\log_signal.txt" 2>&1 
IF "%1"=="open"   python "G:\My Drive\Claude Code\Invest\kabu_order.py" --execute --value %PORTFOLIO_VALUE% >> "G:\My Drive\Claude Code\Invest\log_order.txt" 2>&1
IF "%1"=="close"  python "G:\My Drive\Claude Code\Invest\kabu_order.py" --execute --close --value %PORTFOLIO_VALUE% >> "G:\My Drive\Claude Code\Invest\log_order.txt" 2>&1
IF "%1"=="close_remaining" python "G:\My Drive\Claude Code\Invest\close_all_positions.py" --execute >> "G:\My Drive\Claude Code\Invest\log_order.txt" 2>&1
IF "%1"=="dry"     python "G:\My Drive\Claude Code\Invest\kabu_order.py" --value %PORTFOLIO_VALUE%
REM DRY検証期間は仮想資金100万円で数量算出（本番のPORTFOLIO_VALUE=30万とは独立）
IF "%1"=="dry_open"  python "G:\My Drive\Claude Code\Invest\kabu_order.py" --value 1000000 >> "G:\My Drive\Claude Code\Invest\log_order.txt" 2>&1
IF "%1"=="dry_close" python "G:\My Drive\Claude Code\Invest\kabu_order.py" --close --value 1000000 >> "G:\My Drive\Claude Code\Invest\log_order.txt" 2>&1
IF "%1"=="paper"     python "G:\My Drive\Claude Code\Invest\paper_trade.py" >> "G:\My Drive\Claude Code\Invest\log_paper.txt" 2>&1
IF "%1"=="fills"   python "G:\My Drive\Claude Code\Invest\fetch_fills.py"
IF "%1"=="monitor" python "G:\My Drive\Claude Code\Invest\monitor_agent.py"
IF "%1"=="report"  python "G:\My Drive\Claude Code\Invest\report_agent.py"
