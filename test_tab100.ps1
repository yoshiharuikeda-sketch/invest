$investDir = "G:\My Drive\Claude Code\Invest"
$python = "C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64\python.exe"

Set-Location $investDir
git pull origin claude/check-current-status-gTXDf

& $python -X utf8 "$investDir\test_tab100.py"
