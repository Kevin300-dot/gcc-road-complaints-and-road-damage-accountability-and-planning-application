import os
import uuid
from datetime import datetime

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

COMPLAINTS_PATH = os.path.join(DATA_DIR, "complaints.csv")
EVENTS_PATH = os.path.join(DATA_DIR, "intervention_events.csv")
ESCALATIONS_PATH = os.path.join(DATA_DIR, "escalations.csv")

COMPLAINT_COLUMNS = [
    "complaint_id", "road_segment_id", "complaint_date", "complaint_time",
    "latitude", "longitude", "location_description", "complaint_text",
    "language", "damage_type", "severity", "traffic_impact", "safety_risk",
    "vehicle_accident_reported", "pedestrian_risk", "two_wheeler_risk",
    "emergency_route", "status", "assigned_department", "resolution_date",
    "resolution_type", "photo_path", "submission_channel",
]

DAMAGE_TYPE_LABELS = {
    "Pothole": "Pothole",
    "Alligator_Cracking": "Cracked road surface (alligator cracking)",
    "Crack": "Crack in road surface",
    "Depression": "Sunken / depressed road surface",
    "Subsidence": "Road subsidence / sinking",
    "Road_Collapse": "Collapsed road section",
    "Waterlogging": "Waterlogging",
    "Drainage_Failure": "Blocked or failed drainage",
    "Missing_Manhole_Cover": "Missing manhole cover",
    "Damaged_Manhole": "Damaged manhole",
    "Damaged_Footpath": "Damaged footpath",
    "Damaged_Curb": "Damaged curb / kerb",
    "Damaged_Median": "Damaged road median",
    "Broken_Streetlight": "Broken streetlight",
    "Damaged_Signage": "Damaged road signage",
    "Faded_Road_Marking": "Faded road markings",
    "Missing_Road_Marking": "Missing road markings",
    "Uneven_Surface": "Uneven road surface",
    "Rutting": "Rutting / wheel ruts",
    "Edge_Cracking": "Road edge cracking",
    "Poor_Restoration": "Poorly restored road cut",
    "Unrestored_Road_Cut": "Unrestored road cut",
    "Utility_Excavation": "Open utility excavation",
    "Road_Work_Incomplete": "Incomplete road work",
    "Construction_Debris": "Construction debris on road",
    "Obstruction": "Obstruction on road",
    "Road_Surface_Deterioration": "General road surface deterioration",
    "Other": "Other road issue",
}

LABEL_TO_DAMAGE_TYPE = {v: k for k, v in DAMAGE_TYPE_LABELS.items()}

SEVERITY_OPTIONS = ["Minor", "Moderate", "Severe"]
SEVERITY_TO_FIELD = {"Minor": "Low", "Moderate": "Medium", "Severe": "Critical"}


def _haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    r = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def _build_zones(area_coordinates: dict, threshold_km: float = 1.5):
    import re
    names = list(area_coordinates.keys())
    parent = {n: n for n in names}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            lat1, lon1 = area_coordinates[a]
            lat2, lon2 = area_coordinates[b]
            if _haversine_km(lat1, lon1, lat2, lon2) <= threshold_km:
                union(a, b)

    groups = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)

    zone_lookup = {}
    zone_info = {}
    for root, members in groups.items():
        zone_id = "zone_" + re.sub(r"[^a-z0-9]+", "_", root.lower()).strip("_")
        lats = [area_coordinates[m][0] for m in members]
        lons = [area_coordinates[m][1] for m in members]
        label = " / ".join(m.replace("Near ", "") for m in members)
        zone_info[zone_id] = {
            "zone_id": zone_id,
            "label": label,
            "latitude": sum(lats) / len(lats),
            "longitude": sum(lons) / len(lons),
            "members": members,
        }
        for m in members:
            zone_lookup[m] = zone_id

    return zone_lookup, zone_info


