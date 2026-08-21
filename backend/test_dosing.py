import sys
from unittest.mock import MagicMock

# Mock hardware and grove modules before importing main to allow tests to run on Windows
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()

import unittest
from unittest.mock import patch, mock_open
import os

import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from dosing import _async_dosing
from sensors import log_event

class DummyLimit:
    def __init__(self, min_val, max_val, is_active=True):
        self.min_value = min_val
        self.max_value = max_val
        self.is_active = is_active

class TestDosing(unittest.TestCase):
    
    def setUp(self):
        import dosing
        dosing._reset_dosing_state()


    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('hal.pump_start')
    @patch('hal.pump_stop')
    @patch('time.sleep')
    @patch('dosing.log_pump_action')
    @patch('dosing.log_event')
    def test_dosing_ec_midpoint_and_individual_flow_rates(
        self, mock_log_event, mock_log_pump, mock_sleep, mock_stop, mock_start, mock_file_open, mock_exists
    ):
        """Verify EC dosing targets range midpoint, logs correct event IDs, and uses individual flow rates."""
        mock_exists.return_value = True
        config_data = """{
            "reservoir_volume_l": 50.0,
            "pump_flow_rate_ml_per_sec": 1.0,
            "nutrient_ml_per_l_per_ec": 2.0,
            "max_dose_time_sec": 30.0,
            "dry_run_mode": false
        }"""
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=False)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)
        
        _async_dosing(ph_val=6.0, tds_val=0.8, l_ph=l_ph, l_tds=l_tds)
        
        # Verify log_event was called with specific event IDs for A and B separately
        mock_log_event.assert_any_call(
            "PUMP_ACTIVATION",
            "INFO",
            "Dosed Nutrient A for 30.00s (Delta: 0.70 EC)"
        )
        mock_log_event.assert_any_call(
            "PUMP_ACTIVATION",
            "INFO",
            "Dosed Nutrient B for 30.00s"
        )

        # Verify log_pump_action calls
        mock_log_pump.assert_any_call(1, 30.0, "Automatic")
        mock_log_pump.assert_any_call(2, 30.0, "Automatic")

    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('hal.pump_start')
    @patch('hal.pump_stop')
    @patch('time.sleep')
    @patch('dosing.log_pump_action')
    @patch('dosing.log_event')
    def test_dosing_ph_down_midpoint(
        self, mock_log_event, mock_log_pump, mock_sleep, mock_stop, mock_start, mock_file_open, mock_exists
    ):
        """Verify pH DOWN dosing targets midpoint, logs event ID, and uses pump 4 flow rate."""
        mock_exists.return_value = True
        config_data = """{
            "reservoir_volume_l": 50.0,
            "pump_flow_rate_ml_per_sec": 1.0,
            "ph_down_ml_per_l_per_ph": 0.5,
            "max_dose_time_sec": 30.0,
            "dry_run_mode": false
        }"""
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 2.0, is_active=False)
        
        _async_dosing(ph_val=7.0, tds_val=1.5, l_ph=l_ph, l_tds=l_tds)
        
        # Verify log_event was called with specific event ID
        mock_log_event.assert_any_call(
            "PUMP_ACTIVATION",
            "INFO",
            "Dosed pH DOWN for 12.50s (Delta: 1.00 pH)"
        )
        mock_log_pump.assert_any_call(4, 12.5, "Automatic")

    def test_manual_stop_signals_dosing_cancellation(self):
        import dosing
        self.assertTrue(hasattr(dosing, "request_dosing_cancellation"))
        dosing.cancel_dosing_flag = False
        dosing.request_dosing_cancellation()
        self.assertTrue(dosing.cancel_dosing_flag)

        # Test _safe_pump_run exits early when cancel_dosing_flag is set
        with patch('hal.pump_start') as mock_start, \
             patch('hal.pump_stop') as mock_stop, \
             patch('time.sleep') as mock_sleep:
            def side_effect(duration):
                dosing.cancel_dosing_flag = True

            mock_sleep.side_effect = side_effect
            dosing._safe_pump_run(1, 10.0)
            mock_start.assert_called_once_with(1)
            mock_stop.assert_called_once_with(1)
            # Sleep should have exited after first step (count == 1)
            self.assertEqual(mock_sleep.call_count, 1)




    @patch('sensors.db')
    @patch('sensors.app')
    def test_log_event_saves_to_db(self, mock_app, mock_db):
        """Verify that log_event helper parses JSON and adds record to database session."""
        from models import EventLog
        
        # Call log_event
        log_event("TEST_EVENT", "SYSTEM", "Test message", {"key": "val"})
        
        # Verify db.session.add was called with an EventLog object containing serialized JSON
        self.assertTrue(mock_db.session.add.called)
        added_obj = mock_db.session.add.call_args[0][0]
        self.assertIsInstance(added_obj, EventLog)
        self.assertEqual(added_obj.event_id, "TEST_EVENT")
        self.assertEqual(added_obj.category, "SYSTEM")
        self.assertEqual(added_obj.message, "Test message")
        self.assertEqual(added_obj.details_json, '{"key": "val"}')
        self.assertTrue(mock_db.session.commit.called)

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.PlantPreset')
    @patch('dosing.threading.Thread')
    @patch('dosing.live_ph_data', [{"value": 7.0, "status": "OK"}])
    @patch('dosing.live_tds_data', [{"value": 1.5, "status": "OK"}])
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('db_cache.get_plant_status', return_value={"plant_name": "Lettuce", "state": False, "plant_stage": "Seedling"})
    @patch('db_cache.get_sensor_limit', side_effect=lambda k: {"ph": {"min": 5.5, "max": 6.5, "active": True}, "tds": {"min": 1.0, "max": 2.0, "active": True}}.get(k))
    def test_check_and_adjust_sensors_manual_mode(self, mock_cache_limit, mock_cache_status, mock_log_event, mock_monitor, mock_thread, mock_preset, mock_limits, mock_status):
        from dosing import check_and_adjust_sensors
        
        # Mock Auto Mode OFF
        status_rec = MagicMock()
        status_rec.state = False
        mock_status.query.first.return_value = status_rec
        
        # Mock DB Sensor Limits
        l_ph_db = DummyLimit(5.5, 6.5, is_active=True)
        l_tds_db = DummyLimit(1.0, 2.0, is_active=True)
        
        def filter_by_side_effect(**kwargs):
            m = MagicMock()
            if kwargs.get('sensor_type') == 'ph': m.first.return_value = l_ph_db
            elif kwargs.get('sensor_type') == 'tds': m.first.return_value = l_tds_db
            return m
        mock_limits.query.filter_by.side_effect = filter_by_side_effect
        
        mock_monitor.sensor_states = {}
        
        check_and_adjust_sensors()
        
        # Should dose based on l_ph_db because pH is 7.0 (max 6.5)
        self.assertTrue(mock_thread.called)
        
        # Ensure it didn't query PlantPreset
        self.assertFalse(mock_preset.query.filter_by.called)

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.threading.Thread')
    @patch('dosing.live_ph_data', [{"value": 7.0, "status": "OK"}])
    @patch('dosing.live_tds_data', [{"value": 1.5, "status": "OK"}])
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('grow_cycle_helper.get_active_grow_cycle_details')
    @patch('db_cache.get_plant_status', return_value={"plant_name": "Lettuce", "state": True, "plant_stage": "Seedling"})
    @patch('db_cache.get_sensor_limit', side_effect=lambda k: {"ph": {"min": 5.0, "max": 8.0, "active": True}, "tds": {"min": 0.0, "max": 5.0, "active": True}}.get(k))
    def test_check_and_adjust_sensors_auto_mode(self, mock_cache_limit, mock_cache_status, mock_details, mock_log_event, mock_monitor, mock_thread, mock_limits, mock_status):
        from dosing import check_and_adjust_sensors
        
        status_rec = MagicMock()
        status_rec.state = True
        status_rec.plant_name = "Lettuce"
        status_rec.plant_stage = "Seedling"
        mock_status.query.first.return_value = status_rec
        
        l_ph_db = DummyLimit(5.0, 8.0, is_active=True)
        l_tds_db = DummyLimit(0.0, 5.0, is_active=True)
        def filter_by_side_effect(**kwargs):
            m = MagicMock()
            if kwargs.get('sensor_type') == 'ph': m.first.return_value = l_ph_db
            elif kwargs.get('sensor_type') == 'tds': m.first.return_value = l_tds_db
            return m
        mock_limits.query.filter_by.side_effect = filter_by_side_effect
        
        mock_details.return_value = {"limits": {"ph": {"min": 5.5, "max": 6.5}, "ec": {"min": 1.0, "max": 2.0}}}
        
        mock_monitor.sensor_states = {}
        
        check_and_adjust_sensors()
        self.assertTrue(mock_thread.called)

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.threading.Thread')
    @patch('dosing.live_ph_data', [{"value": 7.0, "status": "OK"}])
    @patch('dosing.live_tds_data', [{"value": 1.5, "status": "OK"}])
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('grow_cycle_helper.get_active_grow_cycle_details')
    @patch('db_cache.get_plant_status', return_value={"plant_name": "Lettuce", "state": True, "plant_stage": "Seedling"})
    @patch('db_cache.get_sensor_limit', side_effect=lambda k: {"ph": {"min": 5.0, "max": 8.0, "active": True}, "tds": {"min": 0.0, "max": 5.0, "active": True}}.get(k))
    def test_check_and_adjust_sensors_malformed_preset(self, mock_cache_limit, mock_cache_status, mock_details, mock_log_event, mock_monitor, mock_thread, mock_limits, mock_status):
        from dosing import check_and_adjust_sensors
        
        status_rec = MagicMock()
        status_rec.state = True
        status_rec.plant_name = "Lettuce"
        status_rec.plant_stage = "Seedling"
        mock_status.query.first.return_value = status_rec
        
        l_ph_db = DummyLimit(5.0, 8.0, is_active=True)
        l_tds_db = DummyLimit(0.0, 5.0, is_active=True)
        def filter_by_side_effect(**kwargs):
            m = MagicMock()
            if kwargs.get('sensor_type') == 'ph': m.first.return_value = l_ph_db
            elif kwargs.get('sensor_type') == 'tds': m.first.return_value = l_tds_db
            return m
        mock_limits.query.filter_by.side_effect = filter_by_side_effect
        
        mock_details.side_effect = Exception("Malformed JSON")
        
        check_and_adjust_sensors()
        self.assertFalse(mock_thread.called)
        mock_log_event.assert_called_once_with(
            "SYSTEM_ERROR",
            "ERROR",
            "Failed to fetch grow cycle limits for dosing. Error: Malformed JSON",
            {"error": "Malformed JSON"}
        )

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.live_ph_data', [{"value": None, "status": "ERROR"}])
    @patch('dosing.live_tds_data', [{"value": 1.5, "status": "OK"}])
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('dosing.hal.emergency_stop_all')
    def test_check_and_adjust_sensors_probe_disconnect(self, mock_estop, mock_log_event, mock_monitor, mock_limits, mock_status):
        import dosing
        from dosing import check_and_adjust_sensors
        dosing._reset_dosing_state()
        
        # Ticks 1-9: silent safety hold (0 email alerts sent)
        for _ in range(9):
            check_and_adjust_sensors()
            self.assertTrue(mock_estop.called)
            mock_monitor.send_email_alert.assert_not_called()
            mock_log_event.assert_not_called()
        
        # Tick 10: triggers critical halt logging and email alert
        check_and_adjust_sensors()
        mock_monitor.send_email_alert.assert_called_once()
        args, kwargs = mock_log_event.call_args
        self.assertEqual(args[0], "CRITICAL_HALT")
        self.assertEqual(args[1], "ALARM")
        self.assertIn("pH invalid", args[2])

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.live_ph_data', [{"value": 6.0, "status": "OK"}])
    @patch('dosing.live_tds_data', [{"value": 8.5, "status": "OK"}])
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('dosing.hal.emergency_stop_all')
    def test_check_and_adjust_sensors_hardware_max_tds(self, mock_estop, mock_log_event, mock_monitor, mock_limits, mock_status):
        import dosing
        from dosing import check_and_adjust_sensors
        dosing._reset_dosing_state()
        
        # Ticks 1-9: silent safety hold (0 email alerts sent)
        for _ in range(9):
            check_and_adjust_sensors()
            self.assertTrue(mock_estop.called)
            mock_monitor.send_email_alert.assert_not_called()
            mock_log_event.assert_not_called()

        # Tick 10: triggers critical email alert
        check_and_adjust_sensors()
        mock_monitor.send_email_alert.assert_called_once()
        args, kwargs = mock_log_event.call_args
        self.assertEqual(args[0], "CRITICAL_HALT")
        self.assertEqual(args[1], "ALARM")
        self.assertIn("EC critical hardware safety limit reached", args[2])

    def test_atomic_system_config_save(self):
        from dosing import save_system_config
        test_config = {"test_key": "test_value"}
        test_filename = "test_system_config_temp.json"
        try:
            save_system_config(test_config, config_path=test_filename)
            self.assertTrue(os.path.exists(test_filename))
            with open(test_filename, "r") as f:
                import json
                data = json.load(f)
            self.assertEqual(data, test_config)
        finally:
            if os.path.exists(test_filename):
                os.remove(test_filename)

    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('dosing.log_event')
    def test_async_dosing_invalid_params_guard(self, mock_log_event, mock_file_open, mock_exists):
        """Verify _async_dosing aborts with DOSING_GUARD_FAIL when flow rate or volume is <= 0."""
        mock_exists.return_value = True
        config_data = '{"pump_flow_rate_ml_per_sec": 0.0, "reservoir_volume_l": 50.0}'
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=False)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)
        
        _async_dosing(ph_val=6.0, tds_val=0.5, l_ph=l_ph, l_tds=l_tds)
        
        mock_log_event.assert_called_once()
        args = mock_log_event.call_args[0]
        self.assertEqual(args[0], "DOSING_GUARD_FAIL")
        self.assertEqual(args[1], "WARNING")

    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('hal.pump_start')
    @patch('hal.pump_stop')
    @patch('time.sleep')
    @patch('dosing.log_pump_action')
    @patch('dosing.log_event')
    def test_async_dosing_min_dose_time_clamping(
        self, mock_log_event, mock_log_pump, mock_sleep, mock_stop, mock_start, mock_file_open, mock_exists
    ):
        """Verify _async_dosing clamps calculated run duration up to min_dose_time_sec."""
        mock_exists.return_value = True
        config_data = """{
            "reservoir_volume_l": 10.0,
            "pump_flow_rate_ml_per_sec": 1.0,
            "nutrient_ml_per_l_per_ec": 0.1,
            "min_dose_time_sec": 2.0,
            "max_dose_time_sec": 30.0,
            "dry_run_mode": false
        }"""
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=False)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)
        
        _async_dosing(ph_val=6.0, tds_val=0.99, l_ph=l_ph, l_tds=l_tds)
        
        mock_log_pump.assert_any_call(1, 2.0, "Automatic")
        mock_log_pump.assert_any_call(2, 2.0, "Automatic")

    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('hal.pump_start')
    @patch('hal.pump_stop')
    @patch('time.sleep')
    @patch('dosing.log_pump_action')
    @patch('dosing.log_event')
    def test_async_dosing_ph_up_path(
        self, mock_log_event, mock_log_pump, mock_sleep, mock_stop, mock_start, mock_file_open, mock_exists
    ):
        """Verify _async_dosing pH UP dosing path actuates pump 3 and logs event."""
        import dosing
        mock_exists.return_value = True
        config_data = """{
            "reservoir_volume_l": 50.0,
            "pump_flow_rate_ml_per_sec": 1.0,
            "ph_up_ml_per_l_per_ph": 0.5,
            "max_dose_time_sec": 30.0,
            "dry_run_mode": false
        }"""
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 2.0, is_active=False)
        
        _async_dosing(ph_val=5.0, tds_val=1.5, l_ph=l_ph, l_tds=l_tds)
        
        mock_log_event.assert_any_call(
            "PUMP_ACTIVATION",
            "INFO",
            "Dosed pH UP for 12.50s (Delta: 1.00 pH)"
        )
        mock_log_pump.assert_any_call(3, 12.5, "Automatic")
        self.assertIsNotNone(dosing._last_ph_up_prediction)
        self.assertEqual(dosing._last_ph_up_prediction['pre_val'], 5.0)

    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('dosing.log_event')
    @patch('dosing.log_pump_action')
    def test_async_dosing_ec_danger_alarm(self, mock_log_pump, mock_log_event, mock_file_open, mock_exists):
        """Verify _async_dosing logs EC_DANGER_ALARM and skips nutrient pumps when EC > max_value."""
        mock_exists.return_value = True
        config_data = '{"reservoir_volume_l": 50.0, "pump_flow_rate_ml_per_sec": 1.0}'
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=False)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)
        
        _async_dosing(ph_val=6.0, tds_val=2.5, l_ph=l_ph, l_tds=l_tds)
        
        mock_log_event.assert_called_once_with(
            "EC_DANGER_ALARM", "ALARM", "EC value 2.5 exceeds limit 2.0. Dosing halted.", {"current_ec": 2.5}
        )
        mock_log_pump.assert_not_called()

    @patch('dosing.save_system_config')
    @patch('dosing.log_event')
    def test_evaluate_last_dose_adaptive_recalibration(self, mock_log_event, mock_save_config):
        """Verify _evaluate_last_dose adjusts nutrient, pH UP, and pH DOWN factors based on actual vs predicted delta."""
        import dosing
        import time
        now = time.time()
        dosing._last_ec_prediction = {'pre_val': 1.0, 'predicted_delta': 0.5, 'time': now - 1000}
        dosing._last_ph_up_prediction = {'pre_val': 5.0, 'predicted_delta': 0.5, 'time': now - 1000}
        dosing._last_ph_down_prediction = {'pre_val': 7.0, 'predicted_delta': 0.5, 'time': now - 1000}
        
        config = {
            "cooldown_minutes": 15.0,
            "nutrient_ml_per_l_per_ec": 2.0,
            "ph_up_ml_per_l_per_ph": 0.5,
            "ph_down_ml_per_l_per_ph": 0.5
        }
        
        dosing._evaluate_last_dose(current_tds=1.25, current_ph=5.25, config=config)
        
        self.assertEqual(config["nutrient_ml_per_l_per_ec"], 2.4)
        self.assertEqual(config["ph_up_ml_per_l_per_ph"], 0.6)
        self.assertIsNone(dosing._last_ec_prediction)
        self.assertIsNone(dosing._last_ph_up_prediction)

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.live_ph_data', [{"value": 6.0, "status": "OK"}])
    @patch('dosing.live_tds_data', [{"value": 2.9, "status": "OK"}])
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('db_cache.get_plant_status', return_value={"plant_name": "Lettuce", "state": False, "plant_stage": "Seedling"})
    @patch('db_cache.get_sensor_limit', side_effect=lambda k: {"ph": {"min": 5.5, "max": 6.5, "active": True}, "tds": {"min": 1.0, "max": 3.0, "active": True}}.get(k))
    def test_check_and_adjust_sensors_prolonged_high_ec_intervention(
        self, mock_cache_limit, mock_cache_status, mock_log_event, mock_monitor, mock_limits, mock_status
    ):
        """Verify check_and_adjust_sensors sends DANGER alert when EC stays high for >= 1 hour."""
        import dosing
        import time
        status_rec = MagicMock()
        status_rec.plant_name = "Lettuce"
        status_rec.state = False
        mock_status.query.first.return_value = status_rec
        
        l_ph_db = DummyLimit(5.5, 6.5, is_active=True)
        l_tds_db = DummyLimit(1.0, 3.0, is_active=True)
        
        def filter_by_side_effect(**kwargs):
            m = MagicMock()
            if kwargs.get('sensor_type') == 'ph': m.first.return_value = l_ph_db
            elif kwargs.get('sensor_type') == 'tds': m.first.return_value = l_tds_db
            return m
        mock_limits.query.filter_by.side_effect = filter_by_side_effect
        
        dosing._ec_high_since = time.time() - 3601
        dosing._ec_intervention_last_sent = None
        
        dosing.check_and_adjust_sensors()
        
        mock_monitor.send_email_alert.assert_called_once()
        args, kwargs = mock_monitor.send_email_alert.call_args
        self.assertEqual(args[0], "SYSTEM")
        self.assertIn("Manual intervention required", args[1])
        self.assertEqual(args[2], "DANGER")
        self.assertTrue(kwargs.get("bypass_cooldown"))

    @patch('dosing.sensor_monitor')
    def test_log_pump_action_solution_tank_depletion_and_alert(self, mock_monitor):
        """Verify log_pump_action updates SolutionTanks volume, clamps at 0.0, and triggers low volume email alert."""
        from dosing import log_pump_action
        from models import SolutionTanks
        from config import app, db
        
        with app.app_context():
            db.create_all()
            # Clear any existing tank with tank_id=1 to prevent conflicts
            existing = SolutionTanks.query.filter_by(tank_id=1).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
                
            tank = SolutionTanks(tank_id=1, name="Nutrient A", current_volume_ml=50.0, capacity_ml=1000.0, last_alert_sent=0.0)
            db.session.add(tank)
            db.session.commit()
            
            log_pump_action(pump_id=1, duration=200.0, trigger_type="Automatic")
            
            updated_tank = SolutionTanks.query.filter_by(tank_id=1).first()
            self.assertEqual(updated_tank.current_volume_ml, 0.0)
            mock_monitor.send_email_alert.assert_called_once()
            args = mock_monitor.send_email_alert.call_args[0]
            self.assertEqual(args[0], "SYSTEM")
            # Tank at exactly 0 triggers the EMPTY alert (not the low-level one)
            self.assertIn("EMPTY", args[1])
            self.assertEqual(args[2], "DANGER")

if __name__ == '__main__':
    unittest.main()

