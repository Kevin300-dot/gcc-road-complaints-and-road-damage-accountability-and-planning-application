"""
Repair failure-risk model.

What changed from the first version (and why)
----------------------------------------------
1. Leakage removed. The old model used `month` as a feature. Repairs finished late in the
   data window had little time left to collect a later complaint, so month simply encoded
   "how much follow-up time exists" and produced a cross-validated AUC of ~0.95 that came
   entirely from the calendar. `month` is gone. Repairs whose follow-up window is not over
   are excluded from training (see analytics.label_repair_outcomes).
2. A real outcome definition: failure = a repair-related complaint on the same segment
   within FOLLOWUP_WINDOW_DAYS of completion, instead of "any complaint, ever".
3. Honest evaluation: out-of-fold AUC with whole road segments held out together
   (GroupKFold) plus a time-ordered holdout (train on earlier repairs, test on later ones).
   The report is shown to the user next to the prediction.

IMPORTANT: until real GCC repair records are available this model is trained on SIMULATED
history in which known effects (contractor quality, road cutting, work type, rushed jobs)
were planted. The reported AUC therefore measures whether the pipeline can recover those
planted effects, not real-world accuracy. The code path is identical for real data.
"""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from analytics import FOLLOWUP_WINDOW_DAYS, label_repair_outcomes

CATEGORICAL = ["department", "contractor", "event_type", "road_cutting"]
NUMERIC = ["duration_days"]
FEATURE_COLUMNS = CATEGORICAL + NUMERIC
MIN_TRAINING_JOBS = 40
MIN_PER_CLASS = 8


def _prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["road_cutting"] = out["road_cutting"].fillna("No")
    start = out["start_date_parsed"] if "start_date_parsed" in out.columns else out["completion_date_parsed"]
    out["duration_days"] = (out["completion_date_parsed"] - start).dt.days.clip(lower=0, upper=60).fillna(1)
    return out[FEATURE_COLUMNS]


def build_training_set(complaints_df: pd.DataFrame, events_df: pd.DataFrame, window_days: int = FOLLOWUP_WINDOW_DAYS):
    """X, y, groups(segment), completion dates - only for repairs with a fully observed window."""
    labelled = label_repair_outcomes(complaints_df, events_df, window_days=window_days)
    if labelled.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=int), pd.Series(dtype=str), pd.Series(dtype="datetime64[ns]")
    judged = labelled[labelled["outcome"].isin(["held", "failed"])]
    X = _prepare_features(judged)
    y = judged["failed"].astype(int)
    return X, y, judged["road_segment_id"], judged["completion_date_parsed"]


def _make_pipeline() -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])
    return Pipeline([("prep", pre), ("clf", LogisticRegression(max_iter=2000, C=0.5))])


def evaluate(X, y, groups, completion_dates) -> dict:
    """Honest evaluation. Returns metrics; never raises on small data."""
    report = {"n_jobs": int(len(y)), "failure_rate": round(float(y.mean()), 3)}

    n_groups = groups.nunique()
    k = min(5, n_groups)
    if k >= 2:
        oof = np.zeros(len(y))
        for train_idx, test_idx in GroupKFold(n_splits=k).split(X, y, groups):
            if y.iloc[train_idx].nunique() < 2:
                oof[test_idx] = y.iloc[train_idx].mean()
                continue
            m = _make_pipeline().fit(X.iloc[train_idx], y.iloc[train_idx])
            oof[test_idx] = m.predict_proba(X.iloc[test_idx])[:, 1]
        report["cv_auc"] = round(float(roc_auc_score(y, oof)), 3) if y.nunique() == 2 else None
        report["cv_brier"] = round(float(brier_score_loss(y, oof)), 3)
        report["baseline_brier"] = round(float(brier_score_loss(y, np.full(len(y), y.mean()))), 3)
        # Bootstrap interval for the AUC (resampling jobs): shows how much a number this small can move.
        rng = np.random.default_rng(0)
        aucs = []
        yv = y.to_numpy()
        for _ in range(300):
            idx = rng.integers(0, len(yv), len(yv))
            if len(np.unique(yv[idx])) == 2:
                aucs.append(roc_auc_score(yv[idx], oof[idx]))
        if aucs:
            report["cv_auc_ci95"] = [round(float(np.percentile(aucs, 2.5)), 3), round(float(np.percentile(aucs, 97.5)), 3)]
    report["cv_method"] = f"{k}-fold, whole road segments held out together"

    order = completion_dates.sort_values().index
    cut = int(len(order) * 0.7)
    train_ix, test_ix = order[:cut], order[cut:]
    if len(test_ix) >= 15 and y.loc[train_ix].nunique() == 2 and y.loc[test_ix].nunique() == 2:
        m = _make_pipeline().fit(X.loc[train_ix], y.loc[train_ix])
        report["time_split_auc"] = round(float(roc_auc_score(y.loc[test_ix], m.predict_proba(X.loc[test_ix])[:, 1])), 3)
        report["time_split_note"] = f"trained on the earliest {len(train_ix)} repairs, tested on the latest {len(test_ix)}"
    return report


