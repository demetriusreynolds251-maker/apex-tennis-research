"""
build_walkforward_rows.py
2026-08-15 — Step 1 of the XGBoost combiner experiment.

WHAT THIS IS: the EXACT walk-forward loop from run_confidence_engine_backtest.py
(the script that produced the real 380,102-match / 69.8% result), with ONE
change: instead of scoring each match and throwing the row away, it SAVES
each match's pre-match signals + the real outcome to a CSV.

The signal computation and the state-update order are copied verbatim, on
purpose. Rewriting the walk-forward logic is exactly where a future-data
leak would sneak in, so it is not rewritten. Every row's signals are built
from matches strictly BEFORE that match. The match's own result is only
used to (a) label the row and (b) update state for LATER matches.

OUTPUT: walkforward_rows.csv, one row per real match that had at least
one real signal. Columns:
  match_date, year, surface, player_a, player_b,
  elo_gap, s5_raw, s1_raw, h2h_raw          (pre-match signals; blank = unavailable)
  n_signals_included                         (how many the current engine actually used)
  engine_prob                                (the CURRENT engine's blended P(player_a wins),
                                              computed on the same row -- for a fair head-to-head)
  label_a_won                                (1 = player_a won, 0 = player_b won)

Rule 9 respected: no odds, no market data anywhere in these rows.

Run ON THE MAC MINI, same folder as everything else:
    python3 build_walkforward_rows.py
This is slow (walks 520K matches). Run it once; train_xgb_combiner.py reads the CSV.
"""
import sqlite3
import json
import os
import sys
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elo_calculator import apply_match
from build_signal_calibration import CalibrationBucket
from confidence_engine import compute_moneyline_confidence

WAREHOUSE_PATH = "data/warehouse/tennis_warehouse.sqlite"
CALIBRATION_JSON = "real_calibration_tables.json"
OUTPUT_CSV = "walkforward_rows.csv"

# ---- constants copied verbatim from run_confidence_engine_backtest.py ----
MIN_SVGMS_FOR_RATE = 20
SERVE_WEIGHT, RETURN_WEIGHT, CLUTCH_WEIGHT, FORM_WEIGHT = 0.35, 0.25, 0.15, 0.25
MIN_H2H_SAMPLE = 3


class _HoldAccum:
    __slots__ = ("svgms", "bp_faced", "bp_saved")
    def __init__(self):
        self.svgms = 0
        self.bp_faced = 0
        self.bp_saved = 0
    def hold_pct(self):
        if self.svgms < MIN_SVGMS_FOR_RATE:
            return None
        return (1.0 - ((self.bp_faced - self.bp_saved) / self.svgms)) * 100


def _load_tables():
    if not os.path.exists(CALIBRATION_JSON):
        print(f"ERROR: {CALIBRATION_JSON} not found. Run build_real_calibration_tables.py first.")
        return None
    with open(CALIBRATION_JSON) as f:
        raw = json.load(f)
    return {
        name: [CalibrationBucket(low=b["low"], high=b["high"], n=b["n"], win_rate=b["win_rate"]) for b in buckets]
        for name, buckets in raw.items()
    }


