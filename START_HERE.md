# GCC portals — complete project, version 2

Two independent Streamlit websites, with a larger professional presentation and visual prediction results. The model, maps and original data are unchanged. The backend differs from the first v2 upload only in restoring the photo filename in the complaint-detail API and dropping the redundant `data_source` column.

## Update your existing websites safely
1. Replace `citizen_app.py`, `officer_app.py` and `portal_ui.py` in your current repository.
2. Replace `.streamlit/config.toml` and add `assets/civic-road.jpg`.
3. Push the changes to your existing GitHub repository. If needed, use Streamlit **Manage app → Reboot app** separately for each website.

Keep each existing Streamlit entry point, backend URL, secrets, records, photos and uploads. **Do not overwrite your current data with the original sample data included in this full-project archive.** No new package is required beyond the original requirements.

## New visual presentation
- Larger civic image banners, headings, fields, metrics and officer navigation.
- Citizen resolution estimates as a labelled timeline; visual receipt and status stages.
- Repair risk ring and comparison with the historical baseline.
- “Why this estimate?” graphs from existing model odds ratios. These are overall model associations, not per-repair causes or causal explanations.
- Department durability bars, annual value/cost comparison and ward-scaling graph, preserving all original tables and formulas.
- Simulated-data, assumption and evaluation disclosures are retained. Estimates are not guarantees.

The civic-road image is AI-generated illustration, not a verified photograph of Kandanchavadi or an official government image. The civic building emblem is not an official seal.

## Run a separate local copy
Use the original instructions in README.md for backend configuration. In three terminals, after installing requirements:

```sh
pip install -r requirements.txt
uvicorn backend_main:app --port 8000
streamlit run citizen_app.py --server.port 8502
streamlit run officer_app.py --server.port 8501
```

Keep your existing production officer password configuration; the original backend remains responsible for authentication.

## Verification
Run `python -m unittest discover -s tests -v`. See VERIFICATION_V2.md for local checks. Applying this archive to your public deployments is still your next step.
