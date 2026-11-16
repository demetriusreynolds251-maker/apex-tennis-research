"""
apex_sa365_coverage_report.py  (APEX-SA365-PERSET-2026-09-27, Phases 2-5)

Reads apex_sa365_stats_v1.db (written by apex_sa365_perset_capture.py /
apex_sa365_backfill.py) and produces evidence-only reports:
  - coverage % / missing % (Phase 2)
  - serve-quality + break-points-saved distributions (Phase 2/3)
  - per-set match-length study (Phase 4)
  - Bo3/Bo5 post-hoc ground-truth check (Phase 5)

Read-only against the DB and the picks log. Writes only its own JSON output
file. No model fitting, no production file changes.
"""

import json
import sqlite3
import pandas as pd
from pathlib import Path

DB = "data/apex_sa365_stats_v1.db"
OUT = "apex_sa365_coverage_report.json"


def load():
    con = sqlite3.connect(DB)
    caps = pd.read_sql("SELECT * FROM captures", con)
    ps = pd.read_sql("SELECT * FROM perset_stats", con)
    con.close()
    return caps, ps


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def main():
    caps, ps = load()
    total_attempted = len(caps)
    stored = caps[caps["note"] == ""]
    n_stored = len(stored)
    report = {"generated_note": "read-only evidence report; no models fit, no production files touched"}

    # ---- Phase 1/2 coverage ----
    report["phase1_2_coverage"] = {
        "unique_matches_attempted": total_attempted,
        "matches_with_stat_sheet": n_stored,
        "coverage_pct": pct(n_stored, total_attempted),
        "no_event_found": int((caps["note"].str.contains("not found", na=False)).sum()),
        "no_stat_sheet": int((caps["note"] == "no stat sheet").sum()),
        "by_surface": caps.groupby("surface")["note"].apply(lambda s: (s == "").sum()).to_dict() if n_stored else {},
    }

    if n_stored == 0:
        report["note"] = "No matches had a usable statistics sheet yet at report time -- see phase1_2_coverage for why (likely a retention-window effect on older events). Re-run after backfill finishes / against more recent match dates."
        Path(OUT).write_text(json.dumps(report, indent=2, default=str))
        print(json.dumps(report, indent=2, default=str))
        return

    stored_ids = set(stored["event_id"])
    ps_s = ps[ps["event_id"].isin(stored_ids)]
    merged = ps_s.merge(caps[["event_id", "surface", "best_of", "tour", "match_date"]], on="event_id", how="left")

    # ---- Phase 2: serve-quality dataset ----
    all_rows = merged[merged["set_label"] == "ALL"]
    def field_cov(col):
        return {
            "coverage_pct": pct(all_rows[col].notna().sum(), len(all_rows)),
            "missing_pct": pct(all_rows[col].isna().sum(), len(all_rows)),
        }
    report["phase2_serve_quality"] = {
        "n_match_rows_ALL_bucket": len(all_rows) // 2,  # 2 sides per match
        "first_serve_acc_pct": field_cov("first_serve_acc_pct"),
        "second_serve_acc_pct": field_cov("second_serve_acc_pct"),
        "first_serve_pts_pct": field_cov("first_serve_pts_pct"),
        "second_serve_pts_pct": field_cov("second_serve_pts_pct"),
        "distribution_first_serve_acc_pct": all_rows["first_serve_acc_pct"].describe().to_dict() if len(all_rows) else {},
        "by_surface_first_serve_acc_pct_mean": all_rows.groupby("surface")["first_serve_acc_pct"].mean().to_dict() if len(all_rows) else {},
    }

    # ---- Phase 3: break-points-saved vs breakPointsScored ----
    bps_cov = field_cov("break_points_saved_pct")
    report["phase3_break_points_saved"] = {
        "coverage": bps_cov,
        "distribution_pct": all_rows["break_points_saved_pct"].describe().to_dict() if len(all_rows) else {},
        "correlation_saved_pct_vs_scored_count": (
            all_rows[["break_points_saved_pct", "break_points_scored"]].dropna().corr().iloc[0, 1]
            if len(all_rows.dropna(subset=["break_points_saved_pct", "break_points_scored"])) > 2 else None
        ),
        "note": "breakPointsSaved is a DEFENSIVE stat (how many of MY break points against ME did I save); "
                "breakPointsScored (already used by apex_settle_sa365) is OFFENSIVE (how many break points I "
                "converted against my opponent). They are not the same information -- one player's saved-pct "
                "does not mechanically determine the other's scored count. Low |correlation| here is evidence "
                "the two carry different information, not redundant duplicates.",
    }

    # ---- Phase 4: per-set match-length study ----
    per_set = merged[merged["set_label"] != "ALL"]
    set_counts = per_set.groupby("event_id")["set_label"].nunique()
    report["phase4_match_length"] = {
        "set_count_distribution": set_counts.value_counts().sort_index().to_dict(),
        "avg_total_games_per_set_by_surface": (
            per_set.assign(total_games=lambda d: d["service_games_total"].fillna(0) + d["return_games_total"].fillna(0))
            .groupby("surface")["total_games"].mean().to_dict()
        ),
        "tiebreak_frequency_by_surface": (
            per_set.groupby("surface")["tiebreaks"].apply(lambda s: pct((s.fillna(0) > 0).sum(), len(s))).to_dict()
        ),
        "tour_split_available": bool(caps["tour"].notna().any()),
    }

    # ---- Phase 5: Bo3/Bo5 ground truth ----
    max_set = per_set.groupby("event_id")["set_label"].apply(
        lambda s: max((set(["1ST","2ND","3RD","4TH","5TH"]) & set(s)), key=lambda x: ["1ST","2ND","3RD","4TH","5TH"].index(x), default=None)
    )
    caps_idx = caps.set_index("event_id")
    contradictions = []
    for eid, lbl in max_set.items():
        if eid not in caps_idx.index or lbl is None:
            continue
        bo = caps_idx.loc[eid, "best_of"]
        set_num = {"1ST": 1, "2ND": 2, "3RD": 3, "4TH": 4, "5TH": 5}[lbl]
        if pd.notna(bo) and int(bo) == 3 and set_num > 3:
            contradictions.append({"event_id": eid, "claimed_best_of": 3, "actual_sets_seen": set_num,
                                    "match_date": caps_idx.loc[eid, "match_date"]})
    report["phase5_bo3_bo5_groundtruth"] = {
        "matches_with_perset_data": int(len(max_set)),
        "bo3_matches_that_actually_exceeded_3_sets": contradictions,
        "conclusion": (
            "No SA365 endpoint checked in the field audit exposes a direct best-of-sets field. "
            "Per-set records let us catch it AFTER THE FACT if a match labeled best_of=3 in the picks "
            "log actually produced a 4th/5th set (which would be a genuine data/format-inference error, "
            "since a real Bo3 match cannot go past 3 sets) -- see bo3_matches_that_actually_exceeded_3_sets. "
            "This is a POST-HOC check only: it cannot supply a ground-truth format field before the match "
            "starts, so it does not close the pre-match Bo5-inference gap flagged in the pre-flight audit "
            "and the SA365 field audit. If bo3_matches_that_actually_exceeded_3_sets is non-empty, that is "
            "direct proof apex_price_feed.fixture_context()'s format_hint was wrong for that match."
        ),
    }

    Path(OUT).write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
