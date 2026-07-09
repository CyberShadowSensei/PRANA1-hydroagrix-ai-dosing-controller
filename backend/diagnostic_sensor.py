import time
import sys
import hal
from sensors import apply_ph_calibration, apply_ec_calibration, get_water_temp

print("Starting Raw Hardware Sensor Diagnostics...")
print("Press Ctrl+C to stop.")
print("=" * 60)

try:
    while True:
        try:
            # 1. Fetch raw ADC values directly from the hardware layer
            raw_ph = hal.get_stable_reading(hal.PH_CHANNEL)
            raw_ec = hal.get_stable_reading(hal.EC_CHANNEL)
            
            # 2. Fetch water temperature for temperature compensation
            w_t = get_water_temp()
            
            # 3. Simulate sensors.py pH Validation & Calibration
            if raw_ph is None or raw_ph < 100 or raw_ph > 4080:
                ph_status = "REJECTED (Value Out of Bounds)"
                ph_calibrated = 0.0
            else:
                ph_calibrated = round(apply_ph_calibration(raw_ph, w_t), 2)
                ph_status = "ACCEPTED (Valid Reading)"

            # 4. Simulate sensors.py EC Validation & Calibration
            if raw_ec is None or raw_ec <= 0 or raw_ec > 4080:
                ec_status = "REJECTED (Value Out of Bounds)"
                ec_calibrated = 0.0
            else:
                ec_calibrated = round(apply_ec_calibration(raw_ec, w_t), 2)
                ec_status = "ACCEPTED (Valid Reading)"
                
            # 5. Output the trace
            print(f"[{time.strftime('%H:%M:%S')}] Water Temp: {w_t:.1f}°C")
            print(f"  pH -> RAW ADC: {raw_ph:<6} | Final pH: {ph_calibrated:<5} | {ph_status}")
            print(f"  EC -> RAW ADC: {raw_ec:<6} | Final EC: {ec_calibrated:<5} | {ec_status}")
            print("-" * 60)
            
        except Exception as e:
            print(f"Hardware/I2C Error: {e}")
            
        time.sleep(2)
        
except KeyboardInterrupt:
    print("\nDiagnostics stopped.")
    hal.cleanup()
    sys.exit(0)
