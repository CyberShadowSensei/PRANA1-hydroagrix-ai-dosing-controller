import os
import sys
import time
import json
import unittest
from unittest.mock import patch, MagicMock

# Mock hardware dependencies
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()

import sensors
from sensors import CirculationPlateauTracker
import dosing
from dosing import check_and_adjust_sensors, _evaluate_last_dose


class TestCirculationPlateauTracker(unittest.TestCase):

    def setUp(self):
        self.tracker = CirculationPlateauTracker(drop_delta=0.6, settle_ticks=5, ro_steady_ticks=10)

    def test_initial_reading_establishes_plateau(self):
        res = self.tracker.process_reading(2.2, "OK")
        self.assertEqual(res["value"], 2.2)
        self.assertEqual(res["effective_value"], 2.2)
        self.assertFalse(res["is_drain_cycle"])
        self.assertTrue(res["is_stable_plateau"])
        self.assertEqual(res["status"], "OK")

    def test_drain_cycle_drop_detected_and_holds_plateau(self):
        # 1. Establish plateau at 2.2
        self.tracker.process_reading(2.2, "OK")
        
        # 2. Water drains to channels -> sensor reads 0.4 in air
        res = self.tracker.process_reading(0.4, "OK")
        self.assertEqual(res["value"], 0.4)
        self.assertEqual(res["effective_value"], 2.2)  # Holds last plateau
        self.assertTrue(res["is_drain_cycle"])
        self.assertFalse(res["is_stable_plateau"])
        self.assertEqual(res["status"], "DRAIN_CYCLE")

    def test_water_return_requires_settle_ticks_before_stable(self):
        # 1. Establish plateau at 2.2 and drain
        self.tracker.process_reading(2.2, "OK")
        self.tracker.process_reading(0.4, "OK")
        
        # 2. Water returns to 2.2 -> ticks 1 to 4 should be returning but not yet stable
        for _ in range(4):
            res = self.tracker.process_reading(2.2, "OK")
            self.assertTrue(res["is_drain_cycle"])  # Still in settling phase
            self.assertFalse(res["is_stable_plateau"])

        # 3. 5th tick satisfies settle_ticks=5
        res = self.tracker.process_reading(2.2, "OK")
        self.assertFalse(res["is_drain_cycle"])
        self.assertTrue(res["is_stable_plateau"])
        self.assertEqual(res["status"], "OK")

    def test_fresh_ro_water_fill_adapts_plateau_to_new_baseline(self):
        # 1. System was previously running at 2.2
        self.tracker.process_reading(2.2, "OK")
        
        # 2. Grower flushes and fills tank with pure RO water (0.25 mS/cm)
        # Feed 10 steady ticks at 0.25 mS/cm (matching ro_steady_ticks=10)
        for i in range(9):
            res = self.tracker.process_reading(0.25, "OK")
            self.assertTrue(res["is_drain_cycle"])  # Initially treated as drain
        
        # On the 10th steady tick, tracker recognizes fresh RO water batch
        res = self.tracker.process_reading(0.25, "OK")
        self.assertFalse(res["is_drain_cycle"])
        self.assertTrue(res["is_stable_plateau"])
        self.assertEqual(res["effective_value"], 0.25)
        self.assertEqual(self.tracker.plateau_ec, 0.25)


class TestDosingDrainCycleGate(unittest.TestCase):

    def setUp(self):
        dosing._reset_dosing_state()
        sensors.live_ph_data.clear()
        sensors.live_tds_data.clear()
        if hasattr(sensors, 'circulation_tracker'):
            sensors.circulation_tracker.reset()

    @patch('dosing._async_dosing')
    def test_dosing_strictly_paused_during_drain_cycle(self, mock_async_dosing):
        # Feed a drain-cycle reading into live_tds_data
        sensors.live_ph_data.append({"value": 6.0, "status": "OK"})
        sensors.live_tds_data.append({
            "value": 0.4,
            "effective_value": 2.2,
            "is_drain_cycle": True,
            "is_stable_plateau": False,
            "status": "DRAIN_CYCLE"
        })

        with patch('db_cache.get_plant_status', return_value={"plant_name": "Tomato", "state": True}), \
             patch('db_cache.get_sensor_limit', side_effect=lambda s: {"min": 1.5, "max": 2.5, "active": True}):
            check_and_adjust_sensors()

        # Dosing thread MUST NOT be spawned while in drain cycle
        mock_async_dosing.assert_not_called()
        self.assertFalse(dosing.is_dosing_active)

    def test_adaptive_evaluation_deferred_during_drain_cycle(self):
        # Setup an active prediction
        dosing._last_ec_prediction = {
            'pre_val': 1.8,
            'predicted_delta': 0.4,
            'time': time.time() - 1000  # Elapsed
        }
        
        sensors.live_tds_data.append({
            "value": 0.4,
            "effective_value": 2.2,
            "is_drain_cycle": True,
            "is_stable_plateau": False,
            "status": "DRAIN_CYCLE"
        })

        config = {"cooldown_minutes": 15.0, "nutrient_ml_per_l_per_ec": 2.0}
        
        # When evaluating during drain cycle, prediction must NOT be consumed or evaluated against 0.4
        _evaluate_last_dose(current_tds=0.4, current_ph=6.0, config=config)
        self.assertIsNotNone(dosing._last_ec_prediction)
        self.assertEqual(config["nutrient_ml_per_l_per_ec"], 2.0)  # Unchanged
