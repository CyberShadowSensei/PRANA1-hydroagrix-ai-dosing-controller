import sys
import pytest
import unittest
from unittest.mock import patch, mock_open
import json

# Mock hardware/Pi-only modules
sys.modules['smbus2'] = unittest.mock.MagicMock()
sys.modules['grove'] = unittest.mock.MagicMock()
sys.modules['grove.grove_moisture_sensor'] = unittest.mock.MagicMock()
sys.modules['RPi'] = unittest.mock.MagicMock()
sys.modules['RPi.GPIO'] = unittest.mock.MagicMock()
try:
    import cv2
except ImportError:
    sys.modules['cv2'] = unittest.mock.MagicMock()

from dosing import _async_dosing
import dosing

def _make_config(**kwargs):
    return json.dumps(kwargs)

class DummyLimit:
    def __init__(self, min_val, max_val, is_active=True):
        self.min_value = min_val
        self.max_value = max_val
        self.is_active = is_active


class TestDosingEdgeCases(unittest.TestCase):

    def setUp(self):
        dosing._reset_dosing_state()

    @patch('os.path.exists', return_value=True)
    @patch('dosing.log_event')
    def test_invalid_parameters_aborts_dosing(self, mock_log_event, mock_exists):
        """Verify that invalid flow rates or volumes abort dosing immediately."""
        cfg = _make_config(
            reservoir_volume_l=0.0,  # Invalid volume
            pump_flow_rate_ml_per_sec=1.0
        )
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)

        with patch('builtins.open', mock_open(read_data=cfg)):
            _async_dosing(ph_val=6.0, tds_val=0.5, l_ph=l_ph, l_tds=l_tds)

        # Ensure DOSING_GUARD_FAIL is logged
        guard_calls = [c for c in mock_log_event.mock_calls if c.args[0] == "DOSING_GUARD_FAIL"]
        self.assertEqual(len(guard_calls), 1)

    @patch('os.path.exists', return_value=True)
    @patch('dosing.log_event')
    @patch('hal.pump_start')
    @patch('dosing.check_tank_has_solution_permission', return_value=True)
    def test_nutrient_ph_guard_blocks_nutrients_when_ph_drops(
        self, mock_permission, mock_start, mock_log_event, mock_exists
    ):
        """Verify that nutrient dosing is skipped if it would push pH below the safe limit."""
        cfg = _make_config(
            reservoir_volume_l=50.0,
            pump_flow_rate_ml_per_sec=1.0,
            nutrient_ml_per_l_per_ec=2.0
        )
        l_ph = DummyLimit(5.8, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)
        
        # Mock average pH impact of nutrients to be highly acidic (-0.1 pH per mL)
        with patch('builtins.open', mock_open(read_data=cfg)), \
             patch('dosing.nutrient_impact_tracker.get_average_ph_impact_per_ml', return_value=-0.1):
            
            # pH is currently 5.9, min limit is 5.8
            # EC target is 1.0 + 0.2 = 1.2
            # Delta EC = 1.2 - 0.8 = 0.4.
            # Volume = 0.4 * 50 * 2 = 40 mL.
            # Predicted pH drop = 40 mL * 0.1 = 4.0 pH.
            # 5.9 - 4.0 = 1.9 < 5.8! So it should abort.
            _async_dosing(ph_val=5.9, tds_val=0.8, l_ph=l_ph, l_tds=l_tds)

        guard_calls = [c for c in mock_log_event.mock_calls if c.args[0] == "NUTRIENT_PH_GUARD"]
        self.assertEqual(len(guard_calls), 1)
        # Pump 1 (Nutrient A) should NOT have started
        mock_start.assert_not_called()

    @patch('os.path.exists', return_value=True)
    @patch('dosing.log_event')
    @patch('hal.pump_start')
    @patch('hal.pump_stop')
    @patch('time.sleep')
    @patch('dosing.check_tank_has_solution_permission', return_value=True)
    @patch('dosing.nutrient_impact_tracker.get_average_ph_impact_per_ml', return_value=0.0)
    def test_max_ec_shift_clamps_dosing_time(
        self, mock_impact, mock_permission, mock_sleep, mock_stop, mock_start, mock_log_event, mock_exists
    ):
        """Verify that MAX_EC_SHIFT restricts the maximum allowable dose."""
        cfg = _make_config(
            reservoir_volume_l=100.0,
            pump_flow_rate_ml_per_sec=1.0,
            nutrient_ml_per_l_per_ec=5.0,  # Huge factor
            MAX_EC_SHIFT=0.2, # Strict limit
            max_dose_time_sec=300.0
        )
        l_ph = DummyLimit(5.5, 6.5, is_active=False)
        l_tds = DummyLimit(1.0, 2.0, is_active=True)
        
        with patch('builtins.open', mock_open(read_data=cfg)):
            # Target EC = 1.2. Delta = 1.2 - 0.2 = 1.0
            # Required volume = 1.0 * 100 * 5 = 500 mL -> 500 seconds
            # MAX_EC_SHIFT = 0.2
            # max_dose = (0.2 * 100 * 5) / 1.0 = 100 seconds
            _async_dosing(ph_val=6.0, tds_val=0.2, l_ph=l_ph, l_tds=l_tds)

        # Expected log should show dose was clamped to 100 seconds
        mock_log_event.assert_any_call(
            "PUMP_ACTIVATION", "INFO", "Dosed Nutrient A for 100.00s (Delta: 1.00 EC)"
        )

