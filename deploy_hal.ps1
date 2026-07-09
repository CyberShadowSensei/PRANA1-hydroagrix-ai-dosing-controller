# Deploy hal.py to Raspberry Pi
$pi_ip = "192.168.29.9"
$user = "raspberrypi"

Write-Host "Deploying Fixed hal.py..." -ForegroundColor Cyan
scp .\backend\hal.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/
scp .\backend\diagnostic_sensor.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/backend/

Write-Host "Deployment complete. Restart your backend!" -ForegroundColor Green
