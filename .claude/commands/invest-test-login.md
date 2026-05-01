Generate a Windows scheduled task PS1 script for testing kabuStation auto-login at a specified time, then commit and push it to GitHub.

## Arguments
$ARGUMENTS contains the test time in HH:MM format (e.g. "09:15").

## Steps

1. Parse the time from $ARGUMENTS (format: HH:MM). If not provided, ask the user for the time.

2. Get today's date using Bash: `date +%Y-%m-%d`

3. Generate a task name: `invest_test_login_HHMM` (e.g. invest_test_login_0915)

4. Write the PS1 file to `/home/user/invest/invest_test_login_HHMM.ps1`:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument '"G:\My Drive\Claude Code\Invest\invest_login_hidden.vbs"'

$trigger = New-ScheduledTaskTrigger -Once -At "YYYY-MM-DD HH:MM:00"

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

Register-ScheduledTask `
    -TaskName "invest_test_login_HHMM" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force

Write-Host "Test task registered: invest_test_login_HHMM at YYYY-MM-DD HH:MM"
```

5. Commit and push to GitHub using this exact sequence:
```bash
git add invest_test_login_HHMM.ps1
git commit -m "add: HH:MMテスト用タスク登録スクリプト"
echo "https://yoshiharuikeda-sketch:${GITHUB_TOKEN}@github.com" > /tmp/git_creds
git remote set-url --push origin https://github.com/yoshiharuikeda-sketch/invest.git
git -c http.proxy="" -c credential.helper="store --file=/tmp/git_creds" push origin claude/debug-auto-login-IFyCm
git remote set-url --push origin http://local_proxy@127.0.0.1:45171/git/yoshiharuikeda-sketch/invest
```

6. Output the following instructions to the user (in Japanese):
```
プッシュ完了。管理者PowerShellで実行してください：

cd "G:\My Drive\Claude Code\Invest"
git pull origin claude/debug-auto-login-IFyCm
powershell.exe -ExecutionPolicy Bypass -File ".\invest_test_login_HHMM.ps1"

`Ready` を確認したらスリープに移行してください。
```
