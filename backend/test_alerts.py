import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

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
from models import EmailBacklog, SensorLimits, EventLog, EmailAuditLog
from checkSensorMail import SensorMonitor
import smtplib

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

@pytest.fixture
def monitor():
    m = SensorMonitor()
    m.email_config = {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'sender_email': 'test@gmail.com',
        'sender_password': 'pass',
        'receiver_email': 'test2@gmail.com'
    }
    return m

def test_muted_humidity(client, monitor):
    with patch.object(monitor, '_add_to_backlog') as mock_backlog:
        with patch('smtplib.SMTP') as mock_smtp:
            monitor.check_sensor_reading('humidity', 99.0)
            mock_smtp.assert_not_called()
            mock_backlog.assert_not_called()

def test_warning_vs_danger_severity(client, monitor):
    user_limits = {'min': 1.0, 'max': 2.0}
    with patch.object(monitor, 'send_email_alert') as mock_send_email:
        monitor.check_sensor_reading('tds', 2.5, user_limits)
        mock_send_email.assert_not_called()
        log = EventLog.query.filter_by(category="WARNING").first()
        assert log is not None
        assert "slightly outside limits" in log.message
        
        monitor.check_sensor_reading('tds', 8.5, user_limits)
        mock_send_email.assert_called_once()
        log2 = EventLog.query.filter_by(category="DANGER").first()
        assert log2 is not None

def test_offline_backlog_50_cap(client, monitor):
    with patch('smtplib.SMTP', side_effect=smtplib.SMTPException("Mocked exception")):
        for i in range(55):
            monitor.send_email_alert('tds', f'error {i}', 'DANGER', bypass_cooldown=True)
            
    count = EmailBacklog.query.count()
    assert count == 50
    oldest = EmailBacklog.query.order_by(EmailBacklog.created_at.asc()).first()
    assert "error 0" not in oldest.body_text
    assert "error 1" not in oldest.body_text

def test_offline_backlog_expiration(client, monitor):
    with app.app_context():
        old_email = EmailBacklog(subject="Old", body_text="text", recipients="test@test.com", created_at=datetime.utcnow() - timedelta(hours=25))
        db.session.add(old_email)
        db.session.commit()
        
    from main import email_backlog_loop
    with patch('time.sleep', side_effect=StopIteration("StopLoop")):
        try:
            email_backlog_loop()
        except StopIteration:
            pass
            
    with app.app_context():
        count = EmailBacklog.query.count()
        assert count == 0

def test_email_backlog_resilience_to_bad_recipient(client, monitor):
    with app.app_context():
        bad_item = EmailBacklog(subject="Bad", body_text="text1", recipients="bad@invalid.com", created_at=datetime.utcnow() - timedelta(minutes=10))
        good_item = EmailBacklog(subject="Good", body_text="text2", recipients="good@valid.com", created_at=datetime.utcnow() - timedelta(minutes=5))
        db.session.add(bad_item)
        db.session.add(good_item)
        db.session.commit()

        bad_id = bad_item.id
        good_id = good_item.id

    from main import process_email_backlog_items
    
    mock_smtp_inst = MagicMock()
    # First send_message fails with SMTPRecipientsRefused, second succeeds
    mock_smtp_inst.send_message.side_effect = [smtplib.SMTPRecipientsRefused({'bad@invalid.com': (550, b'User unknown')}), None]

    with patch('checkSensorMail.SensorMonitor', return_value=monitor), \
         patch('sensors.sensor_monitor', monitor), \
         patch('smtplib.SMTP', return_value=mock_smtp_inst):
        process_email_backlog_items()


    with app.app_context():
        # Bad item should be deleted, good item should also be sent and deleted
        remaining = EmailBacklog.query.all()
        remaining_ids = [r.id for r in remaining]
        assert bad_id not in remaining_ids
        assert good_id not in remaining_ids

