import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("GCC_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="GCC Citizen Portal",
    page_icon="🛣️",
    layout="centered",
)

st.markdown(
    """
    <style>
html, body, [class*="css"] { font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif; }
.stApp { background: #f4f7f6; }
.main .block-container { max-width: 980px; padding-top: 0; padding-bottom: 3rem; }
.gcc-ribbon {
    background: #20322f; margin: -1rem -1rem 0 -1rem; padding: 10px 26px;
    display: flex; align-items: center; gap: 10px;
}
.gcc-ribbon span {
    color: #e7efec; font-weight: 600; font-size: 0.82rem; letter-spacing: 0.06em;
    text-transform: uppercase;
}
.gcc-header {
    background: #ffffff; border-bottom: 1px solid #d8e2df;
    margin: 0 -1rem 2rem -1rem; padding: 1.6rem 1rem 1.4rem 1rem; text-align: center;
}
h1, h2, h3, h4 { color: #20322f; font-weight: 650; letter-spacing: -0.01em; }
h1 { font-size: 2.05rem; margin-bottom: 0.15rem !important; }
h3 { color: #60716d !important; font-weight: 500; font-size: 1.1rem; }
.stButton>button, .stFormSubmitButton>button {
    background: #496b63; color: #ffffff; border: 1px solid #496b63;
    border-radius: 7px; min-height: 2.55rem; font-weight: 600;
}
.stButton>button:hover, .stFormSubmitButton>button:hover {
    background: #3d5b55; border-color: #3d5b55; color: #ffffff;
}
[data-testid="stMetricValue"] { color: #20322f; }
.stTabs [data-baseweb="tab"] { color: #496b63; font-weight: 600; }
.stTabs [aria-selected="true"] { color: #35554e; }
hr { border-color: #d8e2df; }
[data-testid="stForm"] {
    background: #ffffff; border: 1px solid #d8e2df; border-radius: 12px;
    padding: 1.6rem; box-shadow: 0 2px 10px rgba(32, 50, 47, 0.045);
}
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div { border-radius: 7px; }
[data-testid="stFileUploader"] section {
    background: #f8faf9; border: 1px dashed #b9cbc6; border-radius: 9px;
}
[data-testid="stAlert"] { border-radius: 8px; }
.stCaption { color: #657570; }
[data-testid="stMap"] { border: 1px solid #d8e2df; border-radius: 10px; overflow: hidden; }
.gcc-footer { text-align: center; color: #8a9994; font-size: 0.8rem; margin-top: 2.5rem; }
</style>
<div class="gcc-ribbon"><span>GCC &middot; Government Road Maintenance Portal</span></div>
    """,
    unsafe_allow_html=True,
)


def render_footer():
    st.markdown(
        "<div class='gcc-footer'>Prototype developed by Kevin, Keerthi and Lakshikanth</div>",
        unsafe_allow_html=True,
    )

DAMAGE_TYPE_LABELS_FALLBACK = [
    "Pothole", "Cracked road surface (alligator cracking)", "Crack in road surface",
    "Sunken / depressed road surface", "Waterlogging", "Blocked or failed drainage",
    "Missing manhole cover", "Damaged footpath", "Broken streetlight",
    "Uneven road surface", "Open utility excavation", "Other road issue",
]


@st.cache_data(ttl=300)
def get_locations():
    try:
        r = requests.get(f"{API_URL}/locations", timeout=30)
        return r.json()["locations"]
    except Exception:
        return []


@st.cache_data(ttl=300)
def get_damage_type_labels():
    try:
        r = requests.get(f"{API_URL}/damage-types", timeout=30)
        return list(r.json()["damage_types"].values())
    except Exception:
        return DAMAGE_TYPE_LABELS_FALLBACK


@st.cache_data(ttl=120)
def get_predicted_resolution(location_description, damage_type_label):
    try:
        r = requests.get(
            f"{API_URL}/predicted-resolution",
            params={"location_description": location_description, "damage_type_label": damage_type_label},
            timeout=30,
        )
        return r.json().get("predicted_days")
    except Exception:
        return None


def get_complaint_status(complaint_id):
    try:
        r = requests.get(f"{API_URL}/complaint-status", params={"complaint_id": complaint_id}, timeout=30)
        if r.status_code == 404:
            return "not_found"
        r.raise_for_status()
        return r.json()
    except Exception:
        return "error"


st.markdown(
    "<div class='gcc-header'>"
    "<h1>GCC Citizen Portal</h1>"
    "<h3>Public Grievance &amp; Road Complaint System</h3>"
    "</div>",
    unsafe_allow_html=True,
)

