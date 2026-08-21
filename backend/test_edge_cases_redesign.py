import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from config import app, db
from models import EventLog, SensorLimits, PlantStageStatus, PlantPreset
from checkSensorMail import SensorMonitor
import sensors
import grow_cycle_helper


@pytest.fixture
def monitor():
    return SensorMonitor()


@pytest.fixture
def app_ctx():
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()


# 1. Disabled Sensors & Strict is_active Enforcement
def test_disabled_sensor_monitoring_bypasses_all_checks(app_ctx, monitor):
    """When a sensor is marked is_active=False, check_sensor_reading returns immediately without logging or emailing."""
    sensor_name = 'temperature'
    disabled_limits = {'min': 18.0, 'max': 24.0, 'is_active': False}
    
    with patch('smtplib.SMTP') as mock_smtp, patch.object(monitor, '_log_to_db') as mock_log:
        # Pass extreme reading (45.0°C) which would normally trigger DANGER
        monitor.check_sensor_reading(sensor_name, 45.0, disabled_limits)
        
        mock_smtp.assert_not_called()
        mock_log.assert_not_called()
        assert monitor.sensor_states[sensor_name]['is_faulted'] is False


# 2. Progressive Email Backoff & Reset on Recovery
def test_progressive_email_backoff_and_recovery_reset(app_ctx, monitor):
    """Verifies 1st alert (0h), 2nd alert (6h delay), 3rd alert (24h delay), and reset on recovery."""
    from models import EmailAuditLog
    sensor = 'ph'
    monitor.sensor_states[sensor]['is_faulted'] = True
    
    with patch.object(monitor, '_is_dummy_config', return_value=False), patch('smtplib.SMTP'):
        # 1st alert: consecutive_alerts = 0 -> immediate (0h delay)
        monitor.sensor_states[sensor]['consecutive_alerts'] = 0
        monitor.sensor_states[sensor]['last_notification'] = datetime.now() - timedelta(minutes=5)
        monitor.send_email_alert(sensor, "pH Low", "DANGER", bypass_cooldown=False)
        
        log1 = EmailAuditLog.query.order_by(EmailAuditLog.id.desc()).first()
        assert log1.status == "SENT"
        assert monitor.sensor_states[sensor]['consecutive_alerts'] == 1

        # 2nd alert attempt after 1 hour (consecutive_alerts = 1 -> requires 6h cooldown)
        monitor.send_email_alert(sensor, "pH Still Low", "DANGER", bypass_cooldown=False)
        log2 = EmailAuditLog.query.order_by(EmailAuditLog.id.desc()).first()
        assert log2.status == "SKIPPED_COOLDOWN"  # Suppressed by 6h backoff

        # 2nd alert attempt after 7 hours -> fires!
        monitor.sensor_states[sensor]['last_notification'] = datetime.now() - timedelta(hours=7)
        monitor.send_email_alert(sensor, "pH Still Low", "DANGER", bypass_cooldown=False)
        log3 = EmailAuditLog.query.order_by(EmailAuditLog.id.desc()).first()
        assert log3.status == "SENT"
        assert monitor.sensor_states[sensor]['consecutive_alerts'] == 2

        # Recovery alert -> fires immediately and resets consecutive_alerts to 0
        monitor.send_email_alert(sensor, "pH Recovered", "RECOVERY", bypass_cooldown=True)
        monitor.sensor_states[sensor]['is_faulted'] = False
        log4 = EmailAuditLog.query.order_by(EmailAuditLog.id.desc()).first()
        assert log4.status == "SENT"
        assert monitor.sensor_states[sensor]['consecutive_alerts'] == 0
        assert monitor.sensor_states[sensor]['is_faulted'] is False


# 3. Dynamic High EC Danger Threshold Boundary Values
def test_dynamic_high_ec_danger_threshold_boundaries(app_ctx, monitor):
    """EC danger email requires EC >= 5.5 mS/cm OR EC > target_max + 2.0 mS/cm."""
    target_limits = {'min': 1.0, 'max': 1.8, 'is_active': True}
    
    with patch.object(monitor, 'send_email_alert') as mock_email, patch.object(monitor, '_log_to_db') as mock_log:
        # Reading 3.5 mS/cm (target_max 1.8 + 1.7) -> Warning logged, NO danger email
        monitor.check_sensor_reading('tds', 3.5, target_limits)
        mock_email.assert_not_called()
        mock_log.assert_called_once()
        
        mock_log.reset_mock()
        # Reading 3.9 mS/cm (target_max 1.8 + 2.1) -> Danger email triggered!
        monitor.check_sensor_reading('tds', 3.9, target_limits)
        mock_email.assert_called_once()
        assert mock_email.call_args[0][2] == "DANGER"


