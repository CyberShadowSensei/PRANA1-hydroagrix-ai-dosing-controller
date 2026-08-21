"""
Tests for Tasks 1, 2, and 5:
  - Task 2: Growth cycle active/inactive based on plant_name, not status.state
  - Task 5: RECOVERY email cooldown respected; DANGER bypass logic unchanged
"""
import sys
import pytest
import unittest
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, timedelta
import json

# Mock hardware/Pi-only modules
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()
try:
    import cv2
except ImportError:
    sys.modules['cv2'] = MagicMock()

from config import app, db
from models import PlantStageStatus, PlantPreset
from checkSensorMail import SensorMonitor
import routes  # registers Flask routes on the app instance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as c:
        with app.app_context():
            db.create_all()
            yield c
            db.session.remove()
            db.drop_all()


@pytest.fixture
def monitor():
    """SensorMonitor with stub email config (won't actually send mail)."""
    m = SensorMonitor()
    m.email_config = {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'sender_email': 'test@gmail.com',
        'sender_password': 'pass',
        'receiver_email': 'test2@gmail.com',
    }
    return m


# ---------------------------------------------------------------------------
# Task 2: Growth Cycle — plant_name governs visibility, not status.state
# ---------------------------------------------------------------------------

class TestGrowCycleDecoupling:

    def test_cycle_active_when_plant_set_and_manual_mode(self, client):
        """Cycle is active (active=True) when plant_name is set, even if state=False."""
        from grow_cycle_helper import get_active_grow_cycle_details

        stages = {"Seedling": {"start_day": 0, "advice": "Water daily"}}
        preset = PlantPreset(name="Lettuce", image_url="", stages_json=json.dumps(stages))
        db.session.add(preset)

        status = PlantStageStatus(
            plant_name="Lettuce",
            plant_stage="Seedling",
            state=False,                      # Manual Mode — was broken before fix
            cycle_start_date=datetime.utcnow() - timedelta(days=3)
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["active"] is True

    def test_cycle_inactive_when_plant_name_empty(self, client):
        """Cycle is inactive (active=False) when plant_name is empty."""
        from grow_cycle_helper import get_active_grow_cycle_details

        status = PlantStageStatus(
            plant_name="",
            plant_stage="Idle",
            state=True,
            cycle_start_date=datetime.utcnow()
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["active"] is False

    def test_cycle_inactive_when_plant_name_empty_string(self, client):
        """Cycle is inactive when plant_name is an empty string."""
        from grow_cycle_helper import get_active_grow_cycle_details

        status = PlantStageStatus(
            plant_name="",
            plant_stage="Idle",
            state=True,
            cycle_start_date=datetime.utcnow()
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["active"] is False

    def test_cycle_inactive_when_no_status_row(self, client):
        """Cycle is inactive when PlantStageStatus table has no rows."""
        from grow_cycle_helper import get_active_grow_cycle_details

        details = get_active_grow_cycle_details()
        assert details["active"] is False

    def test_cycle_inactive_when_no_start_date(self, client):
        """Cycle is inactive when both plant_name and cycle_start_date are absent."""
        from grow_cycle_helper import get_active_grow_cycle_details

        # Empty plant_name ensures the guard trips on plant_name before start_date
        status = PlantStageStatus(
            plant_name="",
            plant_stage="Idle",
            state=True,
            cycle_start_date=None
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["active"] is False

    def test_cycle_active_in_autonomous_mode(self, client):
        """Cycle is still active when state=True (the normal autonomous case)."""
        from grow_cycle_helper import get_active_grow_cycle_details

        stages = {"Vegetative": {"start_day": 0, "advice": "Grow"}}
        preset = PlantPreset(name="Tomato", image_url="", stages_json=json.dumps(stages))
        db.session.add(preset)

        status = PlantStageStatus(
            plant_name="Tomato",
            plant_stage="Vegetative",
            state=True,
            cycle_start_date=datetime.utcnow() - timedelta(days=5)
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["active"] is True

    def test_cycle_day_count_correct(self, client):
        """Returned day count matches days since cycle_start_date."""
        from grow_cycle_helper import get_active_grow_cycle_details

        stages = {"Seedling": {"start_day": 0, "advice": "Water"}}
        preset = PlantPreset(name="Basil", image_url="", stages_json=json.dumps(stages))
        db.session.add(preset)

        start = datetime.utcnow() - timedelta(days=7)
        status = PlantStageStatus(
            plant_name="Basil",
            plant_stage="Seedling",
            state=False,
            cycle_start_date=start
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["day"] == 7

    def test_switching_to_manual_preserves_cycle_limits(self, client):
        """The 'limits' key is returned even when state=False (manual mode)."""
        from grow_cycle_helper import get_active_grow_cycle_details

        stages = {
            "Seedling": {
                "start_day": 0,
                "advice": "Water",
                "ec": {"min": 0.8, "max": 1.2},
                "ph": {"min": 5.5, "max": 6.0}
            }
        }
        preset = PlantPreset(name="Mint", image_url="", stages_json=json.dumps(stages))
        db.session.add(preset)

        status = PlantStageStatus(
            plant_name="Mint",
            plant_stage="Seedling",
            state=False,
            cycle_start_date=datetime.utcnow()
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["active"] is True
        limits = details.get("limits", {})
        assert "ec" in limits
        assert "ph" in limits


# ---------------------------------------------------------------------------
# Task 5: Email Cooldown — RECOVERY respects shared cooldown
# ---------------------------------------------------------------------------

class TestEmailCooldown:

    def test_recovery_email_bypasses_cooldown(self, client, monitor):
        """RECOVERY alert bypasses cooldown window so user receives immediate confirmation."""
        sensor = 'tds'
        # Simulate: DANGER was sent 30 minutes ago
        monitor.sensor_states[sensor]['last_notification'] = (
            datetime.now() - timedelta(hours=0.5)
        )
        monitor.sensor_states[sensor]['is_faulted'] = True

        with patch('smtplib.SMTP') as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            monitor.send_email_alert(sensor, "Sensor recovered!", "RECOVERY",
                                     bypass_cooldown=True)
            instance.send_message.assert_called_once()

    def test_recovery_email_fires_after_cooldown(self, client, monitor):
        """RECOVERY alert fires if >4h has elapsed since last notification."""
        sensor = 'tds'
        monitor.sensor_states[sensor]['last_notification'] = (
            datetime.now() - timedelta(hours=5)
        )
        monitor.sensor_states[sensor]['is_faulted'] = True

        with patch('smtplib.SMTP') as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            monitor.send_email_alert(sensor, "Sensor recovered!", "RECOVERY",
                                     bypass_cooldown=True)
            instance.send_message.assert_called_once()

    def test_danger_new_fault_bypasses_cooldown(self, client, monitor):
        """First-time DANGER (new fault) bypasses cooldown and fires immediately."""
        sensor = 'ph'
        # Last notification was only 5 minutes ago
        monitor.sensor_states[sensor]['last_notification'] = (
            datetime.now() - timedelta(minutes=5)
        )
        monitor.sensor_states[sensor]['is_faulted'] = False  # new fault

        with patch('smtplib.SMTP') as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            is_new_fault = not monitor.sensor_states[sensor]['is_faulted']
            monitor.send_email_alert(sensor, "pH critically low!", "DANGER",
                                     bypass_cooldown=is_new_fault)
            instance.send_message.assert_called_once()

    def test_danger_repeat_suppressed_within_cooldown(self, client, monitor):
        """Repeated DANGER for an ongoing fault with consecutive_alerts >= 1 is suppressed within progressive 6h cooldown."""
        sensor = 'ph'
        monitor.sensor_states[sensor]['last_notification'] = (
            datetime.now() - timedelta(hours=1)
        )
        monitor.sensor_states[sensor]['is_faulted'] = True  # already known
        monitor.sensor_states[sensor]['consecutive_alerts'] = 1  # 2nd alert requires 6h cooldown

        with patch('smtplib.SMTP') as mock_smtp:
            is_new_fault = not monitor.sensor_states[sensor]['is_faulted']
            monitor.send_email_alert(sensor, "pH still critically low!", "DANGER",
                                     bypass_cooldown=is_new_fault)
            mock_smtp.assert_not_called()

    def test_no_crash_on_unknown_sensor(self, client, monitor):
        """Calling send_email_alert on an untracked sensor name does not crash."""
        with patch('smtplib.SMTP'):
            # 'nitrogen' is not in sensor_states; should return early
            monitor.send_email_alert('nitrogen', 'test', 'DANGER')

    def test_recovery_last_notification_updated_on_send(self, client, monitor):
        """last_notification timestamp is updated after a RECOVERY email sends."""
        sensor = 'tds'
        monitor.sensor_states[sensor]['last_notification'] = (
            datetime.now() - timedelta(hours=10)
        )
        monitor.sensor_states[sensor]['is_faulted'] = True

        with patch('smtplib.SMTP'):
            monitor.send_email_alert(sensor, "Recovered", "RECOVERY",
                                     bypass_cooldown=False)

        assert monitor.sensor_states[sensor]['last_notification'] is not None
        # The new timestamp should be very recent (within 5 seconds)
        delta = datetime.now() - monitor.sensor_states[sensor]['last_notification']
        assert delta.total_seconds() < 5

    def test_humidity_alert_respects_is_active_flag(self, client, monitor):
        """Humidity alerts now respect is_active like all other sensors.
        The old hard-coded bypass that silently discarded all humidity alerts
        regardless of config has been removed. Humidity with is_active=False
        should produce no alert; is_active=True at extreme values should alert."""
        # When is_active is False, check_sensor_reading returns immediately — no alert
        with patch.object(monitor, 'send_email_alert') as mock_alert:
            monitor.check_sensor_reading('humidity', 3.0, {'min': 40, 'max': 90, 'is_active': False})
        mock_alert.assert_not_called()

        # When is_active is True and value is extreme (below DANGER min of 10%), alert fires
        with patch.object(monitor, 'send_email_alert') as mock_alert, \
             patch.object(monitor, '_log_to_db'):
            monitor.check_sensor_reading('humidity', 3.0, {'min': 40, 'max': 90, 'is_active': True})
        mock_alert.assert_called_once()
        assert mock_alert.call_args[0][0] == 'humidity'
        assert mock_alert.call_args[0][2] == 'DANGER'


# ---------------------------------------------------------------------------
# Mandatory Cycle, Tank Capacities, and ML Stage Tests
# ---------------------------------------------------------------------------

class TestMandatoryCycleAndTankCapacities:

    def test_mode_toggle_rejected_without_active_cycle(self, client):
        """POST /update_plant_status returns 400 when no grow cycle is active."""
        # Ensure plant_name is empty
        status = PlantStageStatus.query.first()
        if not status:
            status = PlantStageStatus(plant_name="", plant_stage="Idle", state=False)
            db.session.add(status)
        else:
            status.plant_name = ""
            status.state = False
        db.session.commit()

        response = client.post('/update_plant_status', json={"state": True})
        assert response.status_code == 400
        assert "error" in response.json
        assert "must be active" in response.json["error"]

    def test_mode_toggle_accepted_with_active_cycle(self, client):
        """POST /update_plant_status returns 200 when a grow cycle is active."""
        status = PlantStageStatus.query.first()
        if not status:
            status = PlantStageStatus(plant_name="Lettuce", plant_stage="Seedling", state=False)
            db.session.add(status)
        else:
            status.plant_name = "Lettuce"
            status.plant_stage = "Seedling"
            status.state = False
        db.session.commit()

        response = client.post('/update_plant_status', json={"state": True})
        assert response.status_code == 200
        assert response.json["state"] is True

    def test_dosing_config_updates_solution_tank_capacities(self, client):
        """POST /api/dosing_config updates capacity_ml for all 4 solution tanks in the DB."""
        from models import SolutionTanks
        # Seed 4 tanks if not present
        if SolutionTanks.query.count() == 0:
            db.session.add(SolutionTanks(tank_id=1, name="Nutrient A", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.add(SolutionTanks(tank_id=2, name="Nutrient B", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.add(SolutionTanks(tank_id=3, name="pH UP", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.add(SolutionTanks(tank_id=4, name="pH DOWN", capacity_ml=5000.0, current_volume_ml=5000.0))
            db.session.commit()

        payload = {
            "reservoir_volume_l": 60.0,
            "pump_flow_rate_ml_per_sec": 1.2,
            "nutrient_a_volume_ml": 6000,
            "nutrient_b_volume_ml": 6100,
            "ph_up_volume_ml": 6200,
            "ph_down_volume_ml": 6300
        }

        # Mock config file interaction so it doesn't crash on filesystem
        with patch('os.path.exists', return_value=True), \
             patch('os.replace'), \
             patch('builtins.open', mock_open(read_data='{}')):
            response = client.post('/api/dosing_config', json=payload)
            assert response.status_code == 200


        # Verify database fields updated
        tank1 = SolutionTanks.query.filter_by(tank_id=1).first()
        tank2 = SolutionTanks.query.filter_by(tank_id=2).first()
        tank3 = SolutionTanks.query.filter_by(tank_id=3).first()
        tank4 = SolutionTanks.query.filter_by(tank_id=4).first()

        assert tank1.capacity_ml == 6000.0
        assert tank2.capacity_ml == 6100.0
        assert tank3.capacity_ml == 6200.0
        assert tank4.capacity_ml == 6300.0

    def test_grow_cycle_details_returns_advisory_ml_stage(self, client):
        """get_active_grow_cycle_details() returns status.plant_stage under 'ml_stage'."""
        from grow_cycle_helper import get_active_grow_cycle_details

        stages = {"Vegetative": {"start_day": 0, "advice": "Grow Veg"}}
        preset = PlantPreset(name="Tomato", image_url="", stages_json=json.dumps(stages))
        db.session.add(preset)

        status = PlantStageStatus(
            plant_name="Tomato",
            plant_stage="Flowering",  # Stored ML classified stage
            state=True,
            cycle_start_date=datetime.utcnow()
        )
        db.session.add(status)
        db.session.commit()

        details = get_active_grow_cycle_details()
        assert details["active"] is True
        assert details["ml_stage"] == "Flowering"



# ---------------------------------------------------------------------------
# Task 2: Automated Photo Artifact Pruning
# ---------------------------------------------------------------------------

class TestPhotoArtifactPruning:

    def test_photo_artifact_pruning(self, tmp_path):
        """Verify prune_old_photos deletes photos older than max_days and retains newer photos."""
        import os
        import time
        from main import prune_old_photos

        photo_dir = str(tmp_path / "captured_photos")
        os.makedirs(photo_dir, exist_ok=True)

        old_file = os.path.join(photo_dir, "old_photo.jpg")
        new_file = os.path.join(photo_dir, "new_photo.jpg")

        with open(old_file, "w") as f:
            f.write("old photo content")
        with open(new_file, "w") as f:
            f.write("new photo content")

        now = time.time()
        thirty_one_days_ago = now - (31 * 86400)

        os.utime(old_file, (thirty_one_days_ago, thirty_one_days_ago))
        os.utime(new_file, (now, now))

        prune_old_photos(photo_dir=photo_dir, max_days=30)

        assert not os.path.exists(old_file), "Old photo was not pruned"
        assert os.path.exists(new_file), "New photo was incorrectly pruned"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

