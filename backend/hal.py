import time
import threading
import glob

# Try importing hardware libraries safely
try:
    import RPi.GPIO as GPIO
    from gpiozero.pins.rpigpio import RPiGPIOFactory
    from gpiozero import Device
    import seeed_dht
    from smbus2 import SMBus
    
    # Configure gpiozero to use RPi.GPIO
    Device.pin_factory = RPiGPIOFactory()
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    HARDWARE_AVAILABLE = True
except ImportError as e:
    print(f"CRITICAL WARNING: Hardware library missing ({e}). HAL running in stub mode.")
    HARDWARE_AVAILABLE = False
    GPIO = None

# --- PIN CONFIGURATIONS ---
PUMP_PINS = {
    1: {'in1': 18, 'in2': 19, 'en': None, 'name': 'Nutrient A'},
    2: {'in1': 22, 'in2': 23, 'en': None, 'name': 'Nutrient B'},
    3: {'in1': 24, 'in2': 25, 'en': None, 'name': 'pH UP'},
    4: {'in1': 26, 'in2': 27, 'en': None, 'name': 'pH DOWN'}
}
DHT_PIN = 5
DHT_TYPE = "22"  # Set to "22" as per user feedback (was "11")
EC_CHANNEL = 0
PH_CHANNEL = 2

# --- GLOBALS & LOCKS ---
pump_lock = threading.RLock()  # Use Reentrant Lock to allow nested calls within the same thread
pump_status = {1: "stopped", 2: "stopped", 3: "stopped", 4: "stopped"}

class ManualADC:
    def __init__(self, bus_num=1):
        self.bus_num = bus_num
        self.adc_addr = 0x04
        if HARDWARE_AVAILABLE:
            try:
                self.bus = SMBus(bus_num)
            except Exception as e:
                print(f"DEBUG HAL: Failed to open SMBus {bus_num}: {e}")
                self.bus = None
        else:
            self.bus = None

    def read(self, channel):
        if not isinstance(channel, int):
            raise TypeError("ADC channel must be an integer")
        if not (0 <= channel <= 7):
            raise ValueError("ADC channel must be between 0 and 7")
        if not self.bus:
            return None
        try:
            self.bus.write_byte(self.adc_addr, 0x30 + channel)
            time.sleep(0.01)
            data = self.bus.read_i2c_block_data(self.adc_addr, 0x30 + channel, 2)
            return (data[1] << 8) | data[0]
        except Exception:
            return None

    def close(self):
        if self.bus:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None

# Initialize devices
if HARDWARE_AVAILABLE:
    try:
        dht_sensor = seeed_dht.DHT(DHT_TYPE, DHT_PIN)
    except Exception as e:
        print(f"DEBUG HAL: DHT initialization failed: {e}")
        dht_sensor = None
    try:
        adc = ManualADC(bus_num=1)
    except Exception as e:
        print(f"DEBUG HAL: ADC initialization failed: {e}")
        adc = None
else:
    dht_sensor = None
    adc = None

# DS18B20 Setup
BASE_DIR = '/sys/bus/w1/devices/'
def _get_water_temp_device():
    try:
        devices = glob.glob(BASE_DIR + '28*')
        return devices[0] + '/w1_slave' if devices else None
    except Exception:
        return None

# --- SAFE STARTUP ---
def initialize_hardware():
    """Forces all pump GPIO pins to LOW to prevent runaway on reboot."""
    if not HARDWARE_AVAILABLE: return
    for pump_id, pins in PUMP_PINS.items():
        GPIO.setup(pins['in1'], GPIO.OUT)
        GPIO.setup(pins['in2'], GPIO.OUT)
        GPIO.output(pins['in1'], GPIO.LOW)
        GPIO.output(pins['in2'], GPIO.LOW)
        if pins.get('en') is not None:
            GPIO.setup(pins['en'], GPIO.OUT)
            GPIO.output(pins['en'], GPIO.LOW)
        pump_status[pump_id] = "stopped"
    print("DEBUG HAL: Hardware initialized. All pumps forced LOW (FAILSAFE).")

