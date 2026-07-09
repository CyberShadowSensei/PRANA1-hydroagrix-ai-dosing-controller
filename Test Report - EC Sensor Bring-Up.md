# Test Report - EC Sensor Bring-Up

Project: Hydroponics Monitoring & Automation System

Status: Draft

Classification: Experimental until test data is recorded.

## 1. Problem Definition

The EC sensor is documented as installed on Grove ADC A0 / Channel 0, but its functional status and raw response stability still require verification.

## 2. Existing Evidence

Verified:

- Raspberry Pi CM4 / reTerminal platform is operational.
- Seeed Studio Grove Base HAT V1.0 is installed.
- I2C communication is verified.
- ManualADC interface at address `0x04` is verified.
- pH analog output has shown dynamic raw readings.
- EC sensor is documented as connected to Grove ADC A0 / Channel 0.

Documented but not verified:

- EC raw response behavior.
- EC reading stability.
- EC calibration.

## 3. Unknowns

- Sensor board power status.
- Probe condition.
- Raw ADC range in air.
- Raw ADC range in water.
- Raw ADC range in calibration or nutrient solution.
- Calibration constants.

## 4. Safety and Setup Notes

- Do not apply calibration constants during this bring-up test.
- Preserve raw ADC readings.
- Do not energize dosing pumps or motor drivers during this test.
- Keep probe and electronics dry except for the intended probe tip.
- If the sensor board becomes hot, smells unusual, or behaves erratically, stop testing and document the observation.

## 5. Test Equipment

Required:

- Raspberry Pi CM4 / reTerminal with Grove Base HAT.
- EC sensor board and probe.
- Known Grove cable.
- Clean water sample.

Recommended:

- Known EC calibration solution.
- Laboratory EC/TDS meter for independent reference.
- Camera for wiring documentation.

## 6. Test Procedure

### Step 1: Physical Inspection

Record:

- EC sensor board model:
- Grove port connected: A0 / Channel 0 expected
- Cable condition:
- Probe condition:
- Any visible damage:
- Photo reference filename:

Pass Criteria:

- Sensor is physically connected and no obvious damage is observed.

### Step 2: ADC Channel Discovery

Read raw ADC values from the documented EC channel. Optionally scan all analog channels to independently confirm the wiring.

Record raw readings:

| Condition | A0 | A1 | A2 | A3 | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Probe dry / in air |  |  |  |  |  |
| Probe in clean water |  |  |  |  |  |
| Probe in known solution |  |  |  |  |  |

Pass Criteria:

- A0 / Channel 0 shows a plausible response when probe condition changes.

Fail Criteria:

- A0 / Channel 0 does not change meaningfully.
- All channels read fixed minimum or maximum values.
- Sensor board shows abnormal heating or instability.

### Step 3: Dynamic Response Check

Observe A0 / Channel 0 for at least 30 seconds in each condition.

Record:

| Condition | Minimum Raw | Maximum Raw | Approx. Stable Raw | Notes |
| --- | ---: | ---: | ---: | --- |
| Probe dry / in air |  |  |  |  |
| Probe in clean water |  |  |  |  |
| Probe in known solution |  |  |  |  |

Pass Criteria:

- Raw readings are stable enough for later calibration.
- Raw readings change when solution conductivity changes.

### Step 4: Independent Reference Check

If an independent EC/TDS meter is available, record its reading for the same solution.

| Sample | Reference Meter Reading | Units | Temperature | Notes |
| --- | ---: | --- | ---: | --- |
| Clean water |  |  |  |  |
| Known solution |  |  |  |  |

## 7. Observations

Record factual observations only:

-

## 8. Raw Data

Paste raw console output or reading logs here:

```text

```

## 9. Conclusion

Classification after test:

- Verified:
- Assumed:
- Proposed:
- Experimental:

Conclusion:

## 10. Decision Log

Decision:

Reason:

Alternatives Considered:

Evidence:

Impact:

## 11. Recommended Next Actions

-

## Test Entry - 2026-06-20 04:02

Classification:
Experimental

Observed raw response:

| Condition | Reference EC | Stable Raw Average | Notes |
| --- | ---: | ---: | --- |
| Distilled water | `0.000 mS/cm` assumed | `0.13` | Near-zero response observed |
| 1413 uS/cm standard | `1.413 mS/cm` | `71.17` | Low-range response observed |
| 12.88 mS/cm standard | `12.880 mS/cm` | `643.67` | High-range response observed |

Live monitor after calibration:

```text
A0 raw: 650-653
Calculated EC: approximately 13.007-13.067 mS/cm
Observed span: 2-3 raw counts
```

Conclusion:
A0 / Channel 0 shows a clear increasing raw response from distilled water to `1.413 mS/cm` and from `1.413 mS/cm` to `12.88 mS/cm`. The sensor path is responsive and stable enough to proceed with repeatability testing.

Recommended Next Actions:

1. Repeat the `1.413 mS/cm` measurement after rinse/re-immersion.
2. Recheck distilled water after high-solution exposure.
3. Record calibration temperature.
4. Keep EC automation disabled until low-range repeatability is verified.
