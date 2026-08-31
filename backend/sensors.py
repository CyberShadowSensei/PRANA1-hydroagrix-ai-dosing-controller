import os
import time
import json
import threading
from datetime import datetime
from collections import deque
import pytz
import hal
from config import app, db
from checkSensorMail import SensorMonitor
from models import EventLog

sensor_monitor = SensorMonitor()

# Cache the IST timezone once at module level instead of constructing it
# on every sensor read (6 times/second = 518,400 constructions/day).
IST = pytz.timezone('Asia/Kolkata')


class CirculationPlateauTracker:
    """
    Tracks flood-and-drain / circulation cycles to distinguish probe dry exposure from genuine solution changes.
    
    CRITICAL CONSTRAINT:
    Periodic plateau-holding activates ONLY when the system mathematically confirms a recurring
    interval pattern (at least 2 consecutive cyclical transitions with consistent drain duration and return EC).
    
    States:
    - "STATIC": Standard reservoir / DWC mode (no periodic cycles detected).
    - "DETECTING_PATTERN": One cycle observed; awaiting second cycle confirmation.
    - "CONFIRMED_PERIODIC": Recurring pump circulation verified (e.g. 20m drain / 10m flood).
    - "RETURN_TIMEOUT_FAULT": Sensor remained dry beyond expected interval (>35 mins / pump fault).
    """
    def __init__(self, drop_delta=0.6, settle_ticks=20, ro_steady_ticks=600, max_drain_timeout_sec=2100):
        self.drop_delta = drop_delta
        self.settle_ticks = settle_ticks
        self.ro_steady_ticks = ro_steady_ticks
        self.max_drain_timeout_sec = max_drain_timeout_sec  # 35 minutes default timeout
        
        self.plateau_ec = None
        self.is_drain_cycle = False
        self.is_stable_plateau = False
        self.pattern_status = "STATIC"  # "STATIC" | "DETECTING_PATTERN" | "CONFIRMED_PERIODIC" | "RETURN_TIMEOUT_FAULT"
        self.settle_counter = 0
        self.low_steady_counter = 0
        self.last_raw_ec = None
        self.drain_start_time = None
        self.submerged_start_time = None
        self.completed_cycles = deque(maxlen=10)
        self._lock = threading.Lock()

    def _evaluate_pattern_confirmation(self):
        """Verifies if recorded cycles demonstrate consistent periodic pump intervals."""
        if len(self.completed_cycles) < 2:
            self.pattern_status = "DETECTING_PATTERN" if len(self.completed_cycles) == 1 else "STATIC"
            return

        # Inspect last 2 completed cycles
        c1 = self.completed_cycles[-1]
        c2 = self.completed_cycles[-2]
        d1 = c1.get("drain_duration", 0)
        d2 = c2.get("drain_duration", 0)

        # Realistic hydroponic drain interval range (3 min to 45 min)
        if 180 <= d1 <= 2700 and 180 <= d2 <= 2700:
            variance = abs(d1 - d2) / max(d1, d2)
            # Within 35% timing variance and reasonable return EC fidelity
            if variance <= 0.35:
                self.pattern_status = "CONFIRMED_PERIODIC"
                return

        self.pattern_status = "DETECTING_PATTERN"

    def process_reading(self, raw_ec, status="OK"):
        with self._lock:
            now_t = time.time()
            if status != "OK" or raw_ec is None or raw_ec <= 0.0:
                return {
                    "value": raw_ec,
                    "effective_value": self.plateau_ec if (self.plateau_ec is not None and self.pattern_status == "CONFIRMED_PERIODIC") else raw_ec,
                    "is_drain_cycle": self.is_drain_cycle,
                    "is_stable_plateau": False,
                    "pattern_status": self.pattern_status,
                    "status": status
                }

            # Initialize plateau if first reading
            if self.plateau_ec is None:
                self.plateau_ec = raw_ec
                self.is_drain_cycle = False
                self.is_stable_plateau = True
                self.settle_counter = self.settle_ticks
                self.submerged_start_time = now_t
                return {
                    "value": raw_ec,
                    "effective_value": raw_ec,
                    "is_drain_cycle": False,
                    "is_stable_plateau": True,
                    "pattern_status": self.pattern_status,
                    "status": "OK"
                }

            # 1. Dropped significantly below plateau (Drain Phase / Air exposure)
            if raw_ec < (self.plateau_ec - self.drop_delta):
                if not self.is_drain_cycle:
                    self.is_drain_cycle = True
                    self.drain_start_time = now_t
                self.is_stable_plateau = False
                self.settle_counter = 0

                # Check for Drain Return Timeout Fault (>35 minutes without return)
                drain_elapsed = (now_t - self.drain_start_time) if self.drain_start_time else 0
                if drain_elapsed >= self.max_drain_timeout_sec:
                    self.pattern_status = "RETURN_TIMEOUT_FAULT"

                # Check for Fresh RO water fill: count consecutive steady ticks (variance < 0.05)
                if self.last_raw_ec is not None and abs(raw_ec - self.last_raw_ec) < 0.05:
                    self.low_steady_counter += 1
                else:
                    self.low_steady_counter = 1

                self.last_raw_ec = raw_ec

                # If steady low for ro_steady_ticks, grower filled fresh RO water
                if self.low_steady_counter >= self.ro_steady_ticks:
                    self.plateau_ec = raw_ec
                    self.is_drain_cycle = False
                    self.is_stable_plateau = True
                    self.settle_counter = self.settle_ticks
                    self.low_steady_counter = 0
                    self.drain_start_time = None
                    self.submerged_start_time = now_t
                    self.pattern_status = "STATIC"
                    return {
                        "value": raw_ec,
                        "effective_value": raw_ec,
                        "is_drain_cycle": False,
                        "is_stable_plateau": True,
                        "pattern_status": self.pattern_status,
                        "status": "OK"
                    }

                effective_val = self.plateau_ec if self.pattern_status == "CONFIRMED_PERIODIC" else raw_ec
                return {
                    "value": raw_ec,
                    "effective_value": effective_val,
                    "is_drain_cycle": True,
                    "is_stable_plateau": False,
                    "pattern_status": self.pattern_status,
                    "status": "DRAIN_CYCLE" if self.pattern_status == "CONFIRMED_PERIODIC" else "LOW_EC_ALERT"
                }

            # 2. Reading is near or above plateau (water present/returning)
            self.low_steady_counter = 0
            if self.is_drain_cycle:
                # Water returned, but must settle for settle_ticks before leaving drain state
                self.settle_counter += 1
                if self.settle_counter >= self.settle_ticks:
                    self.is_drain_cycle = False
                    self.is_stable_plateau = True
                    
                    drain_duration = (now_t - self.drain_start_time) if self.drain_start_time else 0
                    self.drain_start_time = None
                    self.submerged_start_time = now_t
                    
                    # Record completed cycle
                    if drain_duration > 0:
                        self.completed_cycles.append({
                            "drain_duration": drain_duration,
                            "return_ec": raw_ec,
                            "plateau_ec": self.plateau_ec,
                            "timestamp": now_t
                        })
                        self._evaluate_pattern_confirmation()

                    if raw_ec > self.plateau_ec:
                        self.plateau_ec = raw_ec
                    else:
                        self.plateau_ec = round(self.plateau_ec * 0.7 + raw_ec * 0.3, 2)
            else:
                self.is_stable_plateau = True
                if raw_ec > self.plateau_ec:
                    self.plateau_ec = raw_ec
                else:
                    self.plateau_ec = round(self.plateau_ec * 0.95 + raw_ec * 0.05, 2)

            self.last_raw_ec = raw_ec
            effective_val = self.plateau_ec if (self.is_drain_cycle and self.pattern_status == "CONFIRMED_PERIODIC") else raw_ec
            return {
                "value": raw_ec,
                "effective_value": effective_val,
                "is_drain_cycle": self.is_drain_cycle,
                "is_stable_plateau": self.is_stable_plateau,
                "pattern_status": self.pattern_status,
                "status": "DRAIN_CYCLE" if (self.is_drain_cycle and self.pattern_status == "CONFIRMED_PERIODIC") else "OK"
            }

    def get_metrics(self):
        with self._lock:
            avg_drain = 0
            if self.completed_cycles:
                avg_drain = sum(c["drain_duration"] for c in self.completed_cycles) / len(self.completed_cycles)
            return {
                "plateau_ec": self.plateau_ec,
                "is_drain_cycle": self.is_drain_cycle,
                "is_stable_plateau": self.is_stable_plateau,
                "pattern_status": self.pattern_status,
                "completed_cycle_count": len(self.completed_cycles),
                "average_drain_duration_sec": round(avg_drain, 1),
                "settle_counter": self.settle_counter,
                "settle_ticks_required": self.settle_ticks,
                "low_steady_counter": self.low_steady_counter,
                "ro_steady_ticks_required": self.ro_steady_ticks,
                "last_raw_ec": self.last_raw_ec,
                "drain_start_time": self.drain_start_time
            }

    def reset(self):
        with self._lock:
            self.plateau_ec = None
            self.is_drain_cycle = False
            self.is_stable_plateau = False
            self.pattern_status = "STATIC"
            self.settle_counter = 0
            self.low_steady_counter = 0
            self.last_raw_ec = None
            self.drain_start_time = None
            self.submerged_start_time = None
            self.completed_cycles.clear()