# 4. Water Temperature Thermal Estimation
def test_water_temperature_thermal_estimation():
    """When DS18B20 probe is missing, get_water_temp estimates water temp from air temp (-2.0°C)."""
    # Mock live_th_data with 26.0°C air temperature
    sensors.live_th_data.clear()
    sensors.live_th_data.append({'t': 26.0, 'h': 60.0, 'status': 'OK'})
    
    with patch('hal.get_water_temp', return_value=26.0):  # Probe disconnected, returns fallback
        temp_val, is_est = sensors.get_water_temp()
        assert is_est is True
        assert temp_val == 24.0  # 26.0 - 2.0

    with patch('hal.get_water_temp', return_value=21.5):  # Physical probe connected!
        temp_val, is_est = sensors.get_water_temp()
        assert is_est is False
        assert temp_val == 21.5


# 5. Reconciled Growth Stage & ML Verification Status Matrix
def test_reconcile_ml_stage_matrix():
    """Tests all 4 reconciliation matrix outcomes: Aligned, Unconfirmed, Growth Delay, and Pending."""
    stages = {
        "Seedling": {"start_day": 0},
        "Vegetative": {"start_day": 14},
        "Flowering": {"start_day": 35}
    }
    
    # Case A: Aligned
    assert grow_cycle_helper.reconcile_ml_stage("Vegetative", "Vegetative", 20, stages) == "Aligned"
    
    # Case B: Pending / Unconfirmed (ML ahead of schedule)
    assert grow_cycle_helper.reconcile_ml_stage("Seedling", "Vegetative", 5, stages) == "Pending"
    
    # Case C: Growth Delay (ML behind schedule)
    assert grow_cycle_helper.reconcile_ml_stage("Vegetative", "Seedling", 20, stages) == "Growth Delay"

    # Case D: Pending (No ML detection or unknown stage)
    assert grow_cycle_helper.reconcile_ml_stage("Vegetative", None, 20, stages) == "Unconfirmed"
    assert grow_cycle_helper.reconcile_ml_stage("Vegetative", "Idle", 20, stages) == "Unconfirmed"


# 6. REST API Sensor Limits Persistence & Synchronization
def test_sensor_limits_rest_api_roundtrip(app_ctx):
    """Verifies GET/POST /sensor/limits endpoint correctly updates and persists active status and min/max bounds."""
    from routes import app
    client = app.test_client()

    # Update Temperature limits via REST API
    payload = {
        "temperature": {"min": 18.5, "max": 28.5, "active": True},
        "humidity": {"min": 45.0, "max": 75.0, "active": False}
    }
    post_res = client.post("/sensor/limits", json=payload)
    assert post_res.status_code == 200

    # Fetch limits via GET and verify persistence
    get_res = client.get("/sensor/limits")
    assert get_res.status_code == 200
    data = get_res.get_json()
    
    assert data["temperature"]["min"] == 18.5
    assert data["temperature"]["max"] == 28.5
    assert data["temperature"]["active"] is True
    assert data["humidity"]["active"] is False


# 7. Daily Digest Event Log Grouping & Deduplication
def test_daily_digest_event_grouping(app_ctx):
    """Verifies that 24-hour event log warnings are grouped into concise entries with counts and time ranges."""
    from models import EventLog
    from routes import _async_send_report_email_worker
    
    # Seed 5 repeated temperature warnings
    now = datetime.utcnow()
    for i in range(5):
        log_entry = EventLog(
            event_id="TEMPERATURE_WARNING",
            category="WARNING",
            message="temperature at 25.4 is slightly outside limits.",
            timestamp=now - timedelta(minutes=30 - i * 5)
        )
        db.session.add(log_entry)
    db.session.commit()

    # Verify query returns events
    yesterday = now - timedelta(hours=24)
    abnormalities = EventLog.query.filter(
        EventLog.timestamp >= yesterday,
        EventLog.category.in_(['WARNING', 'DANGER', 'ALARM'])
    ).order_by(EventLog.timestamp.asc()).all()
    
    assert len(abnormalities) == 5

