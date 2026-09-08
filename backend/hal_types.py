"""Hardware Abstraction Layer Type Definitions
Defines pin mapping interfaces and motor driver runtime contracts.
"""
from typing import NamedTuple

class PumpPinMapping(NamedTuple):
    in1: int
    in2: int
    pump_id: int
    name: str
