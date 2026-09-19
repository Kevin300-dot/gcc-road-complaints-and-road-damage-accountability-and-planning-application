import os

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

API_URL = os.environ.get("GCC_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="GCC Officer Dashboard",
    page_icon="🛠️",
    layout="wide",
)

st.markdown(
    """
    <style>
html, body, [class*="css"] { font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif; }
.stApp { background: #f4f7f6; }
.main .block-container { padding-top: 0; padding-bottom: 3rem; max-width: 1440px; }
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
    margin: 0 -1rem 1.8rem -1rem; padding: 1.4rem 1.5rem 1.2rem 1.5rem;
}
h1, h2, h3, h4 { color: #20322f; font-weight: 650; letter-spacing: -0.01em; }
h2 { font-size: 1.75rem; }
h3, h4 { color: #314b46; }
.stButton>button, .stFormSubmitButton>button {
    background: #496b63; color: #ffffff; border: 1px solid #496b63;
    border-radius: 7px; min-height: 2.45rem; font-weight: 600;
}
.stButton>button:hover, .stFormSubmitButton>button:hover {
    background: #3d5b55; border-color: #3d5b55; color: #ffffff;
}
[data-testid="stMetricValue"] { color: #20322f; font-weight: 650; }
[data-testid="stMetricLabel"] { color: #657570; }
.stTabs [data-baseweb="tab"] { color: #496b63; font-weight: 600; }
.stTabs [aria-selected="true"] { color: #35554e; }
hr { border-color: #d8e2df; }
[data-testid="stForm"], [data-testid="stExpander"] {
    background: #ffffff; border: 1px solid #d8e2df; border-radius: 11px;
    box-shadow: 0 2px 10px rgba(32, 50, 47, 0.04);
}
[data-testid="stForm"] { padding: 1.45rem; }
[data-testid="stExpander"] { overflow: hidden; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div { border-radius: 7px; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border: 1px solid #d8e2df; border-radius: 8px; overflow: hidden;
}
[data-testid="stAlert"] { border-radius: 8px; }
.stCaption { color: #657570; }
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

ESCALATION_TARGETS = [
    "Zonal Office",
    "Chief Engineer (Roads)",
    "Corporation Head Office",
    "Traffic Police Department",
]

PRIORITY_COLORS = {
    "Critical": "#b91c1c",
    "High": "#d97706",
    "Medium": "#2563eb",
    "Low": "#4b5563",
}


def priority_badge(priority: str) -> str:
    color = PRIORITY_COLORS.get(priority, "#4b5563")
    return (
        f"<span style='background-color:{color};color:white;padding:2px 10px;"
        f"border-radius:12px;font-size:0.8rem;font-weight:600'>{priority}</span>"
    )


def check_password():
    if st.session_state.get("officer_authenticated"):
        return True

    st.markdown("## GCC Officer Portal")
    st.caption("Authorized personnel only")
    with st.form("officer_login"):
        password = st.text_input("Officer Password", type="password")
        submitted = st.form_submit_button("Log In")
        if submitted:
            try:
                with st.spinner("Connecting to server — this can take up to a minute if it has been idle..."):
                    r = requests.get(f"{API_URL}/officer/login", params={"password": password}, timeout=60)
                if r.json().get("authenticated"):
                    st.session_state["officer_authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
            except Exception as e:
                st.error(f"Could not reach the server. ({e})")
    render_footer()
    return False


PRIORITY_RGB = {
    "Critical": [185, 28, 28],
    "High": [217, 119, 6],
    "Medium": [37, 99, 235],
    "Low": [107, 114, 128],
}


def render_map():
    try:
        r = requests.get(f"{API_URL}/officer/map-zones", timeout=40)
        zones = r.json()["zones"]
    except Exception as e:
        st.error(f"Could not load map data. ({e})")
        return

    if not zones:
        st.info("No complaint data to display on the map yet.")
        return

    df = pd.DataFrame(zones)
    df["color"] = df["priority"].map(PRIORITY_RGB).apply(
        lambda c: c if isinstance(c, list) else [107, 114, 128]
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["longitude", "latitude"],
        get_fill_color="color",
        get_radius="total_complaints",
        radius_scale=1,
        radius_min_pixels=10,
        radius_max_pixels=45,
        pickable=True,
        opacity=0.75,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
    )

    view_state = pdk.ViewState(latitude=13.04, longitude=80.23, zoom=10.5)
    tooltip = {"text": "{label}\nTotal reports: {total_complaints}\nDistinct problems: {problem_count}\nPriority: {priority}"}

    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
    ))
    st.caption("Marker size reflects total report volume at each locality cluster. Nearby localities are merged into one point.")


def render_accountability():
    try:
        r = requests.get(f"{API_URL}/officer/accountability", timeout=40)
        data = r.json()
    except Exception as e:
        st.error(f"Could not load accountability data. ({e})")
        return

    rename_map = {
        "name": "Name",
        "completed_jobs": "Completed Jobs",
        "durable_jobs": "Durable Jobs",
        "durability_rate": "Durability Rate (%)",
        "status": "Status",
        "predicted_failure_risk": "Risk Predictor (%)",
    }

    st.markdown("#### Departmental Accountability")
    dept_df = pd.DataFrame(data["by_department"])
    if dept_df.empty:
        st.caption("No completed intervention records available.")
    else:
        dept_df = dept_df.rename(columns={"name": "Department", **{k: v for k, v in rename_map.items() if k != "name"}})
        st.dataframe(dept_df, width="stretch", hide_index=True)

    st.markdown("#### Contractor Accountability")
    contractor_df = pd.DataFrame(data["by_contractor"])
    if contractor_df.empty:
        st.caption("No completed intervention records available.")
    else:
        contractor_df = contractor_df.rename(columns={"name": "Contractor", **{k: v for k, v in rename_map.items() if k != "name"}})
        st.dataframe(contractor_df, width="stretch", hide_index=True)


def render_cluster_card(cluster):
    header_cols = st.columns([3, 1])
    with header_cols[0]:
        st.markdown(f"### {cluster['zone_label']} — {cluster['damage_type_label']}")
        if len(cluster.get("member_locations", [])) > 1:
            st.caption("Includes reports from: " + ", ".join(cluster["member_locations"]))
    with header_cols[1]:
        st.markdown(priority_badge(cluster["priority"]), unsafe_allow_html=True)
        st.caption(f"Priority score: {cluster['priority_score']}")

    body_cols = st.columns([1, 2])
    with body_cols[0]:
        photo_path = cluster.get("representative_photo")
        if photo_path:
            filename = os.path.basename(photo_path)
            st.image(f"{API_URL}/photo/{filename}", width="stretch")
        else:
            st.markdown(
                "<div style='background:#f1f5f9;border:1px dashed #cbd5e1;"
                "border-radius:8px;padding:36px 8px;text-align:center;color:#64748b;'>"
                "No photo submitted yet</div>",
                unsafe_allow_html=True,
            )

    with body_cols[1]:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Reports", cluster["complaint_count"])
        m2.metric("Open", cluster["open_count"])
        m3.metric("Last 7 Days", cluster["reports_last_7_days"])
        m4.metric("Last 30 Days", cluster["reports_last_30_days"])

        st.caption(
            f"Worst reported severity: **{cluster['worst_severity']}** · "
            f"Safety risk: **{cluster['worst_safety_risk']}** · "
            f"Traffic impact: **{cluster['worst_traffic_impact']}**"
        )
        if cluster["any_accident_reported"]:
            st.caption(":red[An accident has been reported at this location.]")
        if cluster["any_emergency_route"]:
            st.caption(":orange[This location is on an emergency access route.]")

        if cluster.get("first_reported") and cluster.get("last_reported"):
            st.caption(
                f"First reported {cluster['first_reported'][:10]} · "
                f"Most recent report {cluster['last_reported'][:10]}"
            )

        if cluster.get("escalation"):
            esc = cluster["escalation"]
            st.success(f"Escalated to {esc['escalated_to']} on {esc['escalated_at']}.")

    with st.expander("View individual complaints and take action"):
        cache_key = f"detail_cache_{cluster['cluster_id']}"

        if cache_key not in st.session_state:
            if st.button("Load details", key=f"load_{cluster['cluster_id']}"):
                try:
                    r = requests.get(
                        f"{API_URL}/officer/cluster-detail",
                        params={"cluster_id": cluster["cluster_id"]},
                        timeout=40,
                    )
                    st.session_state[cache_key] = r.json()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not load details. ({e})")
            else:
                st.caption("Click \"Load details\" to view complaints, related road work, and escalation options.")

        if cache_key in st.session_state:
            detail = st.session_state[cache_key]
            tab1, tab2, tab3 = st.tabs(["Complaints", "Related Road Work", "Escalate"])

            with tab1:
                complaints_df = pd.DataFrame(detail["complaints"])
                if complaints_df.empty:
                    st.caption("No complaints found.")
                else:
                    edited = st.data_editor(
                        complaints_df,
                        width="stretch",
                        hide_index=True,
                        disabled=[c for c in complaints_df.columns if c != "status"],
                        column_config={
                            "status": st.column_config.SelectboxColumn(
                                "status", options=["Open", "In Progress", "Resolved"]
                            )
                        },
                        key=f"complaints_editor_{cluster['cluster_id']}",
                    )
                    if st.button("Save status changes", key=f"save_status_{cluster['cluster_id']}"):
                        changes = 0
                        for i in range(len(complaints_df)):
                            old_status = complaints_df.iloc[i]["status"]
                            new_status = edited.iloc[i]["status"]
                            if old_status != new_status:
                                requests.post(
                                    f"{API_URL}/officer/update-status",
                                    data={
                                        "complaint_id": complaints_df.iloc[i]["complaint_id"],
                                        "status": new_status,
                                    },
                                    timeout=40,
                                )
                                changes += 1
                        if changes:
                            st.success(f"Updated {changes} complaint(s).")
                            del st.session_state[cache_key]
                            st.rerun()
                        else:
                            st.info("No changes to save.")

            with tab2:
                related = detail["related_work"]
                if not related:
                    st.caption("No recorded road work found for this location.")
                else:
                    related_df = pd.DataFrame(related)
                    edited_related = st.data_editor(
                        related_df,
                        width="stretch",
                        hide_index=True,
                        disabled=[c for c in related_df.columns if c != "restoration_completed"],
                        column_config={
                            "restoration_completed": st.column_config.SelectboxColumn(
                                "restoration_completed", options=["Yes", "No"]
                            )
                        },
                        key=f"related_editor_{cluster['cluster_id']}",
                    )
                    if st.button("Save restoration changes", key=f"save_restoration_{cluster['cluster_id']}"):
                        changes = 0
                        for i in range(len(related_df)):
                            old_val = related_df.iloc[i]["restoration_completed"]
                            new_val = edited_related.iloc[i]["restoration_completed"]
                            if old_val != new_val:
                                requests.post(
                                    f"{API_URL}/officer/update-restoration",
                                    data={
                                        "event_id": related_df.iloc[i]["event_id"],
                                        "restoration_completed": new_val,
                                    },
                                    timeout=40,
                                )
                                changes += 1
                        if changes:
                            st.success(f"Updated {changes} record(s).")
                            del st.session_state[cache_key]
                            st.rerun()
                        else:
                            st.info("No changes to save.")

            with tab3:
                st.caption(
                    "Escalating this problem records it as forwarded to a higher authority "
                    "for action. This is an internal status update within this system."
                )
                with st.form(f"escalate_{cluster['cluster_id']}"):
                    target = st.selectbox("Escalate to", options=ESCALATION_TARGETS)
                    officer_name = st.text_input("Officer name", placeholder="Your name")
                    note = st.text_area("Note", placeholder="Add context for the receiving authority (optional)")
                    confirm = st.form_submit_button("Escalate this problem")
                    if confirm:
                        requests.post(
                            f"{API_URL}/officer/escalate",
                            data={
                                "cluster_id": cluster["cluster_id"],
                                "escalated_to": target,
                                "officer_name": officer_name,
                                "note": note,
                            },
                            timeout=40,
                        )
                        st.success(f"Marked as escalated to {target}.")
                        st.rerun()


def render_risk_predictor():
    try:
        r = requests.get(f"{API_URL}/officer/repair-risk-options", timeout=40)
        options = r.json()
    except Exception as e:
        st.error(f"Could not load form options. ({e})")
        return

    if not options.get("departments"):
        st.caption("No historical repair data available yet to base predictions on.")
        return

    st.markdown("#### Predict Repair Failure Risk")
    st.caption("Estimate the likelihood a planned repair will fail (receive a follow-up complaint) before work begins, based on a model trained on historical outcomes.")

    with st.form("risk_predictor_form"):
        col1, col2 = st.columns(2)
        with col1:
            department = st.selectbox("Department", options=options["departments"])
            event_type = st.selectbox("Work Type", options=options["event_types"])
        with col2:
            contractor = st.selectbox("Contractor", options=options["contractors"])
            road_cutting = st.selectbox("Involves Road Cutting", options=["Yes", "No"])
        month = st.selectbox("Planned Month", options=list(range(1, 13)), format_func=lambda m: [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ][m - 1])

        predict = st.form_submit_button("Predict Risk")
        if predict:
            try:
                r = requests.get(
                    f"{API_URL}/officer/predict-repair-risk",
                    params={
                        "department": department,
                        "contractor": contractor,
                        "event_type": event_type,
                        "road_cutting": road_cutting,
                        "month": month,
                    },
                    timeout=40,
                )
                result = r.json()
            except Exception as e:
                st.error(f"Could not reach the server. ({e})")
                result = None

            if result:
                risk = result.get("predicted_failure_risk")
                if risk is None:
                    st.info(result.get("note", "Not enough data to generate a prediction."))
                elif risk >= 30:
                    st.error(f"Predicted failure risk: **{risk}%** — High risk of a follow-up complaint.")
                elif risk >= 15:
                    st.warning(f"Predicted failure risk: **{risk}%** — Moderate risk.")
                else:
                    st.success(f"Predicted failure risk: **{risk}%** — Low risk.")


def main():
    if not check_password():
        return

    st.markdown(
        "<div class='gcc-header'><h2 style='margin-bottom:0.15rem;'>GCC Officer Dashboard</h2>"
        "<p style='color:#60716d;margin:0;'>Road Infrastructure Complaint Management</p></div>",
        unsafe_allow_html=True,
    )

    try:
        summary = requests.get(f"{API_URL}/officer/summary", timeout=40).json()
        clusters_response = requests.get(f"{API_URL}/officer/clusters", timeout=40).json()
    except Exception as e:
        st.error(f"Could not reach the server. ({e})")
        return

    clusters = clusters_response["clusters"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Complaints", summary["total_complaints"])
    m2.metric("Active Problem Locations", summary["active_locations"])
    m3.metric("Critical Priority", summary["critical_count"])
    m4.metric("High Priority", summary["high_count"])

    st.divider()

    tab_map, tab_list, tab_accountability, tab_predictor = st.tabs(
        ["Priority Map", "Problem List", "Accountability", "Risk Predictor"]
    )

    with tab_map:
        render_map()

    with tab_list:
        st.markdown("#### Complaint Registry")
        st.caption("Repeated complaints about the same issue and location are grouped together.")

        locations = sorted(set(c["zone_label"] for c in clusters))
        filter_cols = st.columns(4)
        with filter_cols[0]:
            location_filter = st.selectbox("Locality", options=["All"] + locations)
        with filter_cols[1]:
            priority_filter = st.selectbox("Priority", options=["All", "Critical", "High", "Medium", "Low"])
        with filter_cols[2]:
            status_filter = st.selectbox("Status", options=["All", "Has Open Reports", "Fully Resolved"])
        with filter_cols[3]:
            min_count = st.number_input("Minimum reports", min_value=1, value=1, step=1)

        filtered = clusters
        if location_filter != "All":
            filtered = [c for c in filtered if c["zone_label"] == location_filter]
        if priority_filter != "All":
            filtered = [c for c in filtered if c["priority"] == priority_filter]
        if status_filter == "Has Open Reports":
            filtered = [c for c in filtered if c["open_count"] > 0]
        elif status_filter == "Fully Resolved":
            filtered = [c for c in filtered if c["open_count"] == 0]
        filtered = [c for c in filtered if c["complaint_count"] >= min_count]

        st.caption(f"Showing {len(filtered)} of {len(clusters)} problem locations")

        if not filtered:
            st.info("No problem locations match the selected filters.")
        else:
            page_size = 30
            show_count = st.session_state.get("problem_list_show_count", page_size)
            for cluster in filtered[:show_count]:
                render_cluster_card(cluster)
                st.markdown("---")
            if show_count < len(filtered):
                if st.button(f"Show {min(page_size, len(filtered) - show_count)} more"):
                    st.session_state["problem_list_show_count"] = show_count + page_size
                    st.rerun()

    with tab_accountability:
        render_accountability()

    with tab_predictor:
        render_risk_predictor()

    render_footer()


if __name__ == "__main__":
    main()
