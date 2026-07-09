#!/usr/bin/env python3
"""
Raw EC sensor monitor for Grove Base HAT analog inputs.

Purpose:
    - Read raw ADC values only.
    - Help identify the EC sensor channel.
    - Observe real-time responsiveness and stability before calibration.

This script intentionally does not convert raw values to EC, TDS, or salinity.
Calibration must be performed separately with reference solutions and recorded
in the project calibration records.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from temperature_source import TemperatureSource, TemperatureReading


EC_CHANNEL = 0
DEFAULT_CHANNELS = [EC_CHANNEL]


@dataclass
class ChannelStats:
    channel: int
    current: int
    minimum: int
    maximum: int
    average: float
    span: int
    samples: int


@dataclass
class EcCalibration:
    channel: int
    method: str
    segments: list[dict[str, float]]
    units: str
    probe_k: float | None
    reference_temperature_c: float
    temp_coefficient_percent_per_c: float | None

    def convert_actual(self, raw_value: int) -> float:
        segment = self.segments[0]
        for candidate in self.segments:
            if candidate["raw_min"] <= raw_value <= candidate["raw_max"]:
                segment = candidate
                break
            if raw_value > candidate["raw_max"]:
                segment = candidate
        return (segment["slope"] * raw_value) + segment["offset"]

    def convert_to_reference_temperature(self, raw_value: int, water_temp_c: float | None) -> float:
        actual_ec = self.convert_actual(raw_value)
        if water_temp_c is None or self.temp_coefficient_percent_per_c is None:
            return actual_ec
        coefficient = self.temp_coefficient_percent_per_c / 100.0
        correction_factor = 1.0 + coefficient * (water_temp_c - self.reference_temperature_c)
        if correction_factor == 0:
            return actual_ec
        return actual_ec / correction_factor


class GroveAdcReader:
    """Small wrapper around grove.py's ADC class."""

    def __init__(self, bus: int = 1) -> None:
        try:
            import grove.i2c
            # Pre-initialize Bus singleton with the specified bus number (default 1)
            # to prevent it from defaulting to bus 0 (/dev/i2c-0) on some platforms.
            try:
                grove.i2c.Bus(bus)
            except Exception as e:
                print(f"Warning: Pre-initializing I2C bus {bus} failed: {e}", file=sys.stderr)
            
            from grove.adc import ADC
        except ImportError as exc:
            raise SystemExit(
                "Could not import grove.adc.ADC. Run this on the reTerminal "
                "with grove.py installed, or install the verified project "
                "dependencies first."
            ) from exc

        self._adc = ADC()

    def read(self, channel: int) -> int:
        value = self._adc.read(channel)
        return int(value)


def parse_channels(value: str) -> list[int]:
    channels: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        channels.append(int(item))
    if not channels:
        raise argparse.ArgumentTypeError("At least one channel is required.")
    return channels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Monitor raw EC sensor ADC values on Grove Base HAT channels."
    )
    parser.add_argument(
        "--channels",
        type=parse_channels,
        default=DEFAULT_CHANNELS,
        help="Comma-separated ADC channels to read. Default: 0",
    )
    parser.add_argument(
        "--bus",
        type=int,
        default=1,
        help="I2C bus number to use. Default: 1 (/dev/i2c-1)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between readings. Default: 1.0",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=20,
        help="Rolling sample window for stability stats. Default: 20",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Optional run duration in seconds. Default: run until Ctrl+C",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional CSV output path for raw readings.",
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        default=None,
        help="Optional calibration JSON from ec_fit_calibration.py.",
    )
    parser.add_argument(
        "--water-temp-c",
        type=float,
        default=None,
        help="Manual water temperature in C. Used as fallback if sensors fail.",
    )
    parser.add_argument(
        "--temp-source",
        type=str,
        default="auto",
        choices=["auto", "ds18b20", "dht22", "manual", "none"],
        help="Temperature source. Default: auto (fallback chain)",
    )
    parser.add_argument(
        "--air-water-offset",
        type=float,
        default=-2.0,
        help="Offset to add to DHT22 air temp to estimate water temp. Default: -2.0",
    )
    return parser


def summarize(channel: int, values: deque[int]) -> ChannelStats:
    current = values[-1]
    minimum = min(values)
    maximum = max(values)
    average = statistics.fmean(values)
    return ChannelStats(
        channel=channel,
        current=current,
        minimum=minimum,
        maximum=maximum,
        average=average,
        span=maximum - minimum,
        samples=len(values),
    )


def load_calibration(path: Path | None) -> EcCalibration | None:
    if path is None:
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    if "segments" in data:
        segments = data["segments"]
        method = str(data.get("method", "piecewise_linear_raw_adc"))
    else:
        segments = [
            {
                "raw_min": float("-inf"),
                "raw_max": float("inf"),
                "slope": float(data["slope"]),
                "offset": float(data["offset"]),
            }
        ]
        method = str(data.get("method", "two_point_linear_raw_adc"))

    return EcCalibration(
        channel=int(data["ec_channel"]),
        method=method,
        segments=segments,
        units=str(data.get("units", "mS/cm")),
        probe_k=data.get("probe_k"),
        reference_temperature_c=float(data.get("reference_temperature_c", 25.0)),
        temp_coefficient_percent_per_c=data.get("temp_coefficient_percent_per_c"),
    )


