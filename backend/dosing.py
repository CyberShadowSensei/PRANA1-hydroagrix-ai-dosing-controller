"""Adaptive Dosing Engine
Calculates chemical volumes, inter-dose cooldowns, emergency halts, and flow rate execution.
"""
import os
import time
import json
import threading
import config as config_mod
from models import PumpLog, EventLog, SolutionTanks
from config import db, app
from observation_engine import nutrient_impact_tracker, alert_manager, db
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

# ---------------------------------------------------------------------------
# Hardware Fault Detection
# ---------------------------------------------------------------------------
# When a pump runs but the sensor shows zero or negative response over multiple
# consecutive cycles, the system concludes something is physically wrong:
# empty tank, airlocked tubing, worn peristaltic head, disconnected tube, etc.
# After HW_FAULT_THRESHOLD consecutive failures, dosing for that pump is
# suspended for HW_FAULT_SUSPEND_HOURS and an email alert is sent.
# ---------------------------------------------------------------------------
HW_FAULT_THRESHOLD = 2          # consecutive zero-movement doses before fault declared
HW_FAULT_SUSPEND_HOURS = 4      # hours to suspend dosing after fault
HW_FAULT_RENOTIFY_HOURS = 4     # hours between repeated fault emails

# Per-pump fault state: {pump_id: {"failures": int, "suspended_until": float, "last_alert": float}}
_hw_fault_state = {
    3: {"failures": 0, "suspended_until": 0.0, "last_alert": 0.0},  # pH UP
    4: {"failures": 0, "suspended_until": 0.0, "last_alert": 0.0},  # pH DOWN
    "ec": {"failures": 0, "suspended_until": 0.0, "last_alert": 0.0},  # Nutrients (Pumps 1+2)
}

PUMP_LABEL = {
    3: "Pump 3 (pH UP / Tank 3)",
    4: "Pump 4 (pH DOWN / Tank 4)",
    "ec": "Pump 1+2 (Nutrients A+B / Tanks 1&2)",
}


def _record_hw_fault(pump_key: str | int):
    """Increment the failure counter for a pump. If threshold is reached,
    suspend dosing and send a HARDWARE_FAULT_SUSPECTED alert."""
    state = _hw_fault_state.get(pump_key)
    if state is None:
        return
    state["failures"] += 1
    if state["failures"] >= HW_FAULT_THRESHOLD:
        now = time.time()
        state["suspended_until"] = now + HW_FAULT_SUSPEND_HOURS * 3600
        label = PUMP_LABEL.get(pump_key, str(pump_key))
        msg = (
            f"HARDWARE FAULT SUSPECTED — {label}\n\n"
            f"The pump has dosed {state['failures']} consecutive time(s) but the "
            f"corresponding sensor has shown zero or negative response.\n\n"
            f"Possible causes:\n"
            f"  • Tank is empty or nearly empty\n"
            f"  • Tubing is kinked, airlocked, or disconnected\n"
            f"  • Peristaltic pump head is worn or not primed\n\n"
            f"Automatic dosing for {label} has been SUSPENDED for {HW_FAULT_SUSPEND_HOURS} hours "
            f"to prevent wasting solution. Please inspect the hardware.\n"
            f"Dosing will resume automatically at: "
            f"{time.strftime('%Y-%m-%d %H:%M IST', time.localtime(state['suspended_until']))}"
        )
        log_event(
            "HARDWARE_FAULT_SUSPECTED", "DANGER",
            f"{label}: {state['failures']} consecutive zero-movement doses. "
            f"Automatic dosing suspended for {HW_FAULT_SUSPEND_HOURS}h. Inspect hardware."
        )
        print(f"HARDWARE_FAULT_SUSPECTED: {label} — {state['failures']} zero-movement doses. Suspended {HW_FAULT_SUSPEND_HOURS}h.")
        if now - state["last_alert"] >= HW_FAULT_RENOTIFY_HOURS * 3600:
            state["last_alert"] = now
            threading.Thread(
                target=sensor_monitor.send_email_alert,
                args=("SYSTEM", msg, "DANGER", True),
                daemon=True,
            ).start()


def _record_hw_success(pump_key: str | int):
    """Clear the failure counter when a dose actually moved the sensor."""
    state = _hw_fault_state.get(pump_key)
    if state is not None and state["failures"] > 0:
        label = PUMP_LABEL.get(pump_key, str(pump_key))
        log_event(
            "HARDWARE_FAULT_RESOLVED", "INFO",
            f"{label}: sensor responded to dose. Hardware fault cleared."
        )
        state["failures"] = 0
        state["suspended_until"] = 0.0


