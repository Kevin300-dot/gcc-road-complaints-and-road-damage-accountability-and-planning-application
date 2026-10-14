"""
How stable is the repair-risk model's honest accuracy on the simulated history?

Regenerates the simulation under several random seeds and history lengths (into a
temporary folder, leaving data/ untouched) and prints the out-of-fold AUC for each.
Run: python tools/robustness_check.py
"""
import contextlib
import io
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_layer  # noqa: E402
import generate_simulated_history as g  # noqa: E402
import risk_model  # noqa: E402


def main():
    tmp = tempfile.mkdtemp()
    data_layer.SIM_DIR = tmp
    data_layer.SIM_COMPLAINTS_PATH = os.path.join(tmp, "c.csv")
    data_layer.SIM_EVENTS_PATH = os.path.join(tmp, "e.csv")
    rows = []
    for start in ("2024-01-01", "2022-01-01", "2020-01-01"):
        for seed in (1, 2, 3, 4, 5):
            g.START = pd.Timestamp(start)
            g.SEED = seed
            with contextlib.redirect_stdout(io.StringIO()):
                g.main()
            c = data_layer._read_complaints_file(data_layer.SIM_COMPLAINTS_PATH)
            e = pd.read_csv(data_layer.SIM_EVENTS_PATH)
            e["completion_date_parsed"] = pd.to_datetime(e["completion_date"], format="%d-%m-%Y", errors="coerce")
            e["start_date_parsed"] = pd.to_datetime(e["start_date"], format="%d-%m-%Y", errors="coerce")
            b = risk_model.train_risk_model(c, e)
            r = b["report"]
            rows.append((start, seed, r["n_jobs"], r["failure_rate"], r["cv_auc"], r.get("time_split_auc")))
    df = pd.DataFrame(rows, columns=["history_from", "seed", "jobs", "failure_rate", "cv_auc", "time_split_auc"])
    print(df.to_string(index=False))
    print()
    print(df.groupby("history_from")[["jobs", "cv_auc", "time_split_auc"]].agg(["mean", "min", "max"]).round(3).to_string())


if __name__ == "__main__":
    main()
