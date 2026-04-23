# kabu_autologin タスク登録スクリプト
# 管理者PowerShellで実行:
# powershell -ExecutionPolicy Bypass -File "G:\My Drive\Claude Code\Invest\setup_autologin.ps1"

# 中継スクリプト作成
"@echo off`r`npython `"G:\My Drive\Claude Code\Invest\kabu_autologin.py`" >> `"G:\My Drive\Claude Code\Invest\log_autologin.txt`" 2>&1" |
    Out-File "C:\kabu_autologin.bat" -Encoding ascii

Write-Host "[OK] C:\kabu_autologin.bat created"

# 既存タスク削除
Unregister-ScheduledTask -TaskName "投資戦略_自動ログイン" -Confirm:$false -ErrorAction SilentlyContinue

# タスク登録（08:41 スリープ解除の1分後）
SCHTASKS /CREATE /TN "投資戦略_自動ログイン" /TR C:\kabu_autologin.bat /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 08:41 /RL HIGHEST /F

Write-Host "[OK] Task registered at 08:41"
Write-Host ""
Write-Host "Next: Run kabu_autologin.py manually once to complete Gmail OAuth setup"
Write-Host "  python `"G:\My Drive\Claude Code\Invest\kabu_autologin.py`""
