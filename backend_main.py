"""
GCC Road Complaint System - API (Kandanchavadi pilot).

Run:  uvicorn backend_main:app --reload --port 8000

Environment variables
  OFFICER_PASSWORD     officer dashboard password (default "gccofficer", demo only - change it)
  ORION_CORS_ORIGINS   comma-separated allowed browser origins (default: local Streamlit)
"""
import hmac
import math
import os
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import analytics
import area_config
import clustering
import data_layer
import impact
import risk_model


# ---------------------------------------------------------------- JSON cleaning

def _clean_value(v):
    """Make pandas / numpy values JSON-safe (NaN and NaT -> None, numpy scalars -> Python)."""
    if isinstance(v, dict):
        return {k: _clean_value(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean_value(item) for item in v]
    if isinstance(v, np.generic):
        v = v.item()
    if v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _clean_nans(records: list) -> list:
    return [_clean_value(rec) for rec in records]


# ---------------------------------------------------------------- cached computations
# Everything expensive is recomputed only when a data file changes.

_memo = {}


def _cached(name, builder):
    version = data_layer.data_version()
    hit = _memo.get(name)
    if hit and hit[0] == version:
        return hit[1]
    value = builder()
    _memo[name] = (version, value)
    return value


def _get_clusters():
    return _cached("clusters", lambda: clustering.build_clusters(data_layer.load_complaints()))


def _get_risk_model():
    def build():
        complaints, events, label = data_layer.analytics_sources()
        return risk_model.train_risk_model(complaints, events, data_label=label)
    return _cached("risk_model", build)


def _get_accountability():
    def build():
        complaints, events, label = data_layer.analytics_sources()
        result = analytics.compute_accountability(complaints, events, risk_model=_get_risk_model())
        result["data_label"] = label
        return result
    return _cached("accountability", build)


def _get_resolution_lookup():
    """Real resolution times if there are enough resolved real complaints, otherwise simulated."""
    def build():
        real = analytics.build_resolution_time_lookup(data_layer.load_complaints())
        if real["n_resolved"] >= 10:
            return real, "real"
        return analytics.build_resolution_time_lookup(data_layer.load_sim_complaints()), "simulated"
    return _cached("resolution", build)


# ---------------------------------------------------------------- app

app = FastAPI(title="GCC Road Complaint System API - Kandanchavadi")

_origins = [o.strip() for o in os.environ.get("ORION_CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])

OFFICER_PASSWORD = os.environ.get("OFFICER_PASSWORD", "gccofficer")


@app.on_event("startup")
def warm_up_cache():
    if OFFICER_PASSWORD == "gccofficer":
        print("WARNING: using the default officer password. Set OFFICER_PASSWORD before sharing this server.")
    try:
        _get_clusters()
        _get_accountability()
        _get_resolution_lookup()
        print("Startup warm-up complete: data loaded and cached.")
    except Exception as e:  # never stop the server because of warm-up
        print(f"Startup warm-up skipped due to: {e}")


@app.get("/")
def root():
    return {"service": "GCC Road Complaint System API", "area": area_config.AREA_NAME, "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/area")
def get_area():
    """Kandanchavadi boundary (GeoJSON), bounds, centre and size."""
    return area_config.info()


@app.get("/locations")
def get_locations():
    """Road names a citizen can pick from."""
    return {"locations": data_layer.known_locations(data_layer.load_complaints())}


@app.get("/location-coordinates")
def get_location_coordinates(area: str):
    lat, lon = data_layer.road_coordinates(data_layer.load_complaints(), area)
    return {"latitude": lat, "longitude": lon}


@app.get("/location-check")
def location_check(latitude: float, longitude: float):
    """Is a point inside Kandanchavadi (border roads count as inside)?"""
    info = area_config.locate(latitude, longitude)
    return {
        "inside": area_config.contains(latitude, longitude),
        "strictly_inside": info["inside"],
        "distance_to_boundary_m": info["distance_to_edge_m"],
        "nearby_reports": data_layer.nearby_reports(data_layer.load_complaints(), latitude, longitude),
    }


@app.get("/map-points")
def public_map_points():
    """Public, minimal view for the citizen map: where reports already exist.
    No descriptions or photos, so nothing a citizen wrote or photographed is exposed."""
    df = data_layer.load_complaints().dropna(subset=["latitude", "longitude"])
    points = [{
        "complaint_id": r["complaint_id"], "latitude": r["latitude"], "longitude": r["longitude"],
        "road_name": r["road_name"], "damage_type_label": data_layer.DAMAGE_TYPE_LABELS.get(r["damage_type"], r["damage_type"]),
        "status": r["status"],
    } for _, r in df.iterrows()]
    return {"boundary": area_config.to_geojson(), "complaints": _clean_nans(points)}


@app.get("/damage-types")
def get_damage_types():
    return {"damage_types": data_layer.DAMAGE_TYPE_LABELS}


@app.get("/predicted-resolution")
def predicted_resolution(location_description: str, damage_type_label: str):
    lookup, basis = _get_resolution_lookup()
    damage_type = data_layer.LABEL_TO_DAMAGE_TYPE.get(damage_type_label, "Other")
    days = analytics.predicted_resolution_days(lookup, location_description, damage_type)
    return {"predicted_days": days, "basis": basis}


@app.post("/complaints")
async def create_complaint(
    location_description: str = Form(...),
    damage_type_label: str = Form(...),
    description: str = Form(""),
    severity_word: str = Form("Moderate"),
    traffic_blocking: bool = Form(False),
    safety_concern: bool = Form(False),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    photo: Optional[UploadFile] = File(None),
):
    photo_bytes = None
    photo_filename = None
    if photo is not None:
        photo_bytes = await photo.read()
        photo_filename = photo.filename
    try:
        result = data_layer.submit_complaint(
            location_description=location_description,
            damage_type_label=damage_type_label,
            description=description,
            severity_word=severity_word,
            traffic_blocking=traffic_blocking,
            safety_concern=safety_concern,
            latitude=latitude,
            longitude=longitude,
            photo_bytes=photo_bytes,
            photo_filename=photo_filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return result


@app.get("/complaint-status")
def complaint_status(complaint_id: str):
    result = data_layer.get_complaint_status(complaint_id.strip())
    if result is None:
        raise HTTPException(status_code=404, detail="No complaint found with that reference number")
    return _clean_value(result)


# ---------------------------------------------------------------- officer

@app.post("/officer/login")
def officer_login(password: str = Form(...)):
    return {"authenticated": hmac.compare_digest(password.encode(), OFFICER_PASSWORD.encode())}


@app.get("/officer/summary")
def officer_summary():
    complaints_df = data_layer.load_complaints()
    clusters = _get_clusters()
    return {
        "total_complaints": int(len(complaints_df)),
        "active_locations": int(len(clusters)),
        "critical_count": int((clusters["priority"] == "Critical").sum()) if not clusters.empty else 0,
        "high_count": int((clusters["priority"] == "High").sum()) if not clusters.empty else 0,
        "area": area_config.AREA_NAME,
    }


@app.get("/officer/clusters")
def officer_clusters():
    clusters = _get_clusters()
    if clusters.empty:
        return {"clusters": []}
    escalations_df = data_layer.load_escalations()
    result = []
    for _, row in clusters.iterrows():
        record = row.to_dict()
        existing_escalation = None
        if not escalations_df.empty:
            matches = escalations_df[escalations_df["cluster_id"] == row["cluster_id"]]
            if not matches.empty:
                existing_escalation = matches.iloc[-1].to_dict()
        record["escalation"] = existing_escalation
        result.append(record)
    return {"clusters": _clean_nans(result)}


@app.get("/officer/cluster-detail")
def officer_cluster_detail(cluster_id: str):
    complaints_df = data_layer.load_complaints()
    events_df = data_layer.load_events()
    clusters = _get_clusters()

    cluster = clustering.get_cluster_by_id(clusters, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    complaints = clustering.get_cluster_complaints(complaints_df, cluster["complaint_ids"])
    display_cols = ["complaint_id", "road_name", "complaint_date", "complaint_time", "damage_type",
                    "complaint_text", "severity", "safety_risk", "status", "latitude", "longitude"]
    complaints = complaints.copy()
    complaints["photo"] = complaints["photo_path"].apply(
        lambda p: os.path.basename(p) if isinstance(p, str) and p.strip() else None)
    complaints_out = _clean_nans(complaints[display_cols + ["photo"]].to_dict(orient="records"))

    related = clustering.related_interventions(events_df, cluster["road_segment_ids"])
    if related.empty:
        related_out = []
    else:
        cols = [c for c in ["event_id", "event_date", "event_type", "department", "contractor",
                            "work_description", "work_status", "restoration_completed"]
                if c in related.columns]
        related_out = _clean_nans(related[cols].to_dict(orient="records"))
    return {"complaints": complaints_out, "related_work": related_out,
            "related_work_is_simulated": bool(not related.empty and related.get("data_source", pd.Series([""])).astype(str).str.contains("simulated").any())}


@app.get("/officer/map-zones")
def officer_map_zones():
    zones = clustering.build_map_zones(_get_clusters())
    if zones.empty:
        return {"zones": []}
    return {"zones": _clean_nans(zones.to_dict(orient="records"))}


@app.get("/officer/map-data")
def officer_map_data():
    """Everything the OpenStreetMap view needs: boundary, every real complaint, every hotspot."""
    complaints_df = data_layer.load_complaints()
    clusters = _get_clusters()
    points = clustering.build_map_points(complaints_df, clusters)
    zones = clustering.build_map_zones(clusters)
    complaints_out = []
    if not points.empty:
        for _, r in points.iterrows():
            complaints_out.append({
                "complaint_id": r["complaint_id"], "latitude": r["latitude"], "longitude": r["longitude"],
                "road_name": r["road_name"], "damage_type_label": data_layer.DAMAGE_TYPE_LABELS.get(r["damage_type"], r["damage_type"]),
                "severity": r["severity"], "status": r["status"], "priority": r["priority"], "cluster_id": r["cluster_id"],
                "date": r["complaint_date"], "text": r["complaint_text"], "photo": r["photo_path"],
            })
    return {
        "boundary": area_config.to_geojson(),
        "complaints": _clean_nans(complaints_out),
        "hotspots": _clean_nans(zones.to_dict(orient="records")) if not zones.empty else [],
    }


@app.get("/officer/repair-risk-options")
def repair_risk_options():
    events_df = data_layer.load_events()
    if events_df.empty:
        return {"departments": [], "contractors": [], "event_types": []}
    return {
        "departments": sorted(events_df["department"].dropna().unique().tolist()),
        "contractors": sorted(events_df["contractor"].dropna().unique().tolist()),
        "event_types": sorted(events_df["event_type"].dropna().unique().tolist()),
    }


@app.get("/officer/predict-repair-risk")
def predict_repair_risk(department: str, contractor: str, event_type: str, road_cutting: str, duration_days: float = 3):
    bundle = _get_risk_model()
    if bundle is None:
        return {"predicted_failure_risk": None, "note": "Not enough historical repair outcomes to train a model yet."}
    risk = risk_model.predict_risk(bundle, department, contractor, event_type, road_cutting, duration_days)
    report = bundle["report"]
    return {"predicted_failure_risk": risk, "base_rate_pct": round(report["failure_rate"] * 100, 1),
            "data_label": report["data_label"], "window_days": report["window_days"]}


@app.get("/officer/model-report")
def model_report():
    bundle = _get_risk_model()
    if bundle is None:
        return {"available": False, "reason": "Not enough judged repairs (need at least 40, with at least 8 failures and 8 successes)."}
    return {"available": True, **_clean_value(bundle["report"])}


@app.get("/officer/accountability")
def officer_accountability():
    result = _get_accountability()
    return {
        "by_department": _clean_nans(result["by_department"].to_dict(orient="records")),
        "by_contractor": _clean_nans(result["by_contractor"].to_dict(orient="records")),
        "summary": _clean_value(result["summary"]),
        "data_label": result["data_label"],
    }


@app.get("/officer/impact")
def officer_impact(
    population_served: Optional[float] = None,
    monthly_complaints: Optional[float] = None,
    triage_minutes_manual: Optional[float] = None,
    triage_minutes_system: Optional[float] = None,
    officer_cost_per_hour: Optional[float] = None,
    platform_monthly_cost: Optional[float] = None,
    setup_cost_one_time: Optional[float] = None,
    repeat_repair_reduction_pct: Optional[float] = None,
    wards_in_scope: Optional[float] = None,
):
    given = {k: v for k, v in dict(
        population_served=population_served, monthly_complaints=monthly_complaints,
        triage_minutes_manual=triage_minutes_manual, triage_minutes_system=triage_minutes_system,
        officer_cost_per_hour=officer_cost_per_hour, platform_monthly_cost=platform_monthly_cost,
        setup_cost_one_time=setup_cost_one_time, repeat_repair_reduction_pct=repeat_repair_reduction_pct,
        wards_in_scope=wards_in_scope,
    ).items() if v is not None}
    result = impact.compute_impact(
        data_layer.load_complaints(), _get_clusters(), data_layer.load_events(),
        _get_accountability()["summary"], given,
    )
    return _clean_value(result)


@app.post("/officer/update-status")
def update_status(complaint_id: str = Form(...), status: str = Form(...)):
    try:
        data_layer.update_complaint_status(complaint_id, status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return {"status": "updated"}


@app.post("/officer/update-restoration")
def update_restoration(event_id: str = Form(...), restoration_completed: str = Form(...)):
    try:
        data_layer.update_intervention_restoration(event_id, restoration_completed)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "updated"}


@app.post("/officer/escalate")
def officer_escalate(
    cluster_id: str = Form(...),
    escalated_to: str = Form(...),
    officer_name: str = Form(""),
    note: str = Form(""),
):
    data_layer.save_escalation(cluster_id, escalated_to, note, officer_name)
    return {"status": "escalated"}


@app.get("/photo/{filename}")
def get_photo(filename: str):
    from fastapi.responses import FileResponse

    path = data_layer.find_photo_file(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path)
