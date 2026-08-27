import threading
from datetime import datetime

_lock = threading.Lock()
_sensor_limits = {}
_plant_status = {}
_solution_tanks = {}
_initialized = False

def init_cache(app, db):
    global _initialized
    from models import SensorLimits, PlantStageStatus, SolutionTanks
    with app.app_context():
        with _lock:
            try:
                _sensor_limits.clear()
                for limit in SensorLimits.query.all():
                    _sensor_limits[limit.sensor_type] = {
                        "min": limit.min_value,
                        "max": limit.max_value,
                        "active": limit.is_active
                    }
                
                status = PlantStageStatus.query.first()
                if status:
                    _plant_status["plant_name"] = status.plant_name
                    _plant_status["plant_stage"] = status.plant_stage
                    _plant_status["state"] = status.state
                    _plant_status["cycle_start_date"] = status.cycle_start_date
                else:
                    _plant_status["plant_name"] = ""
                    _plant_status["plant_stage"] = "Idle"
                    _plant_status["state"] = False
                    _plant_status["cycle_start_date"] = None

                _solution_tanks.clear()
                for tank in SolutionTanks.query.all():
                    _solution_tanks[tank.tank_id] = {
                        "name": tank.name,
                        "capacity_ml": tank.capacity_ml,
                        "current_volume_ml": tank.current_volume_ml,
                        "last_alert_sent": tank.last_alert_sent or 0.0,
                        "consecutive_blocked_attempts": tank.consecutive_blocked_attempts or 0,
                        "next_allowed_alert_time": tank.next_allowed_alert_time or 0.0
                    }
                _initialized = True
                print("DEBUG: db_cache initialized successfully.")
            except Exception as e:
                print(f"DEBUG: db_cache init skipped or failed: {e}")

def get_sensor_limits():
    if not _initialized:
        from config import app, db
        init_cache(app, db)
    with _lock:
        return dict(_sensor_limits)

def get_sensor_limit(sensor_type):
    if not _initialized:
        from config import app, db
        init_cache(app, db)
    with _lock:
        return _sensor_limits.get(sensor_type)

def update_sensor_limit(sensor_type, min_val, max_val, active):
    with _lock:
        _sensor_limits[sensor_type] = {
            "min": min_val,
            "max": max_val,
            "active": active
        }

def get_plant_status():
    if not _initialized:
        from config import app, db
        init_cache(app, db)
    with _lock:
        return dict(_plant_status)

def update_plant_status(plant_name, plant_stage, state, cycle_start_date):
    with _lock:
        _plant_status["plant_name"] = plant_name
        _plant_status["plant_stage"] = plant_stage
        _plant_status["state"] = state
        _plant_status["cycle_start_date"] = cycle_start_date

def get_solution_tanks():
    if not _initialized:
        from config import app, db
        init_cache(app, db)
    with _lock:
        return dict(_solution_tanks)

def get_solution_tank(tank_id):
    if not _initialized:
        from config import app, db
        init_cache(app, db)
    with _lock:
        return _solution_tanks.get(tank_id)

def update_solution_tank(tank_id, name, capacity_ml, current_volume_ml, last_alert_sent, consecutive_blocked_attempts=0, next_allowed_alert_time=0.0):
    with _lock:
        _solution_tanks[tank_id] = {
            "name": name,
            "capacity_ml": capacity_ml,
            "current_volume_ml": current_volume_ml,
            "last_alert_sent": last_alert_sent or 0.0,
            "consecutive_blocked_attempts": consecutive_blocked_attempts or 0,
            "next_allowed_alert_time": next_allowed_alert_time or 0.0
        }
