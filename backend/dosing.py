"""Adaptive Dosing Engine
Calculates chemical volumes, inter-dose cooldowns, emergency halts, and flow rate execution.
"""
import os
import time
import json
import threading
from config import app, db
import hal
from sensors import live_ph_data, live_tds_data, sensor_monitor, log_event
from models import SensorLimits, PlantStageStatus, PumpLog, PlantPreset

last_dosing_time = 0
last_error_alert_time = 0
is_priming_active = False
is_dosing_active = False
_last_ec_prediction = None
_last_ph_up_prediction = None
_last_ph_down_prediction = None
_ec_high_since = None
_ec_intervention_last_sent = None
_is_system_halt_alert_sent = False
_consecutive_halt_ticks = 0
MIN_PUMP_RUN_SEC = 2.0

EC_INTERVENTION_HOURS = 1
EC_RENOTIFY_HOURS = 4

def log_pump_action(pump_id, duration, trigger_type):
    names = {1: "Pump 1 (Nutrients A)", 2: "Pump 2 (Nutrients B)", 3: "Pump 3 (pH UP)", 4: "Pump 4 (pH DOWN)"}
    name = names.get(pump_id, f"Pump {pump_id}")
    try:
        with app.app_context():
            db.session.add(PumpLog(pump_name=name, duration=duration, trigger_type=trigger_type))
            
            from models import SolutionTanks
            config_path = "system_config.json"
            pump_flow_rate = 37.0 / 60.0
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                    p_flow = float(config.get("pump_flow_rate_ml_per_sec", 37.0 / 60.0))
                    pumps = config.get("pumps", {})
                    pump_config = pumps.get(str(pump_id), {})
                    pump_flow_rate = float(pump_config.get("flow_rate_ml_per_sec", p_flow))
            
            volume_used = duration * pump_flow_rate
            tank = SolutionTanks.query.filter_by(tank_id=pump_id).first()
            if tank:
                tank.current_volume_ml -= volume_used
                if tank.current_volume_ml < 0:
                    tank.current_volume_ml = 0.0

                # Alert: tank completely empty
                if tank.current_volume_ml == 0.0:
                    current_time = time.time()
                    # Setup initial backoff counters: 1st blocked warning will have a 1-hour delay
                    tank.consecutive_blocked_attempts = 1
                    tank.next_allowed_alert_time = current_time + 3600
                    
                    if current_time - tank.last_alert_sent > 3600:
                        # Dispatch email on a daemon thread — SMTP must NOT block the DB commit
                        _msg = f"Tank '{tank.name}' is EMPTY. Pump {pump_id} will be disabled until the tank is refilled. Please refill immediately."
                        threading.Thread(
                            target=sensor_monitor.send_email_alert,
                            args=("SYSTEM", _msg, "DANGER", True),
                            daemon=True
                        ).start()
                        tank.last_alert_sent = current_time
                # Alert: tank critically low (< 10%)
                elif tank.current_volume_ml < tank.capacity_ml * 0.1:
                    if time.time() - tank.last_alert_sent > 86400:
                        _msg = f"Tank '{tank.name}' is critically low ({tank.current_volume_ml:.1f} mL / {tank.capacity_ml:.0f} mL remaining). Please refill soon."
                        # Dispatch email on a daemon thread — SMTP must NOT block the DB commit
                        threading.Thread(
                            target=sensor_monitor.send_email_alert,
                            args=("SYSTEM", _msg, "DANGER"),
                            daemon=True
                        ).start()
                        tank.last_alert_sent = time.time()

            db.session.commit()
            
            try:
                from config import socketio
                socketio.emit('pump_activity', {
                    'pump_id': pump_id, 
                    'duration': duration, 
                    'trigger_type': trigger_type
                })
            except Exception as se:
                print(f"Error emitting pump_activity socket: {se}")
    except Exception as e:
        print(f"Error logging pump action: {e}")

def auto_stop_pump(p_num, duration):
    time.sleep(duration)
    hal.pump_stop(p_num)

