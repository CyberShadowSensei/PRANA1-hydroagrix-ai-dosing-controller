"""REST API Request & Response Schema Type Definitions
Type annotations for dosing configuration, plant preset payloads, and calibration requests.
"""
from typing import TypedDict, Optional

class DosingConfigPayload(TypedDict, total=False):
    reservoir_volume_l: float
    pump_flow_rate_ml_per_min: float
    pump_flow_rate_ml_per_sec: float
