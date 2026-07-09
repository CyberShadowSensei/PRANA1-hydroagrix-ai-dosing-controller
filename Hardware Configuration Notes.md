# Hydroponics Hardware Configuration Notes

Status: Active

Classification: Verified by user statement unless later superseded by physical inspection or test results.

## Analog Sensors

Interface: Grove 12-bit ADC on I2C bus 1.

| Sensor | ADC Channel | Code Variable |
| --- | --- | --- |
| EC Meter (Conductivity) | A0 / Channel 0 | `EC_CHANNEL = 0` |
| pH Meter | A2 / Channel 2 | `PH_CHANNEL = 2` |

## Digital Sensors

| Sensor | GPIO (BCM) | Notes |
| --- | ---: | --- |
| DHT22 air temperature and humidity sensor | 5 | Currently installed. Used as air temp and fallback water temp (-2.0C offset) |
| DS18B20 water temperature sensor | 16 | 1-Wire interface. Primary water temp sensor. Currently failed/in-transit |

## Pump Configuration

Driver: L298N H-Bridge.

| Pump | Function | Pin A (BCM) | Pin B (BCM) |
| --- | --- | ---: | ---: |
| Pump 1 | Nutrients A | 18 | 19 |
| Pump 2 | Nutrients B | 22 | 23 |
| Pump 3 | pH UP / base | 24 | 25 |
| Pump 4 | pH DOWN / acid | 26 | 27 |

Verified pump hardware (confirmed 2026-06-20 by user statement):

- 4 x peristaltic pumps physically installed, one per driver channel.
- All four driver channels are in active use.
- Previous note of "2 x 12 V DC peristaltic pumps" was incomplete; superseded by this record.

## Other Hardware

| Component | Connection | GPIO (BCM) | Status |
| --- | --- | ---: | --- |
| USB Camera | USB | N/A | Currently used |
| Fan Relay | Digital | 22 | Reserved / not currently used |
| Grow Light Relay | Digital | TBD | Planned for future use |
| Servo Motor | Digital | 16 | Reserved / not currently used |

## Wire Connections

Analog:

- EC Meter -> Grove ADC A0 / Channel 0.
- pH Meter -> Grove ADC A2 / Channel 2.

Digital sensors:

- DHT22 -> GPIO 5.
- DS18B20 -> GPIO 16.

Pump driver:

- Pump 1 IN1 -> GPIO 18.
- Pump 1 IN2 -> GPIO 19.
- Pump 2 IN3 -> GPIO 22.
- Pump 2 IN4 -> GPIO 23.
- Pump 3 IN1 -> GPIO 24.
- Pump 3 IN2 -> GPIO 25.
- Pump 4 IN3 -> GPIO 26.
- Pump 4 IN4 -> GPIO 27.

Future or optional connections:

- Fan Relay -> GPIO 22.
- Grow Light Relay -> TBD.
- Servo Motor -> GPIO 16.

## GPIO Conflict Warnings

Verified by user statement (2026-06-20):

- DS18B20 and Servo Motor both reference GPIO 16.
- Pump 2 and Fan Relay both reference GPIO 22.

Resolution (confirmed 2026-06-20 by user statement):

- **Fan Relay (GPIO 22):** Not currently implemented. Retained for future expansion only. GPIO 22 belongs to Pump 2.
- **Grow Light Relay (TBD):** Not currently implemented. Retained for future expansion only. No GPIO assigned.
- **Servo Motor (GPIO 16):** Not currently used. GPIO 16 belongs to DS18B20.
- **No active GPIO conflict exists in the current system.** All four L298N pump channels and the DS18B20 are the active assignments.

Engineering rule (unchanged):

- Future hardware using GPIO 16 or GPIO 22 must not be enabled in software until wiring is physically changed and this document is updated.
- Pump control software treats GPIO 22 as Pump 2.
- Servo control software must not use GPIO 16 while DS18B20 is active.

## Decision Log

Decision:
Use `EC_CHANNEL = 0` and `PH_CHANNEL = 2` as the documented analog channel assignments for software development.

Reason:
The user provided explicit hardware configuration mapping EC to Grove ADC A0 and pH to Grove ADC A2.

Alternatives Considered:
Continue treating EC and pH channels as unknown until rediscovered through channel scanning.

Evidence:
User-provided hardware configuration dated with this project session.

Impact:
EC testing can default to channel 0, while raw multi-channel scanning remains useful for independent verification.
