"""All original non-presentation files must remain byte-identical."""
import hashlib,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class OriginalFiles(unittest.TestCase):
    def test_original_backend_maps_and_data_are_unchanged(self):
        hashes=json.loads((ROOT/'tests/original_file_hashes.json').read_text())
        for relative,expected in hashes.items():
            with self.subTest(file=relative):
                self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),expected)
