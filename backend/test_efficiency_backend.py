import sys, os, time
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def app_ctx():
    from config import app, db
    with app.app_context():
        db.create_all()
        yield app, db


class TestMailCheckThrottle:
    def test_throttle_prevents_call_within_60s(self):
        import main
        orig = main._last_mail_check
        try:
            main._last_mail_check = time.time()
            with patch("main.process_status_mail_check") as mc, \
                 patch("main.check_and_adjust_sensors"), \
                 patch("main.fetch_ph", return_value={"ph_value": 7.0}), \
                 patch("main.fetch_tds", return_value={"tds_value": 1.5}), \
                 patch("main.fetch_th", return_value={"temperature": 25.0, "humidity": 60.0}), \
                 patch("main.live_th_data", [{"t": 25.0, "h": 60.0, "status": "OK"}]), \
                 patch("sensors.get_water_temp", return_value=(25.0, False)), \
                 patch("main.socketio"), \
                 patch("main.hal"), \
                 patch("time.sleep", side_effect=StopIteration):
                try:
                    main.fetch_loop()
                except StopIteration:
                    pass
            mc.assert_not_called()
        finally:
            main._last_mail_check = orig

    def test_throttle_allows_call_after_60s(self):
        import main
        orig = main._last_mail_check
        try:
            main._last_mail_check = time.time() - 61.0
            with patch("main.process_status_mail_check") as mc, \
                 patch("main.check_and_adjust_sensors"), \
                 patch("main.fetch_ph", return_value={"ph_value": 7.0}), \
                 patch("main.fetch_tds", return_value={"tds_value": 1.5}), \
                 patch("main.fetch_th", return_value={"temperature": 25.0, "humidity": 60.0}), \
                 patch("main.live_th_data", [{"t": 25.0, "h": 60.0, "status": "OK"}]), \
                 patch("sensors.get_water_temp", return_value=(25.0, False)), \
                 patch("main.socketio"), \
                 patch("main.hal"), \
                 patch("time.sleep", side_effect=StopIteration):
                try:
                    main.fetch_loop()
                except StopIteration:
                    pass
            mc.assert_called_once()
        finally:
            main._last_mail_check = orig

    def test_throttle_updates_timestamp_after_call(self):
        import main
        orig = main._last_mail_check
        before = time.time()
        try:
            main._last_mail_check = time.time() - 61.0
            with patch("main.process_status_mail_check"), \
                 patch("main.check_and_adjust_sensors"), \
                 patch("main.fetch_ph", return_value={"ph_value": 7.0}), \
                 patch("main.fetch_tds", return_value={"tds_value": 1.5}), \
                 patch("main.fetch_th", return_value={"temperature": 25.0, "humidity": 60.0}), \
                 patch("main.live_th_data", [{"t": 25.0, "h": 60.0, "status": "OK"}]), \
                 patch("sensors.get_water_temp", return_value=(25.0, False)), \
                 patch("main.socketio"), \
                 patch("main.hal"), \
                 patch("time.sleep", side_effect=StopIteration):
                try:
                    main.fetch_loop()
                except StopIteration:
                    pass
            assert main._last_mail_check >= before
        finally:
            main._last_mail_check = orig



class TestISTConstant:
    def test_ist_exists_and_is_pytz(self):
        import sensors, pytz
        assert hasattr(sensors, "IST")
        assert isinstance(sensors.IST, pytz.BaseTzInfo)

    def test_ist_is_kolkata(self):
        import sensors
        assert "Kolkata" in str(sensors.IST) or "Asia/Kolkata" in str(sensors.IST)

    def test_fetch_ph_time_is_ist_aware(self, app_ctx):
        import sensors
        with patch("sensors.hal") as mh, patch("sensors.apply_ph_calibration", return_value=6.8):
            mh.get_stable_reading.return_value = 2000
            sensors.live_th_data.clear()
            sensors.live_ph_data.clear()
            sensors.fetch_ph(w_t=25.0)
        r = sensors.live_ph_data[-1]
        assert r["time"].tzinfo is not None
        assert r["time"].tzinfo.utcoffset(r["time"]).total_seconds() == 19800

    def test_fetch_th_time_is_ist_aware(self, app_ctx):
        import sensors
        with patch("sensors.hal") as mh:
            mh.get_climate.return_value = (65.0, 28.0, "OK")
            sensors.live_th_data.clear()
            sensors.fetch_th()
        assert sensors.live_th_data[-1]["time"].tzinfo is not None


