"""
Tests for Tasks 3 and 4:
  - Minimum pump runtime clamp (MIN_PUMP_RUN_SEC = 2.0)
  - Self-tuning factor correction (_evaluate_last_dose)
  - EC stuck-high intervention alert
"""
import sys
import json
import time
import unittest
from unittest.mock import patch, MagicMock, mock_open

# Mock all hardware/Pi-only modules so tests run on Windows
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()
try:
    import cv2
except ImportError:
    sys.modules['cv2'] = MagicMock()

import dosing
from dosing import _async_dosing, _evaluate_last_dose


class DummyLimit:
    def __init__(self, min_val, max_val, is_active=True):
        self.min_value = min_val
        self.max_value = max_val
        self.is_active = is_active


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Return a minimal config dict, optionally overriding any keys."""
    base = {
        "reservoir_volume_l": 50.0,
        "pump_flow_rate_ml_per_sec": 1.0,
        "nutrient_ml_per_l_per_ec": 2.0,
        "ph_up_ml_per_l_per_ph": 0.5,
        "ph_down_ml_per_l_per_ph": 0.5,
        "max_dose_time_sec": 300.0,
        "MAX_EC_SHIFT": 0.5,
        "MAX_PH_SHIFT": 0.5,
        "nutrient_gap_seconds": 0.0,
        "cooldown_minutes": 15.0,
    }
    base.update(overrides)
    return base


def _reset_dosing_state():
    """Reset all module-level state between tests."""
    dosing._reset_dosing_state()



# ---------------------------------------------------------------------------
# Tests: Minimum Pump Runtime Clamp
# ---------------------------------------------------------------------------

class TestMinPumpRuntimeClamp(unittest.TestCase):

    def setUp(self):
        _reset_dosing_state()
        import sensors
        sensors.live_ph_data.clear()
        sensors.live_tds_data.clear()


    def _run_async_dosing(self, config_dict, ph_val, tds_val, l_ph, l_tds):
        config_json = json.dumps(config_dict)
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_json)), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep'), \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            _async_dosing(ph_val=ph_val, tds_val=tds_val, l_ph=l_ph, l_tds=l_tds)

    def test_short_ec_dose_clamped_to_minimum(self):
        """A tiny EC delta that would produce < 2s of pump time is clamped to exactly 2.0s."""
        # delta = 0.01 EC, factor=2.0, vol=50 -> required_ml=1.0, flow=1.0 -> dose_time=1.0s < 2.0s
        cfg = _make_config(
            nutrient_ml_per_l_per_ec=2.0,
            pump_flow_rate_ml_per_sec=1.0,
            reservoir_volume_l=50.0,
        )
        l_tds = DummyLimit(min_val=1.5, max_val=2.5)
        l_ph = DummyLimit(5.5, 6.5, is_active=False)

        # tds_val=1.49 -> delta to midpoint = 2.0 - 1.49 = 0.51 EC
        # required_ml = 0.51 * 50 * 2.0 = 51 mL -> dose_time = 51s > 2s (capped by MAX_EC_SHIFT ceiling)
        # Use a very small delta instead: tds=1.499, target midpoint=2.0
        # Actually let's force a sub-2s scenario: tiny vol
        cfg['reservoir_volume_l'] = 0.5   # required_ml = delta * 0.5 * 2.0 -> small
        cfg['MAX_EC_SHIFT'] = 0.5

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep') as mock_sleep, \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            # tds=1.49, min=1.5 -> delta to midpoint = 2.0 - 1.49 = 0.51
            # required_ml = 0.51 * 0.5 * 2.0 = 0.51 -> dose_time = 0.51s  (< 2.0)
            _async_dosing(ph_val=6.0, tds_val=1.49, l_ph=l_ph, l_tds=l_tds)

        # pump_start is called; sleep is called with clamped 2.0s (not 0.51s)
        total_sleep = sum(c.args[0] for c in mock_sleep.call_args_list)
        # Nutrient A (2.0s) + Nutrient B (2.0s) = 4.0s total
        self.assertAlmostEqual(total_sleep, 2 * dosing.MIN_PUMP_RUN_SEC, delta=0.01,
                               msg=f"Expected total sleep ~{2 * dosing.MIN_PUMP_RUN_SEC}s, got {total_sleep}s")

    def test_zero_dose_not_clamped_to_minimum(self):
        """When EC is in range, dose_time is 0 and pump is never started."""
        cfg = _make_config()
        l_tds = DummyLimit(min_val=1.0, max_val=3.0)
        l_ph = DummyLimit(5.5, 6.5, is_active=False)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start') as mock_start, \
             patch('hal.pump_stop'), \
             patch('time.sleep'), \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            _async_dosing(ph_val=6.0, tds_val=2.0, l_ph=l_ph, l_tds=l_tds)

        mock_start.assert_not_called()

    def test_large_dose_unchanged_by_clamp(self):
        """A calculated dose already > 2s is not shortened by the clamp."""
        cfg = _make_config(
            reservoir_volume_l=50.0,
            pump_flow_rate_ml_per_sec=1.0,
            nutrient_ml_per_l_per_ec=2.0,
            max_dose_time_sec=300.0,
        )
        l_tds = DummyLimit(min_val=1.0, max_val=3.0)
        l_ph = DummyLimit(5.5, 6.5, is_active=False)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep') as mock_sleep, \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            # tds=0.5, min=1.0, target midpoint=2.0, delta=1.5
            # required_ml = 1.5 * 50 * 2.0 = 150 -> dose_time = 150s (> 2s, no clamp)
            _async_dosing(ph_val=6.0, tds_val=0.5, l_ph=l_ph, l_tds=l_tds)

        total_sleep = sum(c.args[0] for c in mock_sleep.call_args_list)
        # 50s total for pump 1 and 50s total for pump 2 = 100s
        self.assertAlmostEqual(total_sleep, 100.0, delta=0.01,
                               msg=f"Expected total sleep 100.0s across pumps A/B, got {total_sleep}s")

    def test_ph_up_dose_clamped_to_minimum(self):
        """Small pH UP dose is also clamped to MIN_PUMP_RUN_SEC."""
        cfg = _make_config(
            reservoir_volume_l=0.5,
            pump_flow_rate_ml_per_sec=1.0,
            ph_up_ml_per_l_per_ph=0.5,
        )
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 3.0, is_active=False)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep') as mock_sleep, \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'), \
             patch('dosing.check_tank_has_solution_permission', return_value=True):
            # ph=5.4 (below min=5.5), target midpoint=6.0, delta=0.6
            # required_ml = 0.6 * 0.5 * 0.5 = 0.15 -> dose_time = 0.15s < 2s -> clamped
            _async_dosing(ph_val=5.4, tds_val=2.0, l_ph=l_ph, l_tds=l_tds)

        total_sleep = sum(c.args[0] for c in mock_sleep.call_args_list)
        self.assertAlmostEqual(total_sleep, dosing.MIN_PUMP_RUN_SEC, delta=0.01)

    def test_ph_down_dose_clamped_to_minimum(self):
        """Small pH DOWN dose is also clamped to MIN_PUMP_RUN_SEC."""
        cfg = _make_config(
            reservoir_volume_l=0.5,
            pump_flow_rate_ml_per_sec=1.0,
            ph_down_ml_per_l_per_ph=0.5,
        )
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 3.0, is_active=False)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep') as mock_sleep, \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            # ph=6.6 (above max=6.5), target midpoint=6.0, delta=0.6
            # required_ml = 0.6 * 0.5 * 0.5 = 0.15 -> dose_time = 0.15s < 2s -> clamped
            _async_dosing(ph_val=6.6, tds_val=2.0, l_ph=l_ph, l_tds=l_tds)

        total_sleep = sum(c.args[0] for c in mock_sleep.call_args_list)
        self.assertAlmostEqual(total_sleep, dosing.MIN_PUMP_RUN_SEC, delta=0.01)


# ---------------------------------------------------------------------------
# Tests: Prediction Recording
# ---------------------------------------------------------------------------

class TestPredictionRecording(unittest.TestCase):

    def setUp(self):
        _reset_dosing_state()

    def test_ec_prediction_recorded_after_dose(self):
        """_last_ec_prediction is set with correct keys after an EC dose fires."""
        cfg = _make_config(reservoir_volume_l=50.0, pump_flow_rate_ml_per_sec=1.0)
        l_tds = DummyLimit(2.0, 3.0)
        l_ph = DummyLimit(5.5, 6.5, is_active=False)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep'), \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            _async_dosing(ph_val=6.0, tds_val=1.5, l_ph=l_ph, l_tds=l_tds)

        pred = dosing._last_ec_prediction
        self.assertIsNotNone(pred)
        self.assertAlmostEqual(pred['pre_val'], 1.5)
        # target midpoint = 2.5, delta = 2.5 - 1.5 = 1.0
        self.assertAlmostEqual(pred['predicted_delta'], 1.0)
        self.assertIn('time', pred)

    def test_ph_up_prediction_recorded_after_dose(self):
        """_last_ph_up_prediction is set after a pH UP dose fires."""
        cfg = _make_config(reservoir_volume_l=50.0, pump_flow_rate_ml_per_sec=1.0)
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 3.0, is_active=False)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep'), \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            _async_dosing(ph_val=5.0, tds_val=2.0, l_ph=l_ph, l_tds=l_tds)

        pred = dosing._last_ph_up_prediction
        self.assertIsNotNone(pred)
        self.assertAlmostEqual(pred['pre_val'], 5.0)

    def test_ph_down_prediction_recorded_after_dose(self):
        """_last_ph_down_prediction is set after a pH DOWN dose fires."""
        cfg = _make_config(reservoir_volume_l=50.0, pump_flow_rate_ml_per_sec=1.0)
        l_ph = DummyLimit(5.5, 6.5, is_active=True)
        l_tds = DummyLimit(1.0, 3.0, is_active=False)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep'), \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            _async_dosing(ph_val=7.0, tds_val=2.0, l_ph=l_ph, l_tds=l_tds)

        pred = dosing._last_ph_down_prediction
        self.assertIsNotNone(pred)
        self.assertAlmostEqual(pred['pre_val'], 7.0)

    def test_no_prediction_when_in_range(self):
        """No prediction is set when sensors are within limits."""
        cfg = _make_config()
        l_tds = DummyLimit(1.0, 3.0)
        l_ph = DummyLimit(5.5, 6.5, is_active=True)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(cfg))), \
             patch('hal.pump_start'), \
             patch('hal.pump_stop'), \
             patch('time.sleep'), \
             patch('dosing.log_pump_action'), \
             patch('dosing.log_event'):
            _async_dosing(ph_val=6.0, tds_val=2.0, l_ph=l_ph, l_tds=l_tds)

        self.assertIsNone(dosing._last_ec_prediction)
        self.assertIsNone(dosing._last_ph_up_prediction)
        self.assertIsNone(dosing._last_ph_down_prediction)


# ---------------------------------------------------------------------------
# Tests: Self-Tuning Factor Correction
# ---------------------------------------------------------------------------

class TestEvaluateLastDose(unittest.TestCase):

    def setUp(self):
        _reset_dosing_state()

    def _call_evaluate(self, current_tds, current_ph, config, prediction_age_s=None, cooldown_minutes=15.0):
        """Helper: plant a prediction and call _evaluate_last_dose."""
        config['cooldown_minutes'] = cooldown_minutes
        age = prediction_age_s if prediction_age_s is not None else cooldown_minutes * 60 + 10

        dosing._last_ec_prediction = {
            'pre_val': 1.0,
            'predicted_delta': 1.0,  # predicted EC would rise by 1.0
            'time': time.time() - age,
        }

        written = {}

        def fake_open(path, mode='r', *args, **kwargs):
            import io
            if 'w' in mode:
                buf = []
                class FakeWriter:
                    def __enter__(self): return self
                    def __exit__(self, *a):
                        try:
                            written.update(json.loads(''.join(buf)))
                        except Exception:
                            pass
                    def write(self, data): buf.append(data)
                return FakeWriter()
            return mock_open(read_data=json.dumps(config))(path, mode)

        with patch('builtins.open', side_effect=fake_open), \
             patch('os.replace'), \
             patch('dosing.log_event') as mock_log:
            _evaluate_last_dose(current_tds, current_ph, config)

        return written, mock_log


    def test_underdose_nudges_factor_up(self):
        """If actual EC rise was half of predicted (50%), factor should increase."""
        cfg = _make_config(nutrient_ml_per_l_per_ec=2.0)
        # predicted_delta=1.0 EC; actual only rose by 0.5 (from 1.0 to 1.5)
        written, mock_log = self._call_evaluate(current_tds=1.5, current_ph=6.0, config=cfg)

        new_factor = written.get('nutrient_ml_per_l_per_ec')
        self.assertIsNotNone(new_factor, "system_config.json should have been written")
        self.assertGreater(new_factor, 2.0, "Factor should increase after underdose")
        mock_log.assert_called_once()
        self.assertIn('DOSING_CALIBRATION', mock_log.call_args.args[0])

    def test_overdose_nudges_factor_down(self):
        """If actual EC rise was double predicted (200%), factor should decrease."""
        cfg = _make_config(nutrient_ml_per_l_per_ec=2.0)
        # predicted_delta=1.0; actual rose by 2.0 (from 1.0 to 3.0)
        written, mock_log = self._call_evaluate(current_tds=3.0, current_ph=6.0, config=cfg)

        new_factor = written.get('nutrient_ml_per_l_per_ec')
        self.assertIsNotNone(new_factor)
        self.assertLess(new_factor, 2.0, "Factor should decrease after overdose")

    def test_perfect_dose_factor_unchanged(self):
        """If actual delta exactly matches predicted, factor stays the same."""
        cfg = _make_config(nutrient_ml_per_l_per_ec=2.0)
        # predicted=1.0, actual=1.0 -> ratio=1.0 -> correction=current -> new=current
        written, _ = self._call_evaluate(current_tds=2.0, current_ph=6.0, config=cfg)

        new_factor = written.get('nutrient_ml_per_l_per_ec', 2.0)
        self.assertAlmostEqual(new_factor, 2.0, places=3)

    def test_skips_if_cooldown_not_elapsed(self):
        """Nothing is written if prediction is newer than the cooldown window."""
        cfg = _make_config(nutrient_ml_per_l_per_ec=2.0)
        # Set prediction to only 10 seconds ago; cooldown is 15 minutes
        dosing._last_ec_prediction = {
            'pre_val': 1.0, 'predicted_delta': 1.0, 'time': time.time() - 10
        }
        with patch('builtins.open') as mock_file, \
             patch('dosing.log_event') as mock_log:
            _evaluate_last_dose(2.0, 6.0, cfg)

        mock_file.assert_not_called()
        mock_log.assert_not_called()

    def test_skips_if_actual_delta_negative(self):
        """No factor update if actual EC went down (sensor noise / dilution)."""
        cfg = _make_config(nutrient_ml_per_l_per_ec=2.0)
        dosing._last_ec_prediction = {
            'pre_val': 2.0, 'predicted_delta': 1.0,
            'time': time.time() - 1000
        }
        with patch('builtins.open') as mock_file, \
             patch('dosing.log_event') as mock_log:
            # actual EC dropped from 2.0 to 1.5 -> actual_delta = -0.5
            _evaluate_last_dose(1.5, 6.0, cfg)

        mock_file.assert_not_called()
        mock_log.assert_not_called()
        # Prediction should still be cleared
        self.assertIsNone(dosing._last_ec_prediction)

    def test_factor_clamped_to_max(self):
        """A massive underdose cannot push factor above 10.0."""
        # Start with current_factor=9.9; ratio=0.001 (almost no effect seen)
        cfg = _make_config(nutrient_ml_per_l_per_ec=9.9)
        dosing._last_ec_prediction = {
            'pre_val': 1.0, 'predicted_delta': 1.0,
            'time': time.time() - 1000
        }
        written = {}

        def fake_open(path, mode='r', *args, **kwargs):
            if 'w' in mode:
                buf = []
                class FakeWriter:
                    def __enter__(self): return self
                    def __exit__(self, *a):
                        try:
                            written.update(json.loads(''.join(buf)))
                        except Exception:
                            pass
                    def write(self, data): buf.append(data)
                return FakeWriter()
            return mock_open(read_data=json.dumps(cfg))(path, mode)

        with patch('builtins.open', side_effect=fake_open), \
             patch('os.replace'), \
             patch('dosing.log_event'):
            # actual=1.001 -> actual_delta=0.001 -> ratio=0.001 -> correction=9900
            _evaluate_last_dose(1.001, 6.0, cfg)

        new_factor = written.get('nutrient_ml_per_l_per_ec', 0)
        self.assertLessEqual(new_factor, 10.0, "Factor must be clamped at 10.0")

    def test_factor_clamped_to_min(self):
        """A massive overdose cannot push factor below 0.5."""
        cfg = _make_config(nutrient_ml_per_l_per_ec=0.6)
        dosing._last_ec_prediction = {
            'pre_val': 1.0, 'predicted_delta': 1.0,
            'time': time.time() - 1000
        }
        written = {}

        def fake_open(path, mode='r', *args, **kwargs):
            if 'w' in mode:
                buf = []
                class FakeWriter:
                    def __enter__(self): return self
                    def __exit__(self, *a):
                        try:
                            written.update(json.loads(''.join(buf)))
                        except Exception:
                            pass
                    def write(self, data): buf.append(data)
                return FakeWriter()
            return mock_open(read_data=json.dumps(cfg))(path, mode)

        with patch('builtins.open', side_effect=fake_open), \
             patch('os.replace'), \
             patch('dosing.log_event'):
            # actual=1000 -> ratio=999 -> correction tiny -> new_factor < 0.5
            _evaluate_last_dose(1001.0, 6.0, cfg)


        new_factor = written.get('nutrient_ml_per_l_per_ec', 1.0)
        self.assertGreaterEqual(new_factor, 0.5, "Factor must be clamped at 0.5")

    def test_prediction_cleared_after_evaluation(self):
        """_last_ec_prediction is set to None after evaluation regardless of outcome."""
        cfg = _make_config(nutrient_ml_per_l_per_ec=2.0)
        dosing._last_ec_prediction = {
            'pre_val': 1.0, 'predicted_delta': 1.0,
            'time': time.time() - 1000
        }
        with patch('builtins.open', mock_open()), \
             patch('os.replace'), \
             patch('dosing.log_event'):
            _evaluate_last_dose(2.0, 6.0, cfg)

        self.assertIsNone(dosing._last_ec_prediction)

    def test_ph_up_factor_corrected(self):
        """_evaluate_last_dose also corrects ph_up_ml_per_l_per_ph."""
        cfg = _make_config(ph_up_ml_per_l_per_ph=0.5, cooldown_minutes=0.0)
        dosing._last_ph_up_prediction = {
            'pre_val': 5.0, 'predicted_delta': 1.0,
            'time': time.time() - 10
        }
        written = {}

        def fake_open(path, mode='r', *args, **kwargs):
            if 'w' in mode:
                buf = []
                class FakeWriter:
                    def __enter__(self): return self
                    def __exit__(self, *a):
                        try:
                            written.update(json.loads(''.join(buf)))
                        except Exception:
                            pass
                    def write(self, data): buf.append(data)
                return FakeWriter()
            return mock_open(read_data=json.dumps(cfg))(path, mode)

        with patch('builtins.open', side_effect=fake_open), \
             patch('os.replace'), \
             patch('dosing.log_event'):
            # actual pH rose from 5.0 to 5.5 -> actual_delta=0.5, predicted=1.0 -> underdose
            _evaluate_last_dose(2.0, 5.5, cfg)

        new_factor = written.get('ph_up_ml_per_l_per_ph')
        self.assertIsNotNone(new_factor)
        self.assertGreater(new_factor, 0.5)

    def test_ph_down_factor_corrected(self):
        """_evaluate_last_dose also corrects ph_down_ml_per_l_per_ph."""
        cfg = _make_config(ph_down_ml_per_l_per_ph=0.5, cooldown_minutes=0.0)
        dosing._last_ph_down_prediction = {
            'pre_val': 7.0, 'predicted_delta': 1.0,
            'time': time.time() - 10
        }
        written = {}

        def fake_open(path, mode='r', *args, **kwargs):
            if 'w' in mode:
                buf = []
                class FakeWriter:
                    def __enter__(self): return self
                    def __exit__(self, *a):
                        try:
                            written.update(json.loads(''.join(buf)))
                        except Exception:
                            pass
                    def write(self, data): buf.append(data)
                return FakeWriter()
            return mock_open(read_data=json.dumps(cfg))(path, mode)

        with patch('builtins.open', side_effect=fake_open), \
             patch('os.replace'), \
             patch('dosing.log_event'):
            # actual pH dropped from 7.0 to 6.5 -> pre_val - current = 0.5, predicted=1.0 -> underdose
            _evaluate_last_dose(2.0, 6.5, cfg)

        new_factor = written.get('ph_down_ml_per_l_per_ph')
        self.assertIsNotNone(new_factor)
        self.assertGreater(new_factor, 0.5)



# ---------------------------------------------------------------------------
# Tests: EC Stuck-High Intervention Alert (Task 4)
# ---------------------------------------------------------------------------

class TestECInterventionAlert(unittest.TestCase):

    def setUp(self):
        _reset_dosing_state()

    def _run_check(self, tds_val, l_tds, mock_monitor, time_offset=0):
        """Invoke check_and_adjust_sensors with controlled time and sensor data."""
        from dosing import check_and_adjust_sensors

        with patch('dosing.PlantStageStatus') as mock_status, \
             patch('dosing.SensorLimits') as mock_limits, \
             patch('dosing.live_ph_data', [{"value": 6.0, "status": "OK"}]), \
             patch('dosing.live_tds_data', [{"value": tds_val, "status": "OK"}]), \
             patch('dosing.last_dosing_time', 0), \
             patch('dosing.sensor_monitor', mock_monitor), \
             patch('dosing.hal.emergency_stop_all'), \
             patch('dosing.log_event'), \
             patch('dosing._evaluate_last_dose'), \
             patch('os.path.exists', return_value=True), \
             patch('db_cache.get_plant_status', return_value={"plant_name": "Lettuce", "state": False, "plant_stage": "Seedling"}), \
             patch('db_cache.get_sensor_limit', side_effect=lambda k: {
                 "ph": {"min": 5.5, "max": 6.5, "active": True},
                 "tds": {"min": l_tds.min_value, "max": l_tds.max_value, "active": True}
             }.get(k)), \
             patch('builtins.open', mock_open(read_data=json.dumps({
                 'cooldown_minutes': 0.0
             }))):

            status_rec = MagicMock()
            status_rec.state = False
            mock_status.query.first.return_value = status_rec

            def filter_side(**kwargs):
                m = MagicMock()
                if kwargs.get('sensor_type') == 'ph':
                    m.first.return_value = DummyLimit(5.5, 6.5)
                elif kwargs.get('sensor_type') == 'tds':
                    m.first.return_value = l_tds
                return m

            mock_limits.query.filter_by.side_effect = filter_side

            with patch('time.time', return_value=time.time() + time_offset):
                check_and_adjust_sensors()

    def test_alert_fires_after_one_hour(self):
        """Alert fires when EC >= max-0.2 for > 1 hour."""
        l_tds = DummyLimit(1.0, 5.0)
        # EC = 4.9, threshold = 5.0 - 0.2 = 4.8 -> EC is above threshold
        mock_monitor = MagicMock()

        # First call: set _ec_high_since
        dosing._ec_high_since = time.time() - 3700  # 1h 1m 40s ago
        dosing._ec_intervention_last_sent = None

        self._run_check(tds_val=4.9, l_tds=l_tds, mock_monitor=mock_monitor)

        mock_monitor.send_email_alert.assert_called_once()
        call_args = mock_monitor.send_email_alert.call_args
        self.assertIn("Manual intervention", call_args.args[1])

    def test_alert_does_not_fire_before_one_hour(self):
        """Alert does NOT fire when EC has only been high for 30 minutes."""
        l_tds = DummyLimit(1.0, 5.0)
        mock_monitor = MagicMock()

        dosing._ec_high_since = time.time() - 1800  # 30 minutes ago
        dosing._ec_intervention_last_sent = None

        self._run_check(tds_val=4.9, l_tds=l_tds, mock_monitor=mock_monitor)

        mock_monitor.send_email_alert.assert_not_called()

    def test_alert_not_sent_within_renotify_window(self):
        """Only one alert per EC_RENOTIFY_HOURS window (no spam every check cycle)."""
        l_tds = DummyLimit(1.0, 5.0)
        mock_monitor = MagicMock()

        # Already sent 1h ago — renotify window is 4h, so should be suppressed
        dosing._ec_high_since = time.time() - 7200   # 2h stuck
        dosing._ec_intervention_last_sent = time.time() - 3600  # last sent 1h ago

        self._run_check(tds_val=4.9, l_tds=l_tds, mock_monitor=mock_monitor)

        mock_monitor.send_email_alert.assert_not_called()

    def test_renotify_fires_after_4_hours(self):
        """Re-alert fires after EC_RENOTIFY_HOURS (4h) have passed since last alert."""
        l_tds = DummyLimit(1.0, 5.0)
        mock_monitor = MagicMock()

        dosing._ec_high_since = time.time() - 20000   # stuck 5.5h
        dosing._ec_intervention_last_sent = time.time() - 14500  # last sent 4h 1m ago

        self._run_check(tds_val=4.9, l_tds=l_tds, mock_monitor=mock_monitor)

        mock_monitor.send_email_alert.assert_called_once()

    def test_latch_resets_when_ec_recovers(self):
        """_ec_high_since and _ec_intervention_last_sent reset when EC drops below threshold."""
        l_tds = DummyLimit(1.0, 5.0)
        mock_monitor = MagicMock()

        dosing._ec_high_since = time.time() - 7200
        dosing._ec_intervention_last_sent = time.time() - 5000

        # EC=2.9, threshold=3.0 -> below threshold -> should reset
        self._run_check(tds_val=2.9, l_tds=l_tds, mock_monitor=mock_monitor)

        self.assertIsNone(dosing._ec_high_since)
        self.assertIsNone(dosing._ec_intervention_last_sent)
        mock_monitor.send_email_alert.assert_not_called()

    def test_ec_in_range_never_triggers_alert(self):
        """EC well below threshold never sets the timer or fires an alert."""
        l_tds = DummyLimit(1.0, 5.0)
        mock_monitor = MagicMock()

        self._run_check(tds_val=1.5, l_tds=l_tds, mock_monitor=mock_monitor)

        mock_monitor.send_email_alert.assert_not_called()
        self.assertIsNone(dosing._ec_high_since)


# ---------------------------------------------------------------------------
# Tests: Tank Failsafes and Empty-Tank Alert Backoff
# ---------------------------------------------------------------------------

class TestTankFailsafesAndBackoff(unittest.TestCase):

    def setUp(self):
        _reset_dosing_state()
        import hal
        hal.pump_permission_check = None

    def tearDown(self):
        import hal
        hal.pump_permission_check = None

    @patch('dosing.app', create=True)
    @patch('dosing.db', create=True)
    @patch('dosing.sensor_monitor', create=True)
    @patch('dosing.log_event', create=True)
    def test_pump_blocked_when_tank_empty(self, mock_log, mock_monitor, mock_db, mock_app):
        """When a tank's volume is 0, the pump is blocked and safety check fails."""
        import hal
        from config import app as real_app
        mock_app.app_context = real_app.app_context
        
        # Setup mock SolutionTanks DB row
        mock_tank = MagicMock()
        mock_tank.tank_id = 1
        mock_tank.name = "Nutrient A"
        mock_tank.capacity_ml = 5000.0
        mock_tank.current_volume_ml = 0.0
        mock_tank.consecutive_blocked_attempts = 0
        mock_tank.next_allowed_alert_time = 0.0
        
        mock_st = MagicMock()
        mock_st.query.filter_by.return_value.first.return_value = mock_tank
        
        with patch('models.SolutionTanks', mock_st):
            from dosing import check_tank_has_solution_permission
            hal.pump_permission_check = check_tank_has_solution_permission
            
            allowed = check_tank_has_solution_permission(1)
            self.assertFalse(allowed)
            
            self.assertEqual(mock_tank.consecutive_blocked_attempts, 1)
            mock_monitor.send_email_alert.assert_called_once()
        
    @patch('dosing.app', create=True)
    @patch('dosing.db', create=True)
    @patch('dosing.sensor_monitor', create=True)
    @patch('dosing.log_event', create=True)
    def test_blocked_alert_backoff_timer(self, mock_log, mock_monitor, mock_db, mock_app):
        """Alerts are suppressed according to backoff delays when consecutive blocks occur."""
        from config import app as real_app
        mock_app.app_context = real_app.app_context
        
        # Setup mock SolutionTanks DB row
        mock_tank = MagicMock()
        mock_tank.tank_id = 1
        mock_tank.name = "Nutrient A"
        mock_tank.capacity_ml = 5000.0
        mock_tank.current_volume_ml = 0.0
        mock_tank.consecutive_blocked_attempts = 1
        mock_tank.next_allowed_alert_time = time.time() + 3600  # 1 hour in future
        
        mock_st = MagicMock()
        mock_st.query.filter_by.return_value.first.return_value = mock_tank
        
        with patch('models.SolutionTanks', mock_st):
            from dosing import check_tank_has_solution_permission
            
            # Second immediate attempt should be blocked but not trigger new email
            allowed = check_tank_has_solution_permission(1)
            self.assertFalse(allowed)
            
            self.assertEqual(mock_tank.consecutive_blocked_attempts, 1)  # unchanged
            mock_monitor.send_email_alert.assert_not_called()
            
            # Simulating time progression past the 1-hour delay
            mock_tank.next_allowed_alert_time = time.time() - 10
            allowed_after_delay = check_tank_has_solution_permission(1)
            self.assertFalse(allowed_after_delay)
            
            self.assertEqual(mock_tank.consecutive_blocked_attempts, 2)  # incremented
            mock_monitor.send_email_alert.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: ML Report Integration (YOLO & Fallback email attachments)
