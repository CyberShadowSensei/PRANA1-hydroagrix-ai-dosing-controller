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
            "reservoir_volume_l": 10.0,
            "max_dose_time_sec": 30.0,
            "mixing_time_sec": 15.0,
            "pumps": {
                "1": {"flow_rate_ml_per_sec": 2.0},
                "2": {"flow_rate_ml_per_sec": 5.0}
            }
        }"""
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=False)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)
        
        _async_dosing(ph_val=6.0, tds_val=0.8, l_ph=l_ph, l_tds=l_tds)
        
        # Verify log_event was called with specific event ID and minimal debug keys
        mock_log_event.assert_any_call(
            "DOSING_STARTED_EC",
            "DOSING",
            "EC dosing started: current EC=0.8 mS/cm below min=1.0 mS/cm. Targeting midpoint=1.50 mS/cm.",
            {
                "current_ec": 0.8,
                "target_ec": 1.5,
                "pump_1_sec": 30.0,
                "pump_2_sec": 14.0
            }
        )
        
        # Verify log_pump_action calls
        mock_log_pump.assert_any_call(1, 30.0, "Automatic")
        mock_log_pump.assert_any_call(2, 14.0, "Automatic")

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
            "reservoir_volume_l": 20.0,
            "max_dose_time_sec": 30.0,
            "pumps": {
                "4": {"flow_rate_ml_per_sec": 4.0}
            }
        }"""
        mock_file_open.return_value.__enter__.return_value.read.return_value = config_data
        
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 2.0, is_active=False)
        
        _async_dosing(ph_val=7.0, tds_val=1.5, l_ph=l_ph, l_tds=l_tds)
        
        # Verify log_event was called with specific event ID and minimal debug keys
        mock_log_event.assert_called_once_with(
            "DOSING_STARTED_PH_DOWN",
            "DOSING",
            "pH DOWN dosing started: current pH=7.0 above max=6.5. Targeting midpoint=6.00.",
            {
                "current_ph": 7.0,
                "target_ph": 6.0,
                "pump_id": 4,
                "duration_sec": 10.0
            }
        )
        mock_log_pump.assert_called_once_with(4, 10.0, "Automatic")

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

if __name__ == '__main__':
    unittest.main()
