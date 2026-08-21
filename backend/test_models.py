import sys
from unittest.mock import MagicMock

# Mock hardware modules to run without Pi hardware
sys.modules['smbus2'] = MagicMock()
sys.modules['grove'] = MagicMock()
sys.modules['grove.grove_moisture_sensor'] = MagicMock()

import unittest
from models import PlantPreset

class TestPlantPreset(unittest.TestCase):
    def test_get_stage_limits_valid(self):
        preset = PlantPreset(name="Test", stages_json='{"Seedling": {"ph": {"min": 5.5, "max": 6.5}}}')
        limits = preset.get_stage_limits("Seedling")
        self.assertIsNotNone(limits)
        self.assertEqual(limits['ph']['min'], 5.5)

    def test_get_stage_limits_empty(self):
        preset = PlantPreset(name="Test", stages_json='')
        self.assertIsNone(preset.get_stage_limits("Seedling"))

    def test_get_stage_limits_malformed(self):
        preset = PlantPreset(name="Test", stages_json='{malformed json')
        with self.assertRaises(ValueError):
            preset.get_stage_limits("Seedling")

if __name__ == '__main__':
    unittest.main()
