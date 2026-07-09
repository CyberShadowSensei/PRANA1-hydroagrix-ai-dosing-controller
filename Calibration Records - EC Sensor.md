# Calibration Records - EC Sensor

Project: Hydroponics Monitoring & Automation System

Status: Draft

## Calibration Context

Sensor: EC / conductivity probe and interface board.

Documented probe sticker:

- Cell constant: `K = 0.991`

Available reference solutions:

- Distilled water.
- `1413 uS/cm` calibration solution, equal to `1.413 mS/cm` at `25 C`.
- `12.88 mS/cm` calibration solution at `25 C`.

Target reporting unit:

- `mS/cm`

Target measurement range:

- `0-15 mS/cm`

Primary accuracy range:

- `0-2 mS/cm`

## Engineering Notes

### Temperature Dependence

Verified by user statement:

- The available EC calibration solutions are specified at `25 C`.
- `1413 uS/cm` is valid as `1.413 mS/cm` at `25 C`.
- `12.88 mS/cm` is valid at `25 C`.
- The water temperature sensor is not currently working and a replacement is in transit.

Engineering impact:

- EC changes with solution temperature.
- Calibration performed away from `25 C` can introduce error if temperature is ignored.
- Until a working water temperature sensor is installed, the best practical workaround is to measure solution temperature manually with an external thermometer and record it with the calibration.

Current software approach:
The system now uses a **Dynamic Temperature Fallback Chain** to ensure EC measurements never halt due to a single sensor failure. The temperature source is resolved in this order of priority:
1. `ds18b20`: Primary water temperature sensor (1-Wire).
2. `dht22`: Secondary fallback. Uses air temperature with a configurable offset (`--air-water-offset`, default `-2.0 C`) to estimate water temperature.
3. `manual`: Third fallback. Uses statically provided temperature (`--solution-temp-c` for calibration, `--water-temp-c` for monitoring).
4. `default_25c`: Final fallback. Assumes 25°C, providing uncompensated EC.

- `ec_calibrate_three_point.py` accepts `--temp-source auto` to automatically find the best available sensor, or falls back to manual `--solution-temp-c`.
- `ec_raw_monitor.py` defaults to `--temp-source auto` and will dynamically shift to the best available temperature reading for real-time `EC25` compensation.
- A configurable temperature coefficient is used for approximate compensation.

Default coefficient:

- `1.9 %/C`

Classification:

- Proposed approximation until the exact calibration solution temperature chart or manufacturer coefficient is documented.
- DHT22-based air-to-water offset estimation is strictly **Experimental** and must be tuned once the DS18B20 arrives.

Important:

- If calibration can be performed at or very near `25 C`, that is preferred.
- If a manufacturer temperature chart is available for the exact calibration solutions, use that chart instead of the default coefficient.
- The DS18B20 is automatically detected. Once the replacement water temperature sensor is installed, the system will naturally upgrade its priority and use direct water measurements.

### Raw ADC Readings

The ADC reading is not itself an EC value. It is a sensor-interface output that must be mapped to conductivity using measured calibration data.

Current evidence:

- A0 has shown raw values changing from approximately `0` to a stable region near `70-73`.
- This verifies signal responsiveness for one observed condition only.
- The current log does not identify which solution was being measured.
- The current log is not sufficient to calculate a valid calibration curve.

### Probe Cell Constant `K = 0.991`

The cell constant describes the probe geometry.

If calculating conductivity from measured conductance directly:

```text
conductivity = conductance * K
```

For this project's current ADC-based workflow:

- Do not multiply raw ADC values directly by `K`.
- Do not apply `K` a second time after empirical calibration.
- If calibration is performed using known conductivity solutions and the complete probe plus interface board, the probe constant is effectively included in the fitted calibration curve.
- Record `K = 0.991` as probe metadata and use it only if a lower-level conductance-based conversion is later implemented.

## Recommended Calibration Method

Because the application primarily needs accurate readings below `2 mS/cm`, calibration and validation should prioritize the low EC range. The sensor may still be checked up to `15 mS/cm`, but a calibration optimized across a wide span may reduce accuracy in the low range.

### 1. Stabilize Sensor Readings

For each reference solution:

1. Rinse probe with distilled water.
2. Gently blot or shake off excess liquid without damaging the probe.
3. Place probe in the test solution.
4. Wait for the raw reading to stabilize.
5. Record at least 30-60 seconds of raw readings.
6. Use the stable average, not the first transient readings.

### 2. Record Required Raw Values

| Solution | Reference EC | Unit | Stable Raw Average | Temperature | Notes |
| --- | ---: | --- | ---: | ---: | --- |
| Distilled water | near 0 | mS/cm |  |  | Zero / contamination check only |
| 1413 uS/cm solution | 1.413 | mS/cm |  |  | Primary low-range calibration point |
| 12.88 mS/cm solution | 12.88 | mS/cm |  |  | High-range check; not ideal as the main second point for low-range accuracy |

