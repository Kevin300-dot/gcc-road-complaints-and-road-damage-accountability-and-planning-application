import os

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

import maplib
from portal_ui import apply_theme, render_header, render_footer, section_heading, render_risk_result, render_accountability_graph, render_impact_graph, render_scaling_graph

API_URL = os.environ.get("GCC_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="GCC | Officer Operations Portal — Kandanchavadi",
    page_icon="🛠️",
    layout="wide",
)

apply_theme("officer")



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

SIMULATED_NOTE = (
    "**Simulated demo data.** The 48 field-survey complaints are real, but they contain no repair history. "
    "This section runs on a clearly labelled simulated repair history so the feature can be demonstrated; "
    "with real GCC repair records the same code produces real results."
)


def priority_badge(priority: str) -> str:
    color = PRIORITY_COLORS.get(priority, "#4b5563")
    return (
        f"<span style='background-color:{color};color:white;padding:2px 10px;"
        f"border-radius:12px;font-size:0.8rem;font-weight:600'>{priority}</span>"
    )


def check_password():
    if st.session_state.get("officer_authenticated"):
        return True

    render_header("officer")
    st.markdown("### Officer sign in")
    st.caption("Authorized personnel only")
    with st.form("officer_login"):
        password = st.text_input("Officer Password", type="password")
        submitted = st.form_submit_button("Log In")
        if submitted:
            try:
                with st.spinner("Connecting to server — this can take up to a minute if it has been idle..."):
                    r = requests.post(f"{API_URL}/officer/login", data={"password": password}, timeout=60)
                if r.json().get("authenticated"):
                    st.session_state["officer_authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
            except Exception as e:
                st.error(f"Could not reach the server. ({e})")
    render_footer()
    return False


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_photo(filename: str):
    """Photo bytes from the API, or None if the file is not available."""
    try:
        r = requests.get(f"{API_URL}/photo/{filename}", timeout=20)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def render_map():
    try:
        r = requests.get(f"{API_URL}/officer/map-data", timeout=40)
        data = r.json()
    except Exception as e:
        st.error(f"Could not load map data. ({e})")
        return

    if not data["complaints"]:
        st.info("No complaint data to display on the map yet.")

    html = maplib.build_map_html(
        boundary_geojson=data["boundary"],
        complaints=data["complaints"],
        hotspots=data["hotspots"],
        photo_base_url=API_URL,
        height_px=640,
    )
    components.html(html, height=660, scrolling=False)
    st.caption(
        "Every dot is a real field-survey or citizen report at its GPS position, coloured by the priority of its hotspot. "
        "Dashed rings outline hotspots (reports on the same road within 35 m of each other). "
        "The red line is the Kandanchavadi boundary; roads along it count as inside. Click a dot for details."
    )


def render_accountability():
    try:
        r = requests.get(f"{API_URL}/officer/accountability", timeout=40)
        data = r.json()
    except Exception as e:
        st.error(f"Could not load accountability data. ({e})")
        return

    if data.get("data_label") == "simulated":
        st.info(SIMULATED_NOTE)

    summary = data.get("summary", {})
    if summary.get("judged_jobs"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Repairs judged", summary["judged_jobs"])
        c2.metric("Overall durability", f"{summary['overall_durability_rate']}%")
        c3.metric("Still under observation", summary["under_observation"])
        c4.metric("Restoration pending", summary["restoration_pending"])
        st.caption(
            f"A repair is *durable* if no repair-related complaint was filed on the same road segment within "
            f"{summary['window_days']} days of completion. Repairs whose window is not over yet are not judged. "
            "Status compares each group with the overall rate (Good Standing: at or above it; Watch: up to 10 points below; "
            "Needs Review: more than 10 points below). The 95% interval shows how uncertain a rate is when a group has few jobs."
        )

    render_accountability_graph(data, summary)

    rename_map = {
        "completed_jobs": "Judged Jobs",
        "durable_jobs": "Durable Jobs",
        "durability_rate": "Durability Rate (%)",
        "ci_low": "95% Low",
        "ci_high": "95% High",
        "restoration_pending": "Restoration Pending",
        "under_observation": "Under Observation",
        "status": "Status",
        "predicted_failure_risk": "Model Risk (%)",
    }

    st.markdown("#### Departmental Accountability")
    dept_df = pd.DataFrame(data["by_department"])
    if dept_df.empty:
        st.caption("No completed intervention records available.")
    else:
        dept_df = dept_df.rename(columns={"name": "Department", **rename_map})
        st.dataframe(dept_df, width="stretch", hide_index=True)

    st.markdown("#### Contractor Accountability")
    contractor_df = pd.DataFrame(data["by_contractor"])
    if contractor_df.empty:
        st.caption("No completed intervention records available.")
    else:
        contractor_df = contractor_df.rename(columns={"name": "Contractor", **rename_map})
        st.dataframe(contractor_df, width="stretch", hide_index=True)


def render_cluster_card(cluster):
    header_cols = st.columns([3, 1])
    with header_cols[0]:
        st.markdown(f"### {cluster['zone_label']} — {cluster['damage_type_label']}")
        mix = cluster.get("damage_mix") or {}
        if len(mix) > 1:
            st.caption("Reports here: " + ", ".join(f"{k} ×{v}" for k, v in mix.items()))
        if cluster.get("radius_m"):
            st.caption(f"Hotspot spans about {cluster['radius_m']:.0f} m around its centre.")
    with header_cols[1]:
        st.markdown(priority_badge(cluster["priority"]), unsafe_allow_html=True)
        st.caption(f"Priority score: {cluster['priority_score']}")

    body_cols = st.columns([1, 2])
    with body_cols[0]:
        photo_path = cluster.get("representative_photo")
        photo_bytes = _fetch_photo(os.path.basename(photo_path)) if photo_path else None
        if photo_bytes:
            st.image(photo_bytes, width="stretch")
        else:
            st.markdown(
                "<div class='gcc-photo-empty'>"
                + ("Photo not available on this server" if photo_path else "No photo submitted yet")
                + "</div>",
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
                    photo_rows = [c for c in detail["complaints"] if c.get("photo")]
                    if photo_rows:
                        st.markdown("**Photos**")
                        for start in range(0, len(photo_rows), 4):
                            cols = st.columns(4)
                            for col, c in zip(cols, photo_rows[start:start + 4]):
                                img = _fetch_photo(c["photo"])
                                if img:
                                    col.image(img, caption=f"{c['complaint_id']} \u00b7 {c['severity']}", width="stretch")
                                else:
                                    col.caption(f"{c['complaint_id']}: photo file not found in photo_path/")
                    complaints_df = complaints_df.drop(columns=["photo"], errors="ignore")
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
                    if detail.get("related_work_is_simulated"):
                        st.warning("These repair records are **simulated demo data**, not real GCC works.")
                    related_df = pd.DataFrame(related).drop(columns=["data_source"], errors="ignore")
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
        report = requests.get(f"{API_URL}/officer/model-report", timeout=40).json()
    except Exception as e:
        st.error(f"Could not load form options. ({e})")
        return

    if not options.get("departments"):
        st.caption("No historical repair data available yet to base predictions on.")
        return

    st.markdown("#### Repair Risk Assessment")
    if report.get("data_label") == "simulated":
        st.info(SIMULATED_NOTE)
    st.caption(
        "Estimates the chance that a planned repair will draw a repair-related complaint on the same road "
        f"within {report.get('window_days', 60)} days of completion, based on how comparable past repairs turned out."
    )

    if report.get("available"):
        with st.expander("Model reliability"):
            auc = report.get("cv_auc")
            ci = report.get("cv_auc_ci95")
            c1, c2, c3 = st.columns(3)
            c1.metric("Repairs used", report["n_jobs"])
            c2.metric("Share that failed", f"{report['failure_rate'] * 100:.0f}%")
            c3.metric("Cross-validated AUC", f"{auc:.2f}" if auc is not None else "n/a")
            if ci:
                st.caption(f"95% bootstrap interval for the AUC: {ci[0]:.2f} to {ci[1]:.2f}. AUC 0.50 is a coin flip; 1.00 is perfect.")
            if report.get("time_split_auc") is not None:
                st.caption(f"Time-ordered check ({report['time_split_note']}): AUC {report['time_split_auc']:.2f}.")
            st.caption(f"Method: {report['cv_method']}. Month of year is deliberately **not** used (it would only reveal how much follow-up time a repair has had).")
            st.caption(report["interpretation"])
            if report.get("drivers"):
                st.markdown("**Strongest factors in the model** (odds ratio; above 1 raises failure risk)")
                st.dataframe(pd.DataFrame(report["drivers"]).rename(columns={"factor": "Factor", "odds_ratio": "Odds ratio"}),
                             width="stretch", hide_index=True)

    with st.form("risk_predictor_form"):
        col1, col2 = st.columns(2)
        with col1:
            department = st.selectbox("Department", options=options["departments"])
            event_type = st.selectbox("Work Type", options=options["event_types"])
            duration_days = st.number_input("Planned duration (days)", min_value=1, max_value=60, value=5, step=1)
        with col2:
            contractor = st.selectbox("Contractor", options=options["contractors"])
            road_cutting = st.selectbox("Involves Road Cutting", options=["Yes", "No"])

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
                        "duration_days": duration_days,
                    },
                    timeout=40,
                )
                result = r.json()
            except Exception as e:
                st.error(f"Could not reach the server. ({e})")
                result = None

            if result:
                risk = result.get("predicted_failure_risk")
                base = result.get("base_rate_pct")
                if risk is None:
                    st.info(result.get("note", "Not enough data to generate a prediction."))
                else:
                    render_risk_result(result, {
                        "Department": department, "Contractor": contractor,
                        "Work type": event_type, "Road cutting": road_cutting,
                        "Duration": f"{duration_days} days",
                    }, report)


def _inr(v):
    return f"₹{v:,.0f}" if isinstance(v, (int, float)) else "n/a"


def render_impact():
    st.markdown("#### Impact, Cost and Scalability")
    st.warning(
        "Figures tagged **assumption** are placeholders you can edit below. They are not facts. "
        "Replace them with verified numbers (ward population, officer cost, hosting quote) before quoting totals."
    )

    defaults_resp = None
    try:
        defaults_resp = requests.get(f"{API_URL}/officer/impact", timeout=40).json()
    except Exception as e:
        st.error(f"Could not load impact data. ({e})")
        return

    with st.expander("Edit assumptions", expanded=False):
        values = {}
        cols = st.columns(3)
        for i, (key, meta) in enumerate(defaults_resp["assumptions"].items()):
            with cols[i % 3]:
                values[key] = st.number_input(f"{meta['label']} ({meta['unit']})", min_value=0.0,
                                              value=float(meta["value"]), key=f"impact_{key}")
    try:
        data = requests.get(f"{API_URL}/officer/impact", params=values, timeout=40).json()
    except Exception as e:
        st.error(f"Could not recompute. ({e})")
        return

    m = data["measured"]
    st.markdown("**Measured from the real field survey**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Area", f"{m['area_km2']['value']} km²")
    c2.metric("Reports surveyed", m["reports_surveyed"]["value"])
    c3.metric("Hotspots", m["hotspots"]["value"])
    c4.metric("Critical / High hotspots", m["critical_or_high_hotspots"]["value"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("On emergency routes", f"{m['share_on_emergency_routes_pct']['value']}%")
    c2.metric("Two-wheeler risk", f"{m['share_two_wheeler_risk_pct']['value']}%")
    c3.metric("Pedestrian risk", f"{m['share_pedestrian_risk_pct']['value']}%")
    c4.metric("Poor / unrestored road cuts", f"{m['share_restoration_related_pct']['value']}%")
    st.caption("Shares are of surveyed reports. The survey sampled damaged spots, so these are not percentages of all roads.")

    st.markdown("**Estimated value (arithmetic shown; depends on the assumptions above)**")
    render_impact_graph(data)
    res = data["results"]
    rows = []
    labels = {
        "officer_hours_saved_per_month": "Officer hours saved per month",
        "triage_time_value_per_year_inr": "Value of triage time saved per year (₹)",
        "running_cost_per_year_inr": "Running cost per year (₹)",
        "net_benefit_per_year_inr": "Net benefit per year (₹, triage time only)",
        "payback_months": "Payback on setup cost (months)",
        "cost_per_report_handled_inr": "Cost per report handled (₹)",
    }
    for key, label in labels.items():
        if key in res:
            rows.append({"Measure": label, "Value": res[key]["value"], "How": res[key].get("formula", ""), "Basis": res[key]["source"]})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    if "repeat_repair_cost_avoided_per_year_inr" in res:
        st.caption(
            f"Illustrative extra, not counted above: about {res['repeat_repairs_avoided_per_year']['value']} repeat repairs avoided per year "
            f"(≈ ₹{res['repeat_repair_cost_avoided_per_year_inr']['value']:,} at the simulated median repair cost). "
            "This depends on simulated repair volumes and costs, so replace them with real GCC records before quoting it."
        )

    st.markdown("**Who benefits**")
    b = data["beneficiaries"]
    st.caption(
        f"Residents served (assumption): {b['residents']['value']:,}. Cost per resident per year: ₹{b['cost_per_resident_per_year_inr']['value']}. "
        f"In the surveyed reports, {b['two_wheeler_riders_at_risk_reports']['value']}% involve two-wheeler risk, "
        f"{b['pedestrians_at_risk_reports']['value']}% pedestrian risk and {b['emergency_route_reports']['value']}% emergency routes."
    )

    st.markdown("**Scalability (linear per-ward estimate)**")
    render_scaling_graph(data)
    scale = pd.DataFrame(data["scaling"]).rename(columns={
        "wards": "Wards", "running_cost_per_year_inr": "Running cost / yr (₹)", "setup_cost_inr": "Setup (₹)",
        "benefit_per_year_inr": "Triage benefit / yr (₹)", "net_per_year_inr": "Net / yr (₹)",
    })
    st.dataframe(scale, width="stretch", hide_index=True)
    for note in data["scalability_notes"]:
        st.caption("• " + note)


def main():
    if not check_password():
        return

    render_header("officer")

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

    tab_map, tab_list, tab_accountability, tab_predictor, tab_impact = st.tabs(
        ["Priority Map", "Problem List", "Accountability", "Risk Predictor", "Impact & Cost"]
    )

    with tab_map:
        render_map()

    with tab_list:
        st.markdown("#### Complaint Registry")
        st.caption("Reports on the same road that lie within 35 m of each other are grouped into one hotspot. Reports are never merged or deleted.")

        roads = sorted(set(c["zone_label"] for c in clusters))
        filter_cols = st.columns(4)
        with filter_cols[0]:
            location_filter = st.selectbox("Road", options=["All"] + roads)
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

    with tab_impact:
        render_impact()

    render_footer()


if __name__ == "__main__":
    main()