cancel_dosing_flag = False

def request_dosing_cancellation():
    global cancel_dosing_flag
    cancel_dosing_flag = True

def _safe_pump_run(pump_id, duration_sec, stop_condition_fn=None):
    global cancel_dosing_flag
    cancel_dosing_flag = False
    early_stop_reason = None
    try:
        hal.pump_start(pump_id)
        step = 0.1
        elapsed = 0.0
        while elapsed < duration_sec:
            if cancel_dosing_flag:
                early_stop_reason = "Manual cancellation"
                break
            if stop_condition_fn:
                try:
                    should_stop, reason = stop_condition_fn()
                    if should_stop:
                        early_stop_reason = reason
                        break
                except Exception as e:
                    print(f"DEBUG: Error in stop_condition_fn for pump {pump_id}: {e}")
            sleep_time = min(step, duration_sec - elapsed)
            time.sleep(sleep_time)
            elapsed += sleep_time

        if early_stop_reason and early_stop_reason != "Manual cancellation":
            log_event(
                "MID_DOSE_TARGET_REACHED", "INFO",
                f"Pump {pump_id} stopped early at {elapsed:.1f}s / {duration_sec:.1f}s planned: {early_stop_reason}"
            )
            print(f"INFO: Mid-dose target cutoff triggered for pump {pump_id}: {early_stop_reason}")
    finally:
        try:
            hal.pump_stop(pump_id)
        except Exception as e:
            print(f"Safety halt failed for pump {pump_id}: {e}")

def check_tank_has_solution_permission(pump_id):
    """
    Checks if a solution tank is empty. If empty, blocks the pump from starting,
    increments consecutive blocked attempts, and sends email notifications with
    exponential backoff (incrementing delays: 0s, 1h, 4h, 12h, 24h).
    """
    try:
        from models import SolutionTanks
        # Delays in seconds: 0s, 1h, 4h, 12h, 24h
        BACKOFF_DELAYS = [0, 3600, 14400, 43200, 86400]
        
        with app.app_context():
            tank = SolutionTanks.query.filter_by(tank_id=pump_id).first()
            if tank is not None and tank.current_volume_ml <= 0:
                current_time = time.time()
                
                # Check delay backoff
                attempts = tank.consecutive_blocked_attempts or 0
                delay_idx = min(attempts, len(BACKOFF_DELAYS) - 1)
                delay = BACKOFF_DELAYS[delay_idx]
                
                log_event(
                    "PUMP_BLOCKED_EMPTY_TANK", "WARNING",
                    f"Pump {pump_id} start BLOCKED — tank '{tank.name}' is empty. Refill required."
                )
                
                next_allowed = tank.next_allowed_alert_time or 0.0
                if current_time >= next_allowed:
                    new_attempts = attempts + 1
                    tank.consecutive_blocked_attempts = new_attempts
                    
                    next_delay_idx = min(new_attempts, len(BACKOFF_DELAYS) - 1)
                    next_delay = BACKOFF_DELAYS[next_delay_idx]
                    tank.next_allowed_alert_time = current_time + next_delay
                    tank.last_alert_sent = current_time
                    db.session.commit()
                    
                    message = f"Tank '{tank.name}' (Pump {pump_id}) is EMPTY. The dosing controller blocked pump activation to prevent hardware damage. Please refill the tank immediately."
                    threading.Thread(
                        target=sensor_monitor.send_email_alert,
                        args=("SYSTEM", message, "DANGER", True),
                        daemon=True
                    ).start()
                    
                return False
    except Exception as e:
        print(f"DEBUG: Error checking tank solution permission: {e}")
    return True