# --- SENSOR ABSTRACTIONS ---
def get_water_temp(fallback_temp=25.0):
    # Dynamic DS18B20 detection on every read to support unplugging/replacing without reboots
    device_file = _get_water_temp_device()
    if not device_file:
        return fallback_temp
    try:
        with open(device_file, 'r') as f:
            lines = f.readlines()
        if not lines or len(lines) < 2:
            return fallback_temp
        if lines[0].strip()[-3:] != 'YES':
            return fallback_temp
        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            return float(lines[1][equals_pos+2:]) / 1000.0
    except Exception:
        return fallback_temp
    return fallback_temp

def get_climate():
    """Returns (humidity, temperature, status)"""
    if not dht_sensor: return 0, 25.0, "ERROR"
    try:
        humi, t = dht_sensor.read()
        if humi is None or t is None: return 0, 25.0, "ERROR"
        return humi, t, "OK"
    except Exception as e:
        print(f"DEBUG HAL: DHT reading failed: {e}")
        return 0, 25.0, "ERROR"

def get_stable_reading(channel):
    """
    Reads 50 rapid samples from the ADC, discards outliers.
    Guards against empty lists to avoid ZeroDivisionError.
    """
    if adc is None: return 0
    
    if not isinstance(channel, int) or not (0 <= channel <= 7):
        raise ValueError(f"Invalid ADC channel: {channel}")

    readings = []
    for _ in range(50):
        raw = adc.read(channel)
        if raw is not None:
            readings.append(raw)
        time.sleep(0.002)
        
    if len(readings) < 20: 
        raise ValueError(f"I2C Communication Failure on channel {channel}")
        
    readings.sort()
    clean = readings[10:-10] # Drop top/bottom 10 outliers
    
    if not clean:
        clean = readings  # Fallback to raw readings if trimmed list is empty to prevent crashes
        
    if not clean:
        raise ValueError(f"No valid readings obtained on channel {channel}")
        
    return sum(clean) / len(clean)

# --- PUMP ABSTRACTIONS ---
def pump_start(pump_id):
    if not HARDWARE_AVAILABLE: return
    pins = PUMP_PINS.get(pump_id)
    if not pins: return
    with pump_lock:
        try:
            GPIO.output(pins['in1'], GPIO.HIGH)
            GPIO.output(pins['in2'], GPIO.LOW)
            if pins.get('en') is not None:
                GPIO.output(pins['en'], GPIO.HIGH)
            pump_status[pump_id] = "running"
            print(f"DEBUG HAL: Pump {pump_id} started on BCM pins {pins['in1']}(HIGH) and {pins['in2']}(LOW). EN={pins.get('en')}")
        except Exception as e:
            print(f"CRITICAL HAL ERROR: Failed to drive GPIO pins for Pump {pump_id}: {e}")

def pump_stop(pump_id):
    if not HARDWARE_AVAILABLE: return
    pins = PUMP_PINS.get(pump_id)
    if not pins: return
    with pump_lock:
        try:
            GPIO.output(pins['in1'], GPIO.LOW)
            GPIO.output(pins['in2'], GPIO.LOW)
            if pins.get('en') is not None:
                GPIO.output(pins['en'], GPIO.LOW)
            pump_status[pump_id] = "stopped"
            print(f"DEBUG HAL: Pump {pump_id} stopped. Pins {pins['in1']}/{pins['in2']} set to LOW. EN={pins.get('en')}")
        except Exception as e:
            print(f"CRITICAL HAL ERROR: Failed to stop Pump {pump_id}: {e}")

def emergency_stop_all():
    """Forces all pumps to halt instantly."""
    if not HARDWARE_AVAILABLE: return
    with pump_lock:
        for pump_id in PUMP_PINS.keys():
            pins = PUMP_PINS[pump_id]
            try:
                GPIO.output(pins['in1'], GPIO.LOW)
                GPIO.output(pins['in2'], GPIO.LOW)
                if pins.get('en') is not None:
                    GPIO.output(pins['en'], GPIO.LOW)
                pump_status[pump_id] = "stopped"
            except Exception as e:
                print(f"CRITICAL HAL ERROR: Emergency Stop Failed for Pump {pump_id}: {e}")

def cleanup():
    """Forces all pumps to halt instantly and cleans up GPIO and I2C connections."""
    emergency_stop_all()
    global adc
    if adc:
        adc.close()
    if HARDWARE_AVAILABLE:
        try:
            GPIO.cleanup()
        except Exception:
            pass
    print("DEBUG HAL: Hardware resources cleaned up cleanly.")

# Run failsafe safe startup initialization
initialize_hardware()
