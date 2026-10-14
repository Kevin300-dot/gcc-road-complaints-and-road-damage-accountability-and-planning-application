"""Presentation-only styling shared by two independent Streamlit applications.

No API, authentication, state, data, or map logic belongs in this module.
"""
import streamlit as st
from html import escape
from pathlib import Path
import base64
import math

CSS = """
<style>
:root {
 --gcc-ink: #172b3a; --gcc-muted: #63727e; --gcc-brand: #126b61;
 --gcc-brand-hover: #0d544c; --gcc-paper: #ffffff; --gcc-canvas: #f3f6f8;
 --gcc-border: #dce4e9; --gcc-soft: #eaf4f1; --gcc-accent: #c29138;
 --gcc-shadow: 0 3px 14px rgb(23 43 58 / 4%);
 --gcc-focus: 0 0 0 3px rgb(18 107 97 / 18%);
}
html, body, [data-testid="stApp"] { font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif; color: var(--gcc-ink); }
.stApp, [data-testid="stAppViewContainer"] { background: var(--gcc-canvas); }
[data-testid="stHeader"] { background: var(--gcc-canvas); }
[data-testid="stMainBlockContainer"], .main .block-container { padding-top: 2.1rem; padding-bottom: 2rem; }
h1, h2, h3, h4 { color: var(--gcc-ink); font-weight: 650; letter-spacing: 0 !important; }
h1 { font-size: 2.25rem !important; line-height: 1.2 !important; padding-top: 0 !important; }
h2 { font-size: 1.75rem !important; } h3 { font-size: 1.22rem !important; } h4 { font-size: 1.1rem !important; }
p { line-height: 1.65; } a { color: var(--gcc-brand); }
.gcc-ribbon { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:11px 20px; background:var(--gcc-ink); color:var(--gcc-paper); border-top:3px solid var(--gcc-accent); font-size:0.75rem; line-height:1.5; }
.gcc-ribbon span { display:flex; align-items:center; gap:8px; }
.gcc-ribbon .gcc-pilot { color: var(--gcc-paper); opacity:0.8; }
.gcc-government-mark { width:14px; height:14px; }
.gcc-header { background:var(--gcc-paper); padding:30px 28px; border:1px solid var(--gcc-border); border-top:0; margin-bottom:1.1rem; }
.gcc-heading-row { display:flex; align-items:center; gap:20px; }
.gcc-symbol { width:60px; height:60px; flex-shrink:0; display:grid; place-items:center; background:var(--gcc-soft); border:1px solid var(--gcc-border); border-radius:50%; color:var(--gcc-brand); }
.gcc-symbol svg { width:32px; height:32px; }
.gcc-eyebrow { color:var(--gcc-brand); font-size:0.73rem; font-weight:700; text-transform:uppercase; margin-bottom:6px; }
.gcc-header h1, .gcc-header h2 { margin:0 !important; padding:0 !important; }
.gcc-header p { color:var(--gcc-muted); font-size:0.91rem; margin:8px 0 0; }
.gcc-section { display:flex; gap:12px; align-items:center; border-top:1px solid var(--gcc-border); padding:22px 0 8px; margin-top:10px; }
.gcc-section-number { background:var(--gcc-soft); color:var(--gcc-brand); border:1px solid var(--gcc-border); width:30px; height:30px; border-radius:4px; display:grid; place-items:center; font-size:0.8rem; font-weight:700; }
.gcc-section h3 { margin:0 !important; padding:0 !important; }
.gcc-footer { margin-top:36px; padding:22px 0 0; border-top:1px solid var(--gcc-border); display:flex; justify-content:space-between; gap:16px; color:var(--gcc-muted); font-size:0.74rem; line-height:1.6; }
.gcc-footer strong { display:block; color:var(--gcc-ink); font-weight:600; }
[data-testid="stWidgetLabel"] p { color:var(--gcc-ink); font-size:0.875rem; font-weight:600; }
[data-testid="stCaptionContainer"], .stCaption { color:var(--gcc-muted); font-size:0.8rem; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea { color:var(--gcc-ink); background:var(--gcc-paper); border-radius:5px; font-size:0.9rem; }
[data-testid="stTextInput"] [data-baseweb="input"], [data-testid="stTextArea"] [data-baseweb="textarea"], [data-testid="stSelectbox"] [data-baseweb="select"] > div, [data-testid="stNumberInput"] [data-baseweb="input"] { border-color:var(--gcc-border); background:var(--gcc-paper); border-radius:5px; min-height:44px; }
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within, [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within { border-color:var(--gcc-brand); box-shadow:var(--gcc-focus); }
.stButton > button, .stFormSubmitButton > button { min-height:44px; padding:0.6rem 1.2rem; border-radius:5px; background:var(--gcc-brand); color:var(--gcc-paper); border:1px solid var(--gcc-brand); font-weight:600; transition:background 150ms ease; }
.stButton > button:hover, .stFormSubmitButton > button:hover { background:var(--gcc-brand-hover); border-color:var(--gcc-brand-hover); color:var(--gcc-paper); }
.stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible { box-shadow:var(--gcc-focus); }
[data-testid="stForm"] { border:1px solid var(--gcc-border); border-radius:6px; padding:24px; background:var(--gcc-paper); box-shadow:var(--gcc-shadow); }
[data-testid="stExpander"] { border:1px solid var(--gcc-border); border-radius:6px; background:var(--gcc-paper); }
[data-testid="stMetric"] { background:var(--gcc-paper); border:1px solid var(--gcc-border); border-radius:6px; padding:18px 20px; border-top:3px solid var(--gcc-brand); }
[data-testid="stMetricLabel"] { color:var(--gcc-muted); } [data-testid="stMetricValue"] { color:var(--gcc-ink); font-weight:650; font-size:2rem; }
.stTabs [data-baseweb="tab-list"] { gap:6px; border-bottom:1px solid var(--gcc-border); }
.stTabs [data-baseweb="tab"] { min-height:49px; padding:0 18px; font-weight:600; color:var(--gcc-muted); font-size:0.88rem; }
.stTabs [aria-selected="true"] { color:var(--gcc-brand); background:var(--gcc-soft); }
.stTabs [data-baseweb="tab-highlight"] { background:var(--gcc-brand); height:3px; }
.stTabs [data-baseweb="tab-panel"] { padding-top:20px; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border:1px solid var(--gcc-border); border-radius:6px; overflow:hidden; }
[data-testid="stFileUploader"] section { background:var(--gcc-canvas); border:1px dashed var(--gcc-border); border-radius:5px; padding:20px; }
[data-testid="stAlert"] { border-radius:5px; }
[data-testid="stRadio"] [role="radiogroup"] { gap:18px; }
hr { border-color:var(--gcc-border); margin:18px 0; }
.gcc-photo-empty { background:var(--gcc-canvas); border:1px dashed var(--gcc-border); border-radius:6px; padding:36px 12px; text-align:center; color:var(--gcc-muted); }
@media (max-width:640px) {
 [data-testid="stMainBlockContainer"] { padding:1rem 1rem 2rem; }
 .gcc-ribbon { padding:10px 14px; font-size:0.68rem; } .gcc-ribbon .gcc-pilot { display:none; }
 .gcc-header { padding:24px 18px; } .gcc-heading-row { gap:12px; align-items:flex-start; }
 .gcc-symbol { width:44px; height:44px; } .gcc-symbol svg { width:25px; height:25px; }
 h1 { font-size:1.6rem !important; } .gcc-header h2 { font-size:1.45rem !important; }
 .gcc-header p { font-size:0.8rem; } .gcc-footer { flex-direction:column; gap:8px; }
 [data-testid="stForm"] { padding:18px 14px; } .stTabs [data-baseweb="tab"] { padding:0 12px; }
 [data-testid="stMetric"] { padding:14px; }
}
@media (prefers-reduced-motion:reduce) { *, *::before, *::after { transition:none !important; } }

:root { --gcc-blue:#2674a8; --gcc-warning:#a8640e; --gcc-danger:#b53c45; --gcc-ink:#193b37; --gcc-muted:#647873; --gcc-canvas:#f5f8f7; --gcc-accent:#d4a83f; }
[data-testid="stMainBlockContainer"] { padding-top:3.25rem; }
[data-testid="stCaptionContainer"] p { color:var(--gcc-muted) !important; opacity:1; }
.gcc-ribbon { padding:14px 26px; background:var(--gcc-paper); color:var(--gcc-ink); border-top:4px solid var(--gcc-brand); border-bottom:1px solid var(--gcc-border); font-weight:650; }
.gcc-ribbon .gcc-pilot { color:var(--gcc-muted); }
.gcc-header { position:relative; min-height:290px; padding:48px 40px; border:0; background-size:cover; background-position:center; display:flex; align-items:center; margin-bottom:24px; isolation:isolate; }
.gcc-header:before { content:""; position:absolute; inset:0; background:var(--gcc-paper); opacity:.66; z-index:-1; }
.gcc-header h1 { font-size:3rem !important; line-height:1.12 !important; max-width:700px; }
.gcc-header p { font-size:1.05rem; max-width:620px; }
.gcc-heading-row { gap:24px; }
.gcc-symbol { width:72px; height:72px; border-radius:6px; background:var(--gcc-brand); color:var(--gcc-paper); }
.gcc-symbol svg { width:40px; height:40px; }
.gcc-eyebrow { margin-bottom:14px; font-size:.78rem; }
.gcc-section { padding:30px 0 14px; margin-top:12px; }
.gcc-section h3 { font-size:1.45rem !important; }
.gcc-section-number { width:38px; height:38px; background:var(--gcc-brand); color:var(--gcc-paper); }
[data-testid="stForm"] { padding:28px 0; border:0; border-top:1px solid var(--gcc-border); border-bottom:1px solid var(--gcc-border); background:transparent; box-shadow:none; border-radius:0; }
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] { font-size:.98rem; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea { font-size:1rem; }
[data-testid="stSelectbox"] [data-baseweb="select"] > div, [data-testid="stNumberInput"] [data-baseweb="input"], [data-testid="stTextInput"] [data-baseweb="input"] { min-height:50px; }
.stButton > button, .stFormSubmitButton > button { min-height:50px; border-radius:6px; padding:12px 24px; }
[data-testid="stMetric"] { padding:24px; border:1px solid var(--gcc-border); border-top:0; border-left:4px solid var(--gcc-brand); min-height:122px; }
[data-testid="stMetricValue"] { font-size:2.65rem; }
.stTabs [data-baseweb="tab-list"] { background:var(--gcc-paper); gap:4px; padding:6px; }
.stTabs [data-baseweb="tab"] { min-height:56px; padding:0 22px; font-size:.96rem; }
.stTabs [aria-selected="true"] { background:var(--gcc-brand); color:var(--gcc-paper); border-radius:4px; }
.stTabs [data-baseweb="tab-highlight"] { display:none; }
.stTabs [data-baseweb="tab-panel"] { padding-top:30px; }
.gcc-result { border-top:3px solid var(--gcc-brand); border-bottom:1px solid var(--gcc-border); margin:24px 0; padding:26px 0; }
.gcc-result-top { display:flex; justify-content:space-between; gap:18px; align-items:start; }
.gcc-result h3 { font-size:1.5rem !important; margin:0; padding:0; }
.gcc-result-label { text-transform:uppercase; color:var(--gcc-brand); font-weight:700; font-size:.73rem; margin-bottom:8px; }
.gcc-result-sub { color:var(--gcc-muted); font-size:.88rem; margin:6px 0 0; }
.gcc-result-grid { display:grid; grid-template-columns:220px 1fr; gap:40px; align-items:center; margin:24px 0 16px; }
.gcc-donut { width:190px; height:190px; border-radius:50%; display:grid; place-items:center; background:conic-gradient(var(--gcc-brand) var(--gcc-fill),var(--gcc-border) 0); }
.gcc-donut-inner { width:152px; height:152px; border-radius:50%; background:var(--gcc-canvas); display:flex; flex-direction:column; align-items:center; justify-content:center; }
.gcc-result-value { font-size:2.8rem; font-weight:700; line-height:1.2; color:var(--gcc-ink); }
.gcc-result-unit { color:var(--gcc-muted); font-size:.8rem; }
.gcc-chart-row { margin:18px 0; }
.gcc-chart-caption { display:flex; justify-content:space-between; gap:16px; margin-bottom:8px; font-size:.9rem; }
.gcc-track { height:12px; background:var(--gcc-border); border-radius:3px; overflow:hidden; }
.gcc-bar { height:100%; width:var(--gcc-fill); background:var(--gcc-brand); border-radius:3px; }
.gcc-bar-baseline { background:var(--gcc-blue); }
.gcc-graph-note { color:var(--gcc-muted); font-size:.78rem; margin-top:12px; }
.gcc-inputs { display:flex; flex-wrap:wrap; gap:16px; padding-top:16px; border-top:1px solid var(--gcc-border); font-size:.82rem; }
.gcc-inputs span { color:var(--gcc-muted); }
.gcc-inputs strong { display:block; color:var(--gcc-ink); margin-top:3px; }
.gcc-chip { color:var(--gcc-brand); background:var(--gcc-soft); padding:7px 10px; font-size:.76rem; border-radius:4px; font-weight:650; }
.gcc-timeline { display:flex; align-items:center; gap:16px; margin:20px 0; }
.gcc-timeline-line { height:6px; flex:1; background:var(--gcc-border); position:relative; }
.gcc-timeline-line:after { content:""; position:absolute; inset:0; background:var(--gcc-brand); }
.gcc-time-end { text-align:right; }
.gcc-time-end strong { display:block; font-size:1.55rem; color:var(--gcc-ink); }
.gcc-stages { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:20px 0; }
.gcc-stage { padding:12px 0; border-top:3px solid var(--gcc-border); color:var(--gcc-muted); font-size:.9rem; }
.gcc-stage-active { border-color:var(--gcc-brand); color:var(--gcc-brand); font-weight:650; }
.gcc-summary-line { display:flex; gap:24px; flex-wrap:wrap; padding:14px 0; color:var(--gcc-muted); font-size:.88rem; }
@media(max-width:640px) { [data-testid="stMainBlockContainer"] { padding-top:3.75rem; } .gcc-header { padding:28px 20px; min-height:250px; } .gcc-header h1 { font-size:2.05rem !important; } .gcc-symbol { display:none; } .gcc-result-grid { grid-template-columns:1fr; gap:16px; } .gcc-donut { margin:auto; } .gcc-result-top { flex-direction:column; } [data-testid="stForm"] { padding:20px 0; } .gcc-header p { font-size:.92rem; } .stTabs [data-baseweb="tab"] { padding:0 13px; font-size:.82rem; } }
</style>
"""

