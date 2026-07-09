import time
from smbus2 import SMBus

def test_adc():
    bus = SMBus(1)
    adc_addr = 0x04
    channel = 2 # pH channel
    
    try:
        # Read RAW (0x10)
        bus.write_byte(adc_addr, 0x10 + channel)
        time.sleep(0.05)
        raw_data = bus.read_i2c_block_data(adc_addr, 0x10 + channel, 2)
        raw_val = (raw_data[1] << 8) | raw_data[0]
        
        # Read Voltage (0x20)
        bus.write_byte(adc_addr, 0x20 + channel)
        time.sleep(0.05)
        vol_data = bus.read_i2c_block_data(adc_addr, 0x20 + channel, 2)
        vol_val = (vol_data[1] << 8) | vol_data[0]
        
        # Read Ratio (0x30)
        bus.write_byte(adc_addr, 0x30 + channel)
        time.sleep(0.05)
        rat_data = bus.read_i2c_block_data(adc_addr, 0x30 + channel, 2)
        rat_val = (rat_data[1] << 8) | rat_data[0]

        print("=== ADC CHANNEL 2 DIAGNOSTICS ===")
        print(f"Register 0x10 (RAW):     {raw_val}")
        print(f"Register 0x20 (Voltage): {vol_val} mV")
        print(f"Register 0x30 (Ratio):   {rat_val}")
        print("=================================")
        
    except Exception as e:
        print(f"I2C Error: {e}")
    finally:
        bus.close()

if __name__ == "__main__":
    test_adc()