def _async_dosing(ph_val, tds_val, l_ph, l_tds):
    global is_dosing_active, _last_ec_prediction, _last_ph_up_prediction, _last_ph_down_prediction
    try:
        config_path = "system_config.json"
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f: config = json.load(f)
            
        old_res_vol = config.get("reservoir_current_volume_liters", 50.0)
        reservoir_vol = float(config.get("reservoir_volume_l", old_res_vol))
        
        # 37 mL/min = 0.61667 mL/sec
        pump_flow_rate = float(config.get("pump_flow_rate_ml_per_sec", 37.0 / 60.0))
        pumps = config.get("pumps", {})
        flow_rate_1 = float(pumps.get("1", {}).get("flow_rate_ml_per_sec", pump_flow_rate))
        flow_rate_2 = float(pumps.get("2", {}).get("flow_rate_ml_per_sec", pump_flow_rate))
        flow_rate_3 = float(pumps.get("3", {}).get("flow_rate_ml_per_sec", pump_flow_rate))
        flow_rate_4 = float(pumps.get("4", {}).get("flow_rate_ml_per_sec", pump_flow_rate))
        nutrient_factor = float(config.get("nutrient_ml_per_l_per_ec", 2.0))
        ph_up_factor = float(config.get("ph_up_ml_per_l_per_ph", 0.5))
        ph_down_factor = float(config.get("ph_down_ml_per_l_per_ph", 0.5))
        absolute_ceiling = float(config.get("max_dose_time_sec", 300.0))
        nut_gap_s = float(config.get("nutrient_gap_seconds", 10.0))
        global MIN_PUMP_RUN_SEC
        MIN_PUMP_RUN_SEC = float(config.get("min_dose_time_sec", 2.0))

        if flow_rate_1 <= 0 or flow_rate_2 <= 0 or flow_rate_3 <= 0 or flow_rate_4 <= 0 or reservoir_vol <= 0:
            log_event("DOSING_GUARD_FAIL", "WARNING", f"Invalid parameters (flows={[flow_rate_1, flow_rate_2, flow_rate_3, flow_rate_4]}, vol={reservoir_vol}). Dosing aborted.")
            return

        MAX_EC_SHIFT = float(config.get("MAX_EC_SHIFT", 0.5))
        MAX_PH_SHIFT = float(config.get("MAX_PH_SHIFT", 0.5))
        max_dose_ec_1 = min((MAX_EC_SHIFT * reservoir_vol * nutrient_factor) / flow_rate_1, absolute_ceiling)
        max_dose_ec_2 = min((MAX_EC_SHIFT * reservoir_vol * nutrient_factor) / flow_rate_2, absolute_ceiling)
        max_dose_ph_up = min((MAX_PH_SHIFT * reservoir_vol * ph_up_factor) / flow_rate_3, absolute_ceiling)
        max_dose_ph_down = min((MAX_PH_SHIFT * reservoir_vol * ph_down_factor) / flow_rate_4, absolute_ceiling)

        def _tank_has_solution(pump_id):
            """Returns True if pump should run, checking the safety permission callback."""
            return check_tank_has_solution_permission(pump_id)

        with hal.pump_lock:
            # ================= EC Dosing =================
            if l_tds and l_tds.is_active and tds_val < l_tds.min_value:
                target_tds = (l_tds.min_value + l_tds.max_value) / 2.0
                delta_ec = target_tds - tds_val
                required_ml = delta_ec * reservoir_vol * nutrient_factor
                dose_time_1 = max(0.0, min(required_ml / flow_rate_1, max_dose_ec_1))
                if 0 < dose_time_1 < MIN_PUMP_RUN_SEC:
                    dose_time_1 = MIN_PUMP_RUN_SEC
                dose_time_2 = max(0.0, min(required_ml / flow_rate_2, max_dose_ec_2))
                if 0 < dose_time_2 < MIN_PUMP_RUN_SEC:
                    dose_time_2 = MIN_PUMP_RUN_SEC

                def _ec_stop_check():
                    if live_tds_data and live_tds_data[-1].get("status") == "OK":
                        current = live_tds_data[-1].get("value")
                        if current is not None and current >= target_tds:
                            return True, f"EC reached target {target_tds:.2f} (current: {current:.2f})"
                    return False, None

                if dose_time_1 > 0 or dose_time_2 > 0:
                    # Pump 1 (Nutrient A)
                    if dose_time_1 > 0 and _tank_has_solution(1):
                        log_event("PUMP_ACTIVATION", "INFO", f"Dosed Nutrient A for {dose_time_1:.2f}s (Delta: {delta_ec:.2f} EC)")
                        log_pump_action(1, dose_time_1, "Automatic")
                        _safe_pump_run(1, dose_time_1, stop_condition_fn=_ec_stop_check)
                        _last_ec_prediction = {'pre_val': tds_val, 'predicted_delta': delta_ec, 'time': time.time()}
                        time.sleep(nut_gap_s)
                    # Pump 2 (Nutrient B) — checked independently
                    if dose_time_2 > 0 and _tank_has_solution(2):
                        log_event("PUMP_ACTIVATION", "INFO", f"Dosed Nutrient B for {dose_time_2:.2f}s")
                        log_pump_action(2, dose_time_2, "Automatic")
                        _safe_pump_run(2, dose_time_2, stop_condition_fn=_ec_stop_check)
            elif l_tds and l_tds.is_active and tds_val > l_tds.max_value:
                log_event("EC_DANGER_ALARM", "ALARM", f"EC value {tds_val} exceeds limit {l_tds.max_value}. Dosing halted.", {"current_ec": tds_val})

            # ================= pH Dosing =================
            if l_ph and l_ph.is_active:
                target_ph = (l_ph.min_value + l_ph.max_value) / 2.0
                if ph_val < l_ph.min_value:
                    delta_ph = target_ph - ph_val
                    required_ml = delta_ph * reservoir_vol * ph_up_factor
                    dose_time_3 = max(0.0, min(required_ml / flow_rate_3, max_dose_ph_up))
                    if 0 < dose_time_3 < MIN_PUMP_RUN_SEC:
                        dose_time_3 = MIN_PUMP_RUN_SEC

                    def _ph_up_stop_check():
                        if live_ph_data and live_ph_data[-1].get("status") == "OK":
                            current = live_ph_data[-1].get("value")
                            if current is not None and current >= target_ph:
                                return True, f"pH reached target {target_ph:.2f} (current: {current:.2f})"
                        return False, None

                    if dose_time_3 > 0 and _tank_has_solution(3):
                        log_event("PUMP_ACTIVATION", "INFO", f"Dosed pH UP for {dose_time_3:.2f}s (Delta: {delta_ph:.2f} pH)")
                        log_pump_action(3, dose_time_3, "Automatic")
                        _safe_pump_run(3, dose_time_3, stop_condition_fn=_ph_up_stop_check)
                        _last_ph_up_prediction = {'pre_val': ph_val, 'predicted_delta': delta_ph, 'time': time.time()}

                elif ph_val > l_ph.max_value:
                    delta_ph = ph_val - target_ph
                    required_ml = delta_ph * reservoir_vol * ph_down_factor
                    dose_time_4 = max(0.0, min(required_ml / flow_rate_4, max_dose_ph_down))
                    if 0 < dose_time_4 < MIN_PUMP_RUN_SEC:
                        dose_time_4 = MIN_PUMP_RUN_SEC

                    def _ph_down_stop_check():
                        if live_ph_data and live_ph_data[-1].get("status") == "OK":
                            current = live_ph_data[-1].get("value")
                            if current is not None and current <= target_ph:
                                return True, f"pH reached target {target_ph:.2f} (current: {current:.2f})"
                        return False, None

                    if dose_time_4 > 0 and _tank_has_solution(4):
                        log_event("PUMP_ACTIVATION", "INFO", f"Dosed pH DOWN for {dose_time_4:.2f}s (Delta: {delta_ph:.2f} pH)")
                        log_pump_action(4, dose_time_4, "Automatic")
                        _safe_pump_run(4, dose_time_4, stop_condition_fn=_ph_down_stop_check)
                        _last_ph_down_prediction = {'pre_val': ph_val, 'predicted_delta': delta_ph, 'time': time.time()}
    finally:
        for p in [1, 2, 3, 4]:
            try:
                hal.pump_stop(p)
            except Exception:
                pass
        is_dosing_active = False

