import os
import sys
import json
import pytest
import numpy as np
from unittest.mock import patch, MagicMock, ANY

# Mock hardware dependencies before importing app
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

import hal
import camera_ml
from config import app, db
from models import PlantStageStatus, PlantPreset, PresetAuditLog
from routes import *

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            
            # Setup a default PlantStageStatus row which routes.py assumes exists
            status = PlantStageStatus(
                plant_name="",
                plant_stage="Idle",
                state=False
            )
            db.session.add(status)
            db.session.commit()
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_get_plant_status(client):
    response = client.get('/get_plant_status')
    assert response.status_code == 200
    data = response.json
    assert data["plant_name"] == ""
    assert data["plant_stage"] == "Idle"
    assert data["state"] is False

@patch('config.socketio.emit')
def test_update_plant_status(mock_emit, client):
    # Set active plant first as grow cycle is mandatory for mode config
    status = PlantStageStatus.query.first()
    status.plant_name = "Tomato"
    status.cycle_start_date = datetime.utcnow()
    db.session.commit()

    response = client.post('/update_plant_status', json={"state": True})
    assert response.status_code == 200
    data = response.json
    assert data["state"] is True
    
    status = PlantStageStatus.query.first()
    assert status.state is True
    mock_emit.assert_called_with('grow_cycle_update', ANY)
    # Check the call args directly
    event_name = mock_emit.call_args[0][0]
    cycle_data = mock_emit.call_args[0][1]
    assert event_name == 'grow_cycle_update'
    assert cycle_data['active'] is True

@patch('config.socketio.emit')
def test_set_active_plant(mock_emit, client):
    # First create a preset
    preset = PlantPreset(
        name="Tomato",
        image_url="/images/logo.jpg",
        stages_json=json.dumps({
            "Vegetative": {"start_day": 0},
            "Flowering": {"start_day": 14}
        })
    )
    db.session.add(preset)
    db.session.commit()
    
    response = client.post('/set_active_plant', json={"plant_name": "Tomato"})
    assert response.status_code == 200
    data = response.json
    assert data["plant_name"] == "Tomato"
    assert data["plant_stage"] == "Vegetative"  # First stage
    mock_emit.assert_called_with('grow_cycle_update', ANY)
    assert mock_emit.call_args[0][0] == 'grow_cycle_update'

@patch('config.socketio.emit')
@patch('reporting.generate_cycle_report')
def test_complete_cycle(mock_report, mock_emit, client):
    # Setup active plant
    status = PlantStageStatus.query.first()
    status.plant_name = "Tomato"
    status.plant_stage = "Vegetative"
    status.state = True
    db.session.commit()
    
    response = client.post('/complete_cycle')
    assert response.status_code == 200
    assert response.json == {"message": "Cycle completed successfully."}
    
    status = PlantStageStatus.query.first()
    assert status.plant_name == ""
    assert status.plant_stage == "Idle"
    # Decoupled: completing cycle does not reset state (mode) to False
    assert status.state is True
    mock_report.assert_called_once_with("Completed")
    mock_emit.assert_called_with('grow_cycle_update', ANY)
    assert mock_emit.call_args[0][0] == 'grow_cycle_update'

def test_complete_cycle_no_active(client):
    response = client.post('/complete_cycle')
    assert response.status_code == 400
    assert response.json == {"error": "No active cycle to complete."}

def test_presets_crud(client):
    # 1. Create a preset
    payload = {
        "name": "Pepper",
        "image_url": "pepper.jpg",
        "Vegetative": {"min_ph": 5.5},
        "Flowering": {"min_ph": 6.0},
        "Maturity": {"min_ph": 6.5}
    }
    response = client.post('/api/presets', json=payload)
    assert response.status_code == 201
    
    presets = PlantPreset.query.all()
    assert len(presets) == 1
    assert presets[0].name == "Pepper"
    
    # Check audit log
    logs = PresetAuditLog.query.all()
    assert len(logs) == 1
    assert logs[0].preset_name == "Pepper"
    assert logs[0].action == "Created"
    
    # 2. Get presets
    response = client.get('/api/presets')
    assert response.status_code == 200
    data = response.json
    assert len(data) == 1
    assert data[0]["name"] == "Pepper"
    assert data[0]["image"] == "pepper.jpg"
    
    preset_id = data[0]["id"]
    
    # 3. Update preset
    update_payload = {
        "name": "Hot Pepper",
        "image_url": "hot_pepper.jpg",
        "Vegetative": {"min_ph": 5.8},
        "Flowering": {"min_ph": 6.2},
        "Maturity": {"min_ph": 6.8}
    }
    response = client.put(f'/api/presets/{preset_id}', json=update_payload)
    assert response.status_code == 200
    
    preset = db.session.get(PlantPreset, preset_id)
    assert preset.name == "Hot Pepper"
    
    # 4. Get logs
    response = client.get('/api/preset_logs')
    assert response.status_code == 200
    logs = response.json
    assert len(logs) == 2
    assert logs[0]["action"] == "Updated"
    assert logs[1]["action"] == "Created"
    
    # 5. Delete preset
    response = client.delete(f'/api/presets/{preset_id}')
    assert response.status_code == 200
    
    presets = PlantPreset.query.all()
    assert len(presets) == 0

