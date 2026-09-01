<#
.SYNOPSIS
    TwinVolt Automated Git Sync & Push Script
.DESCRIPTION
    Automatically stages all new, modified, and deleted files/folders,
    creates a commit, and pushes changes to GitHub.
.PARAMETER Message
    Optional commit message. If omitted, an automatic timestamp message is used.
#>
param(
    [string]$Message = ""
)

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  TwinVolt — Auto GitHub Sync & Push" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Check if git repository exists
if (-not (Test-Path ".git")) {
    Write-Host "[ERROR] Not a git repository. Initializing git..." -ForegroundColor Yellow
    git init -b main
}

# 2. Check if remote origin is set
$remoteUrl = git remote get-url origin 2>$null
if (-not $remoteUrl) {
    Write-Host "[INFO] Remote 'origin' is not set." -ForegroundColor Yellow
    $repoName = "TwinVolt-Battery-Digital-Twin"
    $defaultRemote = "https://github.com/Prashant110405/$repoName.git"
    Write-Host "Setting remote origin to: $defaultRemote" -ForegroundColor Green
    git remote add origin $defaultRemote
}

# 3. Add all files & new directories
Write-Host "`n[1/4] Staging all files and folders (git add -A)..." -ForegroundColor Yellow
git add -A

# 4. Check if there are changes to commit
$status = git status --porcelain
if (-not $status) {
    Write-Host "[OK] Working tree clean. No new changes or files to commit." -ForegroundColor Green
} else {
    # 5. Commit changes
    if ([string]::IsNullOrWhiteSpace($Message)) {
        $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        $Message = "update: automated sync - $timestamp"
    }

    Write-Host "`n[2/4] Committing changes with message: '$Message'..." -ForegroundColor Yellow
    git commit -m "$Message"
}

# 6. Push to GitHub
Write-Host "`n[3/4] Ensuring branch is 'main'..." -ForegroundColor Yellow
git branch -M main

Write-Host "`n[4/4] Pushing to GitHub (origin main)..." -ForegroundColor Yellow
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=====================================================" -ForegroundColor Green
    Write-Host "  [SUCCESS] All files and folders synced to GitHub!" -ForegroundColor Green
    Write-Host "=====================================================" -ForegroundColor Green
} else {
    Write-Host "`n=====================================================" -ForegroundColor Red
    Write-Host "  [NOTICE] Push encountered an issue." -ForegroundColor Red
    Write-Host "  If you haven't created the repository on GitHub yet:" -ForegroundColor Yellow
    Write-Host "  1. Open https://github.com/new" -ForegroundColor Yellow
    Write-Host "  2. Repository name: TwinVolt-Battery-Digital-Twin (Public)" -ForegroundColor Yellow
    Write-Host "  3. Do NOT check 'Initialize with README' (keep empty)" -ForegroundColor Yellow
    Write-Host "  4. Click 'Create repository' and run this script again!" -ForegroundColor Yellow
    Write-Host "=====================================================" -ForegroundColor Red
}
