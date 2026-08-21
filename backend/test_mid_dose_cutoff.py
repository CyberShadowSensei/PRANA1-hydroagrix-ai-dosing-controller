import unittest
from unittest.mock import patch, MagicMock
import time

class TestMidDoseCutoff(unittest.TestCase):
    @patch('dosing.hal.pump_start')
    @patch('dosing.hal.pump_stop')
    @patch('dosing.log_event')
    def test_safe_pump_run_normal_completion(self, mock_log_event, mock_pump_stop, mock_pump_start):
        from dosing import _safe_pump_run
        # Run a 0.2s pump run without cutoff
        _safe_pump_run(1, 0.2)
        mock_pump_start.assert_called_once_with(1)
        mock_pump_stop.assert_called_once_with(1)
        # Should NOT log MID_DOSE_TARGET_REACHED
        self.assertFalse(any(call[0][0] == "MID_DOSE_TARGET_REACHED" for call in mock_log_event.call_args_list))

    @patch('dosing.hal.pump_start')
    @patch('dosing.hal.pump_stop')
    @patch('dosing.log_event')
    def test_safe_pump_run_early_target_cutoff(self, mock_log_event, mock_pump_stop, mock_pump_start):
        from dosing import _safe_pump_run
        
        counter = {"count": 0}
        def stop_check():
            counter["count"] += 1
            if counter["count"] >= 2:
                return True, "Simulated target reached"
            return False, None

        # Plan for 5.0 seconds, but stop_check triggers on 2nd step (~0.2s)
        start_time = time.time()
        _safe_pump_run(1, 5.0, stop_condition_fn=stop_check)
        elapsed = time.time() - start_time

        # Must have completed in < 1 second due to early cutoff
        self.assertLess(elapsed, 1.0)
        mock_pump_start.assert_called_once_with(1)
        mock_pump_stop.assert_called_once_with(1)
        
        # Must log MID_DOSE_TARGET_REACHED
        logged_events = [call[0][0] for call in mock_log_event.call_args_list]
        self.assertIn("MID_DOSE_TARGET_REACHED", logged_events)

if __name__ == '__main__':
    unittest.main()
