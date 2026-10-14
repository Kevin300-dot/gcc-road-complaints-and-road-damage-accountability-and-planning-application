"""Concrete guarantees for unchanged risk comparisons and safe numeric display."""
import unittest
from portal_ui import risk_level, _number

class ResultRules(unittest.TestCase):
    def test_clearly_above_average_keeps_1_4_multiplier(self):
        self.assertEqual(risk_level(28, 20), 'Clearly above average')
        self.assertNotEqual(risk_level(27.9, 20), 'Clearly above average')
    def test_somewhat_above_average_keeps_1_1_multiplier(self):
        self.assertEqual(risk_level(22, 20), 'Somewhat above average')
        self.assertEqual(risk_level(21.9, 20), 'Around or below average')
    def test_zero_baseline_retains_original_fallback(self):
        self.assertEqual(risk_level(80, 0), 'Around or below average')
    def test_missing_or_nonfinite_results_not_zeroed(self):
        self.assertIsNone(_number(None))
        self.assertIsNone(_number(float('nan')))
        self.assertEqual(_number(0), 0)
