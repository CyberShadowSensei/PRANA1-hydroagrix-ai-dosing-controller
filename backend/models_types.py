"""Database Schema Type Aliases & Helper Structures
Provides helper type conversions and dictionary converters for SQLAlchemy models.
"""
from typing import TypedDict, Optional

class TankDict(TypedDict):
    tank_id: int
    name: str
    capacity_ml: float
    current_volume_ml: float
    last_alert_sent: float
