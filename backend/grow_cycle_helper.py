"""Grow Cycle Progression Helper
Tracks active plant presets, timeline days, phase transitions, and target limits.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from models import PlantStageStatus, PlantPreset

def normalize_stages(stages: Union[str, Dict[str, Any], None]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Normalizes stages JSON or dictionary into an ordered list of tuples:
    [(phase_name, phase_data), ...] where each phase_data is guaranteed
    to contain computed 'start_day' and 'duration_days'.
    """
    if isinstance(stages, str):
        try:
            stages = json.loads(stages)
        except Exception:
            return []
    if not isinstance(stages, dict):
        return []

    raw_items = []
    for k, v in stages.items():
        if isinstance(v, dict):
            raw_items.append((k, dict(v)))

    if not raw_items:
        return []

    has_explicit_start = any('start_day' in v and v['start_day'] is not None for _, v in raw_items)

    if has_explicit_start:
        sorted_items = sorted(raw_items, key=lambda x: x[1].get('start_day', 0))
    else:
        sorted_items = raw_items

    running_start = 0
    normalized = []
    for idx, (name, data) in enumerate(sorted_items):
        data_copy = dict(data)
        
        # 1. Determine start_day
        if 'start_day' in data_copy and data_copy['start_day'] is not None:
            try:
                start_day = int(data_copy['start_day'])
            except (ValueError, TypeError):
                start_day = running_start
        else:
            start_day = running_start
        
        data_copy['start_day'] = start_day

        # 2. Determine duration_days
        if 'duration_days' in data_copy and data_copy['duration_days'] is not None:
            try:
                duration_days = int(data_copy['duration_days'])
            except (ValueError, TypeError):
                duration_days = None
        else:
            duration_days = None

        if duration_days is None and idx + 1 < len(sorted_items) and 'start_day' in sorted_items[idx + 1][1]:
            try:
                next_start = int(sorted_items[idx + 1][1]['start_day'])
                duration_days = max(0, next_start - start_day)
            except (ValueError, TypeError):
                duration_days = None
        
        try:
            buffer_days = int(data_copy.get('buffer_days', 0))
        except (ValueError, TypeError):
            buffer_days = 0
            
        data_copy['duration_days'] = duration_days
        data_copy['buffer_days'] = buffer_days

        running_start = start_day + (duration_days if duration_days is not None else 0) + buffer_days
        normalized.append((name, data_copy))

    normalized.sort(key=lambda x: x[1]['start_day'])
    return normalized


def reconcile_ml_stage(scheduled_phase, ml_stage, current_day, stages_dict):
    """
    Compares the scheduled phase with the ML vision detected stage.
    Returns a reconciliation status string.
    """
    if not ml_stage or ml_stage == "Idle" or ml_stage not in stages_dict:
        return "Unconfirmed"
        
    if scheduled_phase == ml_stage:
        return "Aligned"
        
    sched_start = stages_dict[scheduled_phase].get('start_day', 0)
    ml_start = stages_dict[ml_stage].get('start_day', 0)
    
    if ml_start < sched_start:
        return "Growth Delay"
    else:
        return "Pending"


