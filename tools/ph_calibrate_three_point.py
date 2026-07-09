#!/usr/bin/env python3
"""
Interactive 3-point pH calibration for Grove Base HAT ADC readings.

Primary calibration model:
    piecewise linear

Calibration points:
    1. pH 7.0 buffer (Neutral)
    2. pH 4.0 buffer (Acidic)
    3. pH 10.0 buffer (Alkaline)

This model uses the pH 7.0 point as an anchor. It calculates two slopes:
one for the acidic range (pH 4 to 7) and one for the alkaline range (pH 7 to 10).
The calibration temperature is recorded to allow Nernst equation compensation during monitoring.
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

PH_CHANNEL = 2
RAW_NEGATIVE_LIMIT = -1_000_000_000.0
RAW_POSITIVE_LIMIT = 1_000_000_000.0


@dataclass
class CalibrationPoint:
    label: str
    reference_ph: float
    solution_temperature_c: float | None
    raw_average: float
    raw_minimum: int
    raw_maximum: int
    raw_span: int
    samples: int


@dataclass
class PhThreePointCalibration:
    created_at: str
    units: str
    method: str
    ph_channel: int
    calibration_temperature_c: float | None
    points: list[CalibrationPoint]
    segments: list[dict[str, float]]
    low_segment_slope: float
    low_segment_offset: float
    high_segment_slope: float
    high_segment_offset: float
    neutral_raw: float
    neutral_ph: float
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
        description="Perform 3-point pH calibration (7.0, 4.0, 10.0)."
    )
    parser.add_argument("--channel", type=int, default=PH_CHANNEL, help="pH ADC channel. Default: 2")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number. Default: 1")
    parser.add_argument("--settle", type=float, default=30.0, help="Settling time before sampling. Default: 30 seconds")
    parser.add_argument("--samples", type=int, default=30, help="Samples to average per solution. Default: 30")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples. Default: 1")
    parser.add_argument("--neutral-ph", type=float, default=7.0, help="Neutral buffer pH. Default: 7.0")
    parser.add_argument("--acidic-ph", type=float, default=4.0, help="Acidic buffer pH. Default: 4.0")
    parser.add_argument("--alkaline-ph", type=float, default=10.01, help="Alkaline buffer pH. Default: 10.01")
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
        "--output",
        type=Path,
        default=Path("config/ph_calibration.json"),
        help="Output calibration JSON path. Default: config/ph_calibration.json",
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
    print("Rinse probe in distilled water, place it in the solution, and avoid bubbles on the probe.")
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
    reference_ph: float,
    solution_temperature_c: float | None,
    samples: int,
    interval: float,
) -> CalibrationPoint:
    values: list[int] = []
    print(f"Sampling {label} (pH {reference_ph:.2f})...")

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
        reference_ph=reference_ph,
        solution_temperature_c=solution_temperature_c,
        raw_average=statistics.fmean(values),
        raw_minimum=raw_min,
        raw_maximum=raw_max,
        raw_span=raw_max - raw_min,
        samples=len(values),
    )


def segment(first: CalibrationPoint, second: CalibrationPoint) -> tuple[float, float]:
    raw_delta = second.raw_average - first.raw_average
    ph_delta = second.reference_ph - first.reference_ph

    if raw_delta == 0:
        raise ValueError(
            f"Invalid calibration: raw average is identical between {first.label} and {second.label}."
        )

    slope = ph_delta / raw_delta
    offset = first.reference_ph - (slope * first.raw_average)
    return slope, offset


def convert(raw_value: float, calibration: PhThreePointCalibration) -> float:
    # Find segment dynamically to support any sensor polarity
    # (some pH modules invert the output — higher pH gives lower raw ADC, or vice versa).
    # points order after reorder: [acidic_pt, neutral_pt, alkaline_pt]
    acidic_pt = calibration.points[0]
    neutral_pt = calibration.points[1]
    alkaline_pt = calibration.points[2]

    # Determine which side of neutral_raw the current reading falls on.
    # Works regardless of whether the sensor inverts the voltage with pH.
    if (acidic_pt.raw_average < neutral_pt.raw_average and raw_value <= neutral_pt.raw_average) or \
       (acidic_pt.raw_average > neutral_pt.raw_average and raw_value >= neutral_pt.raw_average):
        return (calibration.low_segment_slope * raw_value) + calibration.low_segment_offset
    else:
        return (calibration.high_segment_slope * raw_value) + calibration.high_segment_offset


def print_validation(calibration: PhThreePointCalibration) -> None:
    print()
    print("Calibration validation at measured points:")
    for point in calibration.points:
        calculated = convert(point.raw_average, calibration)
        error = calculated - point.reference_ph
        print(
            f"- {point.label}: raw_avg={point.raw_average:.2f}, "
            f"expected_ph={point.reference_ph:.2f}, "
            f"calculated_ph={calculated:.2f}, error={error:+.4f}"
        )


def main() -> int:
    args = build_parser().parse_args()

    if args.samples < 2:
        print("--samples must be at least 2.", file=sys.stderr)
        return 2
    if args.interval <= 0:
        print("--interval must be greater than zero.", file=sys.stderr)
        return 2

    reader = GroveAdcReader(bus=args.bus)
    
    # Standard order: Acidic (4), Neutral (7), Alkaline (10) 
    # But usually it's best to calibrate Neutral first as the anchor.
    # We will do Neutral first, then Acidic, then Alkaline.
    solution_plan = [
        ("Neutral_Buffer", args.neutral_ph),
        ("Acidic_Buffer", args.acidic_ph),
        ("Alkaline_Buffer", args.alkaline_ph),
    ]

    points: list[CalibrationPoint] = []
    print("pH 3-point calibration")
    print(f"Channel: A{args.channel} / Channel {args.channel}")
    print("Primary model: piecewise linear, anchored at pH 7.0")
    
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
            f"({temp_reading.classification} via {temp_reading.source})"
        )

    for label, reference_ph in solution_plan:
        wait_for_user(label, args.non_interactive)
        settle(args.settle)
        points.append(
            collect_point(
                reader=reader,
                channel=args.channel,
                label=label,
                reference_ph=reference_ph,
                solution_temperature_c=actual_calibration_temp,
                samples=args.samples,
                interval=args.interval,
            )
        )

    # points[0] is Neutral, points[1] is Acidic, points[2] is Alkaline
    neutral_pt = points[0]
    acidic_pt = points[1]
    alkaline_pt = points[2]

    # Reorder for logic: Acidic, Neutral, Alkaline
    ordered_points = [acidic_pt, neutral_pt, alkaline_pt]

    low_slope, low_offset = segment(acidic_pt, neutral_pt)
    high_slope, high_offset = segment(neutral_pt, alkaline_pt)
    
    # Raw value boundary between low/high depends on polarity.
    # For safety, we use the neutral raw average as the split point.

    calibration = PhThreePointCalibration(
        created_at=datetime.now().isoformat(timespec="seconds"),
        units="pH",
        method="three_point_piecewise_linear",
        ph_channel=args.channel,
        calibration_temperature_c=actual_calibration_temp,
        points=ordered_points,
        segments=[
            {
                "region": "acidic",
                "slope": low_slope,
                "offset": low_offset,
            },
            {
                "region": "alkaline",
                "slope": high_slope,
                "offset": high_offset,
            },
        ],
        low_segment_slope=low_slope,
        low_segment_offset=low_offset,
        high_segment_slope=high_slope,
        high_segment_offset=high_offset,
        neutral_raw=neutral_pt.raw_average,
        neutral_ph=neutral_pt.reference_ph,
        notes=(
            "Piecewise linear calibration anchored at neutral. "
            "Temperature during calibration is recorded to allow Nernst "
            "equation compensation during live monitoring."
        ),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(calibration), indent=2) + "\n", encoding="utf-8")

    print_validation(calibration)
    print()
    print(f"Wrote calibration: {args.output}")
    print("Use this file with ph_raw_monitor.py via --calibration.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
