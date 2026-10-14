"""
Analytics: urgency velocity, resolution-time estimates, repair-outcome labelling and
the contractor / department accountability table.

Repair outcome definition (this replaces the earlier "any later complaint, ever" rule,
which made 86% of repairs count as failures and let the model learn calendar time)
------------------------------------------------------------------------------------
A completed repair is judged over a fixed follow-up window (FOLLOWUP_WINDOW_DAYS):

  failed             at least one repair-related complaint on the same road segment within
                     the window after completion, AND the full window has been observed
  held               no such complaint, AND the full window has been observed
  under_observation  the window is not over yet (excluded from rates and from training,
                     because "no complaint yet" says nothing about a repair finished last week)
  restoration_pending the job needed road restoration that has not been done
                     (tracked separately as "restoration debt")

Only complaint types that a repair could plausibly cause or fail to prevent count as a
follow-up (potholes, cracks, sinking, poor restoration, manhole and drainage problems).
Streetlights, signage, road markings and the like do not.
"""
import math
from datetime import datetime

import pandas as pd

MIN_JOBS_FOR_RATING = 5
FOLLOWUP_WINDOW_DAYS = 60

REPAIR_RELATED_TYPES = {
    "Pothole", "Alligator_Cracking", "Crack", "Depression", "Subsidence", "Road_Collapse",
    "Poor_Restoration", "Unrestored_Road_Cut", "Uneven_Surface", "Rutting", "Edge_Cracking",
    "Road_Surface_Deterioration", "Damaged_Manhole", "Missing_Manhole_Cover",
    "Drainage_Failure", "Waterlogging", "Road_Work_Incomplete",
}


# ---------------------------------------------------------------- repair outcomes

def label_repair_outcomes(
    complaints_df: pd.DataFrame,
    events_df: pd.DataFrame,
    window_days: int = FOLLOWUP_WINDOW_DAYS,
    end_date=None,
) -> pd.DataFrame:
    """One row per completed event with an `outcome` column (see module docstring) and
    `failed` (1/0, only for events with a fully observed window, else NaN)."""
    if events_df is None or events_df.empty:
        return pd.DataFrame()
    ev = events_df[(events_df["work_status"] == "Completed")].dropna(subset=["completion_date_parsed"]).copy()
    if ev.empty:
        return pd.DataFrame()

    comp = complaints_df.dropna(subset=["road_segment_id", "complaint_date_parsed"])
    comp = comp[comp["damage_type"].isin(REPAIR_RELATED_TYPES)]
    if end_date is None:
        all_dates = complaints_df["complaint_date_parsed"].dropna()
        end_date = all_dates.max() if not all_dates.empty else pd.Timestamp(datetime.now().date())
    end_date = pd.Timestamp(end_date)

    dates_by_segment = {seg: g["complaint_date_parsed"].to_numpy() for seg, g in comp.groupby("road_segment_id")}

    outcomes, followups, failed = [], [], []
    for _, e in ev.iterrows():
        completion = e["completion_date_parsed"]
        needs_restoration = str(e.get("restoration_required", "No")) == "Yes"
        restored = str(e.get("restoration_completed", "")) == "Yes"
        if needs_restoration and not restored:
            outcomes.append("restoration_pending")
            followups.append(None)
            failed.append(float("nan"))
            continue
        window_end = completion + pd.Timedelta(days=window_days)
        arr = dates_by_segment.get(e["road_segment_id"])
        n = 0
        if arr is not None:
            n = int(((arr > completion.to_datetime64()) & (arr <= window_end.to_datetime64())).sum())
        followups.append(n)
        if window_end > end_date:
            outcomes.append("under_observation")
            failed.append(float("nan"))
        elif n >= 1:
            outcomes.append("failed")
            failed.append(1.0)
        else:
            outcomes.append("held")
            failed.append(0.0)
    ev["outcome"] = outcomes
    ev["followup_complaints"] = followups
    ev["failed"] = failed
    return ev


