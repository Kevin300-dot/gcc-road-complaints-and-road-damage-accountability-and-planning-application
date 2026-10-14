"""
Cost, beneficiary and scalability estimates.

Every number in the output is tagged with where it comes from:

  measured    computed from the real 48-complaint field survey or the boundary file
  simulated   computed from the simulated repair history (demo only)
  assumption  an editable input with a PLACEHOLDER default. These are not facts. Replace
              them with verified figures (ward population, GCC payroll rates, real repair
              costs, a hosting quote) before quoting any total in a submission.

The arithmetic is deliberately simple and written out in the result so a judge can follow it.
"""
import pandas as pd

import area_config

# name: (default, unit, label)  -- all PLACEHOLDERS: replace with verified figures
ASSUMPTIONS = {
    "population_served": (10000, "people", "Residents in the area served (replace with ward / census figure)"),
    "monthly_complaints": (120, "reports/month", "Expected citizen reports per month once the portal is live"),
    "triage_minutes_manual": (12, "min/report", "Officer time to read, locate, de-duplicate and route one report today"),
    "triage_minutes_system": (3, "min/report", "Officer time per report with hotspot grouping and prioritisation"),
    "officer_cost_per_hour": (300, "INR/hour", "Loaded cost of an officer hour"),
    "platform_monthly_cost": (3000, "INR/month", "Hosting for one ward (cloud server and storage)"),
    "setup_cost_one_time": (20000, "INR", "One-time setup per ward (boundary tracing, data import, training)"),
    "repeat_repair_reduction_pct": (10, "%", "Share of failed repairs avoided if contractors are held to durability data"),
    "wards_in_scope": (1, "wards", "Number of wards to scale to"),
}


def default_assumptions() -> dict:
    return {k: v[0] for k, v in ASSUMPTIONS.items()}


def _share(series_bool) -> float:
    return round(float(series_bool.mean()) * 100, 1) if len(series_bool) else 0.0


