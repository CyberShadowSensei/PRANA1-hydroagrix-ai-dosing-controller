import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import json

# Mock hardware dependencies before importing app
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()
try:
    import cv2
except ImportError:
    sys.modules['cv2'] = MagicMock()

import hal
from config import app, db
from models import PlantStageStatus, PlantPreset
from routes import s_active_plant, complete_cycle
from grow_cycle_helper import get_active_grow_cycle_details

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def test_no_active_cycle(client):
    details = get_active_grow_cycle_details()
    assert details["active"] == False
    assert details["phase"] == "None"
    assert details["scheduled_phase"] == "None"
    assert details["ml_stage"] == "Idle"
    assert details["phase_source"] == "Schedule"
    assert details["next_phase_name"] == "None"
    assert details["expected_transition_day"] == "None"
    assert details["is_automatic"] == False

def test_defensive_parsing(client):
    status = PlantStageStatus(plant_name="Tomato", plant_stage="Vegetative", state=True, cycle_start_date=datetime.utcnow())
    db.session.add(status)
    preset = PlantPreset(name="Tomato", image_url="", stages_json="{invalid json")
    db.session.add(preset)
    db.session.commit()

    details = get_active_grow_cycle_details()
    assert details["phase"] == "Error"
    assert details["scheduled_phase"] == "Error"
    assert details["next_phase_name"] == "Error"
    assert details["expected_transition_day"] == "Error"
    assert details["active"] == True
    assert details["advice"] == "Invalid preset configuration."

def test_preset_not_found(client):
    status = PlantStageStatus(plant_name="UnknownPlant", plant_stage="Vegetative", state=True, cycle_start_date=datetime.utcnow())
    db.session.add(status)
    db.session.commit()

    details = get_active_grow_cycle_details()
    assert details["active"] == True
    assert details["phase"] == "Unknown"
    assert details["scheduled_phase"] == "Unknown"
    assert details["next_phase_name"] == "Unknown"
    assert details["expected_transition_day"] == "Unknown"
    assert details["advice"] == "Preset not found."

def test_phase_calculation_boundary(client):
    start_date = datetime.utcnow() - timedelta(days=21)
    status = PlantStageStatus(plant_name="Tomato", plant_stage="Idle", state=False, cycle_start_date=start_date)
    db.session.add(status)
    
    stages = {
        "Vegetative": {"start_day": 0, "advice": "Veg"},
        "Flowering": {"start_day": 21, "advice": "Flower"}
    }
    preset = PlantPreset(name="Tomato", image_url="", stages_json=json.dumps(stages))
    db.session.add(preset)
    db.session.commit()

    details = get_active_grow_cycle_details()
    assert details["phase"] == "Flowering"
    assert details["scheduled_phase"] == "Flowering"
    assert details["phase_source"] == "Schedule"
    assert details["advice"] == "Flower"

def test_ml_stage_override_and_phase_source(client):
    start_date = datetime.utcnow() - timedelta(days=21)
    # Schedule phase is Flowering (day 21), ML stage is Vegetative and state is True (automatic)
    # Schedule ALWAYS dictates active phase and limits
    status = PlantStageStatus(plant_name="Tomato", plant_stage="Vegetative", state=True, cycle_start_date=start_date)
    db.session.add(status)
    
    stages = {
        "Vegetative": {"start_day": 0, "advice": "Veg"},
        "Flowering": {"start_day": 21, "advice": "Flower"}
    }
    preset = PlantPreset(name="Tomato", image_url="", stages_json=json.dumps(stages))
    db.session.add(preset)
    db.session.commit()

    details = get_active_grow_cycle_details()
    assert details["phase"] == "Flowering"  # Schedule takes precedence, NOT overridden by ML
    assert details["scheduled_phase"] == "Flowering"
    assert details["phase_source"] == "Schedule"
    assert details["ml_stage"] == "Vegetative"
    assert "Vegetative" in details["ml_info"]
    assert details["is_automatic"] == True

    # Case 2: ML stage matches scheduled stage
    status.plant_stage = "Flowering"
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["phase"] == "Flowering"
    assert details["scheduled_phase"] == "Flowering"
    assert details["phase_source"] == "Schedule"
    assert details["ml_stage"] == "Flowering"

    # Case 3: Automatic mode disabled (state=False) -> Schedule takes precedence
    status.state = False
    status.plant_stage = "Vegetative"
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["phase"] == "Flowering"
    assert details["scheduled_phase"] == "Flowering"
    assert details["phase_source"] == "Schedule"
    assert details["is_automatic"] == False

def test_final_phase_indefinitely(client):
    start_date = datetime.utcnow() - timedelta(days=50)
    status = PlantStageStatus(plant_name="Tomato", plant_stage="Idle", state=False, cycle_start_date=start_date)
    db.session.add(status)
    
    stages = {
        "Vegetative": {"start_day": 0},
        "Flowering": {"start_day": 21},
        "Maturity": {"start_day": 40, "advice": "Mature"}
    }
    preset = PlantPreset(name="Tomato", image_url="", stages_json=json.dumps(stages))
    db.session.add(preset)
    db.session.commit()

    details = get_active_grow_cycle_details()
    assert details["phase"] == "Maturity"
    assert details["scheduled_phase"] == "Maturity"
    assert details["next_phase_name"] == "Final Phase (Harvest)"
    assert details["expected_transition_day"] == "Harvest / End of Cycle"
    assert details["days_until_next_phase"] is None