def calculate_current_growth_stage(stages, current_day, ml_stage=None, is_automatic=False):
    """
    Derives active growth stage and target limits for a given day since planting.
    """
    normalized = normalize_stages(stages)
    if not normalized:
        return {
            "scheduled_phase": "Unknown",
            "scheduled_idx": 0,
            "active_phase": "Unknown",
            "phase_source": "Schedule",
            "active_phase_data": {},
            "limits": {},
            "normalized_stages": [],
            "ml_verification": "Unconfirmed"
        }

    scheduled_phase = "Unknown"
    scheduled_idx = 0
    for idx, (p_name, p_data) in enumerate(normalized):
        if current_day >= p_data.get('start_day', 0):
            scheduled_phase = p_name
            scheduled_idx = idx
        else:
            break

    if scheduled_phase == "Unknown" and normalized:
        scheduled_phase = normalized[0][0]
        scheduled_idx = 0

    stages_dict = dict(normalized)
    is_ml_valid = bool(ml_stage and ml_stage in stages_dict)
    ml_verification = reconcile_ml_stage(scheduled_phase, ml_stage, current_day, stages_dict)
    
    active_phase_name = scheduled_phase
    phase_source = "Schedule"

    active_phase_data = stages_dict.get(active_phase_name, {})
    buffer_days = active_phase_data.get('buffer_days', 0)
    duration_days = active_phase_data.get('duration_days', 0)
    start_day = active_phase_data.get('start_day', 0)
    
    is_in_buffer = False
    if duration_days is not None and current_day >= start_day + duration_days and current_day < start_day + duration_days + buffer_days:
        is_in_buffer = True

    # When in the buffer window, the phase remains the CURRENT phase, 
    # and limits are locked to the current phase's upper bound.
    ec_min = active_phase_data.get('ec', {}).get('min', 0)
    ec_max = active_phase_data.get('ec', {}).get('max', 0)
    ph_min = active_phase_data.get('ph', {}).get('min', 0)
    ph_max = active_phase_data.get('ph', {}).get('max', 0)

    if is_in_buffer:
        limits = {
            "ec": {"min": ec_max, "max": ec_max},
            "ph": {"min": ph_max, "max": ph_max}
        }
    else:
        limits = {
            "ec": active_phase_data.get('ec', {}),
            "ph": active_phase_data.get('ph', {})
        }

    if is_ml_valid:
        if ml_verification == "Aligned":
            ml_info = f"ML Vision confirms {ml_stage} phase. Growth is on track."
        elif ml_verification == "Growth Delay":
            ml_info = f"ML Vision detected '{ml_stage}'. Plant may be experiencing stunted growth."
        elif ml_verification == "Pending":
            ml_info = f"ML Vision detected '{ml_stage}'. Awaiting further confirmation."
        else:
            ml_info = f"ML Vision Model detected '{ml_stage}' (informational only; schedule dictates active limits)"
    else:
        ml_verification = "Unconfirmed"
        ml_info = f"ML Vision Model stage: '{ml_stage or 'Idle'}'"

    return {
        "scheduled_phase": scheduled_phase,
        "scheduled_idx": scheduled_idx,
        "active_phase": active_phase_name,
        "phase_source": phase_source,
        "active_phase_data": active_phase_data,
        "limits": limits,
        "normalized_stages": normalized,
        "ml_stage": ml_stage or "Idle",
        "ml_info": ml_info,
        "ml_verification": ml_verification
    }


def calculate_days_until_next_phase(stages, current_day, active_phase_name=None):
    """
    Derives the immediate next phase name and days remaining until transition.
    """
    normalized = normalize_stages(stages)
    if not normalized:
        return {
            "next_phase_name": "Unknown",
            "days_until_next_phase": None,
            "expected_transition_day": "Unknown",
            "next_milestone": "Unknown"
        }

    active_idx = 0
    if active_phase_name:
        for idx, (p_name, _) in enumerate(normalized):
            if p_name == active_phase_name:
                active_idx = idx
                break

    if active_idx + 1 < len(normalized):
        next_phase_name = normalized[active_idx + 1][0]
        next_start = normalized[active_idx + 1][1].get('start_day', 0)
        days_until_next = next_start - current_day
        if days_until_next < 0:
            days_until_next = 0
        expected_transition_day = f"Day {next_start} (in {days_until_next} day(s))"
        next_milestone = f"{next_phase_name} Phase (Day {next_start}) in {days_until_next} day(s)"
    else:
        next_phase_name = "Final Phase (Harvest)"
        expected_transition_day = "Harvest / End of Cycle"
        next_milestone = "Final Phase (All transitions complete)"
        days_until_next = None

    return {
        "next_phase_name": next_phase_name,
        "days_until_next_phase": days_until_next,
        "expected_transition_day": expected_transition_day,
        "next_milestone": next_milestone
    }


_cached_details = None
_last_evaluation_day = None