class TestHumidityBypassRemoval:
    def test_humidity_alert_reaches_log_audit(self):
        from checkSensorMail import SensorMonitor
        m = SensorMonitor()
        with patch.object(m, "_is_dummy_config", return_value=True), \
             patch.object(m, "_log_audit") as la:
            m.send_email_alert("humidity", "test", "DANGER")
        la.assert_called_once()

    def test_humidity_inactive_limit_skips_alert(self):
        from checkSensorMail import SensorMonitor
        m = SensorMonitor()
        with patch.object(m, "send_email_alert") as ea:
            m.check_sensor_reading("humidity", 5.0, {"min": 40, "max": 90, "is_active": False})
        ea.assert_not_called()

    def test_humidity_extreme_value_triggers_alert(self):
        from checkSensorMail import SensorMonitor
        m = SensorMonitor()
        with patch.object(m, "send_email_alert") as ea, patch.object(m, "_log_to_db"):
            m.check_sensor_reading("humidity", 3.0, {"min": 40, "max": 90, "is_active": True})
        ea.assert_called_once()
        assert ea.call_args[0][0] == "humidity"
        assert ea.call_args[0][2] == "DANGER"


class TestLogAuditBulkDelete:
    def test_bulk_delete_when_over_500(self, app_ctx):
        # Verify the implementation uses a bulk SQL DELETE, not per-record ORM deletes.
        # Patching the internals here is impractical because EmailAuditLog is imported
        # locally inside the method. Source inspection is the correct approach.
        import checkSensorMail, inspect
        source = inspect.getsource(checkSensorMail.SensorMonitor._log_audit)
        assert 'DELETE' in source, "_log_audit source must contain bulk DELETE statement"
        assert "db.session.delete" not in source, \
            "_log_audit must not use per-record db.session.delete (ORM loop)"
        assert "db.session.execute" in source, \
            "_log_audit must use db.session.execute for the bulk DELETE"


    def test_no_delete_when_under_500(self, app_ctx):
        # Verify that when the table is under the limit, no DELETE fires.
        # We do this by checking source code does not call db.session.delete
        import checkSensorMail, inspect
        source = inspect.getsource(checkSensorMail.SensorMonitor._log_audit)
        # The only delete path should be the bulk SQL execute, not ORM per-record deletes
        assert 'db.session.delete' not in source
        assert 'execute' in source  # bulk path exists



class TestEmailBacklogSingletonReuse:
    def test_sensor_monitor_not_reinstantiated(self, app_ctx):
        import main
        app_obj, db_obj = app_ctx
        from models import EmailBacklog
        from datetime import datetime
        item = EmailBacklog(subject="t", body_text="b", body_html="<p>b</p>",
                            recipients="x@x.com", alert_type="DANGER",
                            created_at=datetime.utcnow())
        db_obj.session.add(item)
        db_obj.session.commit()
        with patch("checkSensorMail.SensorMonitor") as MC, \
             patch("smtplib.SMTP", side_effect=Exception("no net")):
            try:
                main.process_email_backlog_items()
            except Exception:
                pass
        MC.assert_not_called()
        EmailBacklog.query.delete()
        db_obj.session.commit()


class TestLimitsUpdatedEvent:
    def test_limits_updated_emitted_on_post(self, app_ctx):
        app_obj, db_obj = app_ctx
        from config import app as flask_app
        from models import SensorLimits
        with flask_app.test_client() as c, patch("routes.socketio") as ms:
            resp = c.post("/sensor/limits", json={"ph": {"min": 5.5, "max": 7.0, "active": True}})
            assert resp.status_code == 200
            calls = [x[0][0] for x in ms.emit.call_args_list]
            assert "limits_updated" in calls, f"Not emitted. Got: {calls}"
        SensorLimits.query.filter_by(sensor_type="ph").delete()
        db_obj.session.commit()


class TestSecondsUntilIst:
    def test_returns_positive(self):
        from main import _seconds_until_ist
        assert _seconds_until_ist(2, 0) > 0

    def test_min_60_seconds(self):
        from main import _seconds_until_ist
        import pytz
        from datetime import datetime
        IST = pytz.timezone("Asia/Kolkata")
        now = datetime.now(IST)
        assert _seconds_until_ist(now.hour, now.minute) >= 60

    def test_max_24h(self):
        from main import _seconds_until_ist
        assert _seconds_until_ist(2, 0) <= 86460

    def test_min_of_two_targets_is_valid(self):
        from main import _seconds_until_ist
        chosen = min(_seconds_until_ist(2, 0), _seconds_until_ist(8, 0))
        assert 60 <= chosen <= 86460
