<#
.SYNOPSIS
    TwinVolt Real-time Automated Git Sync Watcher
.DESCRIPTION
    Monitors workspace directory for file and folder changes.
    When changes occur, automatically stages all changes, commits, and pushes to GitHub.
#>
param(
    [int]$DebounceSeconds = 10
)

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  TwinVolt — Continuous Auto-Sync Watcher" -ForegroundColor Cyan
Write-Host "  (Monitors project files and auto-pushes on changes)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "Watching directory: $PSScriptRoot\.." -ForegroundColor Green
Write-Host "Debounce timer: $DebounceSeconds seconds" -ForegroundColor Green
Write-Host "Press Ctrl+C at any time to stop.`n" -ForegroundColor Yellow

$scriptPath = Join-Path $PSScriptRoot "git_sync.ps1"

while ($true) {
    Start-Sleep -Seconds $DebounceSeconds
    
    # Check if there are changes
    $status = git status --porcelain 2>$null
    if ($status) {
        $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        Write-Host "`n[$timestamp] Detected new/modified files or folders!" -ForegroundColor Magenta
        powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Message "auto-sync: $timestamp"
    }
}