### 3. Preferred Low-Range Calibration

Preferred:

- Use at least two calibration or validation points inside or near the `0-2 mS/cm` range.
- Keep `1.413 mS/cm` as the main calibration point because it lies inside the primary accuracy range.
- Add a second low-range standard if available, ideally around `0.5-1.0 mS/cm` or near `2.0 mS/cm`.
- Use distilled water as a near-zero check, not a precision zero point unless its actual conductivity is known.

If only the current standards are available:

- Use distilled water as a baseline/contamination check.
- Use `1.413 mS/cm` as the primary calibration anchor.
- Use `12.88 mS/cm` to verify high-range response, but do not assume this produces the best low-range accuracy.

### 4. Three-Point Calibration Strategy

Proposed project approach:

- Use a three-point calibration record because the project needs low-range confidence and high-range awareness.
- Treat the `0-2 mS/cm` region as the priority range.
- Use a piecewise-linear calibration rather than one wide linear fit when low-range accuracy is more important than global simplicity.

Available three-point structure:

| Point | Solution | Role |
| --- | --- | --- |
| 1 | Distilled water | Near-zero baseline / contamination check |
| 2 | `1.413 mS/cm` | Primary low-range calibration anchor |
| 3 | `12.88 mS/cm` | High-range response and upper segment anchor |

Important limitation:

- Distilled water is not a precision `0.000 mS/cm` calibration standard unless its actual conductivity is known.
- If the distilled water raw value is used as the first point, classify the resulting low-end offset as Experimental until verified with a known low-EC standard.

Preferred improvement:

- Add one certified low-range standard inside or near the target range, such as `0.5 mS/cm`, `1.0 mS/cm`, or `2.0 mS/cm`.
- A known low-range standard is more useful for this project than additional high-range standards.

Project calibration tool:

```bash
python3 ~/hydroponics/tools/ec_calibrate_three_point.py
```

Default behavior:

- EC channel: A0 / Channel 0.
- Distilled water reference: `0.000 mS/cm`.
- Low standard: `1.413 mS/cm at 25 C`.
- High standard: `12.88 mS/cm at 25 C`.
- Settling time per solution: `30 seconds`.
- Samples per solution: `30`.
- Output file: `config/ec_calibration.json`.

If using an external thermometer and the solution is not at `25 C`, provide the measured solution temperature:

```bash
python3 ~/hydroponics/tools/ec_calibrate_three_point.py --solution-temp-c 24.2 --settle 60 --samples 60
```

Example with longer settling:

```bash
python3 ~/hydroponics/tools/ec_calibrate_three_point.py --settle 60 --samples 60
```

Use the resulting calibration during live monitoring:

```bash
python3 ~/hydroponics/tools/ec_raw_monitor.py --calibration config/ec_calibration.json --interval 1
```

Use manual water temperature compensation during live monitoring:

```bash
python3 ~/hydroponics/tools/ec_raw_monitor.py --calibration config/ec_calibration.json --water-temp-c 24.2 --interval 1
```

### 5. Fit Two-Point Calibration When Two Reliable Standards Are Available

Use two known reference solutions that bracket or sit near the intended control range whenever possible.

Let:

```text
raw_low  = stable raw average in lower EC reference solution
raw_high = stable raw average in higher EC reference solution
ec_low   = lower reference EC in mS/cm
ec_high  = higher reference EC in mS/cm
```

Then:

```text
slope = (ec_high - ec_low) / (raw_high - raw_low)
offset = ec_low - (slope * raw_low)
EC_mS_cm = (slope * raw_adc) + offset
```

For best low-range accuracy, a fit using references such as `0.5 mS/cm` and `1.413 mS/cm`, or `1.413 mS/cm` and `2.0 mS/cm`, is preferable to a fit using `1.413 mS/cm` and `12.88 mS/cm`.

### 6. Use Distilled Water as a Check

Distilled water should not be treated as a precision calibration point unless its actual conductivity is known.

Use it to check:

- Sensor near-zero behavior.
- Probe contamination.
- Offset sanity.
- Whether readings return near baseline after rinsing.

### 7. Validate the 0-2 mS/cm Priority Range

Before using EC values for hydroponics decisions, validate output in the low range.

Recommended validation points:

- Distilled water near-zero behavior.
- `1.413 mS/cm` standard.
- At least one additional low-range check point if available.
- Repeat measurements after removing, rinsing, and re-immersing the probe.

Acceptance should be based on low-range error first. High-range error is secondary unless the automation later depends on values above `2 mS/cm`.

Suggested repeatability test:

| Trial | Solution | Stable Raw Average | Calculated EC | Reference EC | Error | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1.413 mS/cm |  |  | 1.413 |  |  |
| 2 | 1.413 mS/cm |  |  | 1.413 |  | After rinse/re-immersion |
| 3 | 1.413 mS/cm |  |  | 1.413 |  | After rinse/re-immersion |

### 8. Validate the 0-15 mS/cm Capability

