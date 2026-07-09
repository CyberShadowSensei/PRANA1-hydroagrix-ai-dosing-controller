#!/usr/bin/env python3
"""
Dynamic Temperature Fallback Source for EC/TDS compensation.

Responsibilities:
- Attempt to read DS18B20 via 1-Wire.
- Fall back to DHT22 via GPIO 5, applying the air-water offset.
- Fall back to manual static value.
- Fall back to 25.0 C default.
- Report the active source and classification with every reading.
"""

from __future__ import annotations

import glob
import logging
import time
from dataclasses import dataclass
from pathlib import Path

# Setup simple logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

@dataclass
class TemperatureReading:
    value_c: float
    source: str
    classification: str
    raw_air_temp_c: float | None = None
    offset_applied_c: float | None = None


class TemperatureSource:
    def __init__(
        self,
        ds18b20_path: str = "/sys/bus/w1/devices/28-*",
        dht22_pin: int = 5,
        air_water_offset_c: float = -2.0,
        manual_fallback_c: float | None = None,
    ):
        self.ds18b20_glob = ds18b20_path
        self.dht22_pin = dht22_pin
        self.air_water_offset_c = air_water_offset_c
        self.manual_fallback_c = manual_fallback_c
        self._last_source = None

        # TODO: Add alert/notification system integration
        # Future system should trigger an alert (e.g., email/SMS/UI warning) 
        # whenever a sensor malfunctions and the system drops to a lower-priority fallback.
        
    def _log_fallback(self, new_source: str, reason: str):
        if self._last_source != new_source:
            logger.warning(f"Temperature source fallback: {new_source} ({reason})")
            self._last_source = new_source

    def _read_ds18b20(self) -> float | None:
        try:
            device_folders = glob.glob(self.ds18b20_glob)
            if not device_folders:
                return None
            
            # Use the first found device directory (e.g. /sys/bus/w1/devices/28-xxxxxxxxxxxx)
            # and append the standard w1_slave filename to get the full readable path.
            device_file = Path(device_folders[0]) / "w1_slave"
            if not device_file.exists():
                return None
                
            lines = device_file.read_text().splitlines()
            if not lines or "YES" not in lines[0]:
                return None
                
            # Second line contains t=
            temp_string = lines[1].split("t=")[-1]
            if not temp_string:
                return None
                
            temp_c = float(temp_string) / 1000.0
            
            # The sensor sometimes returns 85.0 when disconnected or failing
            if temp_c == 85.0:
                return None
                
            return temp_c
        except Exception:
            return None

    def _read_dht22(self) -> float | None:
        try:
            import adafruit_dht
            import board
            
            # Map integer pin to board pin (e.g. 5 -> board.D5)
            pin_attr = f"D{self.dht22_pin}"
            if not hasattr(board, pin_attr):
                logger.error(f"Board does not have pin {pin_attr}")
                return None
                
            board_pin = getattr(board, pin_attr)
            dht = adafruit_dht.DHT22(board_pin)
            
            # Try a few times since DHT sensors can occasionally throw RuntimeErrors
            for _ in range(3):
                try:
                    temp_c = dht.temperature
                    if temp_c is not None and -40 <= temp_c <= 80:
                        dht.exit()
                        return float(temp_c)
                except RuntimeError:
                    time.sleep(2.0)
                    continue
                except Exception:
                    break
                    
            dht.exit()
            return None
        except ImportError:
            # DHT library not installed or not working
            return None
        except Exception as e:
            logger.error(f"DHT22 read failed: {e}")
            return None

    def get_temperature(self, force_source: str | None = None) -> TemperatureReading:
        """
        Get the best available temperature reading.
        force_source: 'auto' (default), 'ds18b20', 'dht22', 'manual', 'none'
        """
        
        # 1. Try DS18B20 (Water)
        if force_source in (None, 'auto', 'ds18b20'):
            water_temp = self._read_ds18b20()
            if water_temp is not None:
                self._log_fallback("ds18b20", "Primary sensor active")
                return TemperatureReading(
                    value_c=water_temp,
                    source="ds18b20",
                    classification="Verified"
                )
            if force_source == 'ds18b20':
                logger.error("Forced DS18B20 but sensor failed to read.")

        # 2. Try DHT22 (Air + Offset)
        if force_source in (None, 'auto', 'dht22'):
            air_temp = self._read_dht22()
            if air_temp is not None:
                self._log_fallback("dht22_estimated", "DS18B20 failed, using air temp")
                estimated_water = air_temp + self.air_water_offset_c
                return TemperatureReading(
                    value_c=estimated_water,
                    source="dht22",
                    classification="Estimated",
                    raw_air_temp_c=air_temp,
                    offset_applied_c=self.air_water_offset_c
                )
            if force_source == 'dht22':
                logger.error("Forced DHT22 but sensor failed to read.")

        # 3. Try Manual Fallback
        if force_source in (None, 'auto', 'manual') and self.manual_fallback_c is not None:
            self._log_fallback("manual", "Using manual fallback")
            return TemperatureReading(
                value_c=self.manual_fallback_c,
                source="manual",
                classification="Manual"
            )

        # 4. Default 25.0 C
        self._log_fallback("default_25c", "All sensors failed, using default")
        return TemperatureReading(
            value_c=25.0,
            source="default_25c",
            classification="Assumed"
        )
