"""Three-Point EC Piecewise Calibration Tool
Computes low/high slope factors using standard reference solutions with thermal compensation.
"""
#!/usr/bin/env python3
"""
Interactive 3-point EC calibration for Grove Base HAT ADC readings.

Primary calibration model:
    piecewise linear

Calibration points:
    1. Distilled water, assumed 0.000 mS/cm unless overridden.
    2. 1413 uS/cm standard, 1.413 mS/cm at 25 C.
    3. 12.88 mS/cm standard at 25 C.

This model prioritizes low-range accuracy by using the distilled-water and
1.413 mS/cm points for low EC readings, while retaining a high-range segment
for readings above the 1.413 mS/cm reference point.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from temperature_source import TemperatureSource


EC_CHANNEL = 0
RAW_NEGATIVE_LIMIT = -1_000_000_000.0
RAW_POSITIVE_LIMIT = 1_000_000_000.0


@dataclass
class CalibrationPoint:
    label: str
    reference_25c_ms_cm: float
    estimated_actual_ms_cm: float
    solution_temperature_c: float | None
    raw_average: float
    raw_minimum: int
    raw_maximum: int
    raw_span: int
    samples: int


@dataclass
class EcThreePointCalibration:
    created_at: str
    units: str
    method: str
    ec_channel: int
    probe_k: float
    reference_temperature_c: float
    temp_coefficient_percent_per_c: float
    calibration_temperature_c: float | None
    low_range_priority: bool
    points: list[CalibrationPoint]
    segments: list[dict[str, float]]
    low_segment_slope: float
    low_segment_offset: float
    high_segment_slope: float
    high_segment_offset: float
    notes: str


class GroveAdcReader:
    def __init__(self, bus: int = 1) -> None:
        try:
            import grove.i2c

            try:
                grove.i2c.Bus(bus)
            except Exception as exc:  # noqa: BLE001
                print(f"Warning: pre-initializing I2C bus {bus} failed: {exc}", file=sys.stderr)

            from grove.adc import ADC
        except ImportError as exc:
            raise SystemExit(
                "Could not import grove.adc.ADC. Run this on the reTerminal "
                "with grove.py installed."
            ) from exc

        self._adc = ADC()

    def read(self, channel: int) -> int:
        return int(self._adc.read(channel))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Perform low-range focused 3-point EC calibration."
    )
    parser.add_argument("--channel", type=int, default=EC_CHANNEL, help="EC ADC channel. Default: 0")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number. Default: 1")
    parser.add_argument("--settle", type=float, default=30.0, help="Settling time before sampling. Default: 30 seconds")
    parser.add_argument("--samples", type=int, default=30, help="Samples to average per solution. Default: 30")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples. Default: 1")
    parser.add_argument("--distilled-ec", type=float, default=0.0, help="Distilled water EC in mS/cm. Default: 0.0")
    parser.add_argument("--low-ec", type=float, default=1.413, help="Low standard EC at 25 C in mS/cm. Default: 1.413")
    parser.add_argument("--high-ec", type=float, default=12.88, help="High standard EC at 25 C in mS/cm. Default: 12.88")
    parser.add_argument("--probe-k", type=float, default=0.991, help="Probe K metadata. Default: 0.991")
    parser.add_argument(
        "--solution-temp-c",
        type=float,
        default=None,
        help="Manual calibration solution temperature in C. Used as fallback.",
    )
    parser.add_argument(
        "--temp-source",
        type=str,
        default="auto",
        choices=["auto", "ds18b20", "dht22", "manual", "none"],
        help="Temperature source for calibration. Default: auto",
    )
    parser.add_argument(
        "--air-water-offset",
        type=float,
        default=-2.0,
        help="Offset to add to DHT22 air temp to estimate water temp. Default: -2.0",
    )
    parser.add_argument(
        "--temp-coeff-percent",
        type=float,
        default=1.9,
        help=(
            "Approximate conductivity temperature coefficient in percent per C. "
            "Default: 1.9. Replace with solution manufacturer chart value if known."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("config/ec_calibration.json"),
        help="Output calibration JSON path. Default: config/ec_calibration.json",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not wait for Enter between solutions. Useful for scripted runs.",
    )
    return parser


def wait_for_user(label: str, non_interactive: bool) -> None:
    print()
    print(f"Prepare solution: {label}")
    print("Rinse probe, place it in the solution, and avoid bubbles on the probe.")
    if not non_interactive:
        input("Press Enter when the probe is in solution and ready to settle...")


def settle(seconds: float) -> None:
    if seconds <= 0:
        return
    print(f"Settling for {seconds:.0f} seconds...")
    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        remaining = int(round(end_time - time.monotonic()))
        print(f"\rRemaining: {remaining:>3} s", end="", flush=True)
        time.sleep(1)
    print()


def collect_point(
    reader: GroveAdcReader,
    channel: int,
    label: str,
    reference_25c_ms_cm: float,
    estimated_actual_ms_cm: float,
    solution_temperature_c: float | None,
    samples: int,
    interval: float,
) -> CalibrationPoint:
    values: list[int] = []
    print(
        f"Sampling {label} "
        f"({reference_25c_ms_cm:.3f} mS/cm at 25 C, "
        f"estimated actual {estimated_actual_ms_cm:.3f} mS/cm)..."
    )

    for index in range(samples):
        raw = reader.read(channel)
        values.append(raw)
        avg = statistics.fmean(values)
        print(
            f"\rSample {index + 1:>3}/{samples}: raw={raw:>5} avg={avg:>8.2f}",
            end="",
            flush=True,
        )
        if index < samples - 1:
            time.sleep(interval)

    print()
    raw_min = min(values)
    raw_max = max(values)
    return CalibrationPoint(
        label=label,
        reference_25c_ms_cm=reference_25c_ms_cm,
        estimated_actual_ms_cm=estimated_actual_ms_cm,
        solution_temperature_c=solution_temperature_c,
        raw_average=statistics.fmean(values),
        raw_minimum=raw_min,
        raw_maximum=raw_max,
        raw_span=raw_max - raw_min,
        samples=len(values),
    )


def segment(first: CalibrationPoint, second: CalibrationPoint) -> tuple[float, float]:
    raw_delta = second.raw_average - first.raw_average
    ec_delta = second.estimated_actual_ms_cm - first.estimated_actual_ms_cm

    if raw_delta <= 0:
        raise ValueError(
            f"Invalid calibration order between {first.label} and {second.label}: "
            "higher EC solution must produce a higher raw average."
        )

    slope = ec_delta / raw_delta
    offset = first.estimated_actual_ms_cm - (slope * first.raw_average)
    return slope, offset


def convert(raw_value: float, calibration: EcThreePointCalibration) -> float:
    middle_raw = calibration.points[1].raw_average
    if raw_value <= middle_raw:
        return (calibration.low_segment_slope * raw_value) + calibration.low_segment_offset
    return (calibration.high_segment_slope * raw_value) + calibration.high_segment_offset


def print_validation(calibration: EcThreePointCalibration) -> None:
    print()
    print("Calibration validation at measured points:")
    for point in calibration.points:
        calculated = convert(point.raw_average, calibration)
        error = calculated - point.estimated_actual_ms_cm
        print(
            f"- {point.label}: raw_avg={point.raw_average:.2f}, "
            f"expected_actual={point.estimated_actual_ms_cm:.3f} mS/cm, "
            f"calculated={calculated:.3f} mS/cm, error={error:+.4f}"
        )


def estimate_actual_ec(reference_25c_ms_cm: float, temperature_c: float | None, coefficient_percent: float) -> float:
    if temperature_c is None:
        return reference_25c_ms_cm
    coefficient = coefficient_percent / 100.0
    return reference_25c_ms_cm * (1.0 + coefficient * (temperature_c - 25.0))


def main() -> int:
    args = build_parser().parse_args()

    if args.samples < 2:
        print("--samples must be at least 2.", file=sys.stderr)
        return 2
    if args.interval <= 0:
        print("--interval must be greater than zero.", file=sys.stderr)
        return 2
    if args.temp_coeff_percent < 0:
        print("--temp-coeff-percent must not be negative.", file=sys.stderr)
        return 2

    reader = GroveAdcReader(bus=args.bus)
    solution_plan = [
        ("distilled_water", args.distilled_ec),
        ("1413_uS_cm_standard", args.low_ec),
        ("12_88_mS_cm_standard", args.high_ec),
    ]

    points: list[CalibrationPoint] = []
    print("EC 3-point calibration")
    print("Classification: Experimental until verified against reference solutions")
    print(f"Channel: A{args.channel} / Channel {args.channel}")
    print("Primary model: piecewise linear, low-range focused")
    
    # Initialize dynamic temperature source
    temp_provider = TemperatureSource(
        air_water_offset_c=args.air_water_offset,
        manual_fallback_c=args.solution_temp_c
    )
    
    temp_reading = None
    if args.temp_source != "none":
        temp_reading = temp_provider.get_temperature(args.temp_source)

    if temp_reading is None or temp_reading.source == "default_25c":
        print("Temperature mode: no temperature detected; standards are treated as 25 C values")
        actual_calibration_temp = None
    else:
        actual_calibration_temp = temp_reading.value_c
        print(
            "Temperature mode: active compensation during calibration; "
            f"solution temperature={actual_calibration_temp:.2f} C "
            f"({temp_reading.classification} via {temp_reading.source}), "
            f"coefficient={args.temp_coeff_percent:.3f}%/C"
        )

    for label, reference_25c in solution_plan:
        estimated_actual = estimate_actual_ec(
            reference_25c_ms_cm=reference_25c,
            temperature_c=actual_calibration_temp,
            coefficient_percent=args.temp_coeff_percent,
        )
        wait_for_user(label, args.non_interactive)
        settle(args.settle)
        points.append(
            collect_point(
                reader=reader,
                channel=args.channel,
                label=label,
                reference_25c_ms_cm=reference_25c,
                estimated_actual_ms_cm=estimated_actual,
                solution_temperature_c=actual_calibration_temp,
                samples=args.samples,
                interval=args.interval,
            )
        )

    low_slope, low_offset = segment(points[0], points[1])
    high_slope, high_offset = segment(points[1], points[2])

    calibration = EcThreePointCalibration(
        created_at=datetime.now().isoformat(timespec="seconds"),
        units="mS/cm",
        method="three_point_piecewise_linear_low_range_priority",
        ec_channel=args.channel,
        probe_k=args.probe_k,
        reference_temperature_c=25.0,
        temp_coefficient_percent_per_c=args.temp_coeff_percent,
        calibration_temperature_c=actual_calibration_temp,
        low_range_priority=True,
        points=points,
        segments=[
            {
                "raw_min": RAW_NEGATIVE_LIMIT,
                "raw_max": points[1].raw_average,
                "slope": low_slope,
                "offset": low_offset,
            },
            {
                "raw_min": points[1].raw_average,
                "raw_max": RAW_POSITIVE_LIMIT,
                "slope": high_slope,
                "offset": high_offset,
            },
        ],
        low_segment_slope=low_slope,
        low_segment_offset=low_offset,
        high_segment_slope=high_slope,
        high_segment_offset=high_offset,
        notes=(
            "Distilled water anchors the near-zero point. The 1.413 mS/cm "
            "standard controls the critical low EC range. The 12.88 mS/cm "
            "standard provides higher-range scaling."
        ),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(calibration), indent=2) + "\n", encoding="utf-8")

    print_validation(calibration)
    print()
    print(f"Wrote calibration: {args.output}")
    print("Use this file with ec_raw_monitor.py via --calibration.")
    print("Probe K is stored as metadata and is not applied as an extra multiplier.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