mode = st.radio(
    "Choose an action",
    options=["Submit a new complaint", "Check complaint status"],
    horizontal=True,
    label_visibility="collapsed",
)

if mode == "Check complaint status":
    st.markdown("**Reference Number**")
    lookup_id = st.text_input("Reference Number", placeholder="e.g. CMP_000123", label_visibility="collapsed")
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
                st.success(f"Status: **{result['status']}**")
                st.write(f"**Issue type:** {result['damage_type_label']}")
                st.write(f"**Area:** {result['location_description']}")
                st.write(f"**Reported on:** {result['complaint_date']}")
                if result["status"] == "Resolved":
                    st.write(f"**Resolved on:** {result['resolution_date'] or 'Not recorded'}")
                    if result["resolution_type"]:
                        st.write(f"**Resolution:** {result['resolution_type']}")
    render_footer()
    st.stop()

if "citizen_submitted_id" in st.session_state:
    st.success(
        f"Thank you. Your complaint has been recorded with reference number "
        f"**{st.session_state['citizen_submitted_id']}**."
    )
    st.info("You can use this reference number to follow up on the status of your complaint.")
    if st.button("Submit another complaint"):
        del st.session_state["citizen_submitted_id"]
        st.rerun()
    render_footer()
    st.stop()

st.write(
    "Use this form to report potholes, damaged footpaths, waterlogging, broken "
    "streetlights, and other road-related issues in your area."
)

location_options = get_locations()
damage_type_labels = get_damage_type_labels()

@st.cache_data(ttl=300)
def get_location_coordinates(area):
    try:
        r = requests.get(f"{API_URL}/location-coordinates", params={"area": area}, timeout=30)
        data = r.json()
        return data["latitude"], data["longitude"]
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_sub_locations(area):
    try:
        r = requests.get(f"{API_URL}/sub-locations", params={"area": area}, timeout=30)
        return r.json().get("sub_locations", {})
    except Exception:
        return {}


st.markdown("**Area / Locality**")
area = st.selectbox("Area / Locality", options=location_options, label_visibility="collapsed")

sub_locations = get_sub_locations(area)
chosen_lat, chosen_lon = None, None

if sub_locations:
    st.caption(f"Your complaint area is {area}. Pick the exact spot for more precise reporting:")
    spot_label = st.selectbox("Exact spot", options=list(sub_locations.keys()), label_visibility="collapsed")
    chosen_lat = sub_locations[spot_label]["latitude"]
    chosen_lon = sub_locations[spot_label]["longitude"]
    st.map(pd.DataFrame([{"lat": chosen_lat, "lon": chosen_lon}]), latitude="lat", longitude="lon", size=30, zoom=15)
else:
    coords = get_location_coordinates(area)
    if coords:
        chosen_lat, chosen_lon = coords
        st.caption(f"Your complaint area is {area}.")
        st.map(pd.DataFrame([{"lat": chosen_lat, "lon": chosen_lon}]), latitude="lat", longitude="lon", size=40, zoom=13)

with st.form("complaint_form", clear_on_submit=False):
    landmark = st.text_input(
        "Nearby landmark (optional)", placeholder="e.g. Opposite bus stop"
    )

    damage_label = st.selectbox("What type of issue are you reporting?", options=damage_type_labels)

    if damage_label and area:
        predicted_days = get_predicted_resolution(area, damage_label)
        if predicted_days is not None:
            st.caption(f"Similar issues in your area have historically taken about {predicted_days:.0f} days to resolve.")

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
        if not description.strip() and not damage_label:
            st.error("Please provide a short description of the issue.")
        else:
            full_description = description
            if landmark.strip():
                full_description = f"{description} (Landmark: {landmark.strip()})"

            files = {}
            if photo is not None:
                files["photo"] = (photo.name, photo.getvalue(), photo.type)

            data = {
                "location_description": area,
                "damage_type_label": damage_label,
                "description": full_description,
                "severity_word": severity,
                "traffic_blocking": str(traffic_blocking),
                "safety_concern": str(safety_concern),
            }
            if chosen_lat is not None and chosen_lon is not None:
                data["latitude"] = chosen_lat
                data["longitude"] = chosen_lon

            try:
                r = requests.post(f"{API_URL}/complaints", data=data, files=files, timeout=45)
                r.raise_for_status()
                st.session_state["citizen_submitted_id"] = r.json()["complaint_id"]
                st.rerun()
            except Exception as e:
                st.error(f"Could not submit your complaint. Please try again. ({e})")

render_footer()