BUILDING = """<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 12 16 5l13 7H3Zm2 15h22M3 29h26M7 14v11m6-11v11m6-11v11m6-11v11"/></svg>"""


def apply_theme(portal):
    width = "1260px" if portal == "citizen" else "1500px"
    st.markdown(CSS + f"<style>[data-testid='stMainBlockContainer'], .main .block-container {{ max-width:{width}; }}</style>", unsafe_allow_html=True)
    st.markdown('<div class="gcc-ribbon"><span>GCC &middot; Government Road Maintenance Portal</span><span class="gcc-pilot">Kandanchavadi pilot</span></div>', unsafe_allow_html=True)


def render_header(portal):
    title = "Citizen Complaint Portal" if portal == "citizen" else "Officer Operations Portal"
    subtitle = "Public Grievance &amp; Road Complaint System" if portal == "citizen" else "Road Infrastructure Complaint Management"
    image = Path(__file__).parent / "assets" / "civic-road.jpg"
    background = ""
    if image.exists():
        encoded = base64.b64encode(image.read_bytes()).decode("ascii")
        background = f" style=\"background-image:url(data:image/jpeg;base64,{encoded})\""
    st.markdown(f'<div class="gcc-header"{background}><div class="gcc-heading-row"><div class="gcc-symbol">{BUILDING}</div><div><div class="gcc-eyebrow">GCC &middot; Kandanchavadi</div><h1>{title}</h1><p>{subtitle} &middot; Kandanchavadi pilot</p></div></div></div>', unsafe_allow_html=True)


