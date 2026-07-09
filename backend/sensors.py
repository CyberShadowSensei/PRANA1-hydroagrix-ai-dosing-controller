import os
import time
import json
from datetime import datetime
from collections import deque
import pytz
import hal
from config import app, db
from checkSensorMail import SensorMonitor
from models import EventLog

sensor_monitor = SensorMonitor()

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
        print(f"DEBUG: Error logging event {event_id}: {e}")

def get_water_temp():
    fallback_temp = 25.0
    if live_th_data:
        latest_th = live_th_data[-1]
        if latest_th.get("status") == "OK" and latest_th.get("t") is not None:
            fallback_temp = float(latest_th["t"])
    return hal.get_water_temp(fallback_temp)

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
        
    return max(-2.0, min(14.0, final_ph))

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
    if w_t is None: w_t = get_water_temp()
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
    live_ph_data.append({
        "value": v,
        "status": status,
        "water_temp": w_t,
        "air_temp": a_t,
        "time": datetime.now(pytz.timezone('Asia/Kolkata'))
    })
    return {"ph_value": v, "status": status}

def fetch_tds(w_t=None):
    if w_t is None: w_t = get_water_temp()
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
    
    a_t = live_th_data[-1]["t"] if (live_th_data and live_th_data[-1]["status"] == "OK") else 25.0
    live_tds_data.append({
        "value": v,
        "status": status,
        "water_temp": w_t,
        "air_temp": a_t,
        "time": datetime.now(pytz.timezone('Asia/Kolkata'))
    })
    return {"tds_value": v, "status": status}

def fetch_th():
    humi, t, status = hal.get_climate()
    live_th_data.append({
        "t": t, 
        "h": humi, 
        "status": status, 
        "time": datetime.now(pytz.timezone('Asia/Kolkata'))
    })
    return {"temperature": t, "humidity": humi, "status": status}