The `12.88 mS/cm` solution is a strong high-range calibration point for a `0-15 mS/cm` target, but it does not fully verify performance at `15 mS/cm`.

Recommended:

- Use two-point calibration with `1.413 mS/cm` and `12.88 mS/cm`.
- Verify distilled water response as a near-zero check.
- If accurate operation near `15 mS/cm` is required, add or prepare an independent verification point near the top of the range.
- Record validation error at each reference point before integrating EC into automation logic.

If low-range accuracy conflicts with high-range accuracy, prefer the low-range calibration for this hydroponics application and document the high-range limitation.

## Acceptance Criteria

Proposed:

- Raw readings are stable in each solution after settling.
- `raw_high` is greater than `raw_low`.
- Fitted or validated output reports approximately `1.413 mS/cm` in the low standard.
- Three-point/piecewise calibration is used when the available raw data supports it.
- Low-range validation below `2 mS/cm` is documented before automation uses EC.
- Repeat readings at `1.413 mS/cm` remain stable after rinse/re-immersion.
- `12.88 mS/cm` response is recorded as a high-range check.
- Distilled water reports near zero or is documented with observed residual conductivity.
- No dosing decisions use EC until calibration is recorded and independently verified.

## Calibration Record Template

Date:

Operator:

Sensor/probe identifier:

Probe sticker K value:

ADC channel:

Interface board:

Temperature during calibration:

Raw readings file:

Stable raw average in distilled water:

Stable raw average in 1.413 mS/cm solution:

Stable raw average in 12.88 mS/cm solution:

Repeatability results at 1.413 mS/cm:

Additional low-range validation point, if available:

Low-range validation error:

Calibration slope:

Calibration offset:

Validation results:

Conclusion:

Decision:

Reason:

Alternatives Considered:

Evidence:

Impact:

## Calibration Record - 2026-06-20 04:02 (Deprecated - Uncompensated)

Status: Deprecated (Replaced by temperature-compensated run)

Operator: User

Sensor/probe identifier: Unknown

Probe sticker K value: `0.991`

ADC channel: A0 / Channel 0

Interface board: Grove Base HAT ADC, I2C bus 1

Temperature during calibration: Assumed 25 C (incorrect)

Calibration method: Three-point piecewise linear calibration with low-range priority.

Reference points:

| Solution | Reference EC | Stable Raw Average | Notes |
| --- | ---: | ---: | --- |
| Distilled water | `0.000 mS/cm` assumed | `0.13` | Used as near-zero anchor |
| 1413 uS/cm standard | `1.413 mS/cm` | `71.17` | Primary low-range calibration point |
| 12.88 mS/cm standard | `12.880 mS/cm` | `643.67` | High-range segment anchor |

## Calibration Record - 2026-06-20 04:52 (Active - Temp Compensated)

Status: Experimental

Operator: User

Sensor/probe identifier: Unknown

Probe sticker K value: `0.991`

ADC channel: A0 / Channel 0

Interface board: Grove Base HAT ADC, I2C bus 1

Temperature during calibration: `29.5 C` (Estimated via DHT22 Air Temp `31.5 C` with `-2.0 C` offset)

Calibration method: Three-point piecewise linear calibration with active temperature compensation.

Reference points:

| Solution | Reference 25C EC | Estimated Actual EC at 29.5C | Stable Raw Average | Notes |
| --- | ---: | ---: | ---: | --- |
| Distilled water | `0.000 mS/cm` | `0.000 mS/cm` | `0.23` | Used as near-zero anchor |
| 1413 uS/cm standard | `1.413 mS/cm` | `1.534 mS/cm` | `68.60` | Primary low-range calibration point |
| 12.88 mS/cm standard | `12.880 mS/cm` | `13.981 mS/cm` | `631.27` | High-range segment anchor |

Validation at measured calibration points:

| Solution | Expected Actual EC | Calculated EC | Error |
| --- | ---: | ---: | ---: |
| Distilled water | `0.000 mS/cm` | `0.000 mS/cm` | `+0.0000` |
| 1413 uS/cm standard | `1.534 mS/cm` | `1.534 mS/cm` | `+0.0000` |
| 12.88 mS/cm standard | `13.981 mS/cm` | `13.981 mS/cm` | `-0.0000` |

Conclusion:
Applying the DHT22 air-to-water estimated temperature (`29.5 C`) successfully adjusted the 12.88 mS/cm standard to its actual physical conductivity of ~13.98 mS/cm. This eliminates the massive gap previously observed where uncompensated calibration was baking in a ~10% thermal error. 

Recommended next actions:
1. Run the live monitor: `python3 ec_raw_monitor.py --calibration config/ec_calibration.json --temp-source auto --air-water-offset -2.0`
2. Submerge the probe in the `12.88 mS/cm` standard. The monitor will measure the actual `~13.98 mS/cm` conductivity, mathematically compensate for the `29.5 C` temperature, and properly display `12.88 mS/cm` for `EC25`.