circulation_tracker = CirculationPlateauTracker()

# --- LIVE MEMORY BUFFERS ---
live_ph_data = deque(maxlen=60)
live_tds_data = deque(maxlen=60)
live_th_data = deque(maxlen=60)


def log_event(event_id, category, message, details=None):
    try:
        with app.app_context():
            details_str = json.dumps(details) if details else None
            db.session.add(EventLog(
                event_id=event_id,
                category=category,
                message=message,
                details_json=details_str
            ))
            db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"DEBUG: Error logging event {event_id}: {e}")

def get_water_temp():
    fallback_temp = 25.0
    air_temp = 25.0
    if live_th_data:
        latest_th = live_th_data[-1]
        if latest_th.get("status") == "OK" and latest_th.get("t") is not None:
            air_temp = float(latest_th["t"])
            fallback_temp = air_temp
            
    raw_temp = hal.get_water_temp(fallback_temp)
    if raw_temp == fallback_temp:
        estimated_temp = round(max(15.0, min(35.0, air_temp - 2.0)), 1)
        return estimated_temp, True
    return raw_temp, False

def load_calibration(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"DEBUG: Failed to load calibration {path}: {e}")
        return None

# Load Calibrations
PH_CALIBRATION = load_calibration(os.path.join("..", "tools", "config", "ph_calibration.json"))
EC_CALIBRATION = load_calibration(os.path.join("..", "tools", "config", "ec_calibration.json"))