def test_check_sensor_reading_deadband_recovery(client, monitor):
    """Verify deadband sensor recovery alerting and threshold hysteresis."""
    monitor.sensor_states['ph']['is_faulted'] = True
    
    with patch.object(monitor, 'send_email_alert') as mock_send_email, \
         patch.object(monitor, '_log_to_db') as mock_log_db:
        
        # Reading 2.6 is within absolute range [2.5, 11.5], but outside deadband bounds [2.7, 11.3]
        monitor.check_sensor_reading('ph', 2.6, user_limits={'is_active': True, 'min': 5.5, 'max': 6.5})
        mock_send_email.assert_not_called()
        assert monitor.sensor_states['ph']['is_faulted'] is True
        
        # Reading 6.0 is inside deadband bounds [2.7, 11.3] -> recovery triggered
        monitor.check_sensor_reading('ph', 6.0, user_limits={'is_active': True, 'min': 5.5, 'max': 6.5})
        mock_send_email.assert_called_once_with('ph', 'Sensor recovered! Current value: 6.0', 'RECOVERY', bypass_cooldown=True)
        mock_log_db.assert_any_call('PH_RECOVERY', 'RECOVERY', 'Sensor recovered! Current value: 6.0', {'value': 6.0})
        assert monitor.sensor_states['ph']['is_faulted'] is False

def test_send_email_alert_cooldown_enforcement_and_bypass(client, monitor):
    """Verify notification cooldown enforcement suppresses duplicate alerts unless bypass_cooldown is True."""
    with patch('smtplib.SMTP') as mock_smtp:
        monitor.send_email_alert('ph', 'pH out of range', 'DANGER')
        assert mock_smtp.called
        mock_smtp.reset_mock()
        
        # Second alert within cooldown window (4h) without bypass is suppressed
        monitor.send_email_alert('ph', 'pH out of range 2', 'DANGER', bypass_cooldown=False)
        mock_smtp.assert_not_called()
        
        # Third alert with bypass_cooldown=True is sent immediately
        monitor.send_email_alert('ph', 'pH out of range 3', 'DANGER', bypass_cooldown=True)
        assert mock_smtp.called

def test_multi_recipient_address_parsing(client, monitor):
    """Verify multi-recipient email address parsing for comma and semicolon separated strings."""
    monitor.email_config['receiver_email'] = 'grower@farm.com; manager@farm.com, tech@farm.com'
    
    with patch('smtplib.SMTP') as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        monitor.send_email_alert('ph', 'Emergency', 'DANGER', bypass_cooldown=True)
        
        assert mock_server.send_message.called
        call_kwargs = mock_server.send_message.call_args[1]
        assert call_kwargs['to_addrs'] == ['grower@farm.com', 'manager@farm.com', 'tech@farm.com']

def test_send_report_html_and_attachments(client, monitor):
    """Verify send_report includes HTML body and MIMEApplication attachments."""
    attachments = {
        'digest.pdf': b'%PDF-1.4 sample content',
        'metrics.csv': b'timestamp,ph,ec\n1000,6.0,1.5'
    }
    html_custom = "<h1>Daily Farm Report</h1>"
    
    with patch('smtplib.SMTP') as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        success, msg = monitor.send_report(
            subject="Daily Summary",
            body="Plain text fallback",
            attachments=attachments,
            html_body=html_custom
        )
        
        assert success is True
        assert mock_server.send_message.called
        sent_msg = mock_server.send_message.call_args[0][0]
        assert sent_msg['Subject'] == "Daily Summary"
        payloads = sent_msg.get_payload()
        attachment_names = [p.get_filename() for p in payloads if p.get_filename()]
        assert 'digest.pdf' in attachment_names
        assert 'metrics.csv' in attachment_names

