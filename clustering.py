"""
Hotspot grouping and priority scoring.

What this does (and does not do)
--------------------------------
* Complaints are grouped into HOTSPOTS: reports on the same road segment whose
  locations chain together within HOTSPOT_RADIUS_M of each other (single-linkage on
  real GPS distance, not on area names).
* It is a spatial grouping. It does NOT read complaint text or compare photos, so it
  should be described as "location-based hotspot grouping", not semantic duplicate
  detection. Two reports a few metres apart can be different defects (the field survey
  confirmed this), so reports are grouped for prioritisation, never merged or deleted.
* Priority score = a weighted sum of simple, explainable factors. The weights below are
  EXPERT-SET starting values, not fitted to outcomes; with real GCC data they should be
  calibrated (e.g. against time-to-repair or accident records).
* Tiers (Low/Medium/High/Critical) are RELATIVE: k-means over the current score
  distribution, so "Critical" means "top group right now".
"""
import re

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

import area_config
from analytics import compute_urgency_velocity
from data_layer import DAMAGE_TYPE_LABELS

HOTSPOT_RADIUS_M = 35.0

SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
TRAFFIC_RANK = {"Low": 1, "Medium": 2, "High": 3, "Severe": 4}
SAFETY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
TIER_LABELS = ["Low", "Medium", "High", "Critical"]

PRIORITY_WEIGHTS = {
    "per_report": 1.5,          # each report at the hotspot (capped at max_reports)
    "max_reports": 40,
    "per_severity_rank": 8,     # worst severity, rank 1-4
    "per_safety_rank": 8,       # worst safety risk, rank 1-4
    "per_traffic_rank": 4,      # worst traffic impact, rank 1-4
    "per_velocity": 3,          # recency-weighted report rate (capped at max_velocity)
    "max_velocity": 10,
    "accident_reported": 15,
    "emergency_route": 10,
}


def _worst(series: pd.Series, rank_map: dict) -> str:
    valid = series.dropna()
    if valid.empty:
        return "Low"
    ranked = valid.map(lambda v: rank_map.get(v, 0))
    return valid.loc[ranked.idxmax()]


def _priority_score(row) -> float:
    w = PRIORITY_WEIGHTS
    score = 0.0
    score += min(row["complaint_count"], w["max_reports"]) * w["per_report"]
    score += SEVERITY_RANK.get(row["worst_severity"], 1) * w["per_severity_rank"]
    score += SAFETY_RANK.get(row["worst_safety_risk"], 1) * w["per_safety_rank"]
    score += TRAFFIC_RANK.get(row["worst_traffic_impact"], 1) * w["per_traffic_rank"]
    score += min(row["velocity_score"], w["max_velocity"]) * w["per_velocity"]
    if row["any_accident_reported"]:
        score += w["accident_reported"]
    if row["any_emergency_route"]:
        score += w["emergency_route"]
    return round(score, 1)


def _fixed_priority_label(score: float) -> str:
    """Fallback thresholds, used only when there are too few hotspots to cluster."""
    if score >= 95:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 38:
        return "Medium"
    return "Low"


def assign_priority_tiers(scores: pd.Series) -> pd.Series:
    """Low/Medium/High/Critical via k-means on the current score distribution.
    Cluster centres are sorted ascending and mapped to the tier labels in order."""
    if len(scores) < 4 or scores.nunique() < 4:
        return scores.apply(_fixed_priority_label)
    X = scores.to_numpy().reshape(-1, 1)
    km = KMeans(n_clusters=4, n_init=10, random_state=42)
    cluster_ids = km.fit_predict(X)
    order = np.argsort(km.cluster_centers_.flatten())
    label_by_cluster = {cluster_idx: TIER_LABELS[rank] for rank, cluster_idx in enumerate(order)}
    return pd.Series([label_by_cluster[c] for c in cluster_ids], index=scores.index)


def _pick_representative_photo(group: pd.DataFrame):
    with_photo = group[group["photo_path"].notna() & (group["photo_path"].astype(str).str.len() > 0)]
    if with_photo.empty:
        return None
    with_photo = with_photo.sort_values("complaint_date_parsed", ascending=False)
    return with_photo.iloc[0]["photo_path"]


def group_by_distance(xy: np.ndarray, radius_m: float) -> np.ndarray:
    """Single-linkage grouping: two points share a group if a chain of points, each
    within radius_m of the next, connects them. Returns an integer label per point."""
    n = len(xy)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        d = np.hypot(xy[i + 1:, 0] - xy[i, 0], xy[i + 1:, 1] - xy[i, 1])
        for off in np.nonzero(d <= radius_m)[0]:
            ra, rb = find(i), find(i + 1 + int(off))
            if ra != rb:
                parent[ra] = rb
    roots = [find(i) for i in range(n)]
    remap = {r: k for k, r in enumerate(dict.fromkeys(roots))}
    return np.array([remap[r] for r in roots])


def make_cluster_id(first_complaint_id: str) -> str:
    """Stable id from the earliest complaint in the hotspot, so escalations keep pointing
    at the same hotspot when new reports join it."""
    return "hs_" + re.sub(r"[^a-z0-9]+", "_", str(first_complaint_id).lower()).strip("_")