AREA_COORDINATES = {
    "Near Adambakkam": (12.9829, 80.2010),
    "Near Adyar": (13.0012, 80.2565),
    "Near Ambattur": (13.1143, 80.1548),
    "Near Anna Nagar": (13.0850, 80.2101),
    "Near Besant Nagar": (12.9990, 80.2668),
    "Near Guindy": (13.0067, 80.2206),
    "Near Maduravoyal": (13.0637, 80.1548),
    "Near Medavakkam": (12.9186, 80.1878),
    "Near Mogappair": (13.0823, 80.1728),
    "Near Mylapore": (13.0339, 80.2685),
    "Near Nungambakkam": (13.0603, 80.2417),
    "Near Pallikaranai": (12.9345, 80.2145),
    "Near Perungudi": (12.9635, 80.2422),
    "Near Porur": (13.0381, 80.1564),
    "Near Saidapet": (13.0212, 80.2211),
    "Near Shenoy Nagar": (13.0784, 80.2226),
    "Near T Nagar": (13.0418, 80.2341),
    "Near Taramani": (12.9843, 80.2452),
    "Near Thoraipakkam": (12.9410, 80.2370),
    "Near Velachery": (12.9791, 80.2183),
}

ZONE_LOOKUP, ZONE_INFO = _build_zones(AREA_COORDINATES)

def _generate_sublocations(area_coordinates: dict) -> dict:
    # Small, consistent offsets (roughly 300-500m) applied to each area's known
    # center, giving every locality 5 distinguishable points instead of one.
    offsets = [
        ("Main Road", 0.0, 0.0),
        ("Junction", 0.004, 0.003),
        ("Bus Stand", -0.003, 0.004),
        ("Market", 0.003, -0.004),
        ("Signal", -0.004, -0.003),
    ]
    result = {}
    for area, (lat, lon) in area_coordinates.items():
        short_name = area.replace("Near ", "")
        points = {}
        for suffix, dlat, dlon in offsets:
            label = f"{short_name} {suffix}"
            points[label] = (round(lat + dlat, 4), round(lon + dlon, 4))
        result[area] = points
    return result


PRECISION_SUBLOCATIONS = _generate_sublocations(AREA_COORDINATES)


def get_sublocations(area: str) -> dict:
    return PRECISION_SUBLOCATIONS.get(area, {})


def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)


_complaints_cache = {"mtime": None, "df": None}
_events_cache = {"mtime": None, "df": None}


def load_complaints() -> pd.DataFrame:
    _ensure_dirs()
    mtime = os.path.getmtime(COMPLAINTS_PATH) if os.path.exists(COMPLAINTS_PATH) else None
    if _complaints_cache["mtime"] == mtime and _complaints_cache["df"] is not None:
        return _complaints_cache["df"].copy()

    df = pd.read_csv(COMPLAINTS_PATH)
    for col in COMPLAINT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df["submission_channel"] = df["submission_channel"].fillna("legacy_record")
    df["complaint_date_parsed"] = pd.to_datetime(
        df["complaint_date"], format="%d-%m-%Y", errors="coerce"
    )
    df["resolution_date_parsed"] = pd.to_datetime(
        df["resolution_date"], format="%d-%m-%Y", errors="coerce"
    )

    _complaints_cache["mtime"] = mtime
    _complaints_cache["df"] = df
    return df.copy()


def load_events() -> pd.DataFrame:
    _ensure_dirs()
    if not os.path.exists(EVENTS_PATH):
        return pd.DataFrame()

    mtime = os.path.getmtime(EVENTS_PATH)
    if _events_cache["mtime"] == mtime and _events_cache["df"] is not None:
        return _events_cache["df"].copy()

    df = pd.read_csv(EVENTS_PATH)
    df["completion_date_parsed"] = pd.to_datetime(
        df["completion_date"], format="%d-%m-%Y", errors="coerce"
    )
    df["start_date_parsed"] = pd.to_datetime(
        df["start_date"], format="%d-%m-%Y", errors="coerce"
    )

    _events_cache["mtime"] = mtime
    _events_cache["df"] = df
    return df.copy()


def known_locations(df: pd.DataFrame) -> list:
    locations = sorted(df["location_description"].dropna().unique().tolist())
    return locations if locations else list(AREA_COORDINATES.keys())


