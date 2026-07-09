import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Mock hardware dependencies before importing app
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

import hal
from config import app, db
from models import SensorLimits, EventLog
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

def test_get_sensor_limits_empty(client):
    response = client.get('/sensor/limits')
    assert response.status_code == 200
    assert response.json == {}

def test_post_sensor_limits(client):
    payload = {
        "ph": {"min": 5.5, "max": 6.5, "active": True},
        "tds": {"min": 1.0, "max": 2.0, "active": False}
    }
    response = client.post('/sensor/limits', json=payload)
    assert response.status_code == 200
    assert response.json == {"message": "Saved"}

    response = client.get('/sensor/limits')
    data = response.json
    assert "ph" in data
    assert data["ph"]["min"] == 5.5
    assert data["ph"]["max"] == 6.5
    assert data["ph"]["active"] is True
    assert "tds" in data
    assert data["tds"]["min"] == 1.0
    assert data["tds"]["max"] == 2.0
    assert data["tds"]["active"] is False

@patch('hal.pump_start')
@patch('routes.log_pump_action')
@patch('threading.Thread')
def test_pump_start(mock_thread, mock_log, mock_start, client):
    response = client.post('/pump/1/start', json={"duration": 10})
    assert response.status_code == 200
    assert response.json == {"message": "OK"}
    mock_start.assert_called_once_with(1)
    mock_log.assert_called_once_with(1, 10, "Manual")
    mock_thread.assert_called_once()

@patch('hal.pump_stop')
def test_pump_stop(mock_stop, client):
    response = client.post('/pump/1/stop')
    assert response.status_code == 200
    assert response.json == {"message": "Stopped"}
    mock_stop.assert_called_once_with(1)

@patch('hal.pump_start')
@patch('routes.log_pump_action')
@patch('threading.Thread')
def test_pump_all_start(mock_thread, mock_log, mock_start, client):
    response = client.post('/pump/all/start', json={"duration": 5})
    assert response.status_code == 200
    assert response.json["message"] == "All pumps started"
    assert mock_start.call_count == len(hal.PUMP_PINS)
    assert mock_log.call_count == len(hal.PUMP_PINS)
    assert mock_thread.call_count == len(hal.PUMP_PINS)

@patch('hal.emergency_stop_all')
def test_pump_all_stop(mock_stop_all, client):
    response = client.post('/pump/all/stop')
    assert response.status_code == 200
    assert response.json == {"message": "All pumps stopped", "status": "stopped"}
    mock_stop_all.assert_called_once()

def test_api_live_gauges(client):
    response = client.get('/api/live_gauges')
    assert response.status_code == 200
    assert "ph" in response.json
    assert "tds" in response.json
    assert "temperature" in response.json
    assert "humidity" in response.json

def test_get_event_logs(client):
    # Setup some test data
    log = EventLog(event_id="TEST_EVENT", category="SYSTEM", message="Test message")
    db.session.add(log)
    db.session.commit()

    response = client.get('/get_event_logs')
    assert response.status_code == 200
    data = response.json
    assert "event_logs" in data
    assert len(data["event_logs"]) == 1
    assert data["event_logs"][0]["event_id"] == "TEST_EVENT"