def reset_hw_fault(pump_key: str | int | None = None):
    """Manually reset hardware fault suspension for a specific pump or all pumps.
    Can be called manually, from UI pump priming, or via REST API."""
    if pump_key is None:
        for k, state in _hw_fault_state.items():
            state["failures"] = 0
            state["suspended_until"] = 0.0
        log_event("HARDWARE_FAULT_RESET", "INFO", "All hardware fault suspensions reset manually.")
    else:
        key = "ec" if pump_key in (1, 2, "1", "2", "ec") else pump_key
        try:
            key = int(key)
        except (ValueError, TypeError):
            pass
        state = _hw_fault_state.get(key)
        if state is not None:
            state["failures"] = 0
            state["suspended_until"] = 0.0
            label = PUMP_LABEL.get(key, str(key))
            log_event("HARDWARE_FAULT_RESET", "INFO", f"{label}: hardware fault suspension reset manually.")


def get_hw_fault_status() -> dict:
    """Return human-readable hardware fault status for all pumps for UI display."""
    now = time.time()
    res = {}
    for key, state in _hw_fault_state.items():
        is_suspended = now < state["suspended_until"]
        remaining_sec = max(0, int(state["suspended_until"] - now)) if is_suspended else 0
        res[str(key)] = {
            "key": key,
            "label": PUMP_LABEL.get(key, str(key)),
            "failures": state["failures"],
            "is_suspended": is_suspended,
            "suspended_until": state["suspended_until"],
            "remaining_sec": remaining_sec,
            "resume_time_str": time.strftime("%H:%M IST", time.localtime(state["suspended_until"])) if is_suspended else None
        }
    return res


def _hw_suspended(pump_key: str | int) -> bool:
    """Return True (and log a short warning) if the pump is currently suspended."""
    state = _hw_fault_state.get(pump_key)
    if state is None:
        return False
    if time.time() < state["suspended_until"]:
        resume_str = time.strftime("%H:%M IST", time.localtime(state["suspended_until"]))
        label = PUMP_LABEL.get(pump_key, str(pump_key))
        print(f"HW_FAULT_SUSPENDED: {label} — skipping automatic dose until {resume_str}")
        return True
    return False


def init_dosing_state():
    global last_dosing_time
    try:
        from models import PumpLog
        import pytz
        with app.app_context():
            # Get the most recent Automatic pump log
            last_log = PumpLog.query.filter_by(trigger_type="Automatic").order_by(PumpLog.id.desc()).first()
            if last_log and last_log.timestamp:
                # timestamp is a naive datetime representing UTC
                ts = last_log.timestamp.replace(tzinfo=pytz.UTC).timestamp()
                # Ensure we don't accidentally set it to a future time if there are clock sync issues
                if ts <= time.time():
                    last_dosing_time = ts
                    print(f"INFO: Restored last_dosing_time from DB: {last_log.timestamp} ({ts})")
    except Exception as e:
        print(f"DEBUG: Failed to init dosing state from DB: {e}")

