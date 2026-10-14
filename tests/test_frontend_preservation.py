"""Protect the original map and API calls against presentation-only regressions."""
import ast
import json
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class FrontendPreservationTests(unittest.TestCase):
    def test_maps_and_api_calls_match_original(self):
        expected = json.loads((ROOT / 'tests' / 'frontend_contract.json').read_text())
        for name, calls in expected.items():
            with self.subTest(app=name):
                tree = ast.parse((ROOT / name).read_text())
                actual = [ast.dump(n, include_attributes=False) for n in ast.walk(tree)
                          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                          and isinstance(n.func.value, ast.Name)
                          and n.func.value.id in {'maplib', 'components', 'requests'}]
                self.assertEqual(actual, calls)

if __name__ == '__main__':
    unittest.main()