@patch('camera_ml.cv2')
@patch('camera_ml.get_latest_frame')
@patch('camera_ml.time.sleep', side_effect=[None, RuntimeError("Stop thread")])
@patch('config.socketio.emit')
def test_camera_ml_stage_transition_emit(mock_emit, mock_sleep, mock_get_frame, mock_cv2, client):
    import numpy as np
    from datetime import datetime
    import camera_ml
    from camera_ml import plant_monitor_thread
    
    camera_ml.plant_monitor_running = True
    
    mock_cv2.COLOR_BGR2GRAY = 6
    mock_cv2.COLOR_BGR2HSV = 40
    mock_cv2.cvtColor.side_effect = lambda f, code: np.full((480, 640), 100, dtype=np.uint8) if code == 6 else np.full((480, 640, 3), 50, dtype=np.uint8)
    mock_cv2.inRange.return_value = np.ones((480, 640), dtype=np.uint8) * 255
    
    # Setup active plant with state=True
    status = PlantStageStatus.query.first()
    status.plant_name = "Tomato"
    status.plant_stage = "Seedling"
    status.state = True
    status.cycle_start_date = datetime.utcnow()
    
    preset = PlantPreset(
        name="Tomato",
        image_url="/images/logo.jpg",
        stages_json=json.dumps({
            "Seedling": {"start_day": 0},
            "Vegetative": {"start_day": 10},
            "Flowering": {"start_day": 25}
        })
    )
    db.session.add(preset)
    db.session.commit()
    
    # Create dummy frame
    mock_get_frame.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    
    try:
        with pytest.raises(RuntimeError, match="Stop thread"):
            plant_monitor_thread()
    finally:
        camera_ml.plant_monitor_running = False
        
    status = PlantStageStatus.query.first()

    assert status.plant_stage == "Flowering"
    mock_emit.assert_called_with('grow_cycle_update', ANY)
    assert mock_emit.call_args[0][0] == 'grow_cycle_update'

def test_sensor_limits_includes_effective_autonomous_limits(client):
    response = client.get('/sensor/limits')
    assert response.status_code == 200
    data = response.json
    assert "autonomous_limits" in data

def test_preset_crud_non_existent_id(client):
    # Non-existent integer ID 99999 for PUT and DELETE
    put_response = client.put('/api/presets/99999', json={"name": "NonExistent"})
    assert put_response.status_code == 404

    delete_response = client.delete('/api/presets/99999')
    assert delete_response.status_code == 404

def test_preset_crud_invalid_type_id(client):
    # Invalid non-integer ID path parameters
    put_str_res = client.put('/api/presets/invalid_id', json={"name": "Test"})
    assert put_str_res.status_code == 404

    delete_str_res = client.delete('/api/presets/invalid_id')
    assert delete_str_res.status_code == 404

    put_float_res = client.put('/api/presets/12.34', json={"name": "Test"})
    assert put_float_res.status_code == 404

    delete_float_res = client.delete('/api/presets/12.34')
    assert delete_float_res.status_code == 404

def test_preset_crud_deleted_id(client):
    # 1. Create a preset
    payload = {
        "name": "Basil",
        "image_url": "basil.jpg",
        "Vegetative": {"min_ph": 5.5}
    }
    post_res = client.post('/api/presets', json=payload)
    assert post_res.status_code == 201

    presets = PlantPreset.query.all()
    assert len(presets) == 1
    preset_id = presets[0].id

    # 2. Verify db.session.get works for valid ID
    with app.app_context():
        p = db.session.get(PlantPreset, preset_id)
        assert p is not None
        assert p.name == "Basil"

    # 3. Delete the preset
    del_res = client.delete(f'/api/presets/{preset_id}')
    assert del_res.status_code == 200

    # 4. Verify db.session.get returns None for deleted ID
    with app.app_context():
        p_deleted = db.session.get(PlantPreset, preset_id)
        assert p_deleted is None

    # 5. Subsequent PUT on deleted ID returns 404
    put_del_res = client.put(f'/api/presets/{preset_id}', json={"name": "Basil Updated"})
    assert put_del_res.status_code == 404

    # 6. Subsequent DELETE on deleted ID returns 404
    del_again_res = client.delete(f'/api/presets/{preset_id}')
    assert del_again_res.status_code == 404

