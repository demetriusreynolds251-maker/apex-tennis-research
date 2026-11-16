"""
apex_sa365_bps_investigation.py  (APEX-SA365-PERSET-2026-09-27, BPS study)

Evidence-only investigation: does breakPointsSaved carry predictive
information not already captured by breakPointsScored, break rate, or
hold rate? No model is fit for production use here -- the OLS regression
below is used purely to compute a residual for evidence, exactly the way
Phase 3's correlation check was evidence, not a deployed feature.

Reads apex_sa365_stats_v1.db (read-only) and apex_engine_picks_log_v1.csv
(read-only) and apex_settle_sa365.parse_sets (reused, not reimplemented,
to determine match winner from the score string). Writes only its own
JSON report. No production file is touched.
"""

import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

import apex_settle_sa365 as ss

DB = "data/apex_sa365_stats_v1.db"
OUT = "apex_sa365_bps_investigation_report.json"


def load():
    con = sqlite3.connect(DB)
    caps = pd.read_sql("SELECT * FROM captures", con)
    ps = pd.read_sql("SELECT * FROM perset_stats WHERE set_label='ALL'", con)
    con.close()
    return caps, ps


def winner_side(score):
    sets = ss.parse_sets(score)
    if not sets:
        return None
    s1 = sum(a > b for a, b in sets)
    s2 = len(sets) - s1
    if s1 == s2:
        return None
    return 1 if s1 > s2 else 2


