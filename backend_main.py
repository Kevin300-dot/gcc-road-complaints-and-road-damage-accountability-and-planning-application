import math
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import data_layer
import analytics
import clustering
import risk_model


def _clean_value(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, dict):
        return {k: _clean_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_clean_value(item) for item in v]
    return v


def _clean_nans(records: list) -> list:
    return [_clean_value(rec) for rec in records]


import os

_computed_cache = {"key": None, "clusters": None, "accountability": None, "risk_model": None, "resolution_lookup": None}


def _cache_key():
    c_mtime = os.path.getmtime(data_layer.COMPLAINTS_PATH) if os.path.exists(data_layer.COMPLAINTS_PATH) else None
    e_mtime = os.path.getmtime(data_layer.EVENTS_PATH) if os.path.exists(data_layer.EVENTS_PATH) else None
    return (c_mtime, e_mtime)


def _get_clusters(complaints_df):
    key = _cache_key()
    if _computed_cache["key"] == key and _computed_cache["clusters"] is not None:
        return _computed_cache["clusters"]
    clusters = clustering.build_clusters(complaints_df, data_layer.ZONE_LOOKUP, data_layer.ZONE_INFO)
    if _computed_cache["key"] != key:
        _computed_cache["accountability"] = None
        _computed_cache["risk_model"] = None
    _computed_cache["key"] = key
    _computed_cache["clusters"] = clusters
    return clusters


def _get_risk_model(complaints_df, events_df):
    key = _cache_key()
    if _computed_cache["key"] == key and _computed_cache["risk_model"] is not None:
        return _computed_cache["risk_model"]
    model = risk_model.train_risk_model(complaints_df, events_df)
    _computed_cache["key"] = key
    _computed_cache["risk_model"] = model
    return model


def _get_resolution_lookup(complaints_df):
    key = _cache_key()
    if _computed_cache["key"] == key and _computed_cache["resolution_lookup"] is not None:
        return _computed_cache["resolution_lookup"]
    lookup = analytics.build_resolution_time_lookup(complaints_df)
    if _computed_cache["key"] != key:
        _computed_cache["accountability"] = None
        _computed_cache["risk_model"] = None
        _computed_cache["clusters"] = None
    _computed_cache["key"] = key
    _computed_cache["resolution_lookup"] = lookup
    return lookup


def _get_accountability(complaints_df, events_df):
    key = _cache_key()
    if _computed_cache["key"] == key and _computed_cache["accountability"] is not None:
        return _computed_cache["accountability"]
    model = _get_risk_model(complaints_df, events_df)
    result = analytics.compute_accountability(complaints_df, events_df, risk_model=model)
    _computed_cache["key"] = key
    _computed_cache["accountability"] = result
    return result

