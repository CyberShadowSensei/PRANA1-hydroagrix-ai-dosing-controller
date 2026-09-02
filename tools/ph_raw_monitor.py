"""Realtime Raw pH Monitoring Utility
Streams raw ADC voltages, trimmed means, and calibrated pH values for bench testing.
"""
#!/usr/bin/env python3
"""
Raw pH sensor monitor for Grove Base HAT analog inputs.

Purpose:
    - Read raw ADC values only.
    - Observe real-time responsiveness and stability before calibration.
    - View live compensated pH readings once calibration is performed.
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


PH_CHANNEL = 2
DEFAULT_CHANNELS = [PH_CHANNEL]


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
class PhCalibration:
    channel: int
    method: str
    segments: list[dict[str, float]]
    units: str
    calibration_temperature_c: float | None
    neutral_raw: float | None
    neutral_ph: float

    def convert_uncompensated(self, raw_value: int) -> float:
        segment = self.segments[0]
        # Find segment: in piecewise pH, we have acidic and alkaline.
        # But for generic fallback we just iterate and use the appropriate one.
        # We look if we have raw_min / raw_max like EC, or just use acidic/alkaline logic.
        if "region" in segment:
            # New 3-point piecewise logic
            if self.neutral_raw is not None:
                acidic = next((s for s in self.segments if s["region"] == "acidic"), self.segments[0])
                alkaline = next((s for s in self.segments if s["region"] == "alkaline"), self.segments[-1])
                
                # We need to know if the sensor voltage goes up or down with pH to pick the right segment.
                # If acidic slope is positive (raw goes up as pH goes up), then acidic is raw < neutral_raw.
                # Just to be robust, we'll check the neutral_raw boundary.
                # Assuming standard polarity: higher pH = lower raw voltage.
                # If raw_value > neutral_raw, we are in the acidic region (since lower pH = higher raw).
                # But we can dynamically check:
                # If slope is negative (higher pH = lower raw):
                if acidic["slope"] < 0:
                    segment = acidic if raw_value >= self.neutral_raw else alkaline
                else:
                    segment = acidic if raw_value <= self.neutral_raw else alkaline
        else:
            # Fallback for simple linear
            for candidate in self.segments:
                if "raw_min" in candidate and candidate["raw_min"] <= raw_value <= candidate["raw_max"]:
                    segment = candidate
                    break

        return (segment["slope"] * raw_value) + segment["offset"]

    def convert_compensated(self, raw_value: int, water_temp_c: float | None) -> float:
        uncompensated_ph = self.convert_uncompensated(raw_value)
        if water_temp_c is None or self.calibration_temperature_c is None:
            return uncompensated_ph
        
        # Nernst Equation Compensation:
        # pH = 7.0 + (pH_uncompensated - 7.0) * (T_cal_K / T_meas_K)
        t_cal_k = self.calibration_temperature_c + 273.15
        t_meas_k = water_temp_c + 273.15
        
        return self.neutral_ph + (uncompensated_ph - self.neutral_ph) * (t_cal_k / t_meas_k)


class GroveAdcReader:
    """Small wrapper around grove.py's ADC class."""

    def __init__(self, bus: int = 1) -> None:
        try:
            import grove.i2c
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


def load_calibration(path: Path | None) -> PhCalibration | None:
    if path is None:
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        
        return PhCalibration(
            channel=int(data.get("ph_channel", PH_CHANNEL)),
            method=str(data.get("method", "unknown")),
            segments=data.get("segments", []),
            units=str(data.get("units", "pH")),
            calibration_temperature_c=data.get("calibration_temperature_c"),
            neutral_raw=data.get("neutral_raw"),
            neutral_ph=float(data.get("neutral_ph", 7.0)),
        )
    except Exception as e:
        print(f"Failed to load calibration file: {e}", file=sys.stderr)
        return None


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
        description="Monitor raw pH sensor ADC values on Grove Base HAT channels."
    )
    parser.add_argument(
        "--channels",
        type=parse_channels,
        default=DEFAULT_CHANNELS,
        help="Comma-separated ADC channels to read. Default: 2",
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
        help="Optional calibration JSON from ph_calibrate_three_point.py.",
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


def print_header(
    channels: list[int],
    calibration: PhCalibration | None,
    temp_source: str,
) -> None:
    channel_labels = " ".join(f"A{channel:>1}" for channel in channels)
    print("Raw pH sensor monitor")
    print("Classification: Experimental")
    print(f"Documented pH channel: A{PH_CHANNEL} / Channel {PH_CHANNEL}")
    print(f"Channels: {channel_labels}")
    if calibration is not None:
        print("Mode: raw ADC readings with calibrated pH display")
        print(
            "Calibration display enabled: "
            f"A{calibration.channel} -> {calibration.units}; "
            f"method={calibration.method}; "
        )
        if calibration.calibration_temperature_c is not None:
            print(
                "Nernst Temperature compensation enabled. "
                f"Calibrated at={calibration.calibration_temperature_c:.2f} C. "
                f"Source mode={temp_source}."
            )
        else:
            print("No calibration temperature recorded; uncompensated mode.")
    else:
        print("Mode: raw ADC readings only; no calibration applied")
    print("Press Ctrl+C to stop.")
    print()


def print_status(
    stats: list[ChannelStats],
    calibration: PhCalibration | None,
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
            uncompensated_ph = calibration.convert_uncompensated(item.current)
            channel_text += f" pH(uncomp):{uncompensated_ph:>5.2f}"
            
            if temp_reading is not None and calibration.calibration_temperature_c is not None:
                comp_ph = calibration.convert_compensated(item.current, temp_reading.value_c)
                channel_text += f" pH(comp):{comp_ph:>5.2f} (T={temp_reading.value_c:.1f}C {temp_reading.classification[:3]})"
        parts.append(channel_text)
    print(" | ".join(parts), flush=True)


def open_csv(
    path: Path | None,
    channels: list[int],
    calibration: PhCalibration | None,
):
    if path is None:
        return None, None

    path.parent.mkdir(parents=True, exist_ok=True)
    csv_file = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)

    if path.stat().st_size == 0:
        columns = ["timestamp", *[f"A{channel}_raw" for channel in channels]]
        if calibration is not None and calibration.channel in channels:
            columns.append(f"A{calibration.channel}_pH_uncomp")
            columns.append(f"A{calibration.channel}_pH_comp")
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
    csv_file, csv_writer = open_csv(args.csv, args.channels, calibration)
    
    # Initialize dynamic temperature source
    temp_provider = TemperatureSource(
        air_water_offset_c=args.air_water_offset,
        manual_fallback_c=args.water_temp_c
    )
    
    start_time = time.monotonic()

    print_header(args.channels, calibration, args.temp_source)

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
                uncomp_ph = calibration.convert_uncompensated(current_raw)
                row.append(uncomp_ph)
                
                if temp_reading is not None and calibration.calibration_temperature_c is not None:
                    comp_ph = calibration.convert_compensated(current_raw, temp_reading.value_c)
                    row.append(comp_ph)
                else:
                    row.append(uncomp_ph)

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