def run():
    tables = _load_tables()
    if tables is None:
        return
    s5_table, s1_table, h2h_table = tables["s5"], tables["s1"], tables["h2h"]

    if not os.path.exists(WAREHOUSE_PATH):
        print(f"ERROR: warehouse not found at {WAREHOUSE_PATH}")
        return
    conn = sqlite3.connect(WAREHOUSE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT player_a, player_b, winner, surface, match_date, "
        "player_a_svgms, player_a_bp_faced, player_a_bp_saved, "
        "player_b_svgms, player_b_bp_faced, player_b_bp_saved "
        "FROM matches WHERE winner IS NOT NULL AND match_date IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    conn.close()

    ratings = {}
    hold_accum, return_accum = {}, {}
    season_record = {}
    h2h_record = {}

    written = 0
    scanned = 0
    out = open(OUTPUT_CSV, "w", newline="")
    w = csv.writer(out)
    w.writerow(["match_date", "year", "surface", "player_a", "player_b",
                "elo_gap", "s5_raw", "s1_raw", "h2h_raw",
                "n_signals_included", "engine_prob", "label_a_won"])

    for row in rows:
        pa, pb, winner, surface, date = row["player_a"], row["player_b"], row["winner"], row["surface"], row["match_date"]
        if winner not in (pa, pb):
            continue
        scanned += 1
        year = date[:4]
        label_a_won = 1 if winner == pa else 0

        # ── ELO (walk-forward, state BEFORE this match) ── [verbatim]
        p, o = ratings.get(pa), ratings.get(pb)
        elo_gap = None
        if p is not None and o is not None and p.overall_matches > 0 and o.overall_matches > 0:
            elo_gap = p.overall - o.overall

        # ── S5 ── [verbatim]
        pa_hold_acc, pb_hold_acc = hold_accum.get((pa, year)), hold_accum.get((pb, year))
        pa_hold = pa_hold_acc.hold_pct() if pa_hold_acc else None
        pb_hold = pb_hold_acc.hold_pct() if pb_hold_acc else None
        pa_bp_save = (pa_hold_acc.bp_saved / pa_hold_acc.bp_faced * 100) if pa_hold_acc and pa_hold_acc.bp_faced >= 5 else None
        pb_bp_save = (pb_hold_acc.bp_saved / pb_hold_acc.bp_faced * 100) if pb_hold_acc and pb_hold_acc.bp_faced >= 5 else None
        pa_r, pb_r = return_accum.get((pa, year)), return_accum.get((pb, year))
        pa_return = (pa_r[0] / pa_r[1] * 100) if pa_r and pa_r[1] >= MIN_SVGMS_FOR_RATE else None
        pb_return = (pb_r[0] / pb_r[1] * 100) if pb_r and pb_r[1] >= MIN_SVGMS_FOR_RATE else None
        pa_rec, pb_rec = season_record.get((pa, year, surface)), season_record.get((pb, year, surface))
        pa_win_pct = (pa_rec[0] / (pa_rec[0] + pa_rec[1]) * 100) if pa_rec and (pa_rec[0] + pa_rec[1]) > 0 else None
        pb_win_pct = (pb_rec[0] / (pb_rec[0] + pb_rec[1]) * 100) if pb_rec and (pb_rec[0] + pb_rec[1]) > 0 else None

        s5_raw = None
        if all(v is not None for v in (pa_hold, pb_hold, pa_return, pb_return, pa_bp_save, pb_bp_save, pa_win_pct, pb_win_pct)):
            serve_edge = pa_hold - pb_hold
            return_edge = pa_return - pb_return
            clutch_edge = pa_bp_save - pb_bp_save
            form_edge = pa_win_pct - pb_win_pct
            s5_raw = (SERVE_WEIGHT * serve_edge + RETURN_WEIGHT * return_edge
                      + CLUTCH_WEIGHT * clutch_edge + FORM_WEIGHT * form_edge)

        # ── S1 ── [verbatim]
        s1_raw = None
        if pa_rec and pb_rec and (pa_rec[0] + pa_rec[1]) > 0 and (pb_rec[0] + pb_rec[1]) > 0:
            s1_raw = pa_win_pct - pb_win_pct

        # ── H2H ── [verbatim]
        h2h_key = frozenset((pa, pb))
        h2h_rec = h2h_record.get(h2h_key)
        h2h_raw = None
        if h2h_rec is not None:
            pa_wins, pb_wins = h2h_rec.get(pa, 0), h2h_rec.get(pb, 0)
            total = pa_wins + pb_wins
            if total >= MIN_H2H_SAMPLE:
                h2h_raw = 2 * (pa_wins / total) - 1

        # ── Current engine on the SAME row (for the head-to-head later) ──
        if any(v is not None for v in (elo_gap, s5_raw, s1_raw, h2h_raw)):
            result = compute_moneyline_confidence(
                elo_gap=elo_gap,
                s5_raw=s5_raw, s5_table=s5_table,
                s1_raw=s1_raw, s1_table=s1_table,
                h2h_raw=h2h_raw, h2h_table=h2h_table,
            )
            n_inc = sum(1 for c in result.contributions if c.included and c.probability is not None)
            w.writerow([date, year, surface, pa, pb,
                        _f(elo_gap), _f(s5_raw), _f(s1_raw), _f(h2h_raw),
                        n_inc,
                        _f(result.win_probability),
                        label_a_won])
            written += 1

        # ── Update all real state AFTER using it ── [verbatim]
        loser = pb if winner == pa else pa
        apply_match(ratings, winner, loser, surface)

        pa_sv, pa_bpf, pa_bps = row["player_a_svgms"], row["player_a_bp_faced"], row["player_a_bp_saved"]
        pb_sv, pb_bpf, pb_bps = row["player_b_svgms"], row["player_b_bp_faced"], row["player_b_bp_saved"]
        if pa_sv is not None and pa_bpf is not None and pa_bps is not None:
            acc = hold_accum.setdefault((pa, year), _HoldAccum())
            acc.svgms += pa_sv; acc.bp_faced += pa_bpf; acc.bp_saved += pa_bps
        if pb_sv is not None and pb_bpf is not None and pb_bps is not None:
            acc = hold_accum.setdefault((pb, year), _HoldAccum())
            acc.svgms += pb_sv; acc.bp_faced += pb_bpf; acc.bp_saved += pb_bps
        if None not in (pb_bpf, pb_bps, pb_sv):
            r_acc = return_accum.setdefault((pa, year), [0, 0])
            r_acc[0] += (pb_bpf - pb_bps); r_acc[1] += pb_sv
        if None not in (pa_bpf, pa_bps, pa_sv):
            r_acc = return_accum.setdefault((pb, year), [0, 0])
            r_acc[0] += (pa_bpf - pa_bps); r_acc[1] += pa_sv

        for name, won in ((pa, winner == pa), (pb, winner == pb)):
            rec = season_record.setdefault((name, year, surface), [0, 0])
            rec[0 if won else 1] += 1

        h2h_rec2 = h2h_record.setdefault(h2h_key, {})
        h2h_rec2[winner] = h2h_rec2.get(winner, 0) + 1

        if scanned % 50000 == 0:
            print(f"  ...{scanned} scanned, {written} rows written")

    out.close()
    print(f"\nDone. {scanned} real matches scanned, {written} rows written to {OUTPUT_CSV}")
    print("Next: python3 train_xgb_combiner.py")


def _f(v):
    return "" if v is None else f"{v:.6f}"


if __name__ == "__main__":
    run()
