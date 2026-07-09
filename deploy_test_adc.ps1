# This script safely deploys the ADC test script to the Raspberry Pi over SCP.
# Run this from Windows PowerShell.

$pi_ip = "192.168.29.9"
$user = "raspberrypi"

Write-Host "Deploying ADC Test Script..." -ForegroundColor Cyan
scp .\test_adc_registers.py ${user}@${pi_ip}:/home/raspberrypi/hydroagrix_reterminal_package/

Write-Host "Deployment transferred successfully." -ForegroundColor Green
Write-Host "Please SSH into the Pi and run the following commands:" -ForegroundColor Yellow
Write-Host "cd ~/hydroagrix_reterminal_package" -ForegroundColor White
Write-Host "python3 test_adc_registers.py" -ForegroundColor White