def test_post_preset_3phase_nested(client):
    """Test POST /api/presets with canonical 3-Phase nested under 'stages' key."""
    payload = {
        "name": "Tomato 3-Phase Nested",
        "image_url": "/images/tomato.jpg",
        "stages": {
            "Seedling": {"duration_days": 10, "ec": {"min": 0.8, "max": 1.2}, "ph": {"min": 5.8, "max": 6.2}},
            "Vegetative": {"duration_days": 25, "ec": {"min": 1.4, "max": 2.0}, "ph": {"min": 5.8, "max": 6.5}},
            "Harvesting": {"duration_days": 20, "ec": {"min": 1.8, "max": 2.4}, "ph": {"min": 6.0, "max": 6.5}}
        }
    }
    res = client.post('/api/presets', json=payload)
    assert res.status_code == 201

    preset = PlantPreset.query.filter_by(name="Tomato 3-Phase Nested").first()
    assert preset is not None
    stages = json.loads(preset.stages_json)

    assert "Seedling" in stages
    assert "Vegetative" in stages
    assert "Harvesting" in stages

    assert stages["Seedling"]["start_day"] == 0
    assert stages["Seedling"]["duration_days"] == 10

    assert stages["Vegetative"]["start_day"] == 10
    assert stages["Vegetative"]["duration_days"] == 25

    assert stages["Harvesting"]["start_day"] == 35
    assert stages["Harvesting"]["duration_days"] == 20

def test_post_preset_3phase_flat(client):
    """Test POST /api/presets with canonical 3-Phase keys at top level."""
    payload = {
        "name": "Strawberry Flat",
        "image_url": "/images/strawberry.jpg",
        "Seedling": {"duration_days": 12, "ec": {"min": 0.8, "max": 1.2}},
        "Vegetative": {"duration_days": 18, "ec": {"min": 1.2, "max": 1.8}},
        "Harvesting": {"duration_days": 30, "ec": {"min": 1.5, "max": 2.2}}
    }
    res = client.post('/api/presets', json=payload)
    assert res.status_code == 201

    preset = PlantPreset.query.filter_by(name="Strawberry Flat").first()
    assert preset is not None
    stages = json.loads(preset.stages_json)

    assert stages["Seedling"]["start_day"] == 0
    assert stages["Seedling"]["duration_days"] == 12

    assert stages["Vegetative"]["start_day"] == 12
    assert stages["Vegetative"]["duration_days"] == 18

    assert stages["Harvesting"]["start_day"] == 30
    assert stages["Harvesting"]["duration_days"] == 30

def test_post_preset_default_durations_and_type_coercion(client):
    """Test POST /api/presets with missing durations and string duration coercion."""
    payload = {
        "name": "Coerced Durations Plant",
        "Seedling": {"duration_days": "14"},
        "Vegetative": {},  # missing -> default 25
        "Harvesting": {"duration_days": "invalid_number"}  # invalid -> default 20
    }
    res = client.post('/api/presets', json=payload)
    assert res.status_code == 201

    preset = PlantPreset.query.filter_by(name="Coerced Durations Plant").first()
    stages = json.loads(preset.stages_json)

    assert stages["Seedling"]["duration_days"] == 14
    assert stages["Seedling"]["start_day"] == 0

    assert stages["Vegetative"]["duration_days"] == 25
    assert stages["Vegetative"]["start_day"] == 14

    assert stages["Harvesting"]["duration_days"] == 20
    assert stages["Harvesting"]["start_day"] == 39  # 14 + 25

