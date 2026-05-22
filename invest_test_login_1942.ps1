$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument '"G:\My Drive\Claude Code\Invest\invest_login_hidden.vbs"'

$trigger = New-ScheduledTaskTrigger -Once -At "2026-05-22 19:42:00"

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

Register-ScheduledTask `
    -TaskName "invest_test_login_1942" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force

Write-Host "Test task registered: invest_test_login_1942 at 2026-05-22 19:42"
