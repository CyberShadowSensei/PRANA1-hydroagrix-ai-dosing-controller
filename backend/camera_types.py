"""Computer Vision & Stage Detection Type Definitions
Defines frame capture payloads and growth stage classification records.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class StageDetectionResult:
    stage_name: str
    confidence: float
    canopy_coverage_pct: float
    timestamp: float
