import os
import re

import requests
import streamlit as st
import streamlit.components.v1 as components

import maplib
from portal_ui import apply_theme, render_header, render_footer, section_heading, render_resolution_estimate, render_status_result, render_receipt

API_URL = os.environ.get("GCC_API_URL", "http://localhost:8000")
OTHER_ROAD = "Other road in Kandanchavadi"

st.set_page_config(
    page_title="GCC | Citizen Complaint Portal — Kandanchavadi",
    page_icon="🛣️",
    layout="wide",
)

apply_theme("citizen")



DAMAGE_TYPE_LABELS_FALLBACK = [
    "Pothole", "Cracked road surface (alligator cracking)", "Crack in road surface",
    "Sunken / depressed road surface", "Waterlogging", "Blocked or failed drainage",
    "Missing manhole cover", "Damaged footpath", "Broken streetlight",
    "Uneven road surface", "Open utility excavation", "Other road issue",
]


@st.cache_data(ttl=300)
def _fetch_locations():
    r = requests.get(f"{API_URL}/locations", timeout=5)
    r.raise_for_status()
    return r.json()["locations"]


def get_locations():
    try:
        return _fetch_locations()
    except Exception:
        return []


@st.cache_data(ttl=300)
def _fetch_damage_type_labels():
    r = requests.get(f"{API_URL}/damage-types", timeout=5)
    r.raise_for_status()
    return list(r.json()["damage_types"].values())


def get_damage_type_labels():
    try:
        return _fetch_damage_type_labels()
    except Exception:
        return DAMAGE_TYPE_LABELS_FALLBACK