def apply_ph_calibration(raw_val, water_temp):
    if not PH_CALIBRATION:
        if raw_val >= 424.67: # Acidic to Neutral
            slope = (7.00 - 4.00) / (424.67 - 610.30)
            uncompensated = 7.00 + slope * (raw_val - 424.67)
        else: # Neutral to Alkaline
            slope = (10.01 - 7.00) / (318.87 - 424.67)
            uncompensated = 7.00 + slope * (raw_val - 424.67)
        return max(0.0, min(14.0, uncompensated))
        
    segments = PH_CALIBRATION.get("segments", [])
    neutral_raw = PH_CALIBRATION.get("neutral_raw", 424.67)
    neutral_ph = PH_CALIBRATION.get("neutral_ph", 7.0)
    cal_temp = PH_CALIBRATION.get("calibration_temperature_c", 25.0)
    
    segment = segments[0] if segments else {"slope": -0.016, "offset": 13.8}
    for s in segments:
        if s.get("region") == "acidic" and raw_val >= neutral_raw:
            segment = s
        elif s.get("region") == "alkaline" and raw_val < neutral_raw:
            segment = s

    uncompensated_ph = (segment["slope"] * raw_val) + segment["offset"]
    
    if water_temp is None:
        final_ph = uncompensated_ph
    else:
        t_cal_k = cal_temp + 273.15
        t_meas_k = water_temp + 273.15
        final_ph = neutral_ph + (uncompensated_ph - neutral_ph) * (t_cal_k / t_meas_k)
        
    return max(0.0, min(14.0, final_ph))