# ---------------------------------------------------------------------------

class TestMLDigestReport(unittest.TestCase):

    def setUp(self):
        _reset_dosing_state()

    @patch('grow_cycle_helper.get_active_grow_cycle_details', return_value={})
    @patch('routes.SolutionTanks')
    @patch('routes.generate_pdf_report_bytes', return_value=b"pdf")
    @patch('routes.sensor_monitor')
    @patch('routes.PHData')
    @patch('routes.TDSData')
    @patch('routes.TemperatureHumidityData')
    @patch('routes.PhotoRecord')
    @patch('routes.EventLog')
    @patch('routes.live_ph_data', [])
    @patch('routes.live_tds_data', [])
    @patch('routes.live_th_data', [])
    @patch('camera_ml.get_latest_frame')
    @patch('camera_ml.cv2.imwrite')
    @patch('camera_ml.db.session')
    @patch('camera_ml.get_ml_model', return_value=None)
    def test_digest_includes_ml_analysis_on_demand(
        self, mock_get_model, mock_db_sess, mock_imwrite, mock_frame, 
        mock_event, mock_photo, mock_th, mock_tds, mock_ph, mock_monitor, mock_pdf, mock_tanks, mock_cycle
    ):
        """When include_ml_analysis is True, email report invokes detect_plant_stage and attaches image."""
        from routes import _async_send_report_email_worker
        from config import app
        
        # Setup dummy frame
        import numpy as np
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_frame.return_value = dummy_img
        
        mock_event.timestamp.__ge__.return_value = True
        mock_event.timestamp.asc.return_value = MagicMock()
        
        # Setup mocks for routes
        mock_tanks.query.all.return_value = []
        mock_ph.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_tds.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_th.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_photo.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_event.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        # Mock file system open for the annotated frame
        with patch('builtins.open', mock_open(read_data=b"annotated_image_bytes")), \
             patch('os.path.exists', return_value=True):
            _async_send_report_email_worker(app, include_ml_analysis=True)
            
        # Verify email report dispatch was called with ML attachments
        mock_monitor.send_report.assert_called_once()
        args, kwargs = mock_monitor.send_report.call_args
        attachments = kwargs.get('attachments') or (args[2] if len(args) > 2 else {})
        self.assertIn("ml_analysis.jpg", attachments)
        self.assertEqual(attachments['ml_analysis.jpg'], b"annotated_image_bytes")
        self.assertIn("Machine Learning Vision Analysis", kwargs['html_body'])

    @patch('grow_cycle_helper.get_active_grow_cycle_details', return_value={})
    @patch('routes.SolutionTanks')
    @patch('routes.generate_pdf_report_bytes', return_value=b"pdf")
    @patch('routes.sensor_monitor')
    @patch('routes.PHData')
    @patch('routes.TDSData')
    @patch('routes.TemperatureHumidityData')
    @patch('routes.PhotoRecord')
    @patch('routes.EventLog')
    @patch('routes.live_ph_data', [])
    @patch('routes.live_tds_data', [])
    @patch('routes.live_th_data', [])
    @patch('camera_ml.get_latest_frame')
    def test_digest_skips_ml_analysis_when_disabled(
        self, mock_frame, mock_event, mock_photo, mock_th, mock_tds, mock_ph, mock_monitor, mock_pdf, mock_tanks, mock_cycle
    ):
        """When include_ml_analysis is False, detect_plant_stage is not run and no ML image is attached."""
        from routes import _async_send_report_email_worker
        from config import app
        
        mock_event.timestamp.__ge__.return_value = True
        mock_event.timestamp.asc.return_value = MagicMock()
        mock_tanks.query.all.return_value = []
        mock_ph.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_tds.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_th.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_photo.query.order_by.return_value.limit.return_value.all.return_value = []
        mock_event.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        _async_send_report_email_worker(app, include_ml_analysis=False)
        
        # Verify email report dispatch called but no ML attachment/text
        mock_monitor.send_report.assert_called_once()
        args, kwargs = mock_monitor.send_report.call_args
        attachments = kwargs.get('attachments') or (args[2] if len(args) > 2 else {})
        self.assertNotIn("ml_analysis.jpg", attachments)
        self.assertNotIn("Machine Learning Vision Analysis", kwargs['html_body'])
        mock_frame.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Anomaly Debouncing (10 Ticks)
