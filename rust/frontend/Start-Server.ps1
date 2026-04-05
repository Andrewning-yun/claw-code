# Start Claude Chat Server
# Double-click this file or run in PowerShell

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Claude Chat Server Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue

if (-not $PythonCmd) {
    Write-Host "Python not found in PATH!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternatively, install Python via winget:" -ForegroundColor Yellow
    Write-Host "  winget install Python.Python.3.12" -ForegroundColor Gray
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Python found: $($PythonCmd.Source)" -ForegroundColor Green
Write-Host ""

# Check and install dependencies
Write-Host "Checking dependencies..." -ForegroundColor Cyan

$RequiredPackages = @("fastapi", "uvicorn", "sse-starlette", "anthropic")
$MissingPackages = @()

foreach ($pkg in $RequiredPackages) {
    $Installed = python -c "import $($pkg.replace('-', '_'))" 2>$null
    if (-not $Installed) {
        $MissingPackages += $pkg
    }
}

if ($MissingPackages.Count -gt 0) {
    Write-Host "Installing missing packages: $($MissingPackages -join ', ')" -ForegroundColor Yellow
    pip install $MissingPackages
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install packages!" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Host "All dependencies installed!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting server at http://localhost:8000" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host ""

# Start the server
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload