import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

# Mock hardware modules before importing app
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

import hal
from config import app, db
from models import PlantStageStatus
from routes import *
from sensors import circulation_tracker, live_tds_data, live_ph_data

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            if not PlantStageStatus.query.first():
                db.session.add(PlantStageStatus(plant_name="Tomato", plant_stage="Vegetative", state=True))
                db.session.commit()
            
            yield client
            
            db.session.remove()
            db.drop_all()

class TestSystemHealthAndCirculationAPI:
    def test_get_system_health_success(self, client):
        res = client.get('/api/system_health')
        assert res.status_code == 200
        data = res.json
        assert data['status'] == 'OK'
        assert 'database' in data
        assert data['database']['healthy'] is True
        assert 'hardware' in data
        assert 'circulation_tracker' in data
        assert 'telemetry' in data

    def test_get_circulation_status_returns_tracker_metrics(self, client):
        circulation_tracker.reset()
        circulation_tracker.process_reading(2.2, status="OK")
        
        res = client.get('/api/circulation_status')
        assert res.status_code == 200
        data = res.json
        assert data['success'] is True
        assert 'metrics' in data
        metrics = data['metrics']
        assert metrics['plateau_ec'] == 2.2
        assert metrics['is_drain_cycle'] is False
        assert metrics['is_stable_plateau'] is True

    def test_get_circulation_status_during_drain_cycle(self, client):
        circulation_tracker.reset()
        circulation_tracker.process_reading(2.4, status="OK")
        # Simulate probe exposed to air
        circulation_tracker.process_reading(0.4, status="OK")
        
        res = client.get('/api/circulation_status')
        assert res.status_code == 200
        data = res.json
        metrics = data['metrics']
        assert metrics['is_drain_cycle'] is True
        assert metrics['plateau_ec'] == 2.4
        assert metrics['last_raw_ec'] == 0.4
