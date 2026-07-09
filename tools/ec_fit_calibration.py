#!/usr/bin/env python3
"""
Fit EC raw-ADC to mS/cm calibration data.

Use this after collecting stable raw averages from known EC standards.
For low-range hydroponics accuracy, prefer two standards in or near the
0-2 mS/cm range. The 12.88 mS/cm standard is useful for high-range checking,
but it is not the ideal second point when low-range precision matters most.

Two-point mode fits one line:

    EC_mS_cm = (slope * raw_adc) + offset

Three-point mode fits two piecewise-linear segments:

    point 1 -> point 2: low-range segment
    point 2 -> point 3: high-range segment

The probe K value is stored as metadata only. Do not apply it again after this
empirical calibration unless the conversion method is deliberately changed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class EcCalibration:
    created_at: str
    units: str
    method: str
    ec_channel: int
    probe_k: float | None
    points: list[dict[str, float]]
    segments: list[dict[str, float]]
    notes: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit EC calibration constants from two or three reference points."
    )
    parser.add_argument(
        "--low-raw",
        type=float,
        required=False,
        help="Stable raw average in the low EC reference solution.",
    )
    parser.add_argument(
        "--high-raw",
        type=float,
        required=False,
        help="Stable raw average in the high EC reference solution.",
    )
    parser.add_argument(
        "--low-ec",
        type=float,
        default=1.413,
        help="Low reference EC in mS/cm. Default: 1.413",
    )
    parser.add_argument(
        "--high-ec",
        type=float,
        default=12.88,
        help=(
            "High reference EC in mS/cm. Default: 12.88. "
            "For low-range calibration, use a known value near 2.0 if available."
        ),
    )
    parser.add_argument(
        "--point",
        action="append",
        default=[],
        metavar="RAW:EC",
        help=(
            "Calibration point as raw:mS/cm. Use three times for 3-point "
            "piecewise calibration, for example --point 10:0.05 "
            "--point 220:1.413 --point 1800:12.88"
        ),
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=0,
        help="ADC channel for EC sensor. Default: 0",
    )
    parser.add_argument(
        "--probe-k",
        type=float,
        default=0.991,
        help="Probe cell constant metadata. Default: 0.991",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("config/ec_calibration.json"),
        help="Calibration JSON output path. Default: config/ec_calibration.json",
    )
    parser.add_argument(
        "--notes",
        default=(
            "EC calibration. Low-range hydroponics accuracy below 2 mS/cm is "
            "the primary project requirement."
        ),
        help="Notes stored with the calibration file.",
    )
    return parser


def parse_point(value: str) -> dict[str, float]:
    try:
        raw_text, ec_text = value.split(":", maxsplit=1)
        return {"raw": float(raw_text), "ec_ms_cm": float(ec_text)}
    except ValueError as exc:
        raise ValueError(f"Invalid calibration point '{value}'. Expected RAW:EC.") from exc


def segment_between(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    raw_delta = right["raw"] - left["raw"]
    ec_delta = right["ec_ms_cm"] - left["ec_ms_cm"]

    if raw_delta <= 0:
        raise ValueError(
            "Calibration point raw values must increase with EC. Verify stable "
            "averages, wiring, and solution order before calibrating."
        )

    slope = ec_delta / raw_delta
    offset = left["ec_ms_cm"] - (slope * left["raw"])
    return {
        "raw_min": left["raw"],
        "raw_max": right["raw"],
        "ec_min_ms_cm": left["ec_ms_cm"],
        "ec_max_ms_cm": right["ec_ms_cm"],
        "slope": slope,
        "offset": offset,
    }


def collect_points(args: argparse.Namespace) -> list[dict[str, float]]:
    if args.point:
        points = [parse_point(point) for point in args.point]
    else:
        if args.low_raw is None or args.high_raw is None:
            raise ValueError("Provide --low-raw and --high-raw, or provide --point values.")
        points = [
            {"raw": args.low_raw, "ec_ms_cm": args.low_ec},
            {"raw": args.high_raw, "ec_ms_cm": args.high_ec},
        ]

    points = sorted(points, key=lambda item: item["ec_ms_cm"])

    if len(points) not in (2, 3):
        raise ValueError("Use exactly two points for linear mode or three points for piecewise mode.")

    for index in range(1, len(points)):
        if points[index]["ec_ms_cm"] <= points[index - 1]["ec_ms_cm"]:
            raise ValueError("Reference EC values must be unique and increasing.")

    return points


def fit_calibration(args: argparse.Namespace) -> EcCalibration:
    points = collect_points(args)
    segments = [
        segment_between(points[index], points[index + 1])
        for index in range(len(points) - 1)
    ]
    method = "two_point_linear_raw_adc" if len(points) == 2 else "three_point_piecewise_linear_raw_adc"

    return EcCalibration(
        created_at=datetime.now().isoformat(timespec="seconds"),
        units="mS/cm",
        method=method,
        ec_channel=args.channel,
        probe_k=args.probe_k,
        points=points,
        segments=segments,
        notes=args.notes,
    )


def main() -> int:
    args = build_parser().parse_args()
    calibration = fit_calibration(args)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(asdict(calibration), indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote calibration: {args.output}")
    print(f"Method: {calibration.method}")
    for index, segment in enumerate(calibration.segments, start=1):
        print(
            f"Segment {index}: raw {segment['raw_min']:.3f}-{segment['raw_max']:.3f}, "
            f"EC_mS_cm = ({segment['slope']:.10f} * raw_adc) + {segment['offset']:.10f}"
        )
    print("Probe K stored as metadata only; not applied as an extra multiplier.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
