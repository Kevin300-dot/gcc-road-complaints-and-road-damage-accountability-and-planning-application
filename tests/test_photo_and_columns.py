"""Guards two fixes: complaint photos reach the officer view, and data_source stays out of Related Road Work."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class PhotoAndColumns(unittest.TestCase):
    def test_backend_returns_photo_filename_and_no_data_source(self):
        s = (ROOT / "backend_main.py").read_text()
        self.assertIn('complaints["photo"]', s)
        self.assertNotIn('"restoration_completed", "data_source"', s)
    def test_officer_app_shows_photos_and_drops_data_source(self):
        s = (ROOT / "officer_app.py").read_text()
        self.assertIn("**Photos**", s)
        self.assertIn('drop(columns=["data_source"]', s)
    def test_photo_folder_is_empty(self):
        self.assertEqual([p.name for p in (ROOT / "photo_path").iterdir()], [".gitkeep"])