app = FastAPI(title="GCC Road Complaint System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OFFICER_PASSWORD = "gccofficer"


@app.on_event("startup")
def warm_up_cache():
    try:
        complaints_df = data_layer.load_complaints()
        events_df = data_layer.load_events()
        _get_clusters(complaints_df)
        _get_risk_model(complaints_df, events_df)
        _get_accountability(complaints_df, events_df)
        _get_resolution_lookup(complaints_df)
        print("Startup warm-up complete: data loaded and cached.")
    except Exception as e:
        print(f"Startup warm-up skipped due to: {e}")


@app.get("/")
def root():
    return {"service": "GCC Road Complaint System API", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/locations")
def get_locations():
    df = data_layer.load_complaints()
    return {"locations": data_layer.known_locations(df)}


@app.get("/location-coordinates")
def get_location_coordinates(area: str):
    lat, lon = data_layer.AREA_COORDINATES.get(area, (13.0827, 80.2707))
    return {"latitude": lat, "longitude": lon}


@app.get("/sub-locations")
def sub_locations(area: str):
    subs = data_layer.get_sublocations(area)
    return {
        "sub_locations": {
            label: {"latitude": lat, "longitude": lon}
            for label, (lat, lon) in subs.items()
        }
    }


@app.get("/damage-types")
def get_damage_types():
    return {"damage_types": data_layer.DAMAGE_TYPE_LABELS}


@app.get("/predicted-resolution")
def predicted_resolution(location_description: str, damage_type_label: str):
    df = data_layer.load_complaints()
    lookup = _get_resolution_lookup(df)
    damage_type = data_layer.LABEL_TO_DAMAGE_TYPE.get(damage_type_label, "Other")
    days = analytics.predicted_resolution_days(lookup, location_description, damage_type)
    return {"predicted_days": days}


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

    complaint_id = data_layer.submit_complaint(
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
    return {"complaint_id": complaint_id}


@app.get("/complaint-status")
def complaint_status(complaint_id: str):
    result = data_layer.get_complaint_status(complaint_id.strip())
    if result is None:
        raise HTTPException(status_code=404, detail="No complaint found with that reference number")
    return result


@app.get("/officer/login")
def officer_login(password: str):
    return {"authenticated": password == OFFICER_PASSWORD}


@app.get("/officer/summary")
def officer_summary():
    complaints_df = data_layer.load_complaints()
    clusters = _get_clusters(complaints_df)
    total_complaints = len(complaints_df)
    total_clusters = len(clusters)
    critical_count = int((clusters["priority"] == "Critical").sum()) if not clusters.empty else 0
    high_count = int((clusters["priority"] == "High").sum()) if not clusters.empty else 0
    return {
        "total_complaints": total_complaints,
        "active_locations": total_clusters,
        "critical_count": critical_count,
        "high_count": high_count,
    }


@app.get("/officer/clusters")
def officer_clusters():
    complaints_df = data_layer.load_complaints()
    clusters = _get_clusters(complaints_df)
    if clusters.empty:
        return {"clusters": []}

    escalations_df = data_layer.load_escalations()
    result = []
    for _, row in clusters.iterrows():
        record = row.to_dict()
        record["first_reported"] = str(record["first_reported"]) if record["first_reported"] is not None else None
        record["last_reported"] = str(record["last_reported"]) if record["last_reported"] is not None else None

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
    clusters = _get_clusters(complaints_df)

    cluster = clustering.get_cluster_by_id(clusters, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    complaints = clustering.get_cluster_complaints(complaints_df, cluster["member_locations"], cluster["damage_type"])
    display_cols = ["complaint_id", "location_description", "complaint_date", "complaint_text", "severity", "safety_risk", "status"]
    complaints_out = _clean_nans(complaints[display_cols].to_dict(orient="records"))

    road_segment_ids = complaints["road_segment_id"].dropna().unique().tolist()
    related = clustering.related_interventions(events_df, road_segment_ids)
    if related.empty:
        related_out = []
    else:
        cols = [c for c in ["event_id", "event_date", "event_type", "department", "contractor",
                             "work_description", "work_status", "restoration_completed"]
                if c in related.columns]
        related_out = _clean_nans(related[cols].to_dict(orient="records"))

    return {"complaints": complaints_out, "related_work": related_out}


@app.get("/officer/map-zones")
def officer_map_zones():
    complaints_df = data_layer.load_complaints()
    clusters = _get_clusters(complaints_df)
    zones = clustering.build_map_zones(clusters)
    if zones.empty:
        return {"zones": []}
    return {"zones": _clean_nans(zones.to_dict(orient="records"))}


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
def predict_repair_risk(department: str, contractor: str, event_type: str, road_cutting: str, month: int):
    complaints_df = data_layer.load_complaints()
    events_df = data_layer.load_events()
    model = _get_risk_model(complaints_df, events_df)
    if model is None:
        return {"predicted_failure_risk": None, "note": "Not enough historical data to train a model yet."}
    risk = risk_model.predict_risk(model, department, contractor, event_type, road_cutting, month)
    return {"predicted_failure_risk": risk}


@app.get("/officer/accountability")
def officer_accountability():
    complaints_df = data_layer.load_complaints()
    events_df = data_layer.load_events()
    result = _get_accountability(complaints_df, events_df)
    return {
        "by_department": _clean_nans(result["by_department"].to_dict(orient="records")),
        "by_contractor": _clean_nans(result["by_contractor"].to_dict(orient="records")),
    }


@app.post("/officer/update-status")
def update_status(complaint_id: str = Form(...), status: str = Form(...)):
    data_layer.update_complaint_status(complaint_id, status)
    return {"status": "updated"}


@app.post("/officer/update-restoration")
def update_restoration(event_id: str = Form(...), restoration_completed: str = Form(...)):
    data_layer.update_intervention_restoration(event_id, restoration_completed)
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
    import os
    from fastapi.responses import FileResponse

    safe_name = os.path.basename(filename)
    filepath = os.path.normpath(os.path.join(data_layer.UPLOAD_DIR, safe_name))

    if not filepath.startswith(os.path.normpath(data_layer.UPLOAD_DIR) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(filepath)