def print_header(
    channels: list[int],
    calibration: EcCalibration | None,
    water_temp_c: float | None,
    temp_source: str,
) -> None:
    channel_labels = " ".join(f"A{channel:>1}" for channel in channels)
    print("Raw EC sensor monitor")
    print("Classification: Experimental")
    print(f"Documented EC channel: A{EC_CHANNEL} / Channel {EC_CHANNEL}")
    print(f"Channels: {channel_labels}")
    if calibration is not None:
        print("Mode: raw ADC readings with calibrated EC display")
        print(
            "Calibration display enabled: "
            f"A{calibration.channel} -> {calibration.units}; "
            f"method={calibration.method}; "
            "raw values are still preserved"
        )
        print(
            "Temperature compensation enabled. "
            f"Reference={calibration.reference_temperature_c:.2f} C. "
            f"Source mode={temp_source}."
        )
    else:
        print("Mode: raw ADC readings only; no calibration applied")
    print("Press Ctrl+C to stop.")
    print()


def print_status(
    stats: list[ChannelStats],
    calibration: EcCalibration | None,
    temp_reading: TemperatureReading | None,
) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    parts = [timestamp]
    for item in stats:
        channel_text = (
            f"A{item.channel}=raw:{item.current:>5} "
            f"avg:{item.average:>7.1f} "
            f"min:{item.minimum:>5} "
            f"max:{item.maximum:>5} "
            f"span:{item.span:>5} "
            f"n:{item.samples:>3}"
        )
        if calibration is not None and item.channel == calibration.channel:
            actual_ec = calibration.convert_actual(item.current)
            channel_text += f" ec_actual:{actual_ec:>8.3f} {calibration.units}"
            if temp_reading is not None:
                ec_ref = calibration.convert_to_reference_temperature(item.current, temp_reading.value_c)
                channel_text += f" ec25:{ec_ref:>8.3f} {calibration.units} (T={temp_reading.value_c:.1f}C {temp_reading.classification[:3]})"
        parts.append(channel_text)
    print(" | ".join(parts), flush=True)


def open_csv(
    path: Path | None,
    channels: list[int],
    calibration: EcCalibration | None,
    water_temp_c: float | None,
):
    if path is None:
        return None, None

    path.parent.mkdir(parents=True, exist_ok=True)
    csv_file = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)

    if path.stat().st_size == 0:
        columns = ["timestamp", *[f"A{channel}_raw" for channel in channels]]
        if calibration is not None and calibration.channel in channels:
            columns.append(f"A{calibration.channel}_ec_actual_{calibration.units.replace('/', '_')}")
            if water_temp_c is not None:
                columns.append(f"A{calibration.channel}_ec25_{calibration.units.replace('/', '_')}")
        writer.writerow(columns)
        csv_file.flush()

    return csv_file, writer


def main() -> int:
    args = build_parser().parse_args()

    if args.interval <= 0:
        print("--interval must be greater than zero.", file=sys.stderr)
        return 2

    if args.window <= 0:
        print("--window must be greater than zero.", file=sys.stderr)
        return 2

    reader = GroveAdcReader(bus=args.bus)
    calibration = load_calibration(args.calibration)
    history = {channel: deque(maxlen=args.window) for channel in args.channels}
    csv_file, csv_writer = open_csv(args.csv, args.channels, calibration, args.water_temp_c)
    
    # Initialize dynamic temperature source
    temp_provider = TemperatureSource(
        air_water_offset_c=args.air_water_offset,
        manual_fallback_c=args.water_temp_c
    )
    
    start_time = time.monotonic()

    print_header(args.channels, calibration, args.water_temp_c, args.temp_source)

    try:
        while True:
            timestamp = datetime.now().isoformat(timespec="seconds")
            row = [timestamp]

            for channel in args.channels:
                try:
                    raw_value = reader.read(channel)
                except Exception as exc:  # noqa: BLE001 - keep monitor alive with clear output
                    print(f"{timestamp} | A{channel}=ERROR: {exc}", file=sys.stderr)
                    raw_value = -1

                history[channel].append(raw_value)
                row.append(raw_value)

            # Get dynamic temperature reading
            temp_reading = None
            if args.temp_source != "none":
                temp_reading = temp_provider.get_temperature(args.temp_source)

            stats = [summarize(channel, history[channel]) for channel in args.channels]
            print_status(stats, calibration, temp_reading)

            if calibration is not None and calibration.channel in args.channels:
                current_raw = history[calibration.channel][-1]
                row.append(calibration.convert_actual(current_raw))
                if temp_reading is not None:
                    row.append(calibration.convert_to_reference_temperature(current_raw, temp_reading.value_c))

            if csv_writer is not None and csv_file is not None:
                csv_writer.writerow(row)
                csv_file.flush()

            if args.duration > 0 and time.monotonic() - start_time >= args.duration:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        if csv_file is not None:
            csv_file.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
