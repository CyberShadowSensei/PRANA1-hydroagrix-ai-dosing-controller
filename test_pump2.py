import RPi.GPIO as GPIO
import time

# --- PUMP 2 PIN CONFIGURATION (BCM) ---
PUMP2_EN  = 24  # Speed/Enable
PUMP2_IN3 = 22  # Direction 1
PUMP2_IN4 = 23  # Direction 2

def test_pump2():
    print("Initializing GPIO for Pump 2...")
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Setup pins
    GPIO.setup(PUMP2_EN, GPIO.OUT)
    GPIO.setup(PUMP2_IN3, GPIO.OUT)
    GPIO.setup(PUMP2_IN4, GPIO.OUT)
    
    try:
        print("STARTING PUMP 2 TEST ---")
        print("Running for 5 seconds...")
        
        # Enable the driver
        GPIO.output(PUMP2_EN, GPIO.HIGH)
        
        # Set direction (IN3 High, IN4 Low)
        GPIO.output(PUMP2_IN3, GPIO.HIGH)
        GPIO.output(PUMP2_IN4, GPIO.LOW)
        
        time.sleep(5)
        
        print("Stopping Pump 2...")
        GPIO.output(PUMP2_EN, GPIO.LOW)
        GPIO.output(PUMP2_IN3, GPIO.LOW)
        GPIO.output(PUMP2_IN4, GPIO.LOW)
        
        print("--- TEST COMPLETE ---")
        
    except KeyboardInterrupt:
        print("Test stopped by user.")
    finally:
        print("Cleaning up GPIO...")
        GPIO.cleanup()

if __name__ == "__main__":
    test_pump2()
