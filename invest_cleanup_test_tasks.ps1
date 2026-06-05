# Remove all leftover test scheduled tasks (invest_test*) and stray test ps1 files.
# Task deletion needs admin -> run this in an ELEVATED PowerShell:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\tropi\invest_cleanup_test_tasks.ps1"
Write-Host "=== Removing invest_test* scheduled tasks ==="
$tasks = Get-ScheduledTask | Where-Object { $_.TaskName -like 'invest_test*' }
if (-not $tasks) { Write-Host "  (none found)" }
foreach ($t in $tasks) {
    try {
        Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false -ErrorAction Stop
        Write-Host ("  [removed] " + $t.TaskName)
    } catch {
        Write-Host ("  [FAILED ] " + $t.TaskName + " : " + $_.Exception.Message)
    }
}
Write-Host "`n=== Removing stray test login ps1 files in C:\Users\tropi ==="
$files = Get-ChildItem 'C:\Users\tropi\invest_test_login_*.ps1' -ErrorAction SilentlyContinue
if (-not $files) { Write-Host "  (none found)" }
foreach ($f in $files) {
    Remove-Item $f.FullName -Force
    Write-Host ("  [deleted] " + $f.Name)
}
Write-Host "`n=== Remaining invest_test* tasks (should be empty) ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like 'invest_test*' } | ForEach-Object { Write-Host ("  " + $_.TaskName) }
Write-Host "Done."
