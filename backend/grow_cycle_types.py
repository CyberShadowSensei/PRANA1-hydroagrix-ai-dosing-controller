"""Grow Cycle Progression Types & Phase Models
Defines phase transition limits and grow cycle status objects.
"""
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class PhaseLimits:
    min_ph: float
    max_ph: float
    min_ec: float
    max_ec: float