def log_pump_action(pump_id, duration, trigger_type, flow_rate_ml_per_sec=None):
    """Log a pump action and deduct the dispensed volume from the corresponding solution tank.

    Args:
        pump_id: Pump number (1–4).
        duration: Actual elapsed run time in seconds (from _safe_pump_run).
        trigger_type: 'Automatic', 'Manual', or 'Priming'.
        flow_rate_ml_per_sec: The already-resolved per-pump flow rate from _async_dosing.
            When supplied this value is used directly, avoiding a second config read and
            eliminating any race condition if the config is updated during a dose.
            Falls back to reading system_config.json when not provided (manual/priming
            callers that don't have the resolved rate available).
    """
    names = {1: "Pump 1 (Nutrients A)", 2: "Pump 2 (Nutrients B)", 3: "Pump 3 (pH UP)", 4: "Pump 4 (pH DOWN)"}
    name = names.get(pump_id, f"Pump {pump_id}")
    try:
        with app.app_context():
            db.session.add(PumpLog(pump_name=name, duration=duration, trigger_type=trigger_type))

            from models import SolutionTanks

            # Bug 4 fix: use the caller-supplied flow rate when available so that
            # volume deduction always matches the rate that was actually used during
            # the dose, even if config is updated concurrently.
            pump_flow_rate = flow_rate_ml_per_sec
            if pump_flow_rate is None:
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
                import db_cache
                if tank:
                    db_cache.update_solution_tank(
                        tank_id=tank.tank_id,
                        name=tank.name,
                        capacity_ml=tank.capacity_ml,
                        current_volume_ml=tank.current_volume_ml,
                        last_alert_sent=tank.last_alert_sent,
                        consecutive_blocked_attempts=tank.consecutive_blocked_attempts,
                        next_allowed_alert_time=tank.next_allowed_alert_time
                    )
            except Exception as dbe:
                print(f"Error updating tank in db_cache: {dbe}")

            try:
                from config import socketio
                socketio.emit('pump_activity', {
                    'pump_id': pump_id, 
                    'duration': duration, 
                    'trigger_type': trigger_type
                })
                if tank:
                    socketio.emit('tank_levels_updated', {
                        'tank_id': tank.tank_id,
                        'current_volume_ml': tank.current_volume_ml
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
    return round(elapsed, 2)

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
            # ================= pH Dosing FIRST =================
            # CRITICAL FIX: pH is corrected BEFORE nutrients, because nutrients
            # are acidic and drop pH.  Dosing nutrients first into a low-pH
            # reservoir wastes the nutrient (pH is out of range for uptake)
            # AND triggers a pH correction cycle that fights the nutrients.
            current_ph_live = ph_val

            if l_ph and l_ph.is_active:
                # OVERSHOOT FIX: target the BOUNDARY with a small buffer, NOT
                # the midpoint.  Aiming for the midpoint causes large deltas
                # that overshoot past the opposite limit → oscillation.
                #   pH too low  → aim for min + 20% of range (just inside)
                #   pH too high → aim for max - 20% of range (just inside)
                ph_range = l_ph.max_value - l_ph.min_value
                ph_buffer = ph_range * 0.2

                if current_ph_live < l_ph.min_value:
                    target_ph = l_ph.min_value + ph_buffer
                    delta_ph = target_ph - current_ph_live
                    required_ml = delta_ph * reservoir_vol * ph_up_factor
                    dose_time_3 = max(0.0, min(required_ml / flow_rate_3, max_dose_ph_up))
                    if 0 < dose_time_3 < MIN_PUMP_RUN_SEC:
                        dose_time_3 = MIN_PUMP_RUN_SEC

                    confirmations = [0]
                    def _ph_up_stop_check():
                        if live_ph_data and live_ph_data[-1].get("status") == "OK":
                            v = live_ph_data[-1].get("value")
                            if v is not None and v >= target_ph:
                                confirmations[0] += 1
                                if confirmations[0] >= 5:
                                    return True, f"pH reached target {target_ph:.2f} (current: {v:.2f})"
                            else:
                                confirmations[0] = 0
                        else:
                            confirmations[0] = 0
                        return False, None

                    if dose_time_3 > 0 and _tank_has_solution(3) and not _hw_suspended(3):
                        log_event("PUMP_ACTIVATION", "INFO", f"Dosed pH UP for {dose_time_3:.2f}s (Delta: {delta_ph:.2f} pH, target: {target_ph:.2f})")
                        actual_time_3 = _safe_pump_run(3, dose_time_3, stop_condition_fn=_ph_up_stop_check)
                        log_pump_action(3, actual_time_3, "Automatic", flow_rate_ml_per_sec=flow_rate_3)
                        _last_ph_up_prediction = {'pre_val': current_ph_live, 'predicted_delta': delta_ph, 'time': time.time()}
                        # Re-sample live pH after dose
                        if live_ph_data and live_ph_data[-1].get("status") == "OK":
                            sampled = live_ph_data[-1].get("value")
                            if sampled is not None:
                                current_ph_live = sampled

                # pH DOWN: same boundary-targeting approach
                if current_ph_live > l_ph.max_value:
                    target_ph = l_ph.max_value - ph_buffer
                    delta_ph = current_ph_live - target_ph
                    required_ml = delta_ph * reservoir_vol * ph_down_factor
                    dose_time_4 = max(0.0, min(required_ml / flow_rate_4, max_dose_ph_down))
                    if 0 < dose_time_4 < MIN_PUMP_RUN_SEC:
                        dose_time_4 = MIN_PUMP_RUN_SEC

                    confirmations = [0]
                    def _ph_down_stop_check():
                        if live_ph_data and live_ph_data[-1].get("status") == "OK":
                            v = live_ph_data[-1].get("value")
                            if v is not None and v <= target_ph:
                                confirmations[0] += 1
                                if confirmations[0] >= 5:
                                    return True, f"pH reached target {target_ph:.2f} (current: {v:.2f})"
                            else:
                                confirmations[0] = 0
                        else:
                            confirmations[0] = 0
                        return False, None

                    if dose_time_4 > 0 and _tank_has_solution(4):
                        log_event("PUMP_ACTIVATION", "INFO", f"Dosed pH DOWN for {dose_time_4:.2f}s (Delta: {delta_ph:.2f} pH, target: {target_ph:.2f})")
                        actual_time_4 = _safe_pump_run(4, dose_time_4, stop_condition_fn=_ph_down_stop_check)
                        log_pump_action(4, actual_time_4, "Automatic", flow_rate_ml_per_sec=flow_rate_4)
                        _last_ph_down_prediction = {'pre_val': current_ph_live, 'predicted_delta': delta_ph, 'time': time.time()}
                        # Re-sample live pH after dose
                        if live_ph_data and live_ph_data[-1].get("status") == "OK":
                            sampled = live_ph_data[-1].get("value")
                            if sampled is not None:
                                current_ph_live = sampled

            # ================= EC Dosing (AFTER pH is stable) =================
            if l_tds and l_tds.is_active and tds_val < l_tds.min_value:
                # Hard nutrient block when pH is below minimum.
                avg_ph_impact = nutrient_impact_tracker.get_average_ph_impact_per_ml()
                dynamic_min_ph = l_ph.min_value
                if avg_ph_impact < -0.01:
                    dynamic_min_ph = l_ph.min_value + 0.1

                ph_below_dynamic_min = bool(l_ph and l_ph.is_active and current_ph_live is not None and current_ph_live < dynamic_min_ph)

                if ph_below_dynamic_min:
                    ph_up_available = check_tank_has_solution_permission(3)
                    if not ph_up_available:
                        log_event(
                            "CROSS_TANK_LOCKOUT", "WARNING",
                            f"Cross-Tank Lock: Nutrient A/B dosing blocked because pH ({current_ph_live:.2f}) is below set limit ({l_ph.min_value:.2f}) and Tank 3 (pH UP) is empty. Refill Tank 3 to resume nutrient dosing."
                        )
                        print(f"CROSS_TANK_LOCKOUT: Nutrient dosing blocked (pH {current_ph_live:.2f} < {l_ph.min_value:.2f}, Tank 3 empty)")
                    else:
                        log_event(
                            "NUTRIENT_HELD_PH_LOW", "WARNING",
                            f"Nutrient dosing held: pH ({current_ph_live:.2f}) is below set minimum ({l_ph.min_value:.2f}). pH UP will dose first; nutrients resume once pH is corrected."
                        )
                        print(f"NUTRIENT_HELD_PH_LOW: pH {current_ph_live:.2f} < {l_ph.min_value:.2f} — nutrients held until pH is corrected")
                    # In BOTH sub-cases: do not dose nutrients.
                else:
                    # OVERSHOOT FIX: target min + 20% of range, not midpoint
                    ec_range = l_tds.max_value - l_tds.min_value
                    target_tds = l_tds.min_value + ec_range * 0.2
                    delta_ec = target_tds - tds_val
                    required_ml = delta_ec * reservoir_vol * nutrient_factor
                    dose_time_1 = max(0.0, min(required_ml / flow_rate_1, max_dose_ec_1))
                    if 0 < dose_time_1 < MIN_PUMP_RUN_SEC:
                        dose_time_1 = MIN_PUMP_RUN_SEC
                    dose_time_2 = max(0.0, min(required_ml / flow_rate_2, max_dose_ec_2))
                    if 0 < dose_time_2 < MIN_PUMP_RUN_SEC:
                        dose_time_2 = MIN_PUMP_RUN_SEC

                    # Nutrient Pair Balance Lock:
                    tank_1_ok = _tank_has_solution(1)
                    tank_2_ok = _tank_has_solution(2)

                    if (dose_time_1 > 0 or dose_time_2 > 0) and not (tank_1_ok and tank_2_ok):
                        log_event(
                            "CROSS_TANK_LOCKOUT", "WARNING",
                            f"Cross-Tank Lock: Both Nutrient A (Tank 1: {'OK' if tank_1_ok else 'EMPTY'}) and Nutrient B (Tank 2: {'OK' if tank_2_ok else 'EMPTY'}) are required for balanced dosing. Dosing aborted."
                        )
                    elif dose_time_1 > 0 or dose_time_2 > 0:
                        if _hw_suspended("ec"):
                            pass  # Suspended — skip silently (already logged inside _hw_suspended)
                        else:
                            total_vol = (dose_time_1 * flow_rate_1) + (dose_time_2 * flow_rate_2)
                            nutrient_impact_tracker.record_nutrient_dose(total_vol, current_ph_live)

                            # PRE-COMPENSATE for nutrient acidity: predict pH drop and
                            # check if nutrients would push pH below the safe range.
                            # If so, skip nutrients this cycle — let the next cycle
                            # re-evaluate after pH is fully stable.
                            predicted_ph_drop = abs(avg_ph_impact) * total_vol
                            predicted_ph_after = current_ph_live - predicted_ph_drop
                            if l_ph and l_ph.is_active and predicted_ph_after < l_ph.min_value:
                                log_event(
                                    "NUTRIENT_PH_GUARD", "INFO",
                                    f"Nutrient dose ({total_vol:.1f} mL) would drop pH from {current_ph_live:.2f} to ~{predicted_ph_after:.2f} (below {l_ph.min_value:.2f}). Skipping nutrients this cycle."
                                )
                                print(f"NUTRIENT_PH_GUARD: Skipping nutrients — predicted pH {predicted_ph_after:.2f} < min {l_ph.min_value:.2f}")
                            else:
                                confirmations = [0]
                                def _ec_stop_check():
                                    if live_tds_data and live_tds_data[-1].get("status") == "OK":
                                        current = live_tds_data[-1].get("value")
                                        if current is not None and current >= target_tds:
                                            confirmations[0] += 1
                                            if confirmations[0] >= 5:
                                                return True, f"EC reached target {target_tds:.2f} (current: {current:.2f})"
                                        else:
                                            confirmations[0] = 0
                                    else:
                                        confirmations[0] = 0
                                    return False, None

                                # Pump 1 (Nutrient A)
                                if dose_time_1 > 0:
                                    log_event("PUMP_ACTIVATION", "INFO", f"Dosed Nutrient A for {dose_time_1:.2f}s (Delta: {delta_ec:.2f} EC)")
                                    actual_time_1 = _safe_pump_run(1, dose_time_1, stop_condition_fn=_ec_stop_check)
                                    log_pump_action(1, actual_time_1, "Automatic", flow_rate_ml_per_sec=flow_rate_1)
                                    _last_ec_prediction = {'pre_val': tds_val, 'predicted_delta': delta_ec, 'time': time.time()}
                                    time.sleep(nut_gap_s)
                                # Pump 2 (Nutrient B)
                                if dose_time_2 > 0:
                                    log_event("PUMP_ACTIVATION", "INFO", f"Dosed Nutrient B for {dose_time_2:.2f}s")
                                    actual_time_2 = _safe_pump_run(2, dose_time_2, stop_condition_fn=_ec_stop_check)
                                    log_pump_action(2, actual_time_2, "Automatic", flow_rate_ml_per_sec=flow_rate_2)

            elif l_tds and l_tds.is_active and tds_val > l_tds.max_value:
                log_event("EC_DANGER_ALARM", "ALARM", f"EC value {tds_val} exceeds limit {l_tds.max_value}. Dosing halted.", {"current_ec": tds_val})

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

    nutrient_impact_tracker.evaluate_impact(current_ph, cooldown_s)

    if _last_ec_prediction:
        actual_delta = current_tds - _last_ec_prediction['pre_val']
        predicted_delta = _last_ec_prediction['predicted_delta']
        if predicted_delta > 0:
            ratio = actual_delta / predicted_delta if actual_delta > 0 else None
            current_factor = float(config.get("nutrient_ml_per_l_per_ec", 2.0))
            if ratio is not None and ratio > 0:
                correction = current_factor / ratio
                new_factor = round(current_factor * 0.8 + correction * 0.2, 4)
                new_factor = max(0.5, min(new_factor, current_factor * 2.0, 50.0))
                config["nutrient_ml_per_l_per_ec"] = new_factor
                save_system_config(config)
                log_event("DOSING_CALIBRATION", "INFO",
                          f"EC factor adjusted: {current_factor:.4f} -> {new_factor:.4f} (ratio: {ratio:.2f})")
                _record_hw_success("ec")
            else:
                # actual_delta <= 0: sensor showed no rise after dose.
                # Do NOT scale up the factor — that compounds errors when the tank
                # is empty or the tubing is blocked.
                log_event("CALIBRATION_SKIP_NO_MOVEMENT", "WARNING",
                          f"EC calibration skipped — no EC rise observed after dose "
                          f"(pre: {_last_ec_prediction['pre_val']:.2f}, current: {current_tds:.2f}). "
                          f"Check Tank 1/2 levels and tubing.")
                _record_hw_fault("ec")

        _last_ec_prediction = None

    if _last_ph_up_prediction:
        actual_delta = current_ph - _last_ph_up_prediction['pre_val']
        predicted_delta = _last_ph_up_prediction['predicted_delta']
        if predicted_delta > 0:
            ratio = actual_delta / predicted_delta if actual_delta > 0 else None
            current_factor = float(config.get("ph_up_ml_per_l_per_ph", 0.5))
            if ratio is None or ratio <= 0:
                # pH did not rise after dose. Likely causes: Tank 3 (pH UP) is empty,
                # airlock in tubing, or peristaltic pump head failure.
                # DO NOT increase the factor — that just makes the next dose longer
                # with the same no-effect result, wasting solution and masking the fault.
                log_event("CALIBRATION_SKIP_NO_MOVEMENT", "WARNING",
                          f"pH UP calibration skipped — no pH rise observed after {_last_ph_up_prediction['predicted_delta']:.2f} pH dose "
                          f"(pre: {_last_ph_up_prediction['pre_val']:.2f}, current: {current_ph:.2f}). "
                          f"Check Tank 3 (pH UP) level and tubing. Current factor: {current_factor:.4f}")
                _record_hw_fault(3)
            else:
                correction = current_factor / ratio
                new_factor = round(current_factor * 0.8 + correction * 0.2, 4)
                # Cap single-step change to 2x to prevent overreaction
                new_factor = max(0.1, min(new_factor, current_factor * 2.0, 10.0))
                config["ph_up_ml_per_l_per_ph"] = new_factor
                save_system_config(config)
                log_event("DOSING_CALIBRATION", "INFO",
                          f"pH UP factor adjusted: {current_factor:.4f} -> {new_factor:.4f} (ratio: {ratio:.2f})")
                _record_hw_success(3)
        _last_ph_up_prediction = None


    if _last_ph_down_prediction:
        actual_delta = _last_ph_down_prediction['pre_val'] - current_ph
        predicted_delta = _last_ph_down_prediction['predicted_delta']
        if predicted_delta > 0:
            ratio = actual_delta / predicted_delta if actual_delta > 0 else None
            current_factor = float(config.get("ph_down_ml_per_l_per_ph", 0.5))
            if ratio is None or ratio <= 0:
                log_event("CALIBRATION_SKIP_NO_MOVEMENT", "WARNING",
                          f"pH DOWN calibration skipped — no pH drop observed after dose "
                          f"(pre: {_last_ph_down_prediction['pre_val']:.2f}, current: {current_ph:.2f}). "
                          f"Check Tank 4 (pH DOWN) level and tubing. Current factor: {current_factor:.4f}")
                _record_hw_fault(4)
            else:
                correction = current_factor / ratio
                new_factor = round(current_factor * 0.8 + correction * 0.2, 4)
                new_factor = max(0.1, min(new_factor, current_factor * 2.0, 10.0))
                config["ph_down_ml_per_l_per_ph"] = new_factor
                save_system_config(config)
                log_event("DOSING_CALIBRATION", "INFO",
                          f"pH DOWN factor adjusted: {current_factor:.4f} -> {new_factor:.4f} (ratio: {ratio:.2f})")
                _record_hw_success(4)
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
        
        # Plant safety emergency limits
        is_ph_critical = isinstance(ph_val, (int, float)) and (ph_val < 3.0 or ph_val > 10.0)


        if is_ph_invalid or is_tds_invalid or is_tds_critical or is_ph_critical:
            _consecutive_halt_ticks += 1
            hal.emergency_stop_all()

            if _consecutive_halt_ticks < 10:
                return

            reason = []
            if is_ph_invalid: reason.append(f"pH invalid ({ph_status}/{ph_val})")
            if is_tds_invalid: reason.append(f"EC invalid ({tds_status}/{tds_val})")
            if is_tds_critical: reason.append(f"EC critical hardware safety limit reached ({tds_val} >= 8.0)")
            if is_ph_critical: reason.append(f"pH critical plant safety limit reached ({ph_val})")
            
            if time.time() - last_error_alert_time > 86400:
                log_event("CRITICAL_HALT", "ALARM", f"Dosing cycle aborted due to critical conditions: {', '.join(reason)}", {"ph_status": ph_status, "tds_status": tds_status, "tds_val": tds_val, "ph_val": ph_val})
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

