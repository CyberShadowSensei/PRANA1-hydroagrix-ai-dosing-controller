# Hardware Mocking & Stubbing Strategy

## Hardware Stub Hierarchy
- **`smbus2`**: Mocked with virtual I2C register maps returning synthetic ADC sine-wave signals.
- **`RPi.GPIO`**: Mocked with pin state dictionaries recording motor high/low timestamps.
- **`w1_slave`**: Mocked with virtual sysfs files returning CRC-checked DS18B20 hex strings.