@st.cache_data(ttl=120)
def _fetch_predicted_resolution(road, damage_type_label):
    r = requests.get(
        f"{API_URL}/predicted-resolution",
        params={"location_description": road, "damage_type_label": damage_type_label},
        timeout=5,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("predicted_days"), data.get("basis")


def get_predicted_resolution(road, damage_type_label):
    try:
        return _fetch_predicted_resolution(road, damage_type_label)
    except Exception:
        return None, None


@st.cache_data(ttl=300)
def _fetch_location_coordinates(road):
    r = requests.get(f"{API_URL}/location-coordinates", params={"area": road}, timeout=5)
    r.raise_for_status()
    data = r.json()
    return data["latitude"], data["longitude"]


def get_location_coordinates(road):
    try:
        return _fetch_location_coordinates(road)
    except Exception:
        return None


@st.cache_data(ttl=60)
def _fetch_public_map():
    r = requests.get(f"{API_URL}/map-points", timeout=10)
    r.raise_for_status()
    return r.json()


def get_public_map():
    try:
        return _fetch_public_map()
    except Exception:
        return None


def check_location(lat, lon):
    try:
        r = requests.get(f"{API_URL}/location-check", params={"latitude": lat, "longitude": lon}, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def parse_coordinates(text):
    """Accepts '12.9645, 80.2449' as pasted from Google Maps (or two numbers separated by space/comma)."""
    nums = re.findall(r"-?\d+(?:\.\d+)?", text or "")
    if len(nums) < 2:
        return None
    lat, lon = float(nums[0]), float(nums[1])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def get_complaint_status(complaint_id):
    try:
        r = requests.get(f"{API_URL}/complaint-status", params={"complaint_id": complaint_id}, timeout=5)
        if r.status_code == 404:
            return "not_found"
        r.raise_for_status()
        return r.json()
    except Exception:
        return "error"


render_header("citizen")

mode = st.radio(
    "Choose an action",
    options=["Submit a new complaint", "Check complaint status"],
    horizontal=True,
    label_visibility="collapsed",
)

if mode == "Check complaint status":
    st.markdown("**Reference Number**")
    lookup_id = st.text_input("Reference Number", placeholder="e.g. CMP_KDV_049", label_visibility="collapsed")
    if st.button("Check Status"):
        if not lookup_id.strip():
            st.warning("Please enter a reference number.")
        else:
            result = get_complaint_status(lookup_id.strip())
            if result == "not_found":
                st.error("No complaint found with that reference number. Please check and try again.")
            elif result == "error":
                st.error("Could not reach the server. Please try again.")
            else:
                render_status_result(result)
                if result["status"] == "Resolved":
                    st.write(f"**Resolved on:** {result['resolution_date'] or 'Not recorded'}")
                    if result["resolution_type"]:
                        st.write(f"**Resolution:** {result['resolution_type']}")
    render_footer()
    st.stop()

if "citizen_submitted" in st.session_state:
    done = st.session_state["citizen_submitted"]
    render_receipt(done)
    nearby = done.get("nearby_reports") or []
    if nearby:
        ids = ", ".join(n["complaint_id"] for n in nearby[:5])
        st.caption(
            f"{len(nearby)} other report(s) were already within 30 m of this spot ({ids}). "
            "Yours has been added to the same hotspot so officers can see how many people are affected."
        )
    if st.button("Submit another complaint"):
        del st.session_state["citizen_submitted"]
        st.rerun()
    render_footer()
    st.stop()

st.write(
    "Use this form to report potholes, damaged footpaths, waterlogging, broken "
    "streetlights, and other road-related issues in Kandanchavadi."
)

roads = get_locations()
road_options = roads + [OTHER_ROAD]
damage_type_labels = get_damage_type_labels()

section_heading(1, "Complaint location")
st.markdown("**Road / Street**")
road = st.selectbox("Road / Street", options=road_options, label_visibility="collapsed")

default_coords = get_location_coordinates(road if road != OTHER_ROAD else "")
default_text = f"{default_coords[0]:.6f}, {default_coords[1]:.6f}" if default_coords else ""

st.markdown("**Exact location**")
st.caption(
    "Open Google Maps, press and hold on the spot, and paste the coordinates here (for example 12.964500, 80.244900). "
    "You can also click the map below to read off coordinates. The location must be inside Kandanchavadi."
)
coords_text = st.text_input("Latitude, longitude", value=default_text, key=f"coords_{road}", label_visibility="collapsed")
coords = parse_coordinates(coords_text)
chosen_lat, chosen_lon = (coords if coords else (None, None))

pin = None
if coords:
    check = check_location(chosen_lat, chosen_lon)
    if check is None:
        st.warning("Could not check the location right now.")
    elif check["inside"]:
        note = "inside Kandanchavadi"
        if not check["strictly_inside"]:
            note += " (on a border road)"
        st.success(f"This spot is {note}.")
        if check["nearby_reports"]:
            st.info(
                f"{len(check['nearby_reports'])} report(s) already exist within 30 m of this spot. "
                "You can still submit yours; it will be linked to the same hotspot."
            )
        pin = {"lat": chosen_lat, "lon": chosen_lon, "label": "Your location"}
    else:
        st.error(
            f"This spot is outside Kandanchavadi (about {check['distance_to_boundary_m']:.0f} m from the boundary). "
            "Please choose a spot inside the area."
        )
        pin = {"lat": chosen_lat, "lon": chosen_lon, "label": "Outside area"}
elif coords_text.strip():
    st.error("Could not read those coordinates. Use the form 12.964500, 80.244900.")

public_map = get_public_map()
if public_map:
    components.html(
        maplib.build_map_html(
            boundary_geojson=public_map["boundary"],
            complaints=[],  # citizen map is plain: boundary + own location only
            photo_base_url="",
            height_px=420,
            pin=pin,
            click_to_pick=True,
            show_hotspot_rings=False,
        ),
        height=500,
        scrolling=False,
    )
    st.caption("The red line is the Kandanchavadi boundary. Click the map to place your location.")

section_heading(2, "Issue details & evidence")
with st.form("complaint_form", clear_on_submit=False):
    landmark = st.text_input(
        "Nearby landmark (optional)", placeholder="e.g. Opposite the temple"
    )

    damage_label = st.selectbox("What type of issue are you reporting?", options=damage_type_labels)

    if damage_label and road != OTHER_ROAD:
        predicted_days, basis = get_predicted_resolution(road, damage_label)
        if predicted_days is not None:
            render_resolution_estimate(predicted_days, basis)

    description = st.text_area(
        "Describe the issue",
        placeholder="Tell us what you observed — for example, the size of the "
        "pothole, how long it has existed, or how it is affecting traffic.",
        height=110,
    )

    severity = st.radio(
        "How would you rate this issue?",
        options=["Minor", "Moderate", "Severe"],
        horizontal=True,
        help="Minor: cosmetic issue. Moderate: needs attention soon. "
        "Severe: urgent, poses a real risk.",
    )

    col3, col4 = st.columns(2)
    with col3:
        traffic_blocking = st.checkbox("This is blocking or slowing down traffic")
    with col4:
        safety_concern = st.checkbox("This poses a safety risk to pedestrians or riders")

    st.markdown("**Upload a photo**")
    st.caption("Accepted formats: JPG, JPEG, PNG · Maximum file size: 5 MB")
    photo = st.file_uploader(
        "Upload a clear photo of the road issue.",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
    )
    if photo is not None and photo.size > 5 * 1024 * 1024:
        st.error("The uploaded file is larger than 5 MB. Please choose a smaller image.")
        photo = None

    submitted = st.form_submit_button("Submit Complaint", use_container_width=True)

    if submitted:
        if chosen_lat is None:
            st.error("Please enter a valid location (latitude, longitude) inside Kandanchavadi.")
        elif not description.strip() and not damage_label:
            st.error("Please provide a short description of the issue.")
        else:
            full_description = description
            if landmark.strip():
                full_description = f"{description} (Landmark: {landmark.strip()})"

            files = {}
            if photo is not None:
                files["photo"] = (photo.name, photo.getvalue(), photo.type)

            data = {
                "location_description": road if road != OTHER_ROAD else "",
                "damage_type_label": damage_label,
                "description": full_description,
                "severity_word": severity,
                "traffic_blocking": str(traffic_blocking),
                "safety_concern": str(safety_concern),
                "latitude": chosen_lat,
                "longitude": chosen_lon,
            }

            try:
                r = requests.post(f"{API_URL}/complaints", data=data, files=files, timeout=45)
                if r.status_code == 422:
                    st.error(r.json().get("detail", "The complaint could not be accepted."))
                else:
                    r.raise_for_status()
                    st.session_state["citizen_submitted"] = r.json()
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"Could not submit your complaint. Please try again. ({e})")

render_footer()
