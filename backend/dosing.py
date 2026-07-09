import os
import time
import json
import threading
from config import app, db
import hal
from sensors import live_ph_data, live_tds_data, sensor_monitor, log_event
from models import SensorLimits, PlantStageStatus, PumpLog

last_dosing_time = 0

def log_pump_action(pump_id, duration, trigger_type):
    names = {1: "Pump 1 (Nutrients A)", 2: "Pump 2 (Nutrients B)", 3: "Pump 3 (pH UP)", 4: "Pump 4 (pH DOWN)"}
    name = names.get(pump_id, f"Pump {pump_id}")
    try:
        with app.app_context():
            db.session.add(PumpLog(pump_name=name, duration=duration, trigger_type=trigger_type))
            db.session.commit()
    except Exception as e:
        print(f"Error logging pump action: {e}")

def auto_stop_pump(p_num, duration):
    time.sleep(duration)
    hal.pump_stop(p_num)

def _async_dosing(ph_val, tds_val, l_ph, l_tds):
    try:
        config_path = "system_config.json"
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
        
        volume_l = float(config.get("reservoir_volume_l", 10.0))
        max_dose_s = float(config.get("max_dose_time_sec", 30.0))
        mixing_time_s = float(config.get("mixing_time_sec", 10.0))
        
        flow_rate_1 = float(config.get("pumps", {}).get("1", {}).get("flow_rate_ml_per_sec", 0.6167))
        flow_rate_2 = float(config.get("pumps", {}).get("2", {}).get("flow_rate_ml_per_sec", 0.6167))
        flow_rate_3 = float(config.get("pumps", {}).get("3", {}).get("flow_rate_ml_per_sec", 0.6167))
        flow_rate_4 = float(config.get("pumps", {}).get("4", {}).get("flow_rate_ml_per_sec", 0.6167))

        EC_STOCK_FACTOR = 10.0 
        PH_STOCK_FACTOR = 2.0 
        
        with hal.pump_lock:
            if l_tds and l_tds.is_active:
                if tds_val < l_tds.min_value:
                    target_tds = (l_tds.min_value + l_tds.max_value) / 2.0
                    delta = target_tds - tds_val
                    ml_needed = delta * volume_l * EC_STOCK_FACTOR
                    
                    dose_time_1 = min(ml_needed / flow_rate_1, max_dose_s)
                    dose_time_1 = max(1.0, round(dose_time_1, 1))
                    
                    dose_time_2 = min(ml_needed / flow_rate_2, max_dose_s)
                    dose_time_2 = max(1.0, round(dose_time_2, 1))
                    
                    log_event(
                        "DOSING_STARTED_EC",
                        "DOSING",
                        f"EC dosing started: current EC={tds_val} mS/cm below min={l_tds.min_value} mS/cm. Targeting midpoint={target_tds:.2f} mS/cm.",
                        {
                            "current_ec": tds_val,
                            "target_ec": target_tds,
                            "pump_1_sec": dose_time_1,
                            "pump_2_sec": dose_time_2
                        }
                    )
                    
                    print(f"DEBUG DOSING: Proportional EC dose targeting midpoint={target_tds:.2f}: Delta={delta:.2f}, Volume={volume_l}L -> needed {ml_needed:.1f}ml. Running Pump 1 for {dose_time_1}s and Pump 2 for {dose_time_2}s (mixing: {mixing_time_s}s)")
                    log_pump_action(1, dose_time_1, "Automatic")
                    hal.pump_start(1); time.sleep(dose_time_1); hal.pump_stop(1)
                    
                    time.sleep(mixing_time_s)
                    
                    log_pump_action(2, dose_time_2, "Automatic")
                    hal.pump_start(2); time.sleep(dose_time_2); hal.pump_stop(2)
                elif tds_val > l_tds.max_value:
                    log_event(
                        "EC_DANGER_ALARM",
                        "ALARM",
                        f"EC value {tds_val} mS/cm exceeds safety limit of {l_tds.max_value} mS/cm. Dosing halted.",
                        {
                            "current_ec": tds_val,
                            "max_limit": l_tds.max_value
                        }
                    )
                    print(f"DEBUG DOSING: EC {tds_val} is too high! Need manual dilution.")
                    sensor_monitor.send_email_alert("tds", f"EC is {tds_val} mS/cm, exceeding max limit of {l_tds.max_value}. Please manually dilute reservoir.", "DANGER")
                    
            if l_ph and l_ph.is_active:
                target_ph = (l_ph.min_value + l_ph.max_value) / 2.0
                if ph_val < l_ph.min_value:
                    delta = target_ph - ph_val
                    ml_needed = delta * volume_l * PH_STOCK_FACTOR
                    dose_time = min(ml_needed / flow_rate_3, max_dose_s)
                    dose_time = max(1.0, round(dose_time, 1))
                    
                    log_event(
                        "DOSING_STARTED_PH_UP",
                        "DOSING",
                        f"pH UP dosing started: current pH={ph_val} below min={l_ph.min_value}. Targeting midpoint={target_ph:.2f}.",
                        {
                            "current_ph": ph_val,
                            "target_ph": target_ph,
                            "pump_id": 3,
                            "duration_sec": dose_time
                        }
                    )
                    
                    print(f"DEBUG DOSING: Proportional pH UP dose targeting midpoint={target_ph:.2f}: Delta={delta:.2f} -> {dose_time}s using flow rate {flow_rate_3} ml/s")
                    log_pump_action(3, dose_time, "Automatic")
                    hal.pump_start(3); time.sleep(dose_time); hal.pump_stop(3)
                elif ph_val > l_ph.max_value:
                    delta = ph_val - target_ph
                    ml_needed = delta * volume_l * PH_STOCK_FACTOR
                    dose_time = min(ml_needed / flow_rate_4, max_dose_s)
                    dose_time = max(1.0, round(dose_time, 1))
                    
                    log_event(
                        "DOSING_STARTED_PH_DOWN",
                        "DOSING",
                        f"pH DOWN dosing started: current pH={ph_val} above max={l_ph.max_value}. Targeting midpoint={target_ph:.2f}.",
                        {
                            "current_ph": ph_val,
                            "target_ph": target_ph,
                            "pump_id": 4,
                            "duration_sec": dose_time
                        }
                    )
                    
                    print(f"DEBUG DOSING: Proportional pH DOWN dose targeting midpoint={target_ph:.2f}: Delta={delta:.2f} -> {dose_time}s using flow rate {flow_rate_4} ml/s")
                    log_pump_action(4, dose_time, "Automatic")
                    hal.pump_start(4); time.sleep(dose_time); hal.pump_stop(4)
                
    except Exception as e:
        print(f"DEBUG DOSING: Error in async dosing: {e}")

