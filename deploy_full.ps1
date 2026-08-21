# deploy_full.ps1 - Complete Full-Stack Deployment to reTerminal
# Upgrades backend, frontend (dist & sources), systemd configurations, and database schema

param (
    [string]$PiIP = "100.64.119.63",
    [string]$User = "raspberrypi",
    [string]$RemotePath = "/home/raspberrypi/hydroagrix_reterminal_package",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Write-Host "=== HydroAgrix Complete Full-Stack Deployment ===" -ForegroundColor Cyan
Write-Host "Target Device: ${User}@${PiIP}:${RemotePath}" -ForegroundColor Gray
Write-Host ""

# ---------------------------------------------------------
# Step 1: Run Backend & Unit Test Suite
# ---------------------------------------------------------
if (-not $SkipTests) {
    Write-Host "[1/5] Running automated backend test suite (pytest)..." -ForegroundColor Yellow
    python -m pytest backend/ -v --tb=short -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backend tests failed. Aborting deployment." -ForegroundColor Red
        exit 1
    }
    Write-Host "All backend tests passed cleanly." -ForegroundColor Green
} else {
    Write-Host "[1/5] Skipping test suite (-SkipTests flag passed)." -ForegroundColor Yellow
}

# ---------------------------------------------------------
# Step 2: Build Frontend Application (Vite)
# ---------------------------------------------------------
Write-Host "[2/5] Building frontend production bundle (Vite)..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend Vite build process exited with error code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
Write-Host "Frontend production bundle built successfully (dist/ ready)." -ForegroundColor Green

# ---------------------------------------------------------
# Step 3: Stage Full Codebase Package
# ---------------------------------------------------------
Write-Host "[3/5] Staging complete codebase for packaging..." -ForegroundColor Yellow
$temp_dir = "$env:TEMP\hydroagrix_full_deploy"
if (Test-Path $temp_dir) { Remove-Item -Recurse -Force $temp_dir }
New-Item -ItemType Directory -Path $temp_dir | Out-Null

New-Item -ItemType Directory -Path "$temp_dir\backend" | Out-Null
New-Item -ItemType Directory -Path "$temp_dir\frontend" | Out-Null
New-Item -ItemType Directory -Path "$temp_dir\systemd" | Out-Null

# Copy full application directories
Copy-Item -Path "backend\*" -Destination "$temp_dir\backend" -Recurse -Force
Copy-Item -Path "frontend\*" -Destination "$temp_dir\frontend" -Recurse -Force
Copy-Item -Path "systemd\*" -Destination "$temp_dir\systemd" -Recurse -Force
if (Test-Path "start_reterminal.sh") {
    Copy-Item -Path "start_reterminal.sh" -Destination "$temp_dir\start_reterminal.sh" -Force
}

# Exclude local build artifacts, virtual environments, node_modules, cache files, and production configs
@("__pycache__", "instance", ".pytest_cache", "captured_photos", "node_modules", ".git", ".vscode", "email_config.json", "system_config.json", "mydatabase.db") | ForEach-Object {
    Remove-Item -Recurse -Force "$temp_dir\backend\$_" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$temp_dir\frontend\$_" -ErrorAction SilentlyContinue
}

# Remove temporary test runner files from staging package
Get-ChildItem "$temp_dir\backend\test_*.py" -ErrorAction SilentlyContinue | Remove-Item -Force

# Create compressed tarball
Push-Location $temp_dir
try {
    tar -czf deploy_package.tar.gz *
} finally {
    Pop-Location
}
Write-Host "Codebase packaged successfully (deploy_package.tar.gz)." -ForegroundColor Green

# ---------------------------------------------------------
# Step 4: Transfer Deployment Package via SCP
# ---------------------------------------------------------
Write-Host "[4/5] Transferring deployment package to reTerminal (${PiIP})..." -ForegroundColor Yellow

# Pre-flight: verify the reTerminal is reachable before attempting SCP
Write-Host "  Checking connectivity to ${PiIP}..." -ForegroundColor Gray
$pingResult = Test-Connection -ComputerName $PiIP -Count 2 -Quiet
if (-not $pingResult) {
    Remove-Item -Recurse -Force $temp_dir -ErrorAction SilentlyContinue
    Write-Host "" 
    Write-Host "[ABORT] Cannot reach ${PiIP}. Is the reTerminal powered on and on the same network?" -ForegroundColor Red
    Write-Host "  Tip: Run 'ping ${PiIP}' or 'ssh ${User}@${PiIP}' to diagnose." -ForegroundColor Yellow
    exit 1
}
Write-Host "  ${PiIP} is reachable." -ForegroundColor Green

# Create remote directory
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${User}@${PiIP} "mkdir -p ${RemotePath}"
if ($LASTEXITCODE -ne 0) {
    Remove-Item -Recurse -Force $temp_dir -ErrorAction SilentlyContinue
    Write-Host "[ABORT] SSH mkdir failed (exit $LASTEXITCODE). Check SSH key authentication." -ForegroundColor Red
    exit 1
}

# Upload package
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$temp_dir\deploy_package.tar.gz" "${User}@${PiIP}:${RemotePath}/"
if ($LASTEXITCODE -ne 0) {
    Remove-Item -Recurse -Force $temp_dir -ErrorAction SilentlyContinue
    Write-Host "[ABORT] SCP transfer failed (exit $LASTEXITCODE). Package was NOT delivered." -ForegroundColor Red
    exit 1
}
Write-Host "  Package uploaded successfully." -ForegroundColor Green
Remove-Item -Recurse -Force $temp_dir

# ---------------------------------------------------------
# Step 5: Extract, Migrate DB & Restart Services
# ---------------------------------------------------------
Write-Host "[5/5] Deploying on reTerminal: extracting archive, updating dependencies, migrating DB, restarting services..." -ForegroundColor Yellow

$ssh_cmd = "cd ${RemotePath} && " + 
           "sudo systemctl stop hydro-backend.service hydro-frontend.service 2>/dev/null || true && " +
           "tar -xzf deploy_package.tar.gz && " +
           "if [ -f 'hydro-db-check.sh' ]; then cp hydro-db-check.sh ~/hydro-db-check.sh && chmod +x ~/hydro-db-check.sh; fi && " +
           "cd backend && " +
           "find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true && " +
           "python3 -c 'from config import app, db; from models import *; app.app_context().push(); db.create_all()' && " +
           "cd .. && " +
           "if [ -d 'systemd' ]; then sudo cp systemd/*.service /etc/systemd/system/ 2>/dev/null || true; sudo systemctl daemon-reload; fi && " +
           "sudo systemctl restart hydro-backend.service hydro-frontend.service 2>/dev/null || echo 'Services restarted or start manually.'"

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${User}@${PiIP} $ssh_cmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Remote deploy command finished with exit code $LASTEXITCODE." -ForegroundColor Yellow
    Write-Host "  SSH into ${PiIP} and check 'sudo journalctl -u hydro-backend -n 50' for details." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "   HYDROAGRIX FULL CODEBASE DEPLOYMENT COMPLETE!        " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "Frontend dist bundle and backend updated on reTerminal." -ForegroundColor Yellow
Write-Host "Access dashboard at: http://${PiIP}:5000 / http://${PiIP}:3000" -ForegroundColor Cyan