def _drivers(pipeline: Pipeline, top: int = 8) -> list:
    names = pipeline.named_steps["prep"].get_feature_names_out()
    coefs = pipeline.named_steps["clf"].coef_[0]
    rows = [{"factor": n.split("__", 1)[1], "odds_ratio": round(float(np.exp(c)), 2)} for n, c in zip(names, coefs)]
    rows.sort(key=lambda r: abs(np.log(r["odds_ratio"])), reverse=True)
    return rows[:top]


def train_risk_model(complaints_df: pd.DataFrame, events_df: pd.DataFrame, data_label: str = "simulated",
                     window_days: int = FOLLOWUP_WINDOW_DAYS):
    """Returns {"model": Pipeline, "report": {...}} or None if there is not enough data."""
    X, y, groups, dates = build_training_set(complaints_df, events_df, window_days)
    n = len(y)
    if n < MIN_TRAINING_JOBS or y.nunique() < 2 or y.value_counts().min() < MIN_PER_CLASS:
        return None
    report = evaluate(X, y, groups, dates)
    model = _make_pipeline().fit(X, y)
    report.update({
        "window_days": window_days,
        "data_label": data_label,
        "features": FEATURE_COLUMNS,
        "drivers": _drivers(model),
        "interpretation": (
            "Trained on SIMULATED repair history with planted effects; the AUC shows the method can recover "
            "them, not real-world accuracy. Retrain on real GCC records before relying on predictions."
            if data_label == "simulated" else
            "Trained on recorded repair outcomes. Out-of-fold AUC is the honest accuracy estimate."
        ),
    })
    return {"model": model, "report": report}


def predict_risk(bundle, department: str, contractor: str, event_type: str, road_cutting: str, duration_days: float = 2):
    if bundle is None:
        return None
    row = pd.DataFrame([{
        "department": department, "contractor": contractor, "event_type": event_type,
        "road_cutting": road_cutting, "duration_days": float(duration_days),
    }])
    model = bundle["model"]
    classes = list(model.named_steps["clf"].classes_)
    if 1 not in classes:
        return None
    return round(float(model.predict_proba(row)[0][classes.index(1)]) * 100, 1)


def predicted_risk_by_group(bundle, labelled_events: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Average model-predicted failure risk per department/contractor over their judged jobs.
    In-sample, so it is shown beside (not instead of) the observed durability rate."""
    empty = pd.DataFrame(columns=["name", "predicted_failure_risk"])
    if bundle is None or labelled_events is None or labelled_events.empty:
        return empty
    judged = labelled_events[labelled_events["outcome"].isin(["held", "failed"])]
    if judged.empty:
        return empty
    model = bundle["model"]
    classes = list(model.named_steps["clf"].classes_)
    if 1 not in classes:
        return empty
    proba = model.predict_proba(_prepare_features(judged))[:, classes.index(1)]
    tmp = judged[[group_col]].copy()
    tmp["predicted_failure_risk"] = proba * 100
    grouped = tmp.groupby(group_col)["predicted_failure_risk"].mean().round(1).reset_index()
    return grouped.rename(columns={group_col: "name"})
