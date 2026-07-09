# This script safely deploys the diagnostic script to the Raspberry Pi over SCP.
# Run this from Windows PowerShell.

$pi_ip = "192.168.29.9"
$user = "raspberrypi"

Write-Host "Deploying Diagnostic Script..." -ForegroundColor Cyan
scp .\backend\diagnostic_sensor.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/

Write-Host "Deployment transferred successfully." -ForegroundColor Green
Write-Host "Please SSH into the Pi and run the following commands:" -ForegroundColor Yellow
Write-Host "cd ~/hydroagrix_reterminal_package" -ForegroundColor White
Write-Host "python3 backend/diagnostic_sensor.py" -ForegroundColor White
