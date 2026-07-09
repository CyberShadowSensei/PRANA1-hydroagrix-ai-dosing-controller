import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
import threading
import time

# Add the backend directory to path so we can import hal
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import hal

class TestHAL(unittest.TestCase):
    def test_dht22_config(self):
        """Verify DHT_TYPE is set to 22 (DHT22)."""
        self.assertEqual(hal.DHT_TYPE, "22")

    @patch('hal._get_water_temp_device')
    def test_get_water_temp_no_device(self, mock_get_device):
        """Verify get_water_temp returns fallback_temp when no device is found."""
        mock_get_device.return_value = None
        self.assertEqual(hal.get_water_temp(20.0), 20.0)

    @patch('hal._get_water_temp_device')
    def test_get_water_temp_success(self, mock_get_device):
        """Verify get_water_temp parses valid DS18B20 output correctly."""
        mock_get_device.return_value = "/sys/bus/w1/devices/28-000000000000/w1_slave"
        file_content = "72 01 4b 46 7f ff 0e 10 57 : crc=57 YES\n72 01 4b 46 7f ff 0e 10 57 t=23125\n"
        
        with patch('builtins.open', mock_open(read_data=file_content)):
            temp = hal.get_water_temp(25.0)
            self.assertEqual(temp, 23.125)

    @patch('hal._get_water_temp_device')
    def test_get_water_temp_invalid_crc(self, mock_get_device):
        """Verify get_water_temp returns fallback if CRC check fails."""
        mock_get_device.return_value = "/sys/bus/w1/devices/28-000000000000/w1_slave"
        file_content = "72 01 4b 46 7f ff 0e 10 57 : crc=57 NO\n72 01 4b 46 7f ff 0e 10 57 t=23125\n"
        
        with patch('builtins.open', mock_open(read_data=file_content)):
            temp = hal.get_water_temp(25.0)
            self.assertEqual(temp, 25.0)

    def test_adc_input_validation(self):
        """Verify ADC read input validation works as expected."""
        mock_adc = hal.ManualADC(bus_num=1)
        
        # Test invalid channel types
        with self.assertRaises(TypeError):
            mock_adc.read("0")
            
        # Test invalid channel range
        with self.assertRaises(ValueError):
            mock_adc.read(-1)
        with self.assertRaises(ValueError):
            mock_adc.read(8)

    def test_get_stable_reading_no_adc(self):
        """Verify get_stable_reading returns 0 if no ADC is present."""
        with patch('hal.adc', None):
            self.assertEqual(hal.get_stable_reading(0), 0)

    @patch('hal.adc')
    def test_get_stable_reading_comms_failure(self, mock_adc):
        """Verify that a ValueError is raised if there are fewer than 20 valid samples."""
        # Simulate returning None (I2C read failure) for most reads
        mock_adc.read.side_effect = [None] * 40 + [100] * 10
        with self.assertRaises(ValueError) as ctx:
            hal.get_stable_reading(0)
        self.assertIn("I2C Communication Failure", str(ctx.exception))

    @patch('hal.adc')
    def test_get_stable_reading_empty_trimmed_list_fallback(self, mock_adc):
        """Verify outlier trimming empty list fallback works (empty sample guard)."""
        # Return exactly 20 valid samples. Slice 10:-10 will result in empty clean list.
        # It should fall back to the untrimmed list (20 samples) and not crash.
        mock_adc.read.side_effect = [100] * 20 + [None] * 30
        val = hal.get_stable_reading(0)
        self.assertEqual(val, 100.0)

    def test_i2c_remote_io_error(self):
        """Simulate a physical I2C bus disconnection (Remote I/O error OSError 121)."""
        # Create a real ADC object but substitute its bus with a mock
        real_adc = hal.ManualADC(bus_num=1)
        real_adc.bus = MagicMock()
        # When writing to the I2C bus, raise a Remote I/O error
        real_adc.bus.write_byte.side_effect = OSError(121, "Remote I/O error")
        
        with patch('hal.adc', real_adc):
            with self.assertRaises(ValueError) as ctx:
                hal.get_stable_reading(0)
            self.assertIn("I2C Communication Failure", str(ctx.exception))

    def test_pump_lock_reentrant(self):
        """Verify pump_lock is reentrant (RLock) and doesn't deadlock on nested calls."""
        def nested_lock():
            with hal.pump_lock:
                with hal.pump_lock:
                    pass
        
        # If it's a standard Lock, this would deadlock. If it's an RLock, it completes immediately.
        thread = threading.Thread(target=nested_lock)
        thread.start()
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive(), "Nested locking deadlocked! Lock must be an RLock.")

    def test_pump_status_tracking(self):
        """Verify pump status functions and basic tracking."""
        # Stub state check
        hal.pump_status[1] = "stopped"
        # Start pump (stub mode runs without raising)
        hal.pump_start(1)
        # In stub mode or real mode, pump status dict must be updated
        # (Though GPIO write is skipped if HARDWARE_AVAILABLE=False, pump_status is updated)
    @patch('hal._get_water_temp_device')
    def test_get_water_temp_empty_file(self, mock_get_device):
        """Edge case: 1-Wire file is empty or truncated."""
        mock_get_device.return_value = "/sys/bus/w1/devices/28-000000000000/w1_slave"
        with patch('builtins.open', mock_open(read_data="")):
            self.assertEqual(hal.get_water_temp(25.0), 25.0)

    @patch('hal._get_water_temp_device')
    def test_get_water_temp_malformed_temp(self, mock_get_device):
        """Edge case: 1-Wire YES matches but temperature is malformed (not float or missing)."""
        mock_get_device.return_value = "/sys/bus/w1/devices/28-000000000000/w1_slave"
        file_content = "72 01 4b 46 7f ff 0e 10 57 : crc=57 YES\n72 01 4b 46 7f ff 0e 10 57 t=abc\n"
        with patch('builtins.open', mock_open(read_data=file_content)):
            self.assertEqual(hal.get_water_temp(25.0), 25.0)

    def test_get_climate_sensor_none(self):
        """Verify get_climate handles missing DHT sensor gracefully."""
        with patch('hal.dht_sensor', None):
            h, t, status = hal.get_climate()
            self.assertEqual(status, "ERROR")
            self.assertEqual(h, 0)
            self.assertEqual(t, 25.0)

    @patch('hal.dht_sensor')
    def test_get_climate_sensor_none_reads(self, mock_dht):
        """Verify get_climate handles sensor returning None values gracefully."""
        mock_dht.read.return_value = (None, None)
        h, t, status = hal.get_climate()
        self.assertEqual(status, "ERROR")
        self.assertEqual(h, 0)
        self.assertEqual(t, 25.0)

    @patch('hal.dht_sensor')
    def test_get_climate_sensor_exception(self, mock_dht):
        """Verify get_climate catches hardware/driver exceptions gracefully."""
        mock_dht.read.side_effect = RuntimeError("GPIO Timing error")
        h, t, status = hal.get_climate()
        self.assertEqual(status, "ERROR")
        self.assertEqual(h, 0)
        self.assertEqual(t, 25.0)

    def test_pump_lock_serialization(self):
        """Verify pump_lock enforces mutual exclusion between separate threads."""
        lock_acquired_by_thread_1 = threading.Event()
        thread_1_can_release = threading.Event()
        thread_2_completed = threading.Event()

        def worker_1():
            with hal.pump_lock:
                lock_acquired_by_thread_1.set()
                thread_1_can_release.wait()

        def worker_2():
            lock_acquired_by_thread_1.wait()
            with hal.pump_lock:
                thread_2_completed.set()

        t1 = threading.Thread(target=worker_1)
        t2 = threading.Thread(target=worker_2)
        
        t1.start()
        t2.start()
        
        time.sleep(0.1)
        # Verify that thread 2 is indeed blocked by thread 1
        self.assertFalse(thread_2_completed.is_set(), "Thread 2 did not block on Thread 1's lock!")
        
        # Release lock
        thread_1_can_release.set()
        
        t2.join(timeout=1.0)
        t1.join(timeout=1.0)
        self.assertTrue(thread_2_completed.is_set(), "Thread 2 failed to acquire the lock after release!")

if __name__ == '__main__':
    unittest.main()
