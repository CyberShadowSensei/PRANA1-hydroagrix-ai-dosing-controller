# deploy_quick.ps1 - Quick Hot-Patch Deployment Script for reTerminal
# Fast-deploys backend modifications (routes.py, dosing.py, checkSensorMail.py, models.py) and restarts systemd service in seconds.

param (
    [string]$PiIP = "100.64.119.63",
    [string]$User = "raspberrypi",
    [string]$RemotePath = "/home/raspberrypi/hydroagrix_reterminal_package",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Write-Host "=== HydroAgrix Quick Backend Hot-Patch ===" -ForegroundColor Cyan
Write-Host "Target Device: ${User}@${PiIP}:${RemotePath}" -ForegroundColor Gray
Write-Host ""

# 1. Pre-deployment Local Unit Tests
if (-not $SkipTests) {
    Write-Host "[1/4] Running automated backend test suite (pytest)..." -ForegroundColor Yellow
    python -m pytest backend/ -v --tb=short -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ABORT] Local tests failed. Aborting deployment." -ForegroundColor Red
        exit 1
    }
    Write-Host "  All backend tests passed cleanly." -ForegroundColor Green
} else {
    Write-Host "[1/4] Skipping local test suite (-SkipTests flag passed)." -ForegroundColor Yellow
}

# 2. Pre-flight Ping Check
Write-Host "[2/4] Checking connectivity to ${PiIP}..." -ForegroundColor Yellow
$pingResult = Test-Connection -ComputerName $PiIP -Count 2 -Quiet
if (-not $pingResult) {
    Write-Host "[ABORT] Cannot reach ${PiIP}. Check power and network connection." -ForegroundColor Red
    exit 1
}
Write-Host "  reTerminal ${PiIP} is online." -ForegroundColor Green

# 3. Transfer Updated Backend & Frontend Dist Files
Write-Host "[3/4] SCP transferring modified backend files and frontend assets..." -ForegroundColor Yellow
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "backend/routes.py" "${User}@${PiIP}:${RemotePath}/backend/routes.py"
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "backend/dosing.py" "${User}@${PiIP}:${RemotePath}/backend/dosing.py"
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "backend/main.py" "${User}@${PiIP}:${RemotePath}/backend/main.py"
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "backend/models.py" "${User}@${PiIP}:${RemotePath}/backend/models.py"
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "backend/checkSensorMail.py" "${User}@${PiIP}:${RemotePath}/backend/checkSensorMail.py"

if (Test-Path "frontend/dist") {
    scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "frontend/dist" "${User}@${PiIP}:${RemotePath}/frontend/"
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ABORT] SCP transfer failed." -ForegroundColor Red
    exit 1
}
Write-Host "  Backend files and frontend assets updated on reTerminal." -ForegroundColor Green

# 4. Migrate Remote DB & Restart Services
Write-Host "[4/4] Upgrading remote database schema and restarting hydro-backend.service..." -ForegroundColor Yellow

$remote_cmd = "cd ${RemotePath}/backend && " +
              "python3 -c 'from config import app, db; from models import *; app.app_context().push(); db.create_all()' && " +
              "sudo systemctl restart hydro-backend.service"

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${User}@${PiIP} $remote_cmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Remote deploy/restart exited with code $LASTEXITCODE." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "   HOT-PATCH DEPLOYED SUCCESSFULLY IN SECONDS!          " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
