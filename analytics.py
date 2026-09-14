from datetime import datetime

import pandas as pd

MIN_JOBS_FOR_RATING = 5


def compute_accountability(complaints_df: pd.DataFrame, events_df: pd.DataFrame) -> dict:
    """Ranks departments and contractors by durability rate: the percentage of their
    completed, restored jobs that never had a single follow-up complaint on that
    road segment, for the entire period on record. No arbitrary time cutoff is used.
    Departments/contractors with fewer than MIN_JOBS_FOR_RATING completed jobs are
    marked 'Insufficient Data' rather than ranked on too little evidence."""
    empty = pd.DataFrame(columns=["name", "completed_jobs", "durable_jobs", "durability_rate", "status"])
    if events_df.empty:
        return {"by_department": empty.copy(), "by_contractor": empty.copy()}

    completed = events_df[
        (events_df["work_status"] == "Completed")
        & (events_df["restoration_required"] == "Yes")
        & (events_df["restoration_completed"] == "Yes")
    ].dropna(subset=["completion_date_parsed"]).copy()

    if completed.empty:
        return {"by_department": empty.copy(), "by_contractor": empty.copy()}

    segment_last_complaint = (
        complaints_df.dropna(subset=["road_segment_id", "complaint_date_parsed"])
        .groupby("road_segment_id")["complaint_date_parsed"]
        .max()
    )

    completed["last_complaint_date"] = completed["road_segment_id"].map(segment_last_complaint)
    completed["held_up"] = ~(
        completed["last_complaint_date"].notna()
        & (completed["last_complaint_date"] > completed["completion_date_parsed"])
    )

    def _status(row):
        if row["completed_jobs"] < MIN_JOBS_FOR_RATING:
            return "Insufficient Data"
        if row["durability_rate"] >= 20:
            return "Good Standing"
        if row["durability_rate"] >= 10:
            return "Watch"
        return "Needs Review"

    def summarize(group_col):
        grouped = completed.groupby(group_col).agg(
            completed_jobs=("event_id", "count"),
            durable_jobs=("held_up", "sum"),
        ).reset_index()
        grouped["durability_rate"] = (
            grouped["durable_jobs"] / grouped["completed_jobs"] * 100
        ).round(1)
        grouped["status"] = grouped.apply(_status, axis=1)
        grouped = grouped.rename(columns={group_col: "name"})
        return grouped.sort_values("durability_rate", ascending=False).reset_index(drop=True)

    return {
        "by_department": summarize("department"),
        "by_contractor": summarize("contractor"),
    }


def compute_urgency_velocity(complaint_dates: pd.Series, reference_date=None) -> dict:
    if reference_date is None:
        reference_date = datetime.now()

    valid_dates = complaint_dates.dropna()
    if valid_dates.empty:
        return {"velocity_score": 0.0, "reports_last_7_days": 0, "reports_last_30_days": 0}

    days_since = (reference_date - valid_dates).dt.days.clip(lower=0)
    velocity_score = (1 / (1 + days_since)).sum()

    return {
        "velocity_score": round(velocity_score, 3),
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
        return {"by_location_type": {}, "by_type": {}, "overall": None}

    resolved["resolution_days"] = (
        resolved["resolution_date_parsed"] - resolved["complaint_date_parsed"]
    ).dt.days
    resolved = resolved[resolved["resolution_days"] >= 0]

    by_location_type = {}
    for (location, damage_type), group in resolved.groupby(["location_description", "damage_type"]):
        by_location_type[(location, damage_type)] = round(group["resolution_days"].median(), 1)

    by_type = {}
    for damage_type, group in resolved.groupby("damage_type"):
        by_type[damage_type] = round(group["resolution_days"].median(), 1)

    overall = resolved["resolution_days"].median() if not resolved.empty else None

    return {
        "by_location_type": by_location_type,
        "by_type": by_type,
        "overall": round(overall, 1) if overall is not None else None,
    }


def predicted_resolution_days(lookup: dict, location: str, damage_type: str):
    key = (location, damage_type)
    if key in lookup.get("by_location_type", {}):
        return lookup["by_location_type"][key]
    if damage_type in lookup.get("by_type", {}):
        return lookup["by_type"][damage_type]
    return lookup.get("overall")