def _wilson(successes: int, n: int, z: float = 1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def compute_accountability(
    complaints_df: pd.DataFrame,
    events_df: pd.DataFrame,
    risk_model=None,
    window_days: int = FOLLOWUP_WINDOW_DAYS,
) -> dict:
    """Ranks departments and contractors by durability rate: the share of their completed
    jobs, over a fixed follow-up window, that did NOT receive a repair-related follow-up
    complaint on the same segment.

    Status is relative to the peer average, not an absolute target:
      Good Standing   at or above the overall durability rate
      Watch           up to 10 percentage points below it
      Needs Review    more than 10 points below it
      Insufficient Data  fewer than MIN_JOBS_FOR_RATING judged jobs
    The 95% Wilson interval is shown because small groups are noisy."""
    cols = ["name", "completed_jobs", "durable_jobs", "durability_rate", "ci_low", "ci_high",
            "restoration_pending", "under_observation", "status", "predicted_failure_risk"]
    empty = {"by_department": pd.DataFrame(columns=cols), "by_contractor": pd.DataFrame(columns=cols),
             "summary": {"window_days": window_days, "judged_jobs": 0, "overall_durability_rate": None,
                         "under_observation": 0, "restoration_pending": 0}}

    labelled = label_repair_outcomes(complaints_df, events_df, window_days=window_days)
    if labelled.empty:
        return empty

    judged = labelled[labelled["outcome"].isin(["held", "failed"])]
    overall = (judged["outcome"] == "held").mean() * 100 if not judged.empty else None

    def summarize(group_col):
        rows = []
        for name, g in labelled.groupby(group_col):
            j = g[g["outcome"].isin(["held", "failed"])]
            n = len(j)
            held = int((j["outcome"] == "held").sum())
            rate = round(held / n * 100, 1) if n else None
            lo, hi = _wilson(held, n)
            if n < MIN_JOBS_FOR_RATING or overall is None:
                status = "Insufficient Data"
            elif rate >= overall:
                status = "Good Standing"
            elif rate >= overall - 10:
                status = "Watch"
            else:
                status = "Needs Review"
            rows.append({
                "name": name, "completed_jobs": n, "durable_jobs": held, "durability_rate": rate,
                "ci_low": None if n == 0 else round(lo * 100, 1), "ci_high": None if n == 0 else round(hi * 100, 1),
                "restoration_pending": int((g["outcome"] == "restoration_pending").sum()),
                "under_observation": int((g["outcome"] == "under_observation").sum()),
                "status": status,
            })
        out = pd.DataFrame(rows)
        if risk_model is not None:
            import risk_model as rm
            risk_df = rm.predicted_risk_by_group(risk_model, labelled, group_col)
            out = out.merge(risk_df, on="name", how="left")
        else:
            out["predicted_failure_risk"] = None
        return out.sort_values(["durability_rate"], ascending=False, na_position="last").reset_index(drop=True)

    return {
        "by_department": summarize("department"),
        "by_contractor": summarize("contractor"),
        "summary": {
            "window_days": window_days,
            "judged_jobs": int(len(judged)),
            "overall_durability_rate": None if overall is None else round(overall, 1),
            "under_observation": int((labelled["outcome"] == "under_observation").sum()),
            "restoration_pending": int((labelled["outcome"] == "restoration_pending").sum()),
        },
    }


# ---------------------------------------------------------------- urgency & resolution time

def compute_urgency_velocity(complaint_dates: pd.Series, reference_date=None) -> dict:
    """Recency-weighted report count: each report contributes 1 / (1 + days since it was
    filed), so fresh reports weigh most. Measured against the newest report in the data."""
    if reference_date is None:
        reference_date = datetime.now()
    valid_dates = complaint_dates.dropna()
    if valid_dates.empty:
        return {"velocity_score": 0.0, "reports_last_7_days": 0, "reports_last_30_days": 0}
    days_since = (reference_date - valid_dates).dt.days.clip(lower=0)
    velocity_score = (1 / (1 + days_since)).sum()
    return {
        "velocity_score": round(float(velocity_score), 3),
        "reports_last_7_days": int((days_since <= 7).sum()),
        "reports_last_30_days": int((days_since <= 30).sum()),
    }


def build_resolution_time_lookup(complaints_df: pd.DataFrame) -> dict:
    resolved = complaints_df[
        (complaints_df["status"] == "Resolved")
        & complaints_df["resolution_date_parsed"].notna()
        & complaints_df["complaint_date_parsed"].notna()
    ].copy()
    if resolved.empty:
        return {"by_location_type": {}, "by_type": {}, "overall": None, "n_resolved": 0}

    resolved["resolution_days"] = (resolved["resolution_date_parsed"] - resolved["complaint_date_parsed"]).dt.days
    resolved = resolved[resolved["resolution_days"] >= 0]

    by_location_type = {}
    for (road, damage_type), group in resolved.groupby(["road_name", "damage_type"]):
        if len(group) >= 3:  # a median of 1-2 jobs is not an estimate
            by_location_type[(road, damage_type)] = round(float(group["resolution_days"].median()), 1)

    by_type = {}
    for damage_type, group in resolved.groupby("damage_type"):
        if len(group) >= 3:
            by_type[damage_type] = round(float(group["resolution_days"].median()), 1)

    overall = float(resolved["resolution_days"].median()) if not resolved.empty else None
    return {
        "by_location_type": by_location_type,
        "by_type": by_type,
        "overall": round(overall, 1) if overall is not None else None,
        "n_resolved": int(len(resolved)),
    }


def predicted_resolution_days(lookup: dict, road_name: str, damage_type: str):
    """Median historical days-to-resolve: same road+type, else same type, else overall."""
    key = (road_name, damage_type)
    if key in lookup.get("by_location_type", {}):
        return lookup["by_location_type"][key]
    if damage_type in lookup.get("by_type", {}):
        return lookup["by_type"][damage_type]
    return lookup.get("overall")
