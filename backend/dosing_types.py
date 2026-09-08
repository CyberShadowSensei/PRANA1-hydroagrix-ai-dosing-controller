"""Dosing Engine Type Definitions & Enumerations
Provides explicit dataclasses and type definitions for chemical dosing operations.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class DosingPrediction:
    pre_val: float
    predicted_delta: float
    timestamp: float

@dataclass
class CrossTankLockStatus:
    is_locked: bool
    reason: Optional[str] = None
    affected_pumps: Optional[list] = None
