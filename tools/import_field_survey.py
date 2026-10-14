"""
Convert the field-survey spreadsheet into data/complaints.csv and validate it.

Usage:
    python tools/import_field_survey.py path/to/kandanchavadi_complaints.xlsx

Checks performed (the script stops with an error if a hard check fails):
  * required columns present, complaint_id unique, coordinates numeric
  * every point is inside the Kandanchavadi boundary, counting border roads
    (within BORDER_TOLERANCE_M of the line) as inside
  * photo_path values are listed; if a photo_path/ folder exists next to the
    project, missing photo files are reported (a warning, not an error)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import area_config  # noqa: E402
import data_layer  # noqa: E402

REQUIRED = ["complaint_id", "road_segment_id", "complaint_date", "latitude", "longitude",
            "damage_type", "severity", "status", "photo_path"]


def main(xlsx_path: str):
    df = pd.read_excel(xlsx_path, sheet_name="complaints", dtype={"complaint_time": str})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        sys.exit(f"Missing required columns: {missing}")
    if not df["complaint_id"].is_unique:
        sys.exit("complaint_id values are not unique")
    if df[["latitude", "longitude"]].isna().any().any():
        sys.exit("Some rows have no coordinates")

    outside = []
    for _, r in df.iterrows():
        if not area_config.contains(r["latitude"], r["longitude"]):
            outside.append((r["complaint_id"], area_config.locate(r["latitude"], r["longitude"])))
    if outside:
        sys.exit(f"{len(outside)} point(s) are outside Kandanchavadi even with the border tolerance: {outside}")

    strict_outside = [
        r["complaint_id"] for _, r in df.iterrows()
        if not area_config.locate(r["latitude"], r["longitude"])["inside"]
    ]

    for col in data_layer.COMPLAINT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    ordered = data_layer.COMPLAINT_COLUMNS + [c for c in df.columns if c not in data_layer.COMPLAINT_COLUMNS]
    df = df[ordered]
    df.to_csv(data_layer.COMPLAINTS_PATH, index=False)

    print(f"Wrote {len(df)} complaints to {data_layer.COMPLAINTS_PATH}")
    print(f"  strictly inside the traced line: {len(df) - len(strict_outside)}")
    print(f"  on the border (within {area_config.BORDER_TOLERANCE_M:.0f} m, counted as inside): {len(strict_outside)} {strict_outside}")

    photo_dir = data_layer.PHOTO_DIR
    present = [f for f in os.listdir(photo_dir)] if os.path.isdir(photo_dir) else []
    wanted = [os.path.basename(str(p)) for p in df["photo_path"].dropna()]
    if present:
        absent = [p for p in wanted if p not in present]
        print(f"  photos found: {len(wanted) - len(absent)}/{len(wanted)}; missing: {absent[:10]}{'...' if len(absent) > 10 else ''}")
    else:
        print(f"  photo folder {photo_dir} is empty - copy your 48 photos into it (file names as in photo_path).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