def save_system_config(config, config_path="system_config.json"):
    tmp_path = f"{config_path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp_path, config_path)

def _evaluate_last_dose(current_tds, current_ph, config):
    global _last_ec_prediction, _last_ph_up_prediction, _last_ph_down_prediction

    # If the system is currently in a drain cycle (probe dry/unsubmerged),
    # defer evaluation until water returns to the stable plateau.
    if live_tds_data and live_tds_data[-1].get("is_drain_cycle"):
        return

    cooldown_s = float(config.get("cooldown_minutes", 15.0)) * 60

    if _last_ec_prediction and (time.time() - _last_ec_prediction['time']) >= cooldown_s:
        actual_delta = current_tds - _last_ec_prediction['pre_val']
        predicted_delta = _last_ec_prediction['predicted_delta']
        if predicted_delta > 0 and actual_delta > 0:
            ratio = actual_delta / predicted_delta
            current_factor = float(config.get("nutrient_ml_per_l_per_ec", 2.0))
            correction = current_factor / ratio
            new_factor = round(current_factor * 0.8 + correction * 0.2, 4)
            new_factor = max(0.5, min(new_factor, 10.0))
            config["nutrient_ml_per_l_per_ec"] = new_factor
            save_system_config(config)
            log_event("DOSING_CALIBRATION", "INFO",
                      f"EC factor adjusted: {current_factor:.4f} -> {new_factor:.4f} (ratio: {ratio:.2f})")
        _last_ec_prediction = None

    if _last_ph_up_prediction and (time.time() - _last_ph_up_prediction['time']) >= cooldown_s:
        actual_delta = current_ph - _last_ph_up_prediction['pre_val']
        predicted_delta = _last_ph_up_prediction['predicted_delta']
        if predicted_delta > 0 and actual_delta > 0:
            ratio = actual_delta / predicted_delta
            current_factor = float(config.get("ph_up_ml_per_l_per_ph", 0.5))
            correction = current_factor / ratio
            new_factor = round(current_factor * 0.8 + correction * 0.2, 4)
            new_factor = max(0.1, min(new_factor, 5.0))
            config["ph_up_ml_per_l_per_ph"] = new_factor
            save_system_config(config)
            log_event("DOSING_CALIBRATION", "INFO",
                      f"pH UP factor adjusted: {current_factor:.4f} -> {new_factor:.4f} (ratio: {ratio:.2f})")
        _last_ph_up_prediction = None

    if _last_ph_down_prediction and (time.time() - _last_ph_down_prediction['time']) >= cooldown_s:
        actual_delta = _last_ph_down_prediction['pre_val'] - current_ph
        predicted_delta = _last_ph_down_prediction['predicted_delta']
        if predicted_delta > 0 and actual_delta > 0:
            ratio = actual_delta / predicted_delta
            current_factor = float(config.get("ph_down_ml_per_l_per_ph", 0.5))
            correction = current_factor / ratio
            new_factor = round(current_factor * 0.8 + correction * 0.2, 4)
            new_factor = max(0.1, min(new_factor, 5.0))
            config["ph_down_ml_per_l_per_ph"] = new_factor
            save_system_config(config)
        _last_ph_down_prediction = None




