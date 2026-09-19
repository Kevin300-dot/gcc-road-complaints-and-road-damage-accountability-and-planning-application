import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

FEATURE_COLUMNS = ["department", "contractor", "event_type", "road_cutting", "month"]


def _prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["month"] = out["completion_date_parsed"].dt.month.fillna(1).astype(int).astype(str)
    out["road_cutting"] = out["road_cutting"].fillna("No")
    return out[FEATURE_COLUMNS]


def build_training_set(complaints_df: pd.DataFrame, events_df: pd.DataFrame):
    """
    Builds a labeled training set from historical completed, restored repairs.
    Label: 1 if a new complaint was later filed on the same road segment
    (the repair did not hold), 0 otherwise. Same underlying definition used
    for the descriptive accountability metric, reused here as a supervised
    learning target.
    """
    completed = events_df[
        (events_df["work_status"] == "Completed")
        & (events_df["restoration_required"] == "Yes")
        & (events_df["restoration_completed"] == "Yes")
    ].dropna(subset=["completion_date_parsed"]).copy()

    if completed.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=int)

    segment_last_complaint = (
        complaints_df.dropna(subset=["road_segment_id", "complaint_date_parsed"])
        .groupby("road_segment_id")["complaint_date_parsed"]
        .max()
    )
    completed["last_complaint_date"] = completed["road_segment_id"].map(segment_last_complaint)
    completed["failed"] = (
        completed["last_complaint_date"].notna()
        & (completed["last_complaint_date"] > completed["completion_date_parsed"])
    ).astype(int)

    X = _prepare_features(completed)
    y = completed["failed"]
    return X, y


def train_risk_model(complaints_df: pd.DataFrame, events_df: pd.DataFrame):
    """
    Trains a logistic regression classifier (one-hot encoded categorical
    features) predicting the probability that a repair job will fail
    (receive a follow-up complaint on the same road segment). Returns None
    if there isn't enough data or label variation to train meaningfully.
    """
    X, y = build_training_set(complaints_df, events_df)
    if len(X) < 20 or y.nunique() < 2:
        return None

    preprocessor = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), FEATURE_COLUMNS),
    ])
    model = Pipeline([
        ("prep", preprocessor),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
    model.fit(X, y)
    return model


def predict_risk(model, department: str, contractor: str, event_type: str, road_cutting: str, month: int):
    if model is None:
        return None
    row = pd.DataFrame([{
        "department": department,
        "contractor": contractor,
        "event_type": event_type,
        "road_cutting": road_cutting,
        "month": str(month),
    }])
    classes = list(model.named_steps["clf"].classes_)
    if 1 not in classes:
        return None
    idx = classes.index(1)
    proba = model.predict_proba(row)[0]
    return round(float(proba[idx]) * 100, 1)


def predicted_risk_by_group(model, events_df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """
    Runs the trained model across all historical completed+restoration-required
    jobs and averages predicted failure probability per department/contractor,
    for side-by-side comparison against the empirical durability rate.
    """
    empty = pd.DataFrame(columns=["name", "predicted_failure_risk"])
    if model is None:
        return empty

    completed = events_df[
        (events_df["work_status"] == "Completed")
        & (events_df["restoration_required"] == "Yes")
    ].dropna(subset=["completion_date_parsed"]).copy()

    if completed.empty:
        return empty

    classes = list(model.named_steps["clf"].classes_)
    if 1 not in classes:
        return empty
    idx = classes.index(1)

    X = _prepare_features(completed)
    proba = model.predict_proba(X)[:, idx]
    completed["predicted_failure_risk"] = proba * 100

    grouped = completed.groupby(group_col)["predicted_failure_risk"].mean().round(1).reset_index()
    grouped = grouped.rename(columns={group_col: "name"})
    return grouped