def test_put_preset_updates_durations_and_recalculates_start_days(client):
    """Test PUT /api/presets/<id> updates durations and recalculates cumulative start_days."""
    create_res = client.post('/api/presets', json={
        "name": "Lettuce Initial",
        "Seedling": {"duration_days": 10},
        "Vegetative": {"duration_days": 20},
        "Harvesting": {"duration_days": 15}
    })
    assert create_res.status_code == 201

    preset = PlantPreset.query.filter_by(name="Lettuce Initial").first()
    preset_id = preset.id

    put_res = client.put(f'/api/presets/{preset_id}', json={
        "name": "Lettuce Updated",
        "image_url": "/images/lettuce.jpg",
        "stages": {
            "Seedling": {"duration_days": 7},
            "Vegetative": {"duration_days": 14},
            "Harvesting": {"duration_days": 21}
        }
    })
    assert put_res.status_code == 200

    updated = db.session.get(PlantPreset, preset_id)
    assert updated.name == "Lettuce Updated"
    stages = json.loads(updated.stages_json)

    assert stages["Seedling"]["duration_days"] == 7
    assert stages["Seedling"]["start_day"] == 0

    assert stages["Vegetative"]["duration_days"] == 14
    assert stages["Vegetative"]["start_day"] == 7

    assert stages["Harvesting"]["duration_days"] == 21
    assert stages["Harvesting"]["start_day"] == 21


def test_update_grow_cycle_progress_success(client):
    """Verifies POST /update_grow_cycle_progress updates active cycle start date and plant stage."""
    preset = PlantPreset(
        name="Tomato",
        image_url="/images/tomato.jpg",
        stages_json=json.dumps({
            "Seedling": {"duration_days": 10, "start_day": 0},
            "Vegetative": {"duration_days": 25, "start_day": 10},
            "Harvesting": {"duration_days": 20, "start_day": 35}
        })
    )
    db.session.add(preset)
    
    status = PlantStageStatus.query.first()
    status.plant_name = "Tomato"
    status.plant_stage = "Seedling"
    status.cycle_start_date = datetime.utcnow()
    db.session.commit()

    # Update progress to Day 15, Vegetative stage
    res = client.post('/update_grow_cycle_progress', json={"day": 15, "plant_stage": "Vegetative"})
    assert res.status_code == 200
    data = res.json
    assert data["status"] == "success"
    assert data["current_day"] == 15
    assert data["plant_stage"] == "Vegetative"

    # Verify DB state
    status_db = PlantStageStatus.query.first()
    assert status_db.plant_stage == "Vegetative"
    days_diff = (datetime.utcnow() - status_db.cycle_start_date).days
    assert days_diff == 15


def test_update_grow_cycle_progress_phase_and_alias_routes(client):
    """Verifies POST /update_grow_cycle_progress accepts 'phase' alias and alias route paths."""
    preset = PlantPreset(
        name="Lettuce",
        image_url="/images/lettuce.jpg",
        stages_json=json.dumps({
            "Seedling": {"duration_days": 5, "start_day": 0},
            "Vegetative": {"duration_days": 15, "start_day": 5},
            "Harvesting": {"duration_days": 10, "start_day": 20}
        })
    )
    db.session.add(preset)
    
    status = PlantStageStatus.query.first()
    status.plant_name = "Lettuce"
    status.plant_stage = "Seedling"
    status.cycle_start_date = datetime.utcnow()
    db.session.commit()

    # Test alias route /update-grow-cycle-progress with payload 'phase'
    res = client.post('/update-grow-cycle-progress', json={"day": 22, "phase": "Harvesting"})
    assert res.status_code == 200
    data = res.json
    assert data["status"] == "success"
    assert data["current_day"] == 22
    assert data["plant_stage"] == "Harvesting"


def test_update_grow_cycle_progress_inferred_stage(client):
    """Verifies POST /update_grow_cycle_progress infers stage if plant_stage/phase is omitted."""
    preset = PlantPreset(
        name="Basil",
        image_url="/images/basil.jpg",
        stages_json=json.dumps({
            "Seedling": {"duration_days": 7, "start_day": 0},
            "Vegetative": {"duration_days": 21, "start_day": 7},
            "Harvesting": {"duration_days": 14, "start_day": 28}
        })
    )
    db.session.add(preset)
    
    status = PlantStageStatus.query.first()
    status.plant_name = "Basil"
    status.plant_stage = "Seedling"
    status.cycle_start_date = datetime.utcnow()
    db.session.commit()

    # Pass day=10 without stage -> should infer Vegetative (7..27)
    res = client.post('/update_grow_cycle_progress', json={"day": 10})
    assert res.status_code == 200
    data = res.json
    assert data["current_day"] == 10
    assert data["plant_stage"] == "Vegetative"