def compute_impact(real_complaints: pd.DataFrame, clusters: pd.DataFrame, events: pd.DataFrame,
                   accountability_summary: dict, assumptions: dict = None) -> dict:
    a = default_assumptions()
    if assumptions:
        a.update({k: float(v) for k, v in assumptions.items() if k in a and v is not None})

    n = len(real_complaints)
    area = area_config.area_km2()

    # ---- measured from the real survey and boundary
    measured = {
        "area_km2": {"value": round(area, 3), "source": "measured", "note": "from the traced boundary"},
        "reports_surveyed": {"value": n, "source": "measured"},
        "hotspots": {"value": int(len(clusters)), "source": "measured", "note": f"reports grouped within {35:.0f} m on the same road"},
        "critical_or_high_hotspots": {"value": int(clusters["priority"].isin(["Critical", "High"]).sum()) if len(clusters) else 0, "source": "measured"},
        "reports_per_km2": {"value": round(n / area, 1) if area else None, "source": "measured", "note": "sample of damaged spots, not a full road survey"},
        "share_on_emergency_routes_pct": {"value": _share(real_complaints["emergency_route"] == "Yes"), "source": "measured"},
        "share_two_wheeler_risk_pct": {"value": _share(real_complaints["two_wheeler_risk"] == "Yes"), "source": "measured"},
        "share_pedestrian_risk_pct": {"value": _share(real_complaints["pedestrian_risk"] == "Yes"), "source": "measured"},
        "share_high_or_severe_traffic_impact_pct": {"value": _share(real_complaints["traffic_impact"].isin(["High", "Severe"])), "source": "measured"},
        "share_restoration_related_pct": {
            "value": _share(real_complaints["damage_type"].isin(["Poor_Restoration", "Unrestored_Road_Cut"])),
            "source": "measured", "note": "poorly restored or unrestored road cuts",
        },
    }

    # ---- simulated repair economics
    sim = {}
    if events is not None and not events.empty:
        label = "simulated" if (events.get("data_source", pd.Series(["simulated"])).astype(str).str.contains("simulated").any()) else "measured"
        span_years = max((events["completion_date_parsed"].max() - events["start_date_parsed"].min()).days / 365.25, 0.5)
        sim["median_repair_cost_inr"] = {"value": int(events["estimated_cost"].median()), "source": label}
        sim["repair_jobs_per_year_in_area"] = {"value": round(len(events) / span_years, 1), "source": label}
    overall = accountability_summary.get("overall_durability_rate") if accountability_summary else None
    if overall is not None:
        sim["repair_failure_rate_pct"] = {"value": round(100 - overall, 1), "source": "simulated",
                                         "note": f"repairs with a repair-related complaint within {accountability_summary.get('window_days')} days"}

    # ---- arithmetic
    results = {}
    hours_saved = a["monthly_complaints"] * (a["triage_minutes_manual"] - a["triage_minutes_system"]) / 60.0
    results["officer_hours_saved_per_month"] = {
        "value": round(hours_saved, 1), "source": "assumption",
        "formula": f"{a['monthly_complaints']:.0f} reports x ({a['triage_minutes_manual']:.0f} - {a['triage_minutes_system']:.0f}) min / 60",
    }
    triage_value_year = hours_saved * a["officer_cost_per_hour"] * 12
    results["triage_time_value_per_year_inr"] = {"value": round(triage_value_year), "source": "assumption",
                                                 "formula": "hours saved x cost per hour x 12"}

    # Headline benefit counts ONLY officer triage time, the most defensible term. The repeat-repair saving
    # depends on simulated repair costs and volumes, so it is reported separately as illustrative and is
    # NOT included in net benefit, payback or the scaling table.
    if {"median_repair_cost_inr", "repair_jobs_per_year_in_area", "repair_failure_rate_pct"} <= sim.keys():
        avoided_jobs = (sim["repair_jobs_per_year_in_area"]["value"] * sim["repair_failure_rate_pct"]["value"] / 100.0
                        * a["repeat_repair_reduction_pct"] / 100.0)
        results["repeat_repairs_avoided_per_year"] = {
            "value": round(avoided_jobs, 1), "source": "simulated+assumption",
            "formula": "repair jobs/yr x failure rate x reduction % (illustrative; not in net benefit)",
        }
        results["repeat_repair_cost_avoided_per_year_inr"] = {
            "value": round(avoided_jobs * sim["median_repair_cost_inr"]["value"]), "source": "simulated+assumption",
            "formula": "avoided repeat repairs x median repair cost (illustrative; not in net benefit)",
        }

    cost_year_one_ward = a["platform_monthly_cost"] * 12
    benefit_year_one_ward = triage_value_year
    results["running_cost_per_year_inr"] = {"value": round(cost_year_one_ward), "source": "assumption"}
    results["net_benefit_per_year_inr"] = {"value": round(benefit_year_one_ward - cost_year_one_ward), "source": "assumption",
                                           "formula": "triage time value - running cost (excludes repair savings)"}
    if benefit_year_one_ward > cost_year_one_ward:
        monthly_net = (benefit_year_one_ward - cost_year_one_ward) / 12
        results["payback_months"] = {"value": round(a["setup_cost_one_time"] / monthly_net, 1), "source": "assumption",
                                     "formula": "one-time setup / monthly net benefit"}
    results["cost_per_report_handled_inr"] = {
        "value": round(cost_year_one_ward / max(a["monthly_complaints"] * 12, 1), 1), "source": "assumption",
        "formula": "running cost per year / reports per year",
    }

    beneficiaries = {
        "residents": {"value": int(a["population_served"]), "source": "assumption"},
        "two_wheeler_riders_at_risk_reports": {"value": measured["share_two_wheeler_risk_pct"]["value"], "source": "measured", "unit": "% of reports"},
        "pedestrians_at_risk_reports": {"value": measured["share_pedestrian_risk_pct"]["value"], "source": "measured", "unit": "% of reports"},
        "emergency_route_reports": {"value": measured["share_on_emergency_routes_pct"]["value"], "source": "measured", "unit": "% of reports"},
        "cost_per_resident_per_year_inr": {"value": round(cost_year_one_ward / max(a["population_served"], 1), 2), "source": "assumption"},
    }

    # ---- scalability: the software and data model are ward-agnostic; a new ward needs a boundary + its own complaints
    scaling = []
    for w in sorted({1, 10, 50, 200, int(a["wards_in_scope"])}):
        scaling.append({
            "wards": w,
            "running_cost_per_year_inr": round(cost_year_one_ward * w),
            "setup_cost_inr": round(a["setup_cost_one_time"] * w),
            "benefit_per_year_inr": round(benefit_year_one_ward * w),  # triage time only
            "net_per_year_inr": round((benefit_year_one_ward - cost_year_one_ward) * w),
        })

    return {
        "measured": measured,
        "simulated": sim,
        "assumptions": {k: {"value": a[k], "unit": ASSUMPTIONS[k][1], "label": ASSUMPTIONS[k][2], "source": "assumption"} for k in ASSUMPTIONS},
        "results": results,
        "beneficiaries": beneficiaries,
        "scaling": scaling,
        "scalability_notes": [
            "Per-ward requirements: one boundary file (a traced KML), complaint data in the same CSV format, optional repair history.",
            "No code change is needed to onboard another ward: replace data/<ward>_boundary.kml and set AREA_NAME in area_config.py.",
            "Costs here scale linearly per ward as a conservative estimate; a shared city-wide deployment would cost less per ward.",
        ],
        "warning": "Values marked 'assumption' are placeholders, not facts. Replace them with verified figures before quoting totals.",
    }
