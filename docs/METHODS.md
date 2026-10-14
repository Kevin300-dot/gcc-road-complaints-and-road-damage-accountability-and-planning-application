# Methods, fixes and limitations

## 1. What was wrong in the first version, and what changed

| # | Problem | Fix |
|---|---|---|
| 1 | The risk model's ~0.95 AUC came from the `month` feature. Repairs finished late in the data window had little time to collect a later complaint, so month just encoded "how much follow-up time exists". | `month` removed. Repairs whose follow-up window is not over are excluded from training. A unit test checks that completion month alone cannot predict the outcome. |
| 2 | "Failure" meant any later complaint on the segment, ever, so ~86% of repairs "failed" and a 20% durable rate counted as Good Standing. | Failure = a **repair-related** complaint on the same segment within a **60-day window** after completion. Repairs with an unfinished window are "under observation". Unrestored cuts are tracked separately as "restoration pending". |
| 3 / 5 | "Duplicate clustering" was a group-by on merged area names plus damage type. | **Hotspots**: reports on the same road segment chained within 35 m by real GPS distance (`clustering.py`). It is a spatial grouping, not text or photo matching, and is described that way. Reports are never merged or deleted: the survey confirmed that reports a few metres apart can be different defects. |
| 4 | Accuracy was reported without an honest evaluation. | Out-of-fold AUC with whole road segments held out, a bootstrap interval, a time-ordered holdout, and the Brier score against a constant baseline, all shown in the dashboard. |
| 5 | Priority weights looked arbitrary. | Weights are named, documented constants (`clustering.PRIORITY_WEIGHTS`) and described as expert-set starting values to calibrate with GCC data. Tiers are relative (k-means over current scores). |
| 6 | No cost, beneficiary or scalability numbers. | `impact.py` and the "Impact & Cost" tab. Every number is tagged `measured`, `simulated` or `assumption`. |

Also changed: officer login is a POST (password no longer in the URL), the password and CORS origins come from environment
variables, CSV writes are atomic and locked, status and restoration updates are validated, uploaded photos are checked
(type, size, file signature), photo lookup blocks path traversal, and all citizen-supplied text is HTML-escaped on the map.

## 2. Real data

`data/complaints.csv` holds the 48 complaints from the 10 Oct 2026 field survey (`tools/import_field_survey.py` converts and
validates the spreadsheet). The survey sampled **damaged spots**, so shares such as "75% are poor or unrestored road cuts"
describe the sample, not the share of all roads. All 48 complaints are on one day and all are Open, so nothing can be said
about resolutions or trends from the real data alone. With one survey day, "reports in the last 7/30 days" and the
urgency velocity carry no extra signal until more reports arrive.

Hotspots on the real data: 36 hotspots from 48 reports (25 with one report, 10 with two, 1 with three), because most real
defects are more than 35 m apart.

## 3. Simulated history (demo only)

`tools/generate_simulated_history.py` (fixed seed) creates 184 repair jobs and 116 complaints from 2024-01-01 to 2026-10-09
on the 18 real road segments, with complaint locations jittered around real survey points and kept inside the boundary.
Planted effects: 12 contractors (4 reliable, 5 average, 3 weaker), road cutting and utility work fail more, rushed jobs fail more.
A failure creates a follow-up complaint on the same segment inside the window.

Because the effects are planted, the model's AUC measures whether the pipeline can recover them, **not** real-world accuracy.

Shipped simulation (seed 1): 157 judged repairs, 39.5% failure rate, out-of-fold AUC **0.67** (95% interval 0.58 to 0.75),
time-ordered AUC 0.76. Overall durability 60.5%. Brier 0.223 vs 0.239 for a constant baseline.

How stable is that? `tools/robustness_check.py` re-simulates under other seeds and history lengths. Out-of-fold AUC, 5 seeds each:

| History | Judged repairs | Mean AUC | Min | Max |
|---|---|---|---|---|
| from 2024 (shipped) | ~158 | 0.63 | 0.57 | 0.68 |
| from 2022 | ~279 | 0.64 | 0.58 | 0.68 |
| from 2020 | ~404 | 0.65 | 0.62 | 0.71 |

For the planted effects, the best achievable AUC is about 0.68, so the model is working near that ceiling.
Seed 1 is the first seed tried, not chosen for its score. The very first draw (seed 2026) gave 0.55, within this range.
Group-level accountability is more reliable than individual prediction at this sample size: the two weakest simulated
contractors are flagged "Needs Review" with durability of about a third.

## 4. Impact calculator

* **Measured** (real survey and boundary): area 0.214 km², reports, hotspots, shares on emergency routes, with two-wheeler risk,
  pedestrian risk, high or severe traffic impact, and poor or unrestored cuts.
* **Simulated**: repair jobs per year, median repair cost, repair failure rate.
* **Assumption** (placeholders, editable in the dashboard; replace before quoting): population served, reports per month,
  officer minutes per report before and after, officer cost per hour, hosting cost, setup cost, share of failed repairs avoided.

The headline net benefit counts **only officer triage time**. The repeat-repair saving depends on simulated repair costs and volumes,
so it is shown as an illustrative extra and is not included in net benefit, payback or the scaling table.
Scalability: a new ward needs a boundary file and complaint data in the same format; costs are scaled linearly per ward as a
conservative estimate.

## 5. Known limitations

* Not exercised with real Streamlit or FastAPI in the build environment (see the hand-over notes); the logic, API functions and
  app scripts were run against stand-ins, and the map script in a browser against a stub of Leaflet. Run the three commands in the
  README and click through once before presenting.
* The map needs internet access. Roads shown are those drawn by OpenStreetMap.
* The officer endpoints are protected only by the dashboard login. Before any public deployment add token authentication.
* The model is a logistic regression with few features; with real data, add repair quality, traffic load and weather, and recheck with the same evaluation.
* The border tolerance (15 m) and hotspot radius (35 m) are judgement calls; both are single constants.