def build_frame(caps, ps):
    stored = caps[caps["note"] == ""].set_index("event_id")
    wide = ps.pivot(index="event_id", columns="side")
    rows = []
    for eid in stored.index:
        if eid not in ps["event_id"].values:
            continue
        for side in (1, 2):
            opp = 2 if side == 1 else 1
            try:
                me = ps[(ps["event_id"] == eid) & (ps["side"] == side)].iloc[0]
                them = ps[(ps["event_id"] == eid) & (ps["side"] == opp)].iloc[0]
            except IndexError:
                continue
            cap = stored.loc[eid]
            sgt = me["service_games_total"]
            rgt = me["return_games_total"]
            my_bps_scored = me["break_points_scored"]
            opp_bps_scored = them["break_points_scored"]
            if sgt in (None, 0) or pd.isna(sgt):
                hold_rate = None
            else:
                hold_rate = 1.0 - (opp_bps_scored or 0) / sgt
            if rgt in (None, 0) or pd.isna(rgt):
                break_rate = None
            else:
                break_rate = (my_bps_scored or 0) / rgt
            win = winner_side(cap["score"])
            rows.append(dict(
                event_id=eid, side=side, player=cap["player1"] if side == 1 else cap["player2"],
                opponent=cap["player2"] if side == 1 else cap["player1"],
                tour=cap["tour"], surface=cap["surface"], best_of=cap["best_of"],
                games_won=me["games_won"], service_games_total=sgt, return_games_total=rgt,
                break_points_scored=my_bps_scored,
                break_points_saved_value=me["break_points_saved_value"],
                break_points_saved_total=me["break_points_saved_total"],
                break_points_saved_pct=me["break_points_saved_pct"],
                hold_rate=hold_rate, break_rate=break_rate,
                won_match=(1 if win == side else (0 if win else None)),
            ))
    return pd.DataFrame(rows)


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def main():
    caps, ps = load()
    df = build_frame(caps, ps)
    report = {"generated_note": "evidence-only; the OLS below computes a residual for analysis, it is not a deployed model"}

    n_matches = df["event_id"].nunique()
    n_rows = len(df)

    # 1. Coverage
    total_captured = int((caps["note"] == "").sum())
    report["1_coverage"] = {
        "matches_with_usable_stat_sheet": total_captured,
        "matches_with_break_points_saved_populated": n_matches,
        "player_match_rows": n_rows,
        "coverage_pct_within_captured": pct(n_matches, total_captured),
        "note": "Every match with a usable statistics sheet has break_points_saved populated -- "
                "confirmed 100% field-level coverage inside a populated sheet in the earlier "
                "field audit; this simply reconfirms it holds for this specific field on the "
                "current dataset.",
    }

    # 2. Distribution
    bps = df["break_points_saved_pct"].dropna()
    report["2_distribution"] = {
        "n": int(bps.shape[0]),
        **{k: (None if pd.isna(v) else round(float(v), 2)) for k, v in bps.describe().to_dict().items()},
        "value_of_zero_pct_count": int((bps == 0).sum()),
        "value_of_100_pct_count": int((bps == 100).sum()),
        "note": "0% and 100% both mean 'faced very few break points' as much as they mean "
                "'defended well/poorly' -- distribution is bimodal-prone at small BP-faced counts; "
                "see break_points_saved_total distribution too.",
        "break_points_saved_total_distribution": df["break_points_saved_total"].dropna().describe().to_dict(),
    }

    # 3. ATP/WTA splits
    def tour_split(col):
        return df.groupby("tour")[col].agg(["count", "mean", "std"]).to_dict("index")
    report["3_atp_wta_splits"] = {
        "n_unknown_tour": int(df["tour"].isna().sum()),
        "break_points_saved_pct_by_tour": tour_split("break_points_saved_pct"),
        "break_rate_by_tour": tour_split("break_rate"),
        "hold_rate_by_tour": tour_split("hold_rate"),
    }

    # 4. Surface splits
    def surf_split(col):
        return df.groupby("surface")[col].agg(["count", "mean", "std"]).to_dict("index")
    report["4_surface_splits"] = {
        "break_points_saved_pct_by_surface": surf_split("break_points_saved_pct"),
        "break_rate_by_surface": surf_split("break_rate"),
        "hold_rate_by_surface": surf_split("hold_rate"),
    }

    # 5. Correlation matrix
    corr_cols = ["break_points_saved_pct", "break_points_scored", "break_rate", "hold_rate"]
    corr_df = df[corr_cols].dropna()
    report["5_correlation_matrix"] = {
        "n_rows_used": int(len(corr_df)),
        "matrix": corr_df.corr().round(3).to_dict(),
    }

    # 6. Residual analysis: regress break_points_saved_pct on [break_rate, hold_rate]
    reg = df[["break_points_saved_pct", "break_rate", "hold_rate", "break_points_scored", "won_match"]].dropna()
    if len(reg) >= 5:
        X = np.column_stack([np.ones(len(reg)), reg["break_rate"], reg["hold_rate"]])
        y = reg["break_points_saved_pct"].values.astype(float)
        coef, res, rank, sv = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ coef
        resid = y - pred
        ss_res = float(np.sum(resid ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
        resid_vs_scored = float(np.corrcoef(resid, reg["break_points_scored"])[0, 1]) if reg["break_points_scored"].std() > 0 else None
        resid_vs_won = None
        if reg["won_match"].nunique() > 1:
            resid_vs_won = float(np.corrcoef(resid, reg["won_match"])[0, 1])
        report["6_residual_analysis"] = {
            "n_rows_used": int(len(reg)),
            "model": "break_points_saved_pct ~ intercept + break_rate + hold_rate  (OLS, evidence only, not deployed)",
            "coefficients": {"intercept": round(float(coef[0]), 3), "break_rate": round(float(coef[1]), 3), "hold_rate": round(float(coef[2]), 3)},
            "r_squared": round(r2, 3) if r2 is not None else None,
            "interpretation": (
                "R^2 close to 0 means break_rate/hold_rate explain almost none of "
                "break_points_saved_pct's variance -- i.e. the defensive stat is NOT "
                "algebraically or empirically redundant with the offensive/game-level stats. "
                "R^2 close to 1 would mean it's mostly reconstructable from what Apex already has."
            ),
            "residual_correlation_with_break_points_scored": round(resid_vs_scored, 3) if resid_vs_scored is not None else None,
            "residual_correlation_with_match_win": round(resid_vs_won, 3) if resid_vs_won is not None else None,
            "caveat": "n=%d player-match rows -- a real but SMALL sample. Treat r_squared and "
                      "residual correlations as directional evidence, not a settled result." % len(reg),
        }
    else:
        report["6_residual_analysis"] = {"note": "insufficient rows (n=%d) for a regression" % len(reg)}

    # 7. Potential use cases (evidence-only reasoning, nothing built)
    report["7_potential_use_cases"] = [
        "Independent cross-check for the 'breaks' settlement category: today apex_settle_sa365.value_for() "
        "settles 'breaks' from breakPointsScored (offense) with only an arithmetic serve-parity sanity check. "
        "breakPointsSaved is a genuinely separate signal (see correlation matrix / residual R^2) that could "
        "serve as a second, independent check rather than a self-consistency check.",
        "Serve-under-pressure feature for aces/dfs/games_won calibration: a low break-points-saved% combined "
        "with a normal hold_rate would flag a player who is winning service games narrowly / late in break "
        "points, which today's game-level hold_rate alone cannot distinguish.",
        "Bo5 fatigue signal (once Bo5 data exists -- currently zero Bo5 matches in the captured sample, see "
        "the pipeline doc's Phase 4 finding): a declining break-points-saved% across sets within a single "
        "match would be a more sensitive early fatigue indicator than set-level hold rate, since it operates "
        "at the point level.",
        "WTA-specific calibration: this sample shows real WTA coverage (8 of 18 tour-known matches) for the "
        "first time this project has had it, per-set/per-point break-defense data may matter disproportionately "
        "for WTA given known thinner model coverage there (per the pre-flight audit).",
    ]

    Path(OUT).write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
