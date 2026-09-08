# Sensor Calibration Reference Procedure

## pH Sensor Three-Point Calibration
- Buffer 4.0: Standard acidic reference point.
- Buffer 7.0: Neutral midpoint reference.
- Buffer 10.0: Standard basic reference point.

Execute piecewise calibration using `tools/ph_calibrate_three_point.py`. Calibration curves are stored atomically in `config/ph_calibration.json`.