def check_and_adjust_sensors():
    global is_dosing_active, last_dosing_time, last_error_alert_time, _is_system_halt_alert_sent, _ec_high_since, _ec_intervention_last_sent, is_priming_active, _consecutive_halt_ticks
    
    if is_priming_active or is_dosing_active:
        return
        
    config = {}
    if os.path.exists("system_config.json"):
        with open("system_config.json", "r") as f: config = json.load(f)
        
    cooldown_s = float(config.get("cooldown_minutes", 15.0)) * 60
    
    if time.time() - last_dosing_time < cooldown_s:
        return
        
    if not live_ph_data or not live_tds_data:
        return

    # Gating: if the system is currently in a drain cycle, pause dosing decisions
    if live_tds_data[-1].get("is_drain_cycle"):
        return
        
    with app.app_context():
        ph_val = live_ph_data[-1]["value"]
        tds_val = live_tds_data[-1]["value"]
        ph_status = live_ph_data[-1]["status"]
        tds_status = live_tds_data[-1]["status"]
        _evaluate_last_dose(tds_val, ph_val, config)
        
        is_ph_invalid = ph_status == "ERROR" or ph_val is None or "ERROR" in str(ph_val) or (isinstance(ph_val, (int, float)) and (ph_val < 0.0 or ph_val > 14.0))
        is_tds_invalid = tds_status == "ERROR" or tds_val is None or "ERROR" in str(tds_val) or (isinstance(tds_val, (int, float)) and (tds_val < 0.0 or tds_val > 10.0))
        is_tds_critical = tds_val is not None and not isinstance(tds_val, str) and tds_val >= 8.0


        if is_ph_invalid or is_tds_invalid or is_tds_critical:
            _consecutive_halt_ticks += 1
            hal.emergency_stop_all()

            if _consecutive_halt_ticks < 10:
                return

            reason = []
            if is_ph_invalid: reason.append(f"pH invalid ({ph_status}/{ph_val})")
            if is_tds_invalid: reason.append(f"EC invalid ({tds_status}/{tds_val})")
            if is_tds_critical: reason.append(f"EC critical hardware safety limit reached ({tds_val} >= 8.0)")
            
            if time.time() - last_error_alert_time > 86400:
                log_event("CRITICAL_HALT", "ALARM", f"Dosing cycle aborted due to critical conditions: {', '.join(reason)}", {"ph_status": ph_status, "tds_status": tds_status, "tds_val": tds_val})
                print(f"ALERT: Critical Conditions! Dosing aborted. {', '.join(reason)}")
                try:
                    sensor_monitor.send_email_alert(
                        "SYSTEM", 
                        f"Dosing system critical halt: {', '.join(reason)}", 
                        "DANGER", 
                        bypass_cooldown=True
                    )
                    _is_system_halt_alert_sent = True
                except Exception as e:
                    print(f"CRITICAL: Failed to send halt email alert! {e}")
                    log_event("SYSTEM_ERROR", "ERROR", f"Failed to send halt alert: {e}")
                last_error_alert_time = time.time()
            return
        else:
            if _consecutive_halt_ticks >= 10:
                try:
                    sensor_monitor.send_email_alert(
                        "SYSTEM",
                        f"Dosing system resumed: Hardware readings restored (pH: {ph_val}, EC: {tds_val}). Normal automated control active.",
                        "RECOVERY",
                        bypass_cooldown=True
                    )
                    _is_system_halt_alert_sent = False
                    log_event("CRITICAL_HALT_RECOVERY", "INFO", f"Dosing system hardware readings restored (pH: {ph_val}, EC: {tds_val}).")
                except Exception as e:
                    print(f"DEBUG: Failed to send halt recovery email: {e}")
            _consecutive_halt_ticks = 0
            last_error_alert_time = 0

        import db_cache
        status_rec = db_cache.get_plant_status()
        # Dosing should not start until the user has started a Growth Cycle
        if not status_rec or not status_rec.get("plant_name"):
            return

        l_ph_db = db_cache.get_sensor_limit("ph")
        l_tds_db = db_cache.get_sensor_limit("tds")
        
        class MockLimit:
            def __init__(self, min_v, max_v, is_act):
                self.min_value, self.max_value, self.is_active = float(min_v), float(max_v), is_act
                
        l_ph = MockLimit(l_ph_db["min"], l_ph_db["max"], l_ph_db["active"]) if l_ph_db else None
        l_tds = MockLimit(l_tds_db["min"], l_tds_db["max"], l_tds_db["active"]) if l_tds_db else None
        
        if status_rec and status_rec.get("state"):
            try:
                from grow_cycle_helper import get_active_grow_cycle_details
                cycle_details = get_active_grow_cycle_details()
                if not isinstance(cycle_details, dict):
                    cycle_details = {}
                limits = cycle_details.get("limits", {})
                if isinstance(limits, dict):
                    if 'ph' in limits and isinstance(limits['ph'], dict):
                        base_min = l_ph_db["min"] if l_ph_db else 0
                        base_max = l_ph_db["max"] if l_ph_db else 14
                        # Preserve user's is_active toggle — grow cycle overrides range only, not monitoring state
                        ph_is_active = l_ph_db.get("active", True) if l_ph_db else True
                        l_ph = MockLimit(limits['ph'].get('min', base_min), limits['ph'].get('max', base_max), ph_is_active)
                    if 'ec' in limits and isinstance(limits['ec'], dict):
                        base_min = l_tds_db["min"] if l_tds_db else 0
                        base_max = l_tds_db["max"] if l_tds_db else 5
                        # Preserve user's is_active toggle — grow cycle overrides range only, not monitoring state
                        tds_is_active = l_tds_db.get("active", True) if l_tds_db else True
                        l_tds = MockLimit(limits['ec'].get('min', base_min), limits['ec'].get('max', base_max), tds_is_active)
            except Exception as e:
                log_event("SYSTEM_ERROR", "ERROR", f"Failed to fetch grow cycle limits for dosing. Error: {e}", {"error": str(e)})
                    
        if l_tds and l_tds.is_active and tds_val is not None:
            intervention_threshold = l_tds.max_value - 0.2
            if tds_val >= intervention_threshold:
                now = time.time()
                if _ec_high_since is None:
                    _ec_high_since = now
                time_stuck = now - _ec_high_since
                time_since_last_alert = (now - _ec_intervention_last_sent) if _ec_intervention_last_sent else float('inf')
                if time_stuck >= EC_INTERVENTION_HOURS * 3600 and time_since_last_alert >= EC_RENOTIFY_HOURS * 3600:
                    sensor_monitor.send_email_alert(
                        "SYSTEM",
                        f"EC has been at {tds_val:.2f} (above {intervention_threshold:.1f}) for over {int(time_stuck/3600)}h. Manual intervention required.",
                        "DANGER",
                        bypass_cooldown=True
                    )
                    _ec_intervention_last_sent = now
            else:
                _ec_high_since = None
                _ec_intervention_last_sent = None

        needs_dosing = False
        if l_ph and l_ph.is_active and (ph_val < l_ph.min_value or ph_val > l_ph.max_value): needs_dosing = True
        if l_tds and l_tds.is_active and (tds_val < l_tds.min_value or tds_val > l_tds.max_value): needs_dosing = True
        
        if needs_dosing:
            print(f"DEBUG DOSING: >>> STARTING DOSING CYCLE (pH={ph_val}, EC={tds_val})")
            last_dosing_time = time.time()
            is_dosing_active = True
            threading.Thread(target=_async_dosing, args=(ph_val, tds_val, l_ph, l_tds), daemon=True).start()
        else:
            print(f"DEBUG DOSING: No dosing needed - values within range")

def _reset_dosing_state():
    global last_dosing_time, last_error_alert_time, is_priming_active, is_dosing_active, _last_ec_prediction, _last_ph_up_prediction, _last_ph_down_prediction, _ec_high_since, _ec_intervention_last_sent, _is_system_halt_alert_sent, _consecutive_halt_ticks
    last_dosing_time = 0
    last_error_alert_time = 0
    is_priming_active = False
    is_dosing_active = False
    _last_ec_prediction = None
    _last_ph_up_prediction = None
    _last_ph_down_prediction = None
    _ec_high_since = None
    _ec_intervention_last_sent = None
    _is_system_halt_alert_sent = False
    _consecutive_halt_ticks = 0
    try:
        import sensors
        if hasattr(sensors, 'circulation_tracker'):
            sensors.circulation_tracker.reset()
    except Exception:
        pass