def save_uploaded_photo(file_bytes: bytes, filename: str, complaint_id: str) -> str:
    _ensure_dirs()
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    out_name = f"{complaint_id}{ext}"
    filepath = os.path.join(UPLOAD_DIR, out_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return filepath


def next_complaint_id(df: pd.DataFrame) -> str:
    existing_numeric = []
    for cid in df["complaint_id"].dropna():
        try:
            existing_numeric.append(int(str(cid).split("_")[-1]))
        except ValueError:
            continue
    next_num = (max(existing_numeric) + 1) if existing_numeric else 1
    return f"CMP_{next_num:06d}"


def submit_complaint(
    location_description: str,
    damage_type_label: str,
    description: str,
    severity_word: str,
    traffic_blocking: bool,
    safety_concern: bool,
    photo_bytes: bytes = None,
    photo_filename: str = None,
    latitude: float = None,
    longitude: float = None,
) -> str:
    _ensure_dirs()
    df = load_complaints().drop(columns=["complaint_date_parsed", "resolution_date_parsed"])

    complaint_id = next_complaint_id(df)
    now = datetime.now()
    damage_type = LABEL_TO_DAMAGE_TYPE.get(damage_type_label, "Other")
    severity_field = SEVERITY_TO_FIELD.get(severity_word, "Medium")

    if latitude is None or longitude is None:
        lat, lon = AREA_COORDINATES.get(location_description, (13.0827, 80.2707))
    else:
        lat, lon = latitude, longitude

    photo_path = ""
    if photo_bytes and photo_filename:
        photo_path = save_uploaded_photo(photo_bytes, photo_filename, complaint_id)

    row = {
        "complaint_id": complaint_id,
        "road_segment_id": f"RD_{uuid.uuid4().hex[:5].upper()}",
        "complaint_date": now.strftime("%d-%m-%Y"),
        "complaint_time": now.strftime("%H:%M"),
        "latitude": lat,
        "longitude": lon,
        "location_description": location_description,
        "complaint_text": description.strip() or "No additional details provided.",
        "language": "English",
        "damage_type": damage_type,
        "severity": severity_field,
        "traffic_impact": "High" if traffic_blocking else "Low",
        "safety_risk": "High" if safety_concern else "Low",
        "vehicle_accident_reported": "No",
        "pedestrian_risk": "Yes" if safety_concern else "No",
        "two_wheeler_risk": "Yes" if safety_concern else "No",
        "emergency_route": "No",
        "status": "Open",
        "assigned_department": "GCC Roads",
        "resolution_date": "",
        "resolution_type": "",
        "photo_path": photo_path,
        "submission_channel": "citizen_app",
    }

    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(COMPLAINTS_PATH, index=False)
    _complaints_cache["mtime"] = None
    return complaint_id


def update_complaint_status(complaint_id: str, new_status: str, resolution_type: str = None):
    _ensure_dirs()
    df = pd.read_csv(COMPLAINTS_PATH)
    mask = df["complaint_id"] == complaint_id
    df.loc[mask, "status"] = new_status
    if new_status == "Resolved":
        existing_date = df.loc[mask, "resolution_date"]
        if existing_date.isna().all() or (existing_date == "").all():
            df.loc[mask, "resolution_date"] = datetime.now().strftime("%d-%m-%Y")
        if resolution_type:
            df.loc[mask, "resolution_type"] = resolution_type
    df.to_csv(COMPLAINTS_PATH, index=False)
    _complaints_cache["mtime"] = None


def update_intervention_restoration(event_id: str, restoration_completed: str):
    _ensure_dirs()
    df = pd.read_csv(EVENTS_PATH)
    df.loc[df["event_id"] == event_id, "restoration_completed"] = restoration_completed
    df.to_csv(EVENTS_PATH, index=False)
    _events_cache["mtime"] = None


def load_escalations() -> pd.DataFrame:
    _ensure_dirs()
    if not os.path.exists(ESCALATIONS_PATH):
        return pd.DataFrame(
            columns=["cluster_id", "escalated_at", "escalated_to", "note", "officer_name"]
        )
    return pd.read_csv(ESCALATIONS_PATH)


def save_escalation(cluster_id: str, escalated_to: str, note: str, officer_name: str):
    _ensure_dirs()
    df = load_escalations()
    row = {
        "cluster_id": cluster_id,
        "escalated_at": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "escalated_to": escalated_to,
        "note": note,
        "officer_name": officer_name or "GCC Officer",
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(ESCALATIONS_PATH, index=False)