def get_active_grow_cycle_details(force_refresh=False):
    global _cached_details, _last_evaluation_day
    current_day_of_year = datetime.utcnow().timetuple().tm_yday
    
    if _cached_details is not None and not force_refresh and _last_evaluation_day == current_day_of_year:
        return _cached_details

    status = PlantStageStatus.query.first()
    if not status or not status.plant_name or not status.cycle_start_date:
        result = {
            "active": False,
            "day": 0,
            "phase": "None",
            "scheduled_phase": "None",
            "ml_stage": "Idle",
            "ml_info": "No active grow cycle.",
            "ml_verification": "Unconfirmed",
            "phase_source": "Schedule",
            "next_phase_name": "None",
            "expected_transition_day": "None",
            "days_until_next_phase": None,
            "advice": "No active grow cycle.",
            "limits": {},
            "is_automatic": False
        }
        _cached_details = result
        _last_evaluation_day = current_day_of_year
        return result
    
    preset = PlantPreset.query.filter_by(name=status.plant_name).first()
    if not preset:
        return {
            "active": True,
            "day": 0,
            "phase": "Unknown",
            "scheduled_phase": "Unknown",
            "ml_stage": status.plant_stage or "Idle",
            "ml_info": f"ML Vision Model stage: '{status.plant_stage or 'Idle'}'",
            "ml_verification": "Unconfirmed",
            "phase_source": "Schedule",
            "next_phase_name": "Unknown",
            "expected_transition_day": "Unknown",
            "days_until_next_phase": None,
            "advice": "Preset not found.",
            "limits": {},
            "is_automatic": status.state
        }
        
    try:
        stages = json.loads(preset.stages_json)
        if not isinstance(stages, dict):
            raise TypeError("Stages JSON must be a dictionary.")
    except (json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError):
        return {
            "active": True,
            "day": 0,
            "phase": "Error",
            "scheduled_phase": "Error",
            "ml_stage": status.plant_stage or "Idle",
            "ml_info": f"ML Vision Model stage: '{status.plant_stage or 'Idle'}'",
            "ml_verification": "Unconfirmed",
            "phase_source": "Schedule",
            "next_phase_name": "Error",
            "expected_transition_day": "Error",
            "days_until_next_phase": None,
            "advice": "Invalid preset configuration.",
            "limits": {},
            "is_automatic": status.state
        }

    start_date = status.cycle_start_date
    if start_date.tzinfo is not None:
        start_date = start_date.replace(tzinfo=None)
        
    current_day = (datetime.utcnow() - start_date).days
    if current_day < 0:
        current_day = 0

    stage_info = calculate_current_growth_stage(
        stages, 
        current_day, 
        ml_stage=status.plant_stage, 
        is_automatic=status.state
    )

    next_info = calculate_days_until_next_phase(
        stages, 
        current_day, 
        active_phase_name=stage_info["active_phase"]
    )

    active_phase_name = stage_info["active_phase"]
    active_phase_data = stage_info["active_phase_data"]

    advice = active_phase_data.get('advice')
    if not advice or advice in ('Maintain optimal conditions.', 'Maintain optimal conditions for this phase.'):
        ec_min = active_phase_data.get('ec', {}).get('min', 1.0)
        ec_max = active_phase_data.get('ec', {}).get('max', 2.0)
        ph_min = active_phase_data.get('ph', {}).get('min', 5.5)
        ph_max = active_phase_data.get('ph', {}).get('max', 6.8)
        
        lower_phase = active_phase_name.lower()
        if 'germ' in lower_phase or 'seed' in lower_phase:
            lighting = "18-24 hours of low-intensity light."
            watering = "Keep root zone moist; run low-volume automated watering cycles."
            nutrients = "Half-strength (diluted) vegetative nutrients."
        elif 'flower' in lower_phase or 'bloom' in lower_phase or 'fruit' in lower_phase:
            lighting = "12 hours of light / 12 hours of darkness."
            watering = "Normal automated feedback dosing; high water consumption expected."
            nutrients = "High phosphorus & potassium bloom nutrients."
        elif 'mature' in lower_phase or 'harvest' in lower_phase:
            lighting = "12 hours of light / 12 hours of darkness."
            watering = "Normal automated feedback dosing; taper off nutrient levels towards harvest."
            nutrients = "Low-to-moderate nutrient concentration."
        else:
            lighting = "18 hours of light / 6 hours of darkness."
            watering = "Continuous feedback-controlled dosing runs."
            nutrients = "Nitrogen-rich growth nutrients."

        advice = (
            f"Targets: pH {ph_min:.1f} - {ph_max:.1f} | EC {ec_min:.1f} - {ec_max:.1f} mS/cm. "
            f"Lighting: {lighting} "
            f"Nutrients: {nutrients} "
            f"Watering: {watering}"
        )

    result = {
        "active": True,
        "day": current_day,
        "phase": active_phase_name,
        "scheduled_phase": stage_info["scheduled_phase"],
        "ml_stage": status.plant_stage or "Idle",
        "ml_info": stage_info.get("ml_info", f"ML Vision Model stage: '{status.plant_stage or 'Idle'}'"),
        "ml_verification": stage_info.get("ml_verification", "Unconfirmed"),
        "phase_source": stage_info["phase_source"],
        "next_phase_name": next_info["next_phase_name"],
        "expected_transition_day": next_info["expected_transition_day"],
        "days_until_next_phase": next_info["days_until_next_phase"],
        "next_milestone": next_info["next_milestone"],
        "advice": advice,
        "limits": stage_info["limits"],
        "target_ph": round((float(stage_info["limits"].get("ph", {}).get("min", 5.5)) + float(stage_info["limits"].get("ph", {}).get("max", 6.5))) / 2.0, 2),
        "target_ec": round((float(stage_info["limits"].get("ec", {}).get("min", 1.0)) + float(stage_info["limits"].get("ec", {}).get("max", 2.0))) / 2.0, 2),
        "is_automatic": status.state
    }
    _cached_details = result
    _last_evaluation_day = current_day_of_year
    return result

def invalidate_cache():
    global _cached_details, _last_evaluation_day
    _cached_details = None
    _last_evaluation_day = None

