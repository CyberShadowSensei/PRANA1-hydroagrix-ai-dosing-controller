# This script safely deploys all updated files to the Raspberry Pi over SCP.
# Run this from Windows PowerShell.

$pi_ip = "192.168.29.9"
$user = "raspberrypi"

Write-Host "Deploying Updated Backend Files..." -ForegroundColor Cyan
scp .\backend\routes.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/
scp .\backend\checkSensorMail.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/
scp .\backend\dosing.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/
scp .\backend\hal.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/
scp .\backend\system_config.json ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/

Write-Host "Deploying Updated Frontend Files..." -ForegroundColor Cyan
scp .\frontend\src\components\GlobalHUD.jsx ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/frontend/src/components/

Write-Host "Deployment transferred successfully." -ForegroundColor Green
Write-Host "Please SSH into the Pi, rebuild the frontend, and restart the backend." -ForegroundColor Yellow