def section_heading(number, title):
    st.markdown(f'<div class="gcc-section"><span class="gcc-section-number">{number:02d}</span><h3>{title}</h3></div>', unsafe_allow_html=True)


def render_footer():
    st.markdown('<footer class="gcc-footer"><div><strong>GCC Road Maintenance Portal</strong>Kandanchavadi &middot; Pilot project</div><div>Prototype developed by<br>Kevin, Keerthi and Lakshikanth</div></footer>', unsafe_allow_html=True)



def _text(value):
    return escape(str(value), quote=True)


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _bar(label, value, maximum=100, baseline=False, unit="%"):
    number = _number(value)
    if number is None:
        return ""
    fill = min(100, max(0, number / max(1, maximum) * 100))
    klass = " gcc-bar-baseline" if baseline else ""
    return f'<div class="gcc-chart-row"><div class="gcc-chart-caption"><span>{_text(label)}</span><strong>{number:,.1f}{_text(unit)}</strong></div><div class="gcc-track"><div class="gcc-bar{klass}" style="--gcc-fill:{fill:.3f}%"></div></div></div>'


def risk_level(risk, base):
    # Preserve the original presentation thresholds exactly.
    if base and risk >= base * 1.4:
        return "Clearly above average"
    if base and risk >= base * 1.1:
        return "Somewhat above average"
    return "Around or below average"


