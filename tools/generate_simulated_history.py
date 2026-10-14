"""
Generate the SIMULATED demo history for Kandanchavadi.

Why this exists
---------------
The 48 field-survey complaints are real, but they come from one afternoon: there are no
repair records, no resolutions and no follow-up complaints. Three features of the system
need that kind of history to run at all:

  * contractor / department accountability (do repairs hold?)
  * the repair-failure risk model
  * the "similar issues usually take N days to resolve" estimate

So that these can be demonstrated end to end, this script produces a clearly labelled,
reproducible (fixed seed) simulated history ON THE REAL ROAD SEGMENTS and inside the real
boundary. Every row is tagged `simulated`; the dashboards say so; nothing here is mixed
into the real complaint map or hotspot list.

The simulation plants known effects, so a correct pipeline should be able to recover them:
  * 12 contractors: 4 reliable, 5 average, 3 weaker
  * repairs that cut the road fail more often than ones that do not
  * utility and pipeline work fails more often than resurfacing
  * rushed jobs (<= 2 days) fail more often
A failure creates a follow-up complaint on the same segment within the follow-up window.
Unrelated background complaints are added at a low random rate.

Outputs (data/simulated/):
  complaints_sim.csv, intervention_events.csv

When real GCC repair history exists, put it in data/intervention_events.csv with the same
columns; the application then uses it automatically and ignores these files.
"""
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import area_config  # noqa: E402
import data_layer  # noqa: E402

# Seed 1 is the first seed tried in tools/robustness_check.py, not one picked for its score.
# Across seeds 1-3 the out-of-fold AUC on this simulation ranges 0.60-0.68 (ceiling for the
# planted effects is about 0.68). Seed 2026, the very first draw, happened to give 0.55.
SEED = 1
START = pd.Timestamp("2024-01-01")
END = pd.Timestamp("2026-10-09")  # day before the real field survey
FOLLOWUP_WINDOW = 60

DEPARTMENTS = {
    "GCC Roads": (0.30, ["Road_Resurfacing"]),
    "Chennai Metro Water": (0.25, ["Pipeline_Laying", "Drainage_Work"]),
    "TANGEDCO": (0.20, ["Cable_Laying", "Utility_Work"]),
    "Telecom Utility": (0.15, ["Cable_Laying"]),
    "Other Utility Agency": (0.10, ["Utility_Work"]),
}
WORK_DESCRIPTION = {
    "Road_Resurfacing": "Road resurfacing",
    "Pipeline_Laying": "Utility excavation and restoration",
    "Drainage_Work": "Drainage maintenance",
    "Cable_Laying": "Utility excavation and restoration",
    "Utility_Work": "Utility excavation and restoration",
}
CUT_PROB = {"Road_Resurfacing": 0.0, "Pipeline_Laying": 0.6, "Drainage_Work": 0.35, "Cable_Laying": 0.55, "Utility_Work": 0.5}
TYPE_EFFECT = {"Road_Resurfacing": -0.3, "Pipeline_Laying": 0.4, "Drainage_Work": 0.0, "Cable_Laying": 0.2, "Utility_Work": 0.3}
COST_LAKH = {"Road_Resurfacing": (4, 9), "Pipeline_Laying": (3, 8), "Drainage_Work": (2, 6), "Cable_Laying": (1.5, 5), "Utility_Work": (1, 4)}

CONTRACTORS = [f"Contractor_{i:02d}" for i in range(1, 13)]
CONTRACTOR_EFFECT = {c: (-0.9 if i < 4 else (0.0 if i < 9 else 1.0)) for i, c in enumerate(CONTRACTORS)}

FOLLOWUP_TYPES = ["Poor_Restoration", "Pothole", "Crack", "Depression", "Subsidence", "Uneven_Surface",
                  "Damaged_Manhole", "Road_Surface_Deterioration"]
