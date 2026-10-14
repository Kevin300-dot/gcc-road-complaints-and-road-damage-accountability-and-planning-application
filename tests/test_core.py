"""
Core tests. They need only pandas, numpy and scikit-learn (no Streamlit or FastAPI).
Run from the project folder:   python -m unittest discover -s tests -v
"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Work on a throw-away copy of the data so tests never touch the real CSVs.
_TMP = tempfile.mkdtemp()
shutil.copytree(os.path.join(ROOT, "data"), os.path.join(_TMP, "data"))
os.environ["ORION_DATA_DIR"] = os.path.join(_TMP, "data")
os.environ["ORION_UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["ORION_PHOTO_DIR"] = os.path.join(_TMP, "photo_path")

import analytics  # noqa: E402
import area_config  # noqa: E402
import clustering  # noqa: E402
import data_layer  # noqa: E402
import impact  # noqa: E402
import maplib  # noqa: E402
import risk_model  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class BoundaryTests(unittest.TestCase):
    def test_all_48_real_points_are_in_kandanchavadi(self):
        df = data_layer.load_complaints()
        real = df[df["data_source"] == "field_pilot"]
        self.assertEqual(len(real), 48)
        for _, r in real.iterrows():
            self.assertTrue(area_config.contains(r["latitude"], r["longitude"]), r["complaint_id"])

    def test_border_roads_count_as_inside_but_far_points_do_not(self):
        # CMP_KDV_011 is 11.7 m outside the traced line, on a border road.
        r = data_layer.load_complaints().set_index("complaint_id").loc["CMP_KDV_011"]
        self.assertFalse(area_config.locate(r["latitude"], r["longitude"])["inside"])
        self.assertTrue(area_config.contains(r["latitude"], r["longitude"]))
        self.assertFalse(area_config.contains(13.0827, 80.2707))  # central Chennai
        self.assertFalse(area_config.contains(12.9645, 80.2600))  # ~1.4 km east

    def test_area_size(self):
        self.assertAlmostEqual(area_config.area_km2(), 0.214, places=2)


class ClusteringTests(unittest.TestCase):
    def setUp(self):
        self.df = data_layer.load_complaints()
        self.clusters = clustering.build_clusters(self.df)

    def test_every_complaint_is_in_exactly_one_hotspot(self):
        ids = [i for ids in self.clusters["complaint_ids"] for i in ids]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(self.df["complaint_id"]))

    def test_hotspots_never_cross_roads(self):
        by_id = self.df.set_index("complaint_id")
        for _, c in self.clusters.iterrows():
            self.assertEqual(by_id.loc[c["complaint_ids"], "road_segment_id"].nunique(), 1)

    def test_radius_chaining(self):
        xy = np.array([[0, 0], [30, 0], [60, 0], [300, 0]], dtype=float)
        labels = clustering.group_by_distance(xy, 35)
        self.assertEqual(len(set(labels[:3])), 1)       # chained 0-30-60
        self.assertNotEqual(labels[0], labels[3])

    def test_ids_are_stable_and_priority_tiers_exist(self):
        again = clustering.build_clusters(self.df)
        self.assertEqual(list(self.clusters["cluster_id"]), list(again["cluster_id"]))
        self.assertTrue(set(self.clusters["priority"]) <= set(clustering.TIER_LABELS))


class RepairOutcomeTests(unittest.TestCase):
    def _events(self, rows):
        df = pd.DataFrame(rows)
        for c in ("completion_date", "start_date"):
            df[c + "_parsed"] = pd.to_datetime(df[c], format="%d-%m-%Y")
        return df

    def _complaints(self, rows):
        df = pd.DataFrame(rows)
        df["complaint_date_parsed"] = pd.to_datetime(df["complaint_date"], format="%d-%m-%Y")
        return df

    def test_window_censoring_and_relevance(self):
        ev = self._events([
            {"event_id": "A", "road_segment_id": "S1", "work_status": "Completed", "completion_date": "01-01-2026", "start_date": "30-12-2025", "restoration_required": "No", "restoration_completed": "N/A"},
            {"event_id": "B", "road_segment_id": "S2", "work_status": "Completed", "completion_date": "01-01-2026", "start_date": "30-12-2025", "restoration_required": "No", "restoration_completed": "N/A"},
            {"event_id": "C", "road_segment_id": "S3", "work_status": "Completed", "completion_date": "05-04-2026", "start_date": "01-04-2026", "restoration_required": "No", "restoration_completed": "N/A"},
            {"event_id": "D", "road_segment_id": "S4", "work_status": "Completed", "completion_date": "01-01-2026", "start_date": "30-12-2025", "restoration_required": "Yes", "restoration_completed": "No"},
            {"event_id": "E", "road_segment_id": "S5", "work_status": "Completed", "completion_date": "01-01-2026", "start_date": "30-12-2025", "restoration_required": "No", "restoration_completed": "N/A"},
        ])
        comp = self._complaints([
            {"road_segment_id": "S1", "complaint_date": "20-01-2026", "damage_type": "Pothole"},            # in window, related -> failed
            {"road_segment_id": "S2", "complaint_date": "20-01-2026", "damage_type": "Broken_Streetlight"},  # unrelated type -> held
            {"road_segment_id": "S5", "complaint_date": "15-06-2026", "damage_type": "Pothole"},            # after the window -> held
            {"road_segment_id": "S9", "complaint_date": "30-06-2026", "damage_type": "Pothole"},            # sets the end of observation
        ])
        out = analytics.label_repair_outcomes(comp, ev, window_days=60).set_index("event_id")["outcome"].to_dict()
        self.assertEqual(out["A"], "failed")
        self.assertEqual(out["B"], "held")
        self.assertEqual(out["C"], "held")              # 05-04 + 60d = 04-06 <= 30-06, fully observed, no complaint
        self.assertEqual(out["D"], "restoration_pending")
        self.assertEqual(out["E"], "held")

    def test_recent_repair_is_not_judged(self):
        ev = self._events([{"event_id": "A", "road_segment_id": "S1", "work_status": "Completed", "completion_date": "01-06-2026", "start_date": "30-05-2026", "restoration_required": "No", "restoration_completed": "N/A"}])
        comp = self._complaints([{"road_segment_id": "S9", "complaint_date": "30-06-2026", "damage_type": "Pothole"}])
        out = analytics.label_repair_outcomes(comp, ev, window_days=60)
        self.assertEqual(out.iloc[0]["outcome"], "under_observation")


class RiskModelTests(unittest.TestCase):
    def setUp(self):
        self.complaints, self.events, self.label = data_layer.analytics_sources()

    def test_month_is_not_a_feature(self):
        self.assertNotIn("month", risk_model.FEATURE_COLUMNS)

    def test_report_is_honest_and_not_inflated(self):
        bundle = risk_model.train_risk_model(self.complaints, self.events, data_label=self.label)
        self.assertIsNotNone(bundle)
        r = bundle["report"]
        self.assertEqual(r["data_label"], "simulated")
        self.assertLess(r["failure_rate"], 0.6)            # not the old 86%
        self.assertGreater(r["cv_auc"], 0.45)
        self.assertLess(r["cv_auc"], 0.85)                  # the old, leaked number was ~0.95

    def test_calendar_cannot_predict_the_outcome(self):
        """The leak that inflated the first model: completion month alone must not score high."""
        from sklearn.compose import ColumnTransformer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold, cross_val_predict
        from sklearn.metrics import roc_auc_score
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder

        labelled = analytics.label_repair_outcomes(self.complaints, self.events)
        judged = labelled[labelled["outcome"].isin(["held", "failed"])]
        X = pd.DataFrame({"month": judged["completion_date_parsed"].dt.month.astype(str)})
        y = judged["failed"].astype(int)
        pipe = Pipeline([("p", ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore"), ["month"])])), ("l", LogisticRegression(max_iter=1000))])
        p = cross_val_predict(pipe, X, y, groups=judged["road_segment_id"], cv=GroupKFold(5), method="predict_proba")[:, 1]
        self.assertLess(roc_auc_score(y, p), 0.65)

    def test_accountability_has_peer_relative_status_and_intervals(self):
        acc = analytics.compute_accountability(self.complaints, self.events)
        df = acc["by_contractor"]
        self.assertTrue({"ci_low", "ci_high", "restoration_pending", "under_observation"} <= set(df.columns))
        self.assertTrue((df["ci_low"].dropna() <= df["durability_rate"].dropna()).all())
        self.assertTrue(set(df["status"]) <= {"Good Standing", "Watch", "Needs Review", "Insufficient Data"})
        overall = acc["summary"]["overall_durability_rate"]
        self.assertTrue(30 < overall < 90)                  # not the old 14%


class DataLayerTests(unittest.TestCase):
    def test_submit_complaint_inside_and_outside(self):
        before = len(data_layer.load_complaints())
        lat, lon = data_layer.road_coordinates(data_layer.load_complaints(), "Church Main Road")
        res = data_layer.submit_complaint("Church Main Road", "Pothole", "test", "Severe", True, True,
                                          latitude=lat, longitude=lon, photo_bytes=PNG, photo_filename="x.png")
        self.assertTrue(res["complaint_id"].startswith("CMP_KDV_"))
        self.assertGreaterEqual(len(res["nearby_reports"]), 1)
        df = data_layer.load_complaints()
        self.assertEqual(len(df), before + 1)
        self.assertTrue(os.path.isfile(data_layer.find_photo_file(os.path.basename(df.iloc[-1]["photo_path"]))))
        with self.assertRaises(ValueError):
            data_layer.submit_complaint("Church Main Road", "Pothole", "x", "Minor", False, False, latitude=13.08, longitude=80.27)
        with self.assertRaises(ValueError):
            data_layer.submit_complaint("Church Main Road", "Pothole", "x", "Minor", False, False,
                                        latitude=lat, longitude=lon, photo_bytes=b"not an image", photo_filename="x.png")
        self.assertEqual(len(data_layer.load_complaints()), before + 1)

    def test_status_update_and_validation(self):
        data_layer.update_complaint_status("CMP_KDV_001", "Resolved", "Patch work")
        s = data_layer.get_complaint_status("CMP_KDV_001")
        self.assertEqual(s["status"], "Resolved")
        self.assertIsNotNone(s["resolution_date"])
        with self.assertRaises(ValueError):
            data_layer.update_complaint_status("CMP_KDV_001", "Banana")
        with self.assertRaises(KeyError):
            data_layer.update_complaint_status("NOPE", "Open")

    def test_photo_lookup_blocks_path_traversal(self):
        self.assertIsNone(data_layer.find_photo_file("../../etc/passwd"))


class ImpactAndMapTests(unittest.TestCase):
    def test_impact_tags_every_number_with_its_source(self):
        c = data_layer.load_complaints()
        cl = clustering.build_clusters(c)
        _, ev, _ = data_layer.analytics_sources()
        acc = analytics.compute_accountability(*data_layer.analytics_sources()[:2])
        out = impact.compute_impact(c, cl, ev, acc["summary"])
        self.assertEqual(out["measured"]["reports_surveyed"]["source"], "measured")
        for v in out["results"].values():
            self.assertIn(v["source"], {"assumption", "simulated+assumption"})
        for v in out["measured"].values():
            self.assertEqual(v["source"], "measured")
        self.assertIn("warning", out)
        edited = impact.compute_impact(c, cl, ev, acc["summary"], {"monthly_complaints": 240})
        self.assertGreater(edited["results"]["officer_hours_saved_per_month"]["value"],
                           out["results"]["officer_hours_saved_per_month"]["value"])

    def test_map_html_escapes_citizen_text(self):
        evil = {"complaint_id": "X", "latitude": 12.9645, "longitude": 80.2449, "road_name": "R",
                "damage_type_label": "Pothole", "text": "</script><script>alert(1)</script>", "priority": "High"}
        html = maplib.build_map_html(area_config.to_geojson(), [evil])
        self.assertNotIn("</script><script>alert(1)", html)
        self.assertIn("openstreetmap", html.lower())


if __name__ == "__main__":
    unittest.main()
