import RPi.GPIO as GPIO
import time

# Pin Mapping (BCM)
# Each tuple is (IN1, IN2) for each pump/port
PUMPS = {
    "Pump 1 (Port D18)": (18, 19),
    "Pump 2 (Port D22)": (22, 23),
    "Pump 3 (Port D24)": (24, 25),
    "Pump 4 (Port D26)": (26, 27)
}

def test_pumps():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Setup all pins as output
    for name, (in1, in2) in PUMPS.items():
        GPIO.setup(in1, GPIO.OUT)
        GPIO.setup(in2, GPIO.OUT)
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.LOW)

    print("--- Starting Pump Hardware Test ---")
    print("Ensure 12V power is connected to L298N and GND is shared with Pi.")
    
    try:
        for name, (in1, in2) in PUMPS.items():
            print(f"Testing: {name}")
            print(f"Forward (IN1=HIGH, IN2=LOW) for 3 seconds...")
            GPIO.output(in1, GPIO.HIGH)
            GPIO.output(in2, GPIO.LOW)
            time.sleep(3)
            
            print("Stopping...")
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.LOW)
            time.sleep(1)

        print("--- Test Complete! All pumps cycled. ---")

    except KeyboardInterrupt:
        print("--- Test aborted by user. ---")
    finally:
        # Final cleanup
        for name, (in1, in2) in PUMPS.items():
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.LOW)
        GPIO.cleanup()

if __name__ == "__main__":
    test_pumps()