def build_clusters(complaints_df: pd.DataFrame, radius_m: float = HOTSPOT_RADIUS_M) -> pd.DataFrame:
    df = complaints_df.copy()
    df = df[df["damage_type"].notna() & df["latitude"].notna() & df["longitude"].notna()]
    if df.empty:
        return pd.DataFrame()
    df["road_segment_id"] = df["road_segment_id"].fillna("UNASSIGNED")
    df["road_name"] = df["road_name"].fillna(df["location_description"])
    reference_date = df["complaint_date_parsed"].max()

    records = []
    for segment_id, seg in df.groupby("road_segment_id"):
        xy = np.array([area_config.project(la, lo) for la, lo in zip(seg["latitude"], seg["longitude"])])
        labels = group_by_distance(xy, radius_m)
        for lab in np.unique(labels):
            group = seg[labels == lab]
            gxy = xy[labels == lab]
            centre = gxy.mean(axis=0)
            radius = float(np.hypot(gxy[:, 0] - centre[0], gxy[:, 1] - centre[1]).max()) if len(gxy) > 1 else 0.0

            damage_mix = group["damage_type"].value_counts().to_dict()
            main_type = next(iter(damage_mix))
            other_types = len(damage_mix) - 1
            main_label = DAMAGE_TYPE_LABELS.get(main_type, main_type)
            first = group.sort_values(["complaint_date_parsed", "complaint_id"]).iloc[0]

            status_counts = group["status"].value_counts().to_dict()
            velocity = compute_urgency_velocity(group["complaint_date_parsed"], reference_date=reference_date)

            record = {
                "cluster_id": make_cluster_id(first["complaint_id"]),
                "zone_id": segment_id,
                "zone_label": group["road_name"].iloc[0],
                "member_locations": sorted(group["location_description"].dropna().unique().tolist()),
                "damage_type": main_type,
                "damage_type_label": main_label + (f" (+{other_types} other type{'s' if other_types > 1 else ''})" if other_types else ""),
                "damage_mix": {DAMAGE_TYPE_LABELS.get(k, k): int(v) for k, v in damage_mix.items()},
                "complaint_count": len(group),
                "open_count": status_counts.get("Open", 0),
                "in_progress_count": status_counts.get("In Progress", 0),
                "resolved_count": status_counts.get("Resolved", 0),
                "worst_severity": _worst(group["severity"], SEVERITY_RANK),
                "worst_safety_risk": _worst(group["safety_risk"], SAFETY_RANK),
                "worst_traffic_impact": _worst(group["traffic_impact"], TRAFFIC_RANK),
                "any_accident_reported": bool((group["vehicle_accident_reported"] == "Yes").any()),
                "any_emergency_route": bool((group["emergency_route"] == "Yes").any()),
                "first_reported": group["complaint_date_parsed"].min(),
                "last_reported": group["complaint_date_parsed"].max(),
                "avg_latitude": float(group["latitude"].mean()),
                "avg_longitude": float(group["longitude"].mean()),
                "radius_m": round(radius, 1),
                "road_segment_ids": [segment_id],
                "complaint_ids": group["complaint_id"].dropna().tolist(),
                "velocity_score": velocity["velocity_score"],
                "reports_last_7_days": velocity["reports_last_7_days"],
                "reports_last_30_days": velocity["reports_last_30_days"],
            }
            record["priority_score"] = _priority_score(record)
            record["representative_photo"] = _pick_representative_photo(group)
            records.append(record)

    clusters = pd.DataFrame(records)
    if not clusters.empty:
        clusters["priority"] = assign_priority_tiers(clusters["priority_score"])
        clusters = clusters.sort_values(["priority_score", "complaint_count"], ascending=[False, False]).reset_index(drop=True)
    return clusters


def get_cluster_by_id(clusters: pd.DataFrame, cluster_id: str):
    if clusters.empty:
        return None
    matches = clusters[clusters["cluster_id"] == cluster_id]
    return None if matches.empty else matches.iloc[0].to_dict()


def get_cluster_complaints(complaints_df: pd.DataFrame, complaint_ids: list) -> pd.DataFrame:
    subset = complaints_df[complaints_df["complaint_id"].isin(complaint_ids)].copy()
    return subset.sort_values("complaint_date_parsed", ascending=False)


def related_interventions(events_df: pd.DataFrame, road_segment_ids: list) -> pd.DataFrame:
    if events_df.empty or not road_segment_ids:
        return pd.DataFrame()
    return events_df[events_df["road_segment_id"].isin(road_segment_ids)]


def build_map_points(complaints_df: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    """One row per real complaint, tagged with its hotspot and the hotspot's priority."""
    if clusters.empty:
        return pd.DataFrame()
    lookup = {}
    for _, c in clusters.iterrows():
        for cid in c["complaint_ids"]:
            lookup[cid] = (c["cluster_id"], c["priority"], c["priority_score"])
    d = complaints_df.dropna(subset=["latitude", "longitude"]).copy()
    d["cluster_id"] = d["complaint_id"].map(lambda x: lookup.get(x, (None, "Low", 0))[0])
    d["priority"] = d["complaint_id"].map(lambda x: lookup.get(x, (None, "Low", 0))[1])
    return d


def build_map_zones(clusters: pd.DataFrame) -> pd.DataFrame:
    """One row per hotspot for the map (kept under the original name for API compatibility)."""
    if clusters.empty:
        return pd.DataFrame()
    z = clusters[[
        "cluster_id", "zone_id", "zone_label", "avg_latitude", "avg_longitude", "radius_m",
        "complaint_count", "priority", "priority_score", "damage_type_label",
    ]].copy()
    z = z.rename(columns={
        "zone_label": "label", "avg_latitude": "latitude", "avg_longitude": "longitude",
        "complaint_count": "total_complaints", "priority_score": "max_priority_score",
    })
    z["problem_count"] = 1
    return z.sort_values("max_priority_score", ascending=False).reset_index(drop=True)