def render_risk_result(result, inputs, report):
    risk = _number(result.get("predicted_failure_risk"))
    if risk is None:
        return
    base = _number(result.get("base_rate_pct"))
    level = risk_level(risk, base)
    tag = "Simulated history" if result.get("data_label") == "simulated" else "Historical estimate"
    window = report.get("window_days", 60)
    comparison = "Historical average unavailable." if base is None else f"{abs(risk-base):.1f} percentage points {'above' if risk >= base else 'below'} the historical average."
    details = "".join(f'<span>{_text(k)}<strong>{_text(v)}</strong></span>' for k, v in inputs.items())
    st.markdown(f'<section class="gcc-result"><div class="gcc-result-top"><div><div class="gcc-result-label">Repair risk assessment</div><h3>{level}</h3><p class="gcc-result-sub">Repair-related complaint within {_text(window)} days · not a guarantee</p></div><span class="gcc-chip">{tag}</span></div><div class="gcc-result-grid"><div class="gcc-donut" style="--gcc-fill:{min(100,max(0,risk))}%"><div class="gcc-donut-inner"><strong class="gcc-result-value">{risk:.1f}%</strong><span class="gcc-result-unit">Predicted failure risk</span></div></div><div>{_bar("This repair",risk)}{_bar("Historical average",base,baseline=True)}<p class="gcc-graph-note">{comparison}</p></div></div><div class="gcc-inputs">{details}</div></section>', unsafe_allow_html=True)
    render_drivers(report)


