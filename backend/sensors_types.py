"""Sensors Engine Type Definitions & Data Structures
Defines telemetry packet models and circulation detection state structures.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class TelemetryReading:
    value: Optional[float]
    status: str
    timestamp: float
    is_drain_cycle: bool = False
