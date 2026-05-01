Delete all invest_test_login_*.ps1 files and push the cleanup to GitHub.

## Steps

1. Find all test PS1 files:
```bash
ls /home/user/invest/invest_test_login_*.ps1 2>/dev/null
```

2. If no files found, tell the user there are no test scripts to clean up.

3. Delete all found files:
```bash
rm /home/user/invest/invest_test_login_*.ps1
```

4. Stage deletions, commit and push:
```bash
git add -u
git commit -m "chore: テスト用タスク登録スクリプトを削除"
echo "https://yoshiharuikeda-sketch:${GITHUB_TOKEN}@github.com" > /tmp/git_creds
git remote set-url --push origin https://github.com/yoshiharuikeda-sketch/invest.git
git -c http.proxy="" -c credential.helper="store --file=/tmp/git_creds" push origin claude/debug-auto-login-IFyCm
git remote set-url --push origin http://local_proxy@127.0.0.1:45171/git/yoshiharuikeda-sketch/invest
```

5. Output the following to the user (in Japanese), listing the task names that were deleted:
```
クリーンアップ完了。Windows側でタスクを削除するには管理者PowerShellで：

git pull origin claude/debug-auto-login-IFyCm

# 登録済みタスクを確認
Get-ScheduledTask | Where-Object { $_.TaskName -like "invest_test_login_*" }

# まとめて削除
Get-ScheduledTask | Where-Object { $_.TaskName -like "invest_test_login_*" } | Unregister-ScheduledTask -Confirm:$false
```