def render_drivers(report):
    drivers = report.get("drivers") or []
    if not drivers:
        return
    with st.expander("Why this estimate?"):
        st.caption("Overall model associations, not individual causes. Odds ratios above 1 indicate higher odds; below 1 indicate lower odds.")
        values = [(d.get("factor", ""), _number(d.get("odds_ratio"))) for d in drivers]
        values = [(name, value) for name, value in values if value is not None]
        # A centered log scale correctly represents both protective and risk-raising associations.
        extent = max([abs(math.log(max(v, .0001))) for _, v in values] + [1])
        rows = []
        for name, value in values[:8]:
            score = math.log(max(value, .0001)) / extent * 45
            left = 50 + min(0, score)
            rows.append(f'<div class="gcc-chart-row"><div class="gcc-chart-caption"><span>{_text(name.replace("_", " "))}</span><strong>{value:.2f}×</strong></div><div class="gcc-track" style="position:relative"><div style="position:absolute;left:50%;height:100%;border-left:1px solid var(--gcc-muted)"></div><div class="gcc-bar" style="position:absolute;left:{left}%;--gcc-fill:{abs(score)}%;background:var({"--gcc-warning" if score > 0 else "--gcc-brand"})"></div></div></div>')
        st.markdown(''.join(rows)+'<p class="gcc-graph-note">Lower odds ← · 1× baseline · → Higher odds</p>', unsafe_allow_html=True)
        st.caption(report.get("interpretation", ""))