def check_and_adjust_sensors():
    global last_dosing_time
    if time.time() - last_dosing_time < 300:
        print("DEBUG DOSING: Skipped - 5min cooldown active")
        return
    
    with app.app_context():
        status_rec = PlantStageStatus.query.first()
        if not status_rec or not status_rec.state:
            print(f"DEBUG DOSING: Skipped - Auto mode OFF (state={status_rec.state if status_rec else 'None'})")
            return
        
        if not live_ph_data or not live_tds_data:
            print(f"DEBUG DOSING: Skipped - No buffer data (ph={len(live_ph_data)}, tds={len(live_tds_data)})")
            return
            
        system_fault = any(state.get('is_faulted', False) for state in sensor_monitor.sensor_states.values())
        if system_fault:
            log_event(
                "SYSTEM_FAULT_ABORT",
                "ALARM",
                "Dosing cycle aborted: system is locked in a danger fault state.",
                {"faulted_sensors": [s for s, state in sensor_monitor.sensor_states.items() if state.get('is_faulted')]}
            )
            print("ALERT: System is in DANGER FAULT state! Hardware dosing disabled. Asserting GPIO LOW.")
            hal.emergency_stop_all()
            return
            
        ph_val = live_ph_data[-1]["value"]
        tds_val = live_tds_data[-1]["value"]
        
        if live_ph_data[-1]["status"] == "ERROR" or live_tds_data[-1]["status"] == "ERROR":
            ph_status = live_ph_data[-1]['status']
            tds_status = live_tds_data[-1]['status']
            log_event(
                "SENSOR_FAULT_ABORT",
                "SENSORS",
                f"Dosing cycle aborted due to sensor communication error (pH: {ph_status}, EC: {tds_status}).",
                {"ph_status": ph_status, "tds_status": tds_status}
            )
            print(f"ALERT: Sensor Error! Dosing aborted. (ph_status={ph_status}, tds_status={tds_status})")
            hal.emergency_stop_all()
            return

        l_ph = SensorLimits.query.filter_by(sensor_type="ph").first()
        l_tds = SensorLimits.query.filter_by(sensor_type="tds").first()
        
        print(f"DEBUG DOSING: pH={ph_val}, EC={tds_val}, limits_tds={l_tds.min_value if l_tds else 'None'}-{l_tds.max_value if l_tds else 'None'} active={l_tds.is_active if l_tds else 'None'}")
        
        needs_dosing = False
        if l_ph and l_ph.is_active and (ph_val < l_ph.min_value or ph_val > l_ph.max_value): needs_dosing = True
        if l_tds and l_tds.is_active and (tds_val < l_tds.min_value or tds_val > l_tds.max_value): needs_dosing = True
        
        if needs_dosing:
            print(f"DEBUG DOSING: >>> STARTING DOSING CYCLE (pH={ph_val}, EC={tds_val})")
            last_dosing_time = time.time()
            threading.Thread(target=_async_dosing, args=(ph_val, tds_val, l_ph, l_tds), daemon=True).start()
        else:
            print(f"DEBUG DOSING: No dosing needed - values within range")