def test_placeholder_email_stubbing_behavior(client):
    """Verify placeholder email config prints stubs and returns without attempting SMTP connections."""
    m = SensorMonitor()
    m.email_config = {
        'sender_email': 'placeholder@gmail.com',
        'receiver_email': 'placeholder_recipient@gmail.com'
    }
    
    with patch('smtplib.SMTP') as mock_smtp:
        m.send_email_alert('ph', 'Stub Test', 'DANGER')
        mock_smtp.assert_not_called()
        
        success, res = m.send_report('Stub Report', 'Body')
        assert success is True
        assert "Stubbed" in res
        mock_smtp.assert_not_called()

def test_email_audit_logging(client, monitor):
    """Verify that email delivery attempts log correctly to EmailAuditLog."""
    # 1. Test STUBBED audit logging
    stub_monitor = SensorMonitor()
    stub_monitor.email_config = {
        'sender_email': 'placeholder@gmail.com',
        'receiver_email': 'recipient@gmail.com'
    }
    stub_monitor.send_email_alert('ph', 'Stubbed testing alert', 'DANGER')
    audit1 = EmailAuditLog.query.filter_by(status='STUBBED').first()
    assert audit1 is not None
    assert audit1.sensor_name == 'ph'
    assert 'DANGER' in audit1.alert_type

    # 2. Test SENT audit logging
    with patch('smtplib.SMTP') as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        monitor.send_email_alert('tds', 'Value out of bounds', 'DANGER', bypass_cooldown=True)
        
        audit2 = EmailAuditLog.query.filter_by(status='SENT').first()
        assert audit2 is not None
        assert audit2.sensor_name == 'tds'
        assert audit2.recipients == 'test2@gmail.com'

    # 3. Test SKIPPED_COOLDOWN audit logging
    with patch('smtplib.SMTP') as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        # Trigger another TDS alert immediately without bypass_cooldown
        monitor.send_email_alert('tds', 'Another bounds alert', 'DANGER', bypass_cooldown=False)
        
        audit3 = EmailAuditLog.query.filter_by(status='SKIPPED_COOLDOWN').first()
        assert audit3 is not None
        assert audit3.sensor_name == 'tds'

    # 4. Test FAILED audit logging
    with patch('smtplib.SMTP', side_effect=Exception("SMTP Connection Error")):
        monitor.send_email_alert('ph', 'Connection fail alert', 'DANGER', bypass_cooldown=True)
        
        audit4 = EmailAuditLog.query.filter_by(status='FAILED').first()
        assert audit4 is not None
        assert audit4.sensor_name == 'ph'
        assert 'SMTP Connection Error' in audit4.error_message

    # 5. Test capacity bounding (keeps at most 500 records)
    EmailAuditLog.query.delete()
    db.session.commit()
    for i in range(550):
        monitor._log_audit(f"Subject {i}", "test@test.com", "REPORT", "SENT")
    
    count = EmailAuditLog.query.count()
    assert count <= 500

def test_check_sensor_reading_null_debouncing(client, monitor):
    """Verify check_sensor_reading debounces None/NULL readings up to min_consecutive."""
    user_limits = {'min': 5.5, 'max': 6.5, 'is_active': True}
    with patch.object(monitor, 'send_email_alert') as mock_send_email:
        # Ticks 1-9 with value=None and min_consecutive=10 -> silent hold (0 alerts)
        for i in range(1, 10):
            monitor.check_sensor_reading('ph', None, user_limits, min_consecutive=10)
            mock_send_email.assert_not_called()
            assert monitor.sensor_states['ph']['consecutive_null'] == i

        # Tick 10 with value=None -> triggers email alert
        monitor.check_sensor_reading('ph', None, user_limits, min_consecutive=10)
        assert monitor.sensor_states['ph']['consecutive_null'] == 10
        mock_send_email.assert_called_once()
        assert "no reading" in mock_send_email.call_args[0][1]

        # Valid reading resets consecutive_null to 0
        monitor.check_sensor_reading('ph', 6.0, user_limits, min_consecutive=10)
        assert monitor.sensor_states['ph']['consecutive_null'] == 0



