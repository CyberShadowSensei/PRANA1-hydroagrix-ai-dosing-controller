import time
import sys
try:
    import RPi.GPIO as GPIO
except ImportError:
    print("CRITICAL: RPi.GPIO is not installed. Run: pip3 install RPi.GPIO")
    sys.exit(1)

# Pins configured in your hal.py
PUMP_PINS = {
    1: {'in1': 18, 'in2': 19, 'en': 16, 'name': 'Nutrient A'},
    2: {'in1': 22, 'in2': 23, 'en': 24, 'name': 'Nutrient B'},
    3: {'in1': 26, 'in2': 27, 'en': None, 'name': 'pH UP'},
    4: {'in1': 5,  'in2': 6,  'en': None, 'name': 'pH DOWN'}
}

def test_pumps():
    print("=======================================")
    print("   Low-Level Hardware Pump Test Tool   ")
    print("=======================================")
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Initialize all pins to LOW
    print("Initializing all pump pins to LOW (OFF)...")
    for pid, pins in PUMP_PINS.items():
        GPIO.setup(pins['in1'], GPIO.OUT)
        GPIO.setup(pins['in2'], GPIO.OUT)
        GPIO.output(pins['in1'], GPIO.LOW)
        GPIO.output(pins['in2'], GPIO.LOW)
        if pins.get('en') is not None:
            GPIO.setup(pins['en'], GPIO.OUT)
            GPIO.output(pins['en'], GPIO.LOW)
    
    time.sleep(1)

    print("\n--- Starting Individual Pump Test ---")
    for pid, pins in PUMP_PINS.items():
        in1 = pins['in1']
        in2 = pins['in2']
        name = pins['name']
        
        print(f"\nTesting Pump {pid} ({name})")
        print(f" -> Setting BCM {in1} HIGH, BCM {in2} LOW. EN={pins.get('en')}")
        
        # Turn ON
        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.LOW)
        if pins.get('en') is not None:
            GPIO.output(pins['en'], GPIO.HIGH)
        
        # Keep on for 3 seconds
        for i in range(3, 0, -1):
            print(f"    Running for {i} seconds...", end="\r")
            time.sleep(1)
            
        print("    Stopping pump...          ")
        # Turn OFF
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.LOW)
        if pins.get('en') is not None:
            GPIO.output(pins['en'], GPIO.LOW)
        
        time.sleep(1)

    print("\n=======================================")
    print("Test Complete. Cleaning up GPIO...")
    GPIO.cleanup()
    print("Done. If motors did NOT spin during this test, your hardware wiring or power supply is the issue.")

if __name__ == "__main__":
    test_pumps()
