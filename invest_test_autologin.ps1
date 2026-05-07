$investDir = "G:\My Drive\Claude Code\Invest"
$python = "C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$script = "$investDir\kabu_autologin.py"
$log    = "$investDir\log_autologin.txt"

Write-Host "=== kabuStation auto-login test ===" -ForegroundColor Cyan
Write-Host "Start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

& $python -X utf8 $script

Write-Host ""
Write-Host "=== log_autologin.txt (last 30 lines) ===" -ForegroundColor Cyan
Get-Content $log -Encoding UTF8 | Select-Object -Last 30