def apply_ec_calibration(raw_val, water_temp):
    if not EC_CALIBRATION:
        return 0.0
    segments = EC_CALIBRATION.get("segments", [])
    cal_temp = EC_CALIBRATION.get("reference_temperature_c", 25.0)
    temp_coeff = EC_CALIBRATION.get("temp_coefficient_percent_per_c", 2.0) / 100.0
    
    segment = segments[0] if segments else {"slope": 0, "offset": 0}
    for candidate in segments:
        if candidate.get("raw_min", 0) <= raw_val <= candidate.get("raw_max", 4095):
            segment = candidate
            break
        if raw_val > candidate.get("raw_max", 4095):
            segment = candidate
            
    actual_ec = (segment["slope"] * raw_val) + segment["offset"]
    
    if water_temp is None:
        return max(0.0, actual_ec)
    correction_factor = 1.0 + temp_coeff * (water_temp - cal_temp)
    if correction_factor <= 0:
        return max(0.0, actual_ec)
    return max(0.0, actual_ec / correction_factor)

def fetch_ph(w_t=None):
    is_estimated = False
    if w_t is None: 
        w_t, is_estimated = get_water_temp()
    try:
        raw_ph = hal.get_stable_reading(hal.PH_CHANNEL)
        if raw_ph is None or raw_ph <= 0 or raw_ph > 4080:
            print(f"DEBUG: pH sensor error or unplugged! raw_ph={raw_ph}")
            v, status = 0.0, "ERROR"
        else:
            v = round(apply_ph_calibration(raw_ph, w_t), 2)
            status = "OK"
    except Exception as e: 
        print(f"DEBUG: Exception in get_ph: {e}")
        v, status = 0.0, "ERROR"
    
    a_t = live_th_data[-1]["t"] if (live_th_data and live_th_data[-1]["status"] == "OK") else 25.0
    is_drain = circulation_tracker.is_drain_cycle
    live_ph_data.append({
        "value": v,
        "status": "DRAIN_CYCLE" if (is_drain and status == "OK") else status,
        "is_drain_cycle": is_drain,
        "water_temp": w_t,
        "is_water_temp_estimated": is_estimated,
        "air_temp": a_t,
        "time": datetime.now(IST)
    })
    return {"ph_value": v, "status": status, "is_drain_cycle": is_drain}

def fetch_tds(w_t=None):
    is_estimated = False
    if w_t is None: 
        w_t, is_estimated = get_water_temp()
    try:
        raw_ec = hal.get_stable_reading(hal.EC_CHANNEL)
        # Reject raw reads that signify an unplugged sensor or floating bus
        if raw_ec is None or raw_ec <= 0 or raw_ec > 4080:
            v, status = 0.0, "ERROR"
        else:
            v = round(apply_ec_calibration(raw_ec, w_t), 2)
            status = "OK"
    except Exception as e: 
        print(f"DEBUG: Exception in get_tds: {e}")
        v, status = 0.0, "ERROR"
    
    res = circulation_tracker.process_reading(v, status)
    a_t = live_th_data[-1]["t"] if (live_th_data and live_th_data[-1]["status"] == "OK") else 25.0
    live_tds_data.append({
        "value": res["value"],
        "effective_value": res["effective_value"],
        "is_drain_cycle": res["is_drain_cycle"],
        "is_stable_plateau": res["is_stable_plateau"],
        "status": res["status"],
        "water_temp": w_t,
        "is_water_temp_estimated": is_estimated,
        "air_temp": a_t,
        "time": datetime.now(IST)
    })
    return {
        "tds_value": res["value"],
        "effective_tds": res["effective_value"],
        "is_drain_cycle": res["is_drain_cycle"],
        "is_stable_plateau": res["is_stable_plateau"],
        "pattern_status": res.get("pattern_status", "STATIC"),
        "status": res["status"]
    }

def fetch_th():
    humi, t, status = hal.get_climate()
    if not live_th_data or live_th_data[-1]["t"] != t or live_th_data[-1]["h"] != humi or live_th_data[-1]["status"] != status:
        live_th_data.append({
            "t": t, 
            "h": humi, 
            "status": status, 
            "time": datetime.now(IST)
        })
    return {"temperature": t, "humidity": humi, "status": status}


