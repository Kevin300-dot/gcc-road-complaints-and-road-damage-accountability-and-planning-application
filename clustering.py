import re

import pandas as pd

from data_layer import DAMAGE_TYPE_LABELS
from analytics import compute_urgency_velocity

SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
TRAFFIC_RANK = {"Low": 1, "Medium": 2, "High": 3, "Severe": 4}
SAFETY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def make_cluster_id(location: str, damage_type: str) -> str:
    raw = f"{location}_{damage_type}".lower()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")


def _worst(series: pd.Series, rank_map: dict) -> str:
    valid = series.dropna()
    if valid.empty:
        return "Low"
    ranked = valid.map(lambda v: rank_map.get(v, 0))
    return valid.loc[ranked.idxmax()]


def _priority_score(row) -> float:
    score = 0.0
    score += min(row["complaint_count"], 40) * 1.5
    score += SEVERITY_RANK.get(row["worst_severity"], 1) * 8
    score += SAFETY_RANK.get(row["worst_safety_risk"], 1) * 8
    score += TRAFFIC_RANK.get(row["worst_traffic_impact"], 1) * 4
    score += min(row["velocity_score"], 10) * 3
    if row["any_accident_reported"]:
        score += 15
    if row["any_emergency_route"]:
        score += 10
    return round(score, 1)


def _priority_label(score: float) -> str:
    if score >= 95:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 38:
        return "Medium"
    return "Low"


def _pick_representative_photo(group: pd.DataFrame):
    with_photo = group[
        group["photo_path"].notna() & (group["photo_path"].astype(str).str.len() > 0)
    ]
    if with_photo.empty:
        return None
    with_photo = with_photo.sort_values("complaint_date_parsed", ascending=False)
    return with_photo.iloc[0]["photo_path"]


def build_clusters(complaints_df: pd.DataFrame, zone_lookup: dict, zone_info: dict) -> pd.DataFrame:
    df = complaints_df.copy()
    df = df[df["location_description"].notna() & df["damage_type"].notna()]
    df["zone_id"] = df["location_description"].map(zone_lookup)
    df["zone_id"] = df["zone_id"].fillna(df["location_description"])

    reference_date = df["complaint_date_parsed"].max()

    records = []
    for (zone_id, damage_type), group in df.groupby(["zone_id", "damage_type"]):
        info = zone_info.get(zone_id)
        if info:
            zone_label = info["label"]
            lat, lon = info["latitude"], info["longitude"]
        else:
            zone_label = group["location_description"].iloc[0]
            lat, lon = group["latitude"].mean(), group["longitude"].mean()

        member_locations = sorted(group["location_description"].dropna().unique().tolist())

        cluster_id = make_cluster_id(zone_id, damage_type)
        complaint_count = len(group)
        worst_severity = _worst(group["severity"], SEVERITY_RANK)
        worst_safety_risk = _worst(group["safety_risk"], SAFETY_RANK)
        worst_traffic_impact = _worst(group["traffic_impact"], TRAFFIC_RANK)
        any_accident_reported = (group["vehicle_accident_reported"] == "Yes").any()
        any_emergency_route = (group["emergency_route"] == "Yes").any()

        status_counts = group["status"].value_counts().to_dict()
        open_count = status_counts.get("Open", 0)
        in_progress_count = status_counts.get("In Progress", 0)
        resolved_count = status_counts.get("Resolved", 0)

        latest_date = group["complaint_date_parsed"].max()
        first_date = group["complaint_date_parsed"].min()

        velocity = compute_urgency_velocity(group["complaint_date_parsed"], reference_date=reference_date)

        record = {
            "cluster_id": cluster_id,
            "zone_id": zone_id,
            "zone_label": zone_label,
            "member_locations": member_locations,
            "damage_type": damage_type,
            "damage_type_label": DAMAGE_TYPE_LABELS.get(damage_type, damage_type),
            "complaint_count": complaint_count,
            "open_count": open_count,
            "in_progress_count": in_progress_count,
            "resolved_count": resolved_count,
            "worst_severity": worst_severity,
            "worst_safety_risk": worst_safety_risk,
            "worst_traffic_impact": worst_traffic_impact,
            "any_accident_reported": any_accident_reported,
            "any_emergency_route": any_emergency_route,
            "first_reported": first_date,
            "last_reported": latest_date,
            "avg_latitude": lat,
            "avg_longitude": lon,
            "road_segment_ids": group["road_segment_id"].dropna().unique().tolist(),
            "complaint_ids": group["complaint_id"].dropna().tolist(),
            "velocity_score": velocity["velocity_score"],
            "reports_last_7_days": velocity["reports_last_7_days"],
            "reports_last_30_days": velocity["reports_last_30_days"],
        }
        record["priority_score"] = _priority_score(record)
        record["priority"] = _priority_label(record["priority_score"])
        record["representative_photo"] = _pick_representative_photo(group)
        records.append(record)

    clusters = pd.DataFrame(records)
    if not clusters.empty:
        clusters = clusters.sort_values(
            ["priority_score", "complaint_count"], ascending=[False, False]
        ).reset_index(drop=True)
    return clusters


def get_cluster_by_id(clusters: pd.DataFrame, cluster_id: str):
    matches = clusters[clusters["cluster_id"] == cluster_id]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def get_cluster_complaints(complaints_df: pd.DataFrame, member_locations: list, damage_type: str) -> pd.DataFrame:
    subset = complaints_df[
        (complaints_df["location_description"].isin(member_locations))
        & (complaints_df["damage_type"] == damage_type)
    ].copy()
    return subset.sort_values("complaint_date_parsed", ascending=False)


def related_interventions(events_df: pd.DataFrame, road_segment_ids: list) -> pd.DataFrame:
    if events_df.empty or not road_segment_ids:
        return pd.DataFrame()
    return events_df[events_df["road_segment_id"].isin(road_segment_ids)]


def build_map_zones(clusters: pd.DataFrame) -> pd.DataFrame:
    if clusters.empty:
        return pd.DataFrame()

    records = []
    for zone_id, group in clusters.groupby("zone_id"):
        top_row = group.loc[group["priority_score"].idxmax()]
        records.append({
            "zone_id": zone_id,
            "label": top_row["zone_label"],
            "latitude": top_row["avg_latitude"],
            "longitude": top_row["avg_longitude"],
            "total_complaints": int(group["complaint_count"].sum()),
            "problem_count": len(group),
            "max_priority_score": top_row["priority_score"],
            "priority": top_row["priority"],
        })

    zones = pd.DataFrame(records)
    if not zones.empty:
        zones = zones.sort_values("max_priority_score", ascending=False).reset_index(drop=True)
    return zones