# ---------------------------------------------------------------------------

class TestAnomalyDebouncing(unittest.TestCase):

    def setUp(self):
        _reset_dosing_state()
        import sensors
        sensors.live_ph_data.clear()
        sensors.live_tds_data.clear()

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('dosing.hal.emergency_stop_all')
    @patch('db_cache.get_plant_status', return_value={"plant_name": "Lettuce", "state": False, "plant_stage": "Seedling"})
    @patch('db_cache.get_sensor_limit', side_effect=lambda k: {"ph": {"min": 5.5, "max": 6.5, "active": True}, "tds": {"min": 1.0, "max": 2.0, "active": True}}.get(k))
    def test_strict_anomaly_debouncing_10_ticks(
        self, mock_cache_limit, mock_cache_status, mock_estop, mock_log_event, mock_monitor, mock_limits, mock_status
    ):
        import dosing
        from dosing import check_and_adjust_sensors
        import sensors

        status_rec = MagicMock()
        status_rec.plant_name = "Lettuce"
        status_rec.state = False
        mock_status.query.first.return_value = status_rec

        # Set invalid pH reading
        sensors.live_ph_data.append({"value": None, "status": "ERROR"})
        sensors.live_tds_data.append({"value": 1.5, "status": "OK"})

        # Ticks 1-9: silent safety hold (0 email alerts sent)
        for i in range(1, 10):
            check_and_adjust_sensors()
            self.assertTrue(mock_estop.called)
            mock_monitor.send_email_alert.assert_not_called()
            mock_log_event.assert_not_called()
            self.assertEqual(dosing._consecutive_halt_ticks, i)

        # Tick 10: triggers critical email alert and event log
        check_and_adjust_sensors()
        self.assertEqual(dosing._consecutive_halt_ticks, 10)
        mock_monitor.send_email_alert.assert_called_once()
        args, kwargs = mock_monitor.send_email_alert.call_args
        self.assertEqual(args[0], "SYSTEM")
        self.assertIn("Dosing system critical halt", args[1])
        self.assertEqual(args[2], "DANGER")

        # Now test RECOVERY alert on valid reading after 10 ticks
        sensors.live_ph_data.append({"value": 6.0, "status": "OK"})
        mock_monitor.send_email_alert.reset_mock()
        check_and_adjust_sensors()

        mock_monitor.send_email_alert.assert_called_once()
        rec_args, rec_kwargs = mock_monitor.send_email_alert.call_args
        self.assertEqual(rec_args[0], "SYSTEM")
        self.assertIn("Dosing system resumed", rec_args[1])
        self.assertEqual(rec_args[2], "RECOVERY")
        self.assertEqual(dosing._consecutive_halt_ticks, 0)

    @patch('dosing.PlantStageStatus')
    @patch('dosing.SensorLimits')
    @patch('dosing.last_dosing_time', 0)
    @patch('dosing.sensor_monitor')
    @patch('dosing.log_event')
    @patch('dosing.hal.emergency_stop_all')
    @patch('db_cache.get_plant_status', return_value={"plant_name": "Lettuce", "state": False, "plant_stage": "Seedling"})
    @patch('db_cache.get_sensor_limit', side_effect=lambda k: {"ph": {"min": 5.5, "max": 6.5, "active": True}, "tds": {"min": 1.0, "max": 2.0, "active": True}}.get(k))
    def test_unrealistic_ph_out_of_range_rejected(
        self, mock_cache_limit, mock_cache_status, mock_estop, mock_log_event, mock_monitor, mock_limits, mock_status
    ):
        """Verify pH values outside 0.0 - 14.0 are classified as invalid hardware readings and debounced."""
        import dosing
        from dosing import check_and_adjust_sensors
        import sensors

        # Set physically impossible pH reading (-5.0 or 25.0)
        sensors.live_ph_data.append({"value": 25.0, "status": "OK"})
        sensors.live_tds_data.append({"value": 1.5, "status": "OK"})

        # Ticks 1-9: silent safety hold
        for i in range(1, 10):
            check_and_adjust_sensors()
            self.assertTrue(mock_estop.called)
            mock_monitor.send_email_alert.assert_not_called()
            self.assertEqual(dosing._consecutive_halt_ticks, i)

        # Tick 10: triggers critical email alert
        check_and_adjust_sensors()
        self.assertEqual(dosing._consecutive_halt_ticks, 10)
        mock_monitor.send_email_alert.assert_called_once()


if __name__ == '__main__':
    unittest.main()