FOLLOWUP_P = [0.30, 0.25, 0.10, 0.10, 0.10, 0.05, 0.05, 0.05]
BACKGROUND_TYPES = list(data_layer.DAMAGE_TYPE_LABELS.keys())
RESOLUTION_MEDIAN_DAYS = {
    "Pothole": 12, "Poor_Restoration": 25, "Unrestored_Road_Cut": 30, "Crack": 30, "Depression": 28,
    "Subsidence": 35, "Damaged_Manhole": 14, "Missing_Manhole_Cover": 7, "Waterlogging": 10,
    "Drainage_Failure": 12, "Broken_Streetlight": 9, "Damaged_Footpath": 40,
}
RESOLUTION_TYPE = {
    "Pothole": "Patch work", "Poor_Restoration": "Re-restoration", "Unrestored_Road_Cut": "Restoration",
    "Crack": "Crack sealing", "Depression": "Resurfacing", "Subsidence": "Resurfacing",
    "Damaged_Manhole": "Manhole repair", "Missing_Manhole_Cover": "Cover replaced",
    "Waterlogging": "Drain cleared", "Drainage_Failure": "Drain cleared",
}


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


def _fmt(d):
    return pd.Timestamp(d).strftime("%d-%m-%Y")


def main():
    rng = np.random.default_rng(SEED)
    real = pd.read_csv(data_layer.COMPLAINTS_PATH)
    real = real[real["data_source"] == "field_pilot"]
    segments = {}
    for seg, g in real.groupby("road_segment_id"):
        segments[seg] = {"road": g["road_name"].iloc[0], "points": list(zip(g["latitude"], g["longitude"]))}
    if not segments:
        sys.exit("Import the real survey first (tools/import_field_survey.py).")

    def sample_point(seg):
        pts = segments[seg]["points"]
        for _ in range(50):
            la, lo = pts[rng.integers(len(pts))]
            la += rng.normal(0, 6) / 110574.0
            lo += rng.normal(0, 6) / (111320.0 * math.cos(math.radians(12.9645)))
            if area_config.contains(la, lo):
                return round(la, 6), round(lo, 6)
        la, lo = pts[0]
        return la, lo

    complaints = []

    def add_complaint(seg, date, damage_type, source):
        la, lo = sample_point(seg)
        age = (END - date).days
        sev = rng.choice(["Low", "Medium", "High", "Critical"], p=[0.2, 0.45, 0.28, 0.07])
        safety = {"Low": "Low", "Medium": "Medium", "High": "High", "Critical": "Critical"}[sev]
        median = RESOLUTION_MEDIAN_DAYS.get(damage_type, 20)
        res_days = int(max(2, rng.lognormal(math.log(median), 0.5)))
        if age > 20 and rng.random() < 0.7 and date + pd.Timedelta(days=res_days) <= END:
            status, res_date = "Resolved", date + pd.Timedelta(days=res_days)
            res_type = RESOLUTION_TYPE.get(damage_type, "Repaired")
        else:
            status = rng.choice(["Open", "In Progress"], p=[0.6, 0.4]) if age <= 20 else rng.choice(["Open", "In Progress"], p=[0.4, 0.6])
            res_date, res_type = None, None
        complaints.append({
            "complaint_id": "", "road_segment_id": seg, "complaint_date": _fmt(date),
            "complaint_time": f"{rng.integers(7, 20):02d}:{rng.integers(0, 60):02d}",
            "latitude": la, "longitude": lo,
            "location_description": f"{segments[seg]['road']}, {area_config.AREA_NAME}",
            "complaint_text": f"Simulated report: {data_layer.DAMAGE_TYPE_LABELS[damage_type].lower()}",
            "language": "English", "damage_type": damage_type, "severity": sev,
            "traffic_impact": rng.choice(["Low", "Medium", "High", "Severe"], p=[0.3, 0.35, 0.25, 0.1]),
            "safety_risk": safety, "vehicle_accident_reported": "No",
            "pedestrian_risk": rng.choice(["Yes", "No"], p=[0.3, 0.7]),
            "two_wheeler_risk": rng.choice(["Yes", "No"], p=[0.5, 0.5]),
            "emergency_route": "No", "status": status, "assigned_department": "GCC Roads",
            "resolution_date": _fmt(res_date) if res_date is not None else "",
            "resolution_type": res_type or "", "photo_path": "", "submission_channel": "simulated",
            "data_source": source, "area": area_config.AREA_NAME, "road_name": segments[seg]["road"], "observed_at": "",
        })

    # ---- repair events + the follow-up complaints they cause
    events = []
    dept_names = list(DEPARTMENTS)
    dept_p = np.array([DEPARTMENTS[d][0] for d in dept_names])
    for seg in segments:
        t = START + pd.Timedelta(days=int(rng.integers(0, 60)))
        while t < END - pd.Timedelta(days=3):
            dept = dept_names[rng.choice(len(dept_names), p=dept_p / dept_p.sum())]
            etype = DEPARTMENTS[dept][1][rng.integers(len(DEPARTMENTS[dept][1]))]
            contractor = CONTRACTORS[rng.integers(len(CONTRACTORS))]
            rushed = rng.random() < 0.35
            duration = int(rng.integers(1, 3)) if rushed else int(rng.integers(3, 15))
            completion = t + pd.Timedelta(days=duration)
            cut = rng.random() < CUT_PROB[etype]
            restoration_required = "Yes" if cut else "No"
            restored = "Yes" if (cut and rng.random() < 0.88) else ("No" if cut else "N/A")
            lakh = rng.uniform(*COST_LAKH[etype])
            status = "Completed" if completion <= END else "In Progress"

            logit = -1.3 + CONTRACTOR_EFFECT[contractor] + 0.7 * cut + TYPE_EFFECT[etype] + 0.5 * rushed
            if status == "Completed":
                if restoration_required == "Yes" and restored == "No":
                    if rng.random() < 0.6:  # an unrestored cut draws complaints
                        d = completion + pd.Timedelta(days=int(rng.integers(5, FOLLOWUP_WINDOW - 2)))
                        if d <= END:
                            add_complaint(seg, d, "Unrestored_Road_Cut", "simulated_history")
                elif rng.random() < _sigmoid(logit):
                    d = completion + pd.Timedelta(days=int(rng.integers(5, FOLLOWUP_WINDOW - 2)))
                    if d <= END:
                        add_complaint(seg, d, rng.choice(FOLLOWUP_TYPES, p=FOLLOWUP_P), "simulated_history")

            events.append({
                "event_id": "", "road_segment_id": seg, "event_date": _fmt(t), "event_type": etype,
                "department": dept, "contractor": contractor, "work_description": WORK_DESCRIPTION[etype],
                "work_status": status, "start_date": _fmt(t),
                "completion_date": _fmt(completion) if status == "Completed" else "",
                "reference_number": f"GCC/ROAD/{t.year}/{rng.integers(1000, 9999)}",
                "estimated_cost": int(lakh * 100000), "road_cutting": "Yes" if cut else "No",
                "restoration_required": restoration_required, "restoration_completed": restored,
                "notes": "SIMULATED demo record", "data_source": "simulated",
            })
            t = completion + pd.Timedelta(days=int(rng.integers(75, 121)))

    # ---- unrelated background complaints at a low random rate
    span = (END - START).days
    for seg in segments:
        for _ in range(rng.poisson(span / 400.0)):
            add_complaint(seg, START + pd.Timedelta(days=int(rng.integers(0, span))),
                          BACKGROUND_TYPES[rng.integers(len(BACKGROUND_TYPES))], "simulated_history")

    cdf = pd.DataFrame(complaints)
    cdf["_d"] = pd.to_datetime(cdf["complaint_date"], format="%d-%m-%Y")
    cdf = cdf.sort_values("_d").drop(columns="_d").reset_index(drop=True)
    cdf["complaint_id"] = [f"SIM_{i + 1:06d}" for i in range(len(cdf))]
    cdf = cdf[data_layer.COMPLAINT_COLUMNS]

    edf = pd.DataFrame(events)
    edf["_d"] = pd.to_datetime(edf["event_date"], format="%d-%m-%Y")
    edf = edf.sort_values("_d").drop(columns="_d").reset_index(drop=True)
    edf["event_id"] = [f"EVT_{i + 1:06d}" for i in range(len(edf))]

    os.makedirs(data_layer.SIM_DIR, exist_ok=True)
    cdf.to_csv(data_layer.SIM_COMPLAINTS_PATH, index=False)
    edf.to_csv(data_layer.SIM_EVENTS_PATH, index=False)
    print(f"Wrote {len(cdf)} simulated complaints and {len(edf)} simulated repair events to {data_layer.SIM_DIR}")


if __name__ == "__main__":
    main()