@patch('reporting.generate_cycle_report')
def test_route_interruption(mock_report, client):
    status = PlantStageStatus(plant_name="Tomato", plant_stage="Vegetative", state=True, cycle_start_date=datetime.utcnow() - timedelta(days=5))
    db.session.add(status)
    preset = PlantPreset(name="Lettuce", image_url="", stages_json='{"Seedling": {"start_day": 0}}')
    db.session.add(preset)
    db.session.commit()
    
    old_start_date = status.cycle_start_date

    response = client.post('/set_active_plant', json={"plant_name": "Lettuce"})
    assert response.status_code == 200
    
    status = PlantStageStatus.query.first()
    assert status.plant_name == "Lettuce"
    assert status.plant_stage == "Seedling"
    assert status.cycle_start_date > old_start_date
    mock_report.assert_called_once_with("Interrupted")

@patch('reporting.generate_cycle_report')
def test_route_completion(mock_report, client):
    status = PlantStageStatus(plant_name="Tomato", plant_stage="Flowering", state=True, cycle_start_date=datetime.utcnow() - timedelta(days=25))
    db.session.add(status)
    db.session.commit()

    response = client.post('/complete_cycle')
    assert response.status_code == 200

    status = PlantStageStatus.query.first()
    assert status.plant_name == ""
    assert status.plant_stage == "Idle"
    mock_report.assert_called_once_with("Completed")

def test_3_phase_duration_stage_resolution(client):
    """
    Verifies 3-phase stage calculation based on explicit duration_days
    and cumulative start_day (Seedling, Vegetative, Harvesting).
    """
    stages = {
        "Seedling": {"duration_days": 10, "start_day": 0, "ec": {"min": 0.8, "max": 1.2}, "ph": {"min": 5.8, "max": 6.2}},
        "Vegetative": {"duration_days": 25, "start_day": 10, "ec": {"min": 1.4, "max": 2.0}, "ph": {"min": 5.8, "max": 6.5}},
        "Harvesting": {"duration_days": 20, "start_day": 35, "ec": {"min": 1.8, "max": 2.4}, "ph": {"min": 6.0, "max": 6.5}}
    }
    preset = PlantPreset(name="Tomato 3Phase", image_url="", stages_json=json.dumps(stages))
    db.session.add(preset)
    
    # Day 0: Seedling
    status = PlantStageStatus(plant_name="Tomato 3Phase", plant_stage="Idle", state=False, cycle_start_date=datetime.utcnow() - timedelta(days=0))
    db.session.add(status)
    db.session.commit()

    details = get_active_grow_cycle_details()
    assert details["active"] is True
    assert details["day"] == 0
    assert details["phase"] == "Seedling"
    assert details["scheduled_phase"] == "Seedling"
    assert details["next_phase_name"] == "Vegetative"
    assert details["days_until_next_phase"] == 10

    # Day 10: Transition to Vegetative
    status.cycle_start_date = datetime.utcnow() - timedelta(days=10)
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["day"] == 10
    assert details["phase"] == "Vegetative"
    assert details["scheduled_phase"] == "Vegetative"
    assert details["next_phase_name"] == "Harvesting"
    assert details["days_until_next_phase"] == 25  # start_day 35 - day 10

    # Day 25: Mid-Vegetative
    status.cycle_start_date = datetime.utcnow() - timedelta(days=25)
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["day"] == 25
    assert details["phase"] == "Vegetative"
    assert details["days_until_next_phase"] == 10  # 35 - 25

    # Day 35: Transition to Harvesting
    status.cycle_start_date = datetime.utcnow() - timedelta(days=35)
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["day"] == 35
    assert details["phase"] == "Harvesting"
    assert details["scheduled_phase"] == "Harvesting"
    assert details["next_phase_name"] == "Final Phase (Harvest)"
    assert details["days_until_next_phase"] is None

    # Day 60: Post-harvest indefinitely in Harvesting phase
    status.cycle_start_date = datetime.utcnow() - timedelta(days=60)
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["day"] == 60
    assert details["phase"] == "Harvesting"
    assert details["days_until_next_phase"] is None


def test_3_phase_cumulative_start_day_inference(client):
    """
    Verifies stage resolution when duration_days is provided without explicit start_day.
    """
    stages = {
        "Seedling": {"duration_days": 7},
        "Vegetative": {"duration_days": 21},
        "Harvesting": {"duration_days": 14}
    }
    preset = PlantPreset(name="Basil AutoStart", image_url="", stages_json=json.dumps(stages))
    db.session.add(preset)
    
    status = PlantStageStatus(plant_name="Basil AutoStart", plant_stage="Idle", state=False, cycle_start_date=datetime.utcnow() - timedelta(days=5))
    db.session.add(status)
    db.session.commit()

    # Day 5 -> Seedling (0..6)
    details = get_active_grow_cycle_details()
    assert details["phase"] == "Seedling"
    assert details["days_until_next_phase"] == 2  # 7 - 5

    # Day 7 -> Vegetative (7..27)
    status.cycle_start_date = datetime.utcnow() - timedelta(days=7)
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["phase"] == "Vegetative"
    assert details["days_until_next_phase"] == 21  # 28 - 7

    # Day 28 -> Harvesting (28+)
    status.cycle_start_date = datetime.utcnow() - timedelta(days=28)
    db.session.commit()
    details = get_active_grow_cycle_details()
    assert details["phase"] == "Harvesting"
    assert details["next_phase_name"] == "Final Phase (Harvest)"
    assert details["days_until_next_phase"] is None


