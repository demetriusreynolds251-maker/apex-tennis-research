"""
apex_sa365_7day_validation.py  (APEX-SA365-PERSET-2026-09-27, Phase 6)

Run this after the daily capture job (apex_sa365_daily_capture.py) has
been running for about 7 days, to report on data accumulation:
  - total matches captured
  - ATP coverage / WTA coverage
  - Bo3 coverage / Bo5 coverage
  - surface coverage
  - daily-job run log summary (attempted/new/duplicate/empty/missing)

"Coverage" here means: of matches Apex attempted to capture in that
subgroup, what % actually got a usable statistics sheet (i.e. beat the
retention-window problem documented in Phase 1). This is evidence-only --
no model is fit, no ranking/probability logic is touched.

Usage: python3 apex_sa365_7day_validation.py [--since YYYY-MM-DD]
  --since restricts to captures/log entries at or after that date;
  defaults to 7 days before today.
"""

import argparse
import json
import sqlite3
import datetime as dt
from pathlib import Path
import pandas as pd

DB = "data/apex_sa365_stats_v1.db"
JSONL_LOG = "apex_sa365_daily_capture_log.jsonl"
OUT = "apex_sa365_7day_validation_report.json"


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def load_captures():
    con = sqlite3.connect(DB)
    caps = pd.read_sql("SELECT * FROM captures", con)
    con.close()
    return caps


def load_run_log():
    if not Path(JSONL_LOG).exists():
        return []
    with open(JSONL_LOG) as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    args = ap.parse_args()
    since = args.since or (dt.date.today() - dt.timedelta(days=7)).isoformat()

    caps = load_captures()
    caps["fetched_date"] = caps["fetched_at"].str.slice(0, 10)
    window = caps[caps["fetched_date"] >= since]
    stored = window[window["note"] == ""]

    def coverage_by(col, val):
        sub = window[window[col] == val]
        return {
            "attempted": int(len(sub)),
            "captured": int((sub["note"] == "").sum()),
            "coverage_pct": pct((sub["note"] == "").sum(), len(sub)),
        }

    report = {
        "generated_note": "read-only evidence report; no models fit, no production files touched",
        "window_since": since,
        "total_matches_captured_in_window": int(len(stored)),
        "total_matches_attempted_in_window": int(len(window)),
        "atp_coverage": coverage_by("tour", "atp"),
        "wta_coverage": coverage_by("tour", "wta"),
        "tour_unknown_count": int(window["tour"].isna().sum()),
        "bo3_coverage": coverage_by("best_of", 3),
        "bo5_coverage": coverage_by("best_of", 5),
        "surface_coverage": {
            s: coverage_by("surface", s) for s in [x for x in window["surface"].dropna().unique()]
        },
    }

    runs = load_run_log()
    runs_in_window = [r for r in runs if r["run_at"][:10] >= since]
    agg = {"attempted": 0, "new_captures": 0, "duplicates": 0, "empty": 0, "missing": 0, "error": 0}
    for r in runs_in_window:
        for k in agg:
            agg[k] += r.get(k, 0)
    report["daily_job_runs_in_window"] = len(runs_in_window)
    report["daily_job_totals"] = agg
    report["daily_job_run_dates"] = sorted(set(r["target_date"] for r in runs_in_window))

    if len(runs_in_window) < 7:
        report["caveat"] = (
            "Fewer than 7 daily runs found in the log (%d). This report is still valid "
            "evidence for whatever window it covers, but was likely run before a full "
            "7-day accumulation period completed -- re-run after 7 daily fires for the "
            "originally-intended read." % len(runs_in_window)
        )

    Path(OUT).write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
