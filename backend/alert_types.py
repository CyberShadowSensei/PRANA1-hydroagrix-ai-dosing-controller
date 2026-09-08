"""Alert & Notification Type Definitions
Defines alert severity levels and notification dispatch payloads.
"""
from enum import Enum

class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    DANGER = "DANGER"
    RECOVERY = "RECOVERY"
