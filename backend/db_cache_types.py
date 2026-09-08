"""Database Cache Type Definitions
Defines cached telemetry structures and LRU cache invalidation tokens.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class CachedSensorLimit:
    min_val: float
    max_val: float
    is_active: bool