def test_update_grow_cycle_progress_error_handling(client):
    """Verifies error handling for no active cycle and invalid day inputs."""
    # 1. No active cycle (plant_name is empty)
    status = PlantStageStatus.query.first()
    status.plant_name = ""
    db.session.commit()

    res = client.post('/update_grow_cycle_progress', json={"day": 10, "plant_stage": "Vegetative"})
    assert res.status_code == 400
    assert "error" in res.json

    # Set active cycle for input validation testing
    status.plant_name = "Tomato"
    db.session.commit()

    # 2. Missing day
    res_no_day = client.post('/update_grow_cycle_progress', json={"plant_stage": "Vegetative"})
    assert res_no_day.status_code == 400

    # 3. Negative day
    res_neg_day = client.post('/update_grow_cycle_progress', json={"day": -5, "plant_stage": "Vegetative"})
    assert res_neg_day.status_code == 400

    # 4. Non-integer day
    res_invalid_day = client.post('/update_grow_cycle_progress', json={"day": "abc", "plant_stage": "Vegetative"})
    assert res_invalid_day.status_code == 400


def test_update_grow_cycle_progress_strict_preset_immutability(client):
    """
    STRICT IMMUTABILITY TEST: Verifies POST /update_grow_cycle_progress NEVER alters or mutates
    any PlantPreset database records.
    """
    stages_original_dict = {
        "Seedling": {"duration_days": 10, "start_day": 0, "ec": {"min": 0.8, "max": 1.2}},
        "Vegetative": {"duration_days": 25, "start_day": 10, "ec": {"min": 1.4, "max": 2.0}},
        "Harvesting": {"duration_days": 20, "start_day": 35, "ec": {"min": 1.8, "max": 2.4}}
    }
    stages_original_json = json.dumps(stages_original_dict)
    
    preset = PlantPreset(
        name="Strawberry Immutable",
        image_url="/images/strawberry.jpg",
        stages_json=stages_original_json
    )
    db.session.add(preset)
    db.session.commit()

    preset_id = preset.id
    initial_preset_count = PlantPreset.query.count()

    status = PlantStageStatus.query.first()
    status.plant_name = "Strawberry Immutable"
    status.plant_stage = "Seedling"
    status.cycle_start_date = datetime.utcnow()
    db.session.commit()

    # Perform multiple progress updates across different days and stages
    client.post('/update_grow_cycle_progress', json={"day": 5, "plant_stage": "Seedling"})
    client.post('/update_grow_cycle_progress', json={"day": 18, "plant_stage": "Vegetative"})
    client.post('/update_grow_cycle_progress', json={"day": 40, "plant_stage": "Harvesting"})

    # Verify PlantPreset records in database
    preset_after = db.session.get(PlantPreset, preset_id)
    assert preset_after is not None
    assert preset_after.name == "Strawberry Immutable"
    assert preset_after.image_url == "/images/strawberry.jpg"
    assert preset_after.stages_json == stages_original_json
    assert PlantPreset.query.count() == initial_preset_count






def test_change_grow_cycle_phase_endpoint(client):
    """Test manual transition forward and backward through growth cycle phases."""
    with app.app_context():
        # Set active preset to Basil with Seedling/Vegetative/Maturity stages
        preset = PlantPreset(
            name="Tulsi/Basil",
            image_url="/images/tulsi.jpg",
            stages_json=json.dumps({
                "Seedling": {"duration_days": 14, "start_day": 1},
                "Vegetative": {"duration_days": 21, "start_day": 15},
                "Maturity": {"duration_days": 30, "start_day": 36}
            }),
            is_continuous_harvest=False,
            is_builtin=True
        )
        db.session.add(preset)
        s = PlantStageStatus.query.first()
        s.plant_name = "Tulsi/Basil"
        s.plant_stage = "Seedling"
        db.session.commit()

    # Transition to next phase (Vegetative)
    res = client.post('/api/grow_cycle/change_phase', json={"direction": "next"})
    assert res.status_code == 200
    data = res.get_json()
    assert "Vegetative" in data["message"]

    with app.app_context():
        db.session.expire_all()
        s = PlantStageStatus.query.first()
        assert s.plant_stage == "Vegetative"

    # Transition to previous phase (Seedling)
    res_prev = client.post('/api/grow_cycle/change_phase', json={"direction": "prev"})
    assert res_prev.status_code == 200
    with app.app_context():
        db.session.expire_all()
        s = PlantStageStatus.query.first()
        assert s.plant_stage == "Seedling"
