# GCC Road Complaint System — Kandanchavadi pilot

A citizen complaint portal and an officer dashboard for road defects, scoped to **Kandanchavadi** (Chennai).
Real GPS complaints from a field survey are mapped on OpenStreetMap inside the Kandanchavadi boundary,
grouped into hotspots, and prioritised. Repair accountability, repair-failure risk and resolution-time
estimates are included and run on a **clearly labelled simulated repair history** until real GCC records exist.

## Run it

```bash
pip install -r requirements.txt
uvicorn backend_main:app --port 8000          # terminal 1: API
streamlit run officer_app.py --server.port 8501   # terminal 2: officer dashboard
streamlit run citizen_app.py --server.port 8502   # terminal 3: citizen portal
```

* Put the 48 survey photos in `photo_path/` (file names exactly as in the `photo_path` column of `data/complaints.csv`).
  New citizen uploads are saved in `uploads/`. If a photo is missing the dashboard shows a placeholder, nothing breaks.
* The maps need internet (Leaflet and OpenStreetMap tiles load in the viewer's browser).
* Officer password: environment variable `OFFICER_PASSWORD` (default `gccofficer`, demo only).
* If the API is not on localhost, set `GCC_API_URL` for both Streamlit apps. Set `ORION_CORS_ORIGINS` if you serve the apps from other origins.
* Tests: `python -m unittest discover -s tests -v` (need only pandas, numpy, scikit-learn).

## What is real and what is simulated

| Part | Data | Status |
|---|---|---|
| Complaint map, hotspots, priority list, citizen portal | `data/complaints.csv`: 48 field-survey complaints (10 Oct 2026) plus new citizen reports | **Real** |
| Kandanchavadi boundary | `data/kandanchavadi_boundary.kml` (traced in Google My Maps) | **Real** |
| Contractor / department accountability, repair-risk model, "typically N days to resolve" | `data/simulated/*.csv`, made by `tools/generate_simulated_history.py` on the real road segments | **Simulated** (labelled in the UI) |
| Cost, beneficiaries, scalability | measured shares from the real survey + editable **placeholder assumptions** | See `docs/METHODS.md` |

Drop a real repair history into `data/intervention_events.csv` (same columns as `data/simulated/intervention_events.csv`)
and, together with real follow-up complaints, the same code uses it automatically.

## Border rule

Roads along the red boundary line count as part of Kandanchavadi. A point is accepted if it is inside the polygon or within
15 m of its edge (`area_config.BORDER_TOLERANCE_M`). In the survey, 42 of 48 points are strictly inside and 6 sit on border
roads 0.9 to 11.7 m outside the traced line. The citizen form rejects locations outside the area.

## Layout

```
area_config.py   boundary, point-in-area test, border rule
data_layer.py    load / validate / write complaints, events, escalations, photos
clustering.py    distance-based hotspots, priority score and tiers
analytics.py     repair-outcome labelling, accountability, urgency, resolution times
risk_model.py    repair failure-risk model with honest evaluation
impact.py        cost / beneficiary / scalability calculator
maplib.py        OpenStreetMap (Leaflet) page builder
backend_main.py  FastAPI service
officer_app.py   officer dashboard (Streamlit)    citizen_app.py  citizen portal (Streamlit)
tools/           import_field_survey.py, generate_simulated_history.py, robustness_check.py
tests/           test_core.py
docs/METHODS.md  methods, fixes, limitations
```

Prototype developed by Kevin, Keerthi and Lakshikanth.
