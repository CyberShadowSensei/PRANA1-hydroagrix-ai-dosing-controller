"""Reporting & Digest Type Definitions
Defines report metadata structures and CSV aggregation schemas.
"""
from dataclasses import dataclass
from typing import List

@dataclass
class DigestSummary:
    avg_ph: float
    avg_ec: float
    avg_water_temp: float
    total_doses: int
