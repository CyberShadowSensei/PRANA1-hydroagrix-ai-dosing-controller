"""Test Suite: Dosing Configuration REST Endpoints
Verifies GET and POST for reservoir volumes, motor flow rates, and solution tank syncing.
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock

# Mock hardware dependencies before importing app
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

import hal
from config import app, db
from models import EventLog
from routes import *

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def test_get_dosing_config_default(client):
    with patch('os.path.exists', return_value=False):
        response = client.get('/api/dosing_config')
        assert response.status_code == 200
        data = response.json
        assert data['reservoir_volume_l'] == 50.0
        assert data['pump_flow_rate_ml_per_sec'] == 1.0
        assert data['dry_run_mode'] is False

def test_get_dosing_config_existing(client):
    mock_config = {
        "reservoir_volume_l": 100.0,
        "pump_flow_rate_ml_per_sec": 2.0,
        "dry_run_mode": True
    }
    with patch('os.path.exists', return_value=True):
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))):
            response = client.get('/api/dosing_config')
            assert response.status_code == 200
            data = response.json
            assert data['reservoir_volume_l'] == 100.0
            assert data['pump_flow_rate_ml_per_sec'] == 2.0
            assert data['dry_run_mode'] is True

def test_post_dosing_config(client):
    payload = {
        "reservoir_volume_l": 75.0,
        "dry_run_mode": True
    }
    
    # We mock open to verify that it writes the data
    m = mock_open()
    with patch('os.path.exists', return_value=False), \
         patch('os.replace'):
        with patch('builtins.open', m):
            response = client.post('/api/dosing_config', json=payload)
            assert response.status_code == 200
            assert response.json == {"message": "Dosing configuration updated"}
            
            # verify that the tmp file was written to
            m.assert_called_with("system_config.json.tmp", "w")

            
            # collect all strings written
            handle = m()
            written_data = "".join(call.args[0] for call in handle.write.call_args_list)
            
            # verify it contains our payload
            saved_config = json.loads(written_data)
            assert saved_config["reservoir_volume_l"] == 75.0
            assert saved_config["dry_run_mode"] is True

def test_dosing_config_post_input_validation(client):
    """Verify POST /api/dosing_config handles string numbers and partial updates correctly."""
    payload = {
        "reservoir_volume_l": 60,
        "nutrient_a_volume_ml": "2500.0"
    }
    m = mock_open()
    with patch('os.path.exists', return_value=False), \
         patch('os.replace'), \
         patch('builtins.open', m):
        response = client.post('/api/dosing_config', json=payload)
        assert response.status_code == 200
        assert response.json == {"message": "Dosing configuration updated"}

def test_dosing_config_post_solution_tanks_sync(client):
    """Verify POST /api/dosing_config synchronizes SolutionTanks table records for volume and capacity."""
    from models import SolutionTanks
    tank1 = SolutionTanks(tank_id=1, name="Nutrient A", current_volume_ml=1000.0, capacity_ml=5000.0)
    tank4 = SolutionTanks(tank_id=4, name="pH DOWN", current_volume_ml=500.0, capacity_ml=2000.0)
    db.session.add(tank1)
    db.session.add(tank4)
    db.session.commit()
    
    payload = {
        "nutrient_a_volume_ml": 2500.0,
        "nutrient_a_capacity_ml": 4000.0,
        "ph_down_volume_ml": 800.0
    }
    
    with patch('os.path.exists', return_value=False), \
         patch('os.replace'), \
         patch('builtins.open', mock_open()):
        response = client.post('/api/dosing_config', json=payload)
        assert response.status_code == 200
        
        t1 = SolutionTanks.query.filter_by(tank_id=1).first()
        assert t1.current_volume_ml == 2500.0
        assert t1.capacity_ml == 4000.0
        
        t4 = SolutionTanks.query.filter_by(tank_id=4).first()
        assert t4.current_volume_ml == 800.0
        assert t4.capacity_ml == 800.0

def test_manual_pump_start_stop_routes(client):
    """Verify POST /pump/<id>/start and /pump/<id>/stop routes control individual pumps and handle early stop."""
    with patch('hal.pump_start') as mock_start, \
         patch('hal.pump_stop') as mock_stop, \
         patch('dosing.request_dosing_cancellation') as mock_cancel:
        
        res1 = client.post('/pump/1/start', json={"duration": 10})
        assert res1.status_code == 200
        assert res1.json == {"message": "OK"}
        mock_start.assert_called_once_with(1)
        
        res2 = client.post('/pump/1/stop')
        assert res2.status_code == 200
        assert res2.json == {"message": "Stopped"}
        mock_cancel.assert_called_once()

def test_manual_pump_all_start_stop_routes(client):
    """Verify POST /pump/all/start and /pump/all/stop batch pump control routes."""
    with patch('hal.pump_start') as mock_start, \
         patch('hal.pump_stop') as mock_stop, \
         patch('dosing.request_dosing_cancellation') as mock_cancel:
        
        res1 = client.post('/pump/all/start', json={"duration": 5})
        assert res1.status_code == 200
        assert res1.json['message'] == "All pumps started"
        assert res1.json['status'] == "running"
        
        res2 = client.post('/pump/all/stop')
        assert res2.status_code == 200
        assert res2.json['message'] == "All pumps stopped"
        assert res2.json['status'] == "stopped"
        mock_cancel.assert_called_once()

def test_manual_pump_invalid_id(client):
    """Verify /pump/<id>/start with invalid pump ID returns 200 without calling pump_start."""
    with patch('hal.pump_start') as mock_start:
        res = client.post('/pump/99/start', json={"duration": 5})
        assert res.status_code == 200
        mock_start.assert_not_called()

def test_refill_tank_route(client):
    """Verify /refill_tank POST resets volume to capacity, clears last_alert_sent, and handles missing/invalid IDs."""
    from models import SolutionTanks
    tank = SolutionTanks(tank_id=1, name="Nutrient A", current_volume_ml=100.0, capacity_ml=3000.0, last_alert_sent=1000.0)
    db.session.add(tank)
    db.session.commit()
    
    res_bad = client.post('/refill_tank', json={})
    assert res_bad.status_code == 400
    assert res_bad.json['error'] == "tank_id required"
    
    res_nf = client.post('/refill_tank', json={"tank_id": 999})
    assert res_nf.status_code == 404
    assert res_nf.json['error'] == "tank not found"
    
    res_ok = client.post('/refill_tank', json={"tank_id": 1})
    assert res_ok.status_code == 200
    assert res_ok.json['current_volume_ml'] == 3000.0
    assert res_ok.json['last_alert_sent'] == 0.0

def test_system_config_get_post_routes(client):
    """Verify GET /get_system_config and POST /update_system_config routes."""
    with patch('os.path.exists', return_value=False):
        res_get = client.get('/get_system_config')
        assert res_get.status_code == 200
        assert res_get.json == {"manual_location": None}
        
    mock_conf = {"reservoir_volume_l": 50.0}
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data=json.dumps(mock_conf))):
        res_get2 = client.get('/get_system_config')
        assert res_get2.status_code == 200
        assert res_get2.json['reservoir_volume_l'] == 50.0

    with patch('dosing.save_system_config') as mock_save, \
         patch('os.path.exists', return_value=False):
        res_post = client.post('/update_system_config', json={"reservoir_volume_l": 80.0})
        assert res_post.status_code == 200
        assert res_post.json['message'] == "System configuration updated"
        mock_save.assert_called_once_with({"reservoir_volume_l": 80.0})

def test_pump_priming_route(client):
    """Verify POST /api/pumps/prime starts priming when idle and returns 400 when active."""
    import dosing
    dosing.is_priming_active = False
    
    with patch('routes._prime_pumps_thread'):
        res1 = client.post('/api/pumps/prime')
        assert res1.status_code == 200
        assert res1.json['message'] == "Priming started"
        assert dosing.is_priming_active is True
        
        res2 = client.post('/api/pumps/prime')
        assert res2.status_code == 400
        assert res2.json['error'] == "Priming is already active"
        
    dosing.is_priming_active = False

