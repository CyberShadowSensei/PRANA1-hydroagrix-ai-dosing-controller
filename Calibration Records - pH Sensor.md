# Calibration Records - pH Sensor

Project: Hydroponics Monitoring & Automation System

Status: Active

## Purpose

This document tracks all manual calibration events for the pH sensor. A 3-point calibration is necessary because the pH sensor relies on raw analog voltage to measure the Hydrogen ion activity in the solution. pH sensors use the Nernst equation, and their slope varies slightly between acidic and alkaline ranges.

## Hardware Under Test

- **Sensor Type**: Analog pH Sensor
- **ADC Interface**: Grove Base HAT, 12-bit ADC
- **Channel**: A2 / Channel 2
- **Calibration Script**: `tools/ph_calibrate_three_point.py`
- **Monitor Script**: `tools/ph_raw_monitor.py`

## Calibration Procedure

1. Clean the probe with distilled water and dry it gently.
2. Ensure you have three calibration buffers:
   - pH 7.0 (Neutral)
   - pH 4.0 (Acidic)
   - pH 10.01 (Alkaline) — use the exact labeled value of the physical solution
3. Run the calibration script in `auto` temperature mode:
   ```bash
   cd ~/tools
   python3 ph_calibrate_three_point.py --temp-source auto
   ```
4. Follow the on-screen prompts (Neutral first, then Acidic, then Alkaline). Rinse probe with distilled water between each solution. Wait for readings to stabilize (default 30 seconds).
5. The calibration slopes and offsets will be automatically saved to `config/ph_calibration.json`.
6. Record the date, temperature, and raw average values in the Record Log below.

## Nernst Temperature Compensation

The calibration tool records the temperature of the buffer solutions during calibration (`T_cal`).
Because the pH slope is temperature-dependent (Nernst equation), the live monitor applies real-time compensation using the formula:

```
pH_compensated = 7.0 + (pH_uncompensated - 7.0) * (T_cal_Kelvin / T_measure_Kelvin)
```

## Sensor Polarity — Verified

**Verified 2026-06-20:**

This pH sensor module inverts the output: **higher pH produces a lower raw ADC value, lower pH produces a higher raw ADC value.**

| Buffer | pH | Raw ADC Average |
| :--- | ---: | ---: |
| Acidic | 4.00 | 610.30 (highest raw) |
| Neutral | 7.00 | 424.67 |
| Alkaline | 10.01 | 318.87 (lowest raw) |

This polarity is handled correctly by the piecewise segment selection in `ph_calibrate_three_point.py` and `ph_raw_monitor.py`. No configuration change is needed.

Engineering rule: If the pH probe or sensor module is replaced, re-verify polarity before using calibration data from a previous probe.

## Engineering Notes

### Temperature Dependence

The Nernst slope is temperature-dependent. Calibration performed at a different temperature than measurement introduces error if uncompensated. The current fallback chain mitigates this by applying the Nernst formula at runtime using the best available temperature reading.

Classification of current temperature source: **Estimated** (DHT22 air temp − 2.0°C offset). This will upgrade to **Verified** once the DS18B20 water temperature sensor is installed.

### Calibration Output File

The active calibration file is: `~/tools/config/ph_calibration.json`

This file contains the piecewise slopes, offsets, calibration temperature, and neutral raw anchor used by the live monitor.

### Validation Policy

After calibration, validate with the live monitor:

```bash
python3 ~/tools/ph_raw_monitor.py --calibration config/ph_calibration.json --temp-source auto
```

Check that:
- Each buffer solution reads approximately its labeled pH value.
- Readings are stable after a 30-second settle period.
- Transitions between solutions are smooth and directionally correct.
- The temperature source and classification are displayed as expected.

---

## Record Log Summary

| Date | Calibration Temp (°C) | Temp Source | Raw Avg (pH 7.0) | Raw Avg (pH 4.0) | Raw Avg (pH 10.01) | Status | Notes |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- | :--- |
| 2026-06-20 | 29.4 | DHT22 Estimated | 424.67 | 610.30 | 318.87 | Experimental | First calibration. DS18B20 unavailable. |

---

## Calibration Record - 2026-06-20 (Active)

**Status:** Experimental

**Date:** 2026-06-20

**Operator:** User

**Sensor/probe identifier:** Unknown (probe not individually marked)

**ADC channel:** A2 / Channel 2

**Interface board:** Grove Base HAT, 12-bit ADC, I2C bus 1

**Temperature during calibration:** 29.4°C

**Temperature source:** DHT22 air temperature − 2.0°C offset (Estimated)

**Classification:** Estimated — DS18B20 water temperature sensor was non-functional (replacement in transit). DHT22 air-to-water offset of −2.0°C is unvalidated until DS18B20 arrives and a side-by-side comparison is recorded.

**Calibration method:** Three-point piecewise linear, anchored at pH 7.0. Nernst temperature compensation applied at runtime.

**Buffer solutions used:**

| Buffer | Labeled pH | Raw ADC Average | Raw Minimum | Raw Maximum |
| :--- | ---: | ---: | ---: | ---: |
| Neutral | 7.00 | 424.67 | — | — |
| Acidic | 4.00 | 610.30 | — | — |
| Alkaline | 10.01 | 318.87 | — | — |

*Raw min/max not captured in summary. Retrieve from `config/ph_calibration.json` on the reTerminal for full span data.*

**Calibration output file:** `~/tools/config/ph_calibration.json`

**Validation at calibration points:**

| Buffer | Expected pH | Calculated pH | Error |
| :--- | ---: | ---: | ---: |
| pH 4.00 | 4.00 | 4.00 | 0.0000 |
| pH 7.00 | 7.00 | 7.00 | 0.0000 |
| pH 10.01 | 10.01 | 10.01 | 0.0000 |

**Monitor validation (live test):**

| Condition | Expected pH | Observed ADC Range | Behaviour |
| :--- | ---: | :--- | :--- |
| Probe in pH 10.01 buffer | ~10.0 | 318–323 | Stable, correct range |
| Probe in pH 4.0 buffer | ~4.0 | 616–623 | Stable, correct range |
| Probe in pH 7.0 buffer | ~7.0 | 422–425 | Stable, correct range |

Transitions between solutions were smooth and directionally correct.

**Sensor polarity confirmed:** Higher pH = lower ADC raw value (inverted output).

**Known limitations of this calibration:**

- Temperature is estimated via DHT22 + offset, not directly measured in the buffer solution. Thermal error is partially mitigated by the Nernst runtime compensation, but the offset itself (−2.0°C) is unvalidated.
- Probe is not individually marked. If the probe is replaced, this calibration record does not apply.
- Raw span (min/max) per solution not captured in this summary. Retrieve from JSON for full data.
- No independent pH meter cross-check was performed against the calculated pH values.
- No repeatability test performed (rinse/re-immerse ×3 per buffer).

**Conclusion:**
First pH calibration successful. Sensor is responsive, polarity confirmed, piecewise calibration and Nernst compensation are functioning. Classification is Experimental pending DS18B20 installation and optional independent meter cross-check.

**Recommended next actions:**
1. Install DS18B20 replacement sensor.
2. Re-run pH calibration with DS18B20 providing verified water temperature — this will upgrade the temperature source from Estimated to Verified.
3. Optionally cross-check calculated pH readings against an independent calibrated pH meter.
4. Perform repeatability test (rinse/re-immerse at pH 7.0 × 3) and record raw averages.
5. Do not use pH values for automated dosing decisions until classification is upgraded to Verified.