def render_resolution_estimate(days, basis):
    number = _number(days)
    if number is None:
        return
    tag = "Simulated history · demo estimate" if basis == "simulated" else "Historical estimate"
    st.markdown(f'<section class="gcc-result"><div class="gcc-result-top"><div><div class="gcc-result-label">Expected resolution</div><h3>About {number:.0f} days</h3></div><span class="gcc-chip">{tag}</span></div><div class="gcc-timeline"><span>Reported</span><div class="gcc-timeline-line"></div><div class="gcc-time-end"><strong>~{number:.0f} days</strong><span>Typical resolution</span></div></div><p class="gcc-graph-note">Based on similar resolved reports. Not a promised completion date.</p></section>', unsafe_allow_html=True)


def render_status_result(result):
    status = result["status"]
    stages = ["Open", "In Progress", "Resolved"]
    index = stages.index(status) if status in stages else -1
    html = ''.join(f'<div class="gcc-stage{ " gcc-stage-active" if i <= index else ""}">{i+1:02d} · {_text(s)}</div>' for i,s in enumerate(stages))
    st.markdown(f'<section class="gcc-result"><div class="gcc-result-label">Complaint status</div><h3>{_text(status)}</h3><div class="gcc-stages">{html}</div><div class="gcc-summary-line"><span>{_text(result["damage_type_label"])}</span><span>{_text(result["location_description"])}</span><span>Reported {_text(result["complaint_date"])}</span></div></section>', unsafe_allow_html=True)


def render_receipt(done):
    st.markdown(f'<section class="gcc-result"><div class="gcc-result-label">Complaint received</div><h3>{_text(done["complaint_id"])}</h3><p class="gcc-result-sub">Keep this reference to check your complaint status.</p><div class="gcc-stages"><div class="gcc-stage gcc-stage-active">01 · Received</div><div class="gcc-stage">02 · In progress</div><div class="gcc-stage">03 · Resolved</div></div></section>', unsafe_allow_html=True)


def render_accountability_graph(data, summary):
    groups = data.get("by_department") or []
    if not groups:
        return
    st.markdown("#### Repair durability")
    baseline = summary.get("overall_durability_rate")
    html = _bar("Overall durability", baseline, baseline=True)
    for row in groups:
        html += _bar(row.get("name", "Department"), row.get("durability_rate"))
    st.markdown(html, unsafe_allow_html=True)
    st.caption("Observed durable repairs by department. Job counts and 95% intervals appear in the tables below.")


def render_impact_graph(data):
    res = data["results"]
    keys = [("triage_time_value_per_year_inr", "Triage time value"), ("running_cost_per_year_inr", "Running cost"), ("net_benefit_per_year_inr", "Net benefit")]
    values = [(key,label,_number(res.get(key,{}).get("value"))) for key,label in keys]
    maximum = max([abs(v) for _,_,v in values if v is not None]+[1])
    st.markdown("#### Annual value & cost")
    st.caption("Assumption-based estimates · INR per year")
    st.markdown(''.join(_bar(label, value, maximum, baseline=key=="running_cost_per_year_inr",unit=" ₹") for key,label,value in values if value is not None and value >= 0), unsafe_allow_html=True)
    for key,label,value in values:
        if value is not None and value < 0:
            st.metric(label, f"₹{value:,.0f}")
    with st.expander("Calculation basis"):
        for key,label,value in values:
            if key in res:
                st.caption(f"{label}: {res[key].get('formula', '')} · {res[key].get('source', '')}")


def render_scaling_graph(data):
    scaling = data.get("scaling") or []
    if not scaling:
        return
    import pandas as pd
    frame = pd.DataFrame(scaling)
    frame = frame.rename(columns={"wards":"Wards", "running_cost_per_year_inr":"Running cost", "benefit_per_year_inr":"Triage benefit"})
    st.line_chart(frame, x="Wards", y=["Running cost", "Triage benefit"], x_label="Wards", y_label="INR / year", color=["#2674a8", "#126b61"])
