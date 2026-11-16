"""
confidence_band_breakdown.py
Breaks the new blended engine's real accuracy down by CONFIDENCE
BAND, checked against the real PrizePicks breakeven (65.83%). This
answers the open question from the last run: the aggregate 69.8%
accuracy blends weak confident calls (just past 55%) with strong ones
(near 95%) -- this checks whether the weak end is actually profitable
on its own, or riding on the strong end's coattails.

Same real walk-forward logic as run_confidence_engine_backtest.py
(not reimplemented differently -- copied verbatim so the comparison
is apples-to-apples), just with band-level bucketing added.

USAGE:
    python3 confidence_band_breakdown.py
"""
import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elo_calculator import apply_match
from build_signal_calibration import CalibrationBucket
from confidence_engine import compute_moneyline_confidence

WAREHOUSE_PATH = "data/warehouse/tennis_warehouse.sqlite"
CALIBRATION_JSON = "real_calibration_tables.json"

MIN_SVGMS_FOR_RATE = 20
SERVE_WEIGHT, RETURN_WEIGHT, CLUTCH_WEIGHT, FORM_WEIGHT = 0.35, 0.25, 0.15, 0.25
MIN_H2H_SAMPLE = 3

REAL_BREAKEVEN = 0.6583  # PrizePicks 6-pick Flex, established earlier this session

# Confidence bands: (low, high) on the CONFIDENCE scale (max(p, 1-p)),
# i.e. distance from a coin flip, not raw probability. 45-55% is
# already excluded (that's the "too close to call" advisory range).
BANDS = [
    (0.55, 0.65), (0.65, 0.75), (0.75, 0.85), (0.85, 0.95), (0.95, 1.01),
]


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

    print("Real distinct 'source' values on file, with counts:")
    for r in conn.execute("SELECT source, COUNT(*) FROM matches GROUP BY source ORDER BY COUNT(*) DESC"):
        print(f"  {r[0]!r}: {r[1]} real rows")
    print()

    rows = conn.execute(
        "SELECT player_a, player_b, winner, surface, match_date, source, "
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

    # band_key -> [n, correct]
    band_stats = {band: [0, 0] for band in BANDS}
    # (band_key, source) -> [n, correct] -- the real question: which source is filling which band
    band_source_stats = {}

    for row in rows:
        pa, pb, winner, surface, date, source = row["player_a"], row["player_b"], row["winner"], row["surface"], row["match_date"], row["source"]
        if winner not in (pa, pb):
            continue
        year = date[:4]
        label_a_won = 1 if winner == pa else 0

        p, o = ratings.get(pa), ratings.get(pb)
        elo_gap = None
        if p is not None and o is not None and p.overall_matches > 0 and o.overall_matches > 0:
            elo_gap = p.overall - o.overall

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

        s1_raw = None
        if pa_rec and pb_rec and (pa_rec[0] + pa_rec[1]) > 0 and (pb_rec[0] + pb_rec[1]) > 0:
            s1_raw = pa_win_pct - pb_win_pct

        h2h_key = frozenset((pa, pb))
        h2h_rec = h2h_record.get(h2h_key)
        h2h_raw = None
        if h2h_rec is not None:
            pa_wins, pb_wins = h2h_rec.get(pa, 0), h2h_rec.get(pb, 0)
            total = pa_wins + pb_wins
            if total >= MIN_H2H_SAMPLE:
                h2h_raw = 2 * (pa_wins / total) - 1

        if any(v is not None for v in (elo_gap, s5_raw, s1_raw, h2h_raw)):
            result = compute_moneyline_confidence(
                elo_gap=elo_gap,
                s5_raw=s5_raw, s5_table=s5_table,
                s1_raw=s1_raw, s1_table=s1_table,
                h2h_raw=h2h_raw, h2h_table=h2h_table,
            )
            if result.win_probability is not None and result.advisory_label is None:
                confidence = max(result.win_probability, 1 - result.win_probability)
                predicted_a = result.win_probability > 0.5
                correct = predicted_a == bool(label_a_won)
                for band in BANDS:
                    if band[0] <= confidence < band[1]:
                        band_stats[band][0] += 1
                        if correct:
                            band_stats[band][1] += 1
                        key = (band, source)
                        if key not in band_source_stats:
                            band_source_stats[key] = [0, 0]
                        band_source_stats[key][0] += 1
                        if correct:
                            band_source_stats[key][1] += 1
                        break

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

    # ── Report ──
    print("\n" + "=" * 78)
    print("REAL ACCURACY BY CONFIDENCE BAND vs REAL BREAKEVEN (65.83%)")
    print("=" * 78)
    header = f"{'BAND':<14} {'N':>8} {'CORRECT':>9} {'ACCURACY':>10} {'vs BREAKEVEN':>14}"
    print(header)
    print("-" * len(header))
    for band in BANDS:
        n, correct = band_stats[band]
        label = f"{band[0]*100:.0f}-{min(band[1],1.0)*100:.0f}%"
        if n == 0:
            print(f"{label:<14} {n:>8} {'--':>9} {'n/a':>10} {'n/a':>14}")
            continue
        acc = correct / n
        verdict = "CLEARS breakeven" if acc >= REAL_BREAKEVEN else "BELOW breakeven"
        print(f"{label:<14} {n:>8} {correct:>9} {acc*100:>9.1f}% {verdict:>14}")

    print("\nReal breakeven for PrizePicks 6-pick Flex: 65.83% per leg.")
    print("Any band showing BELOW breakeven is, on its own, not a profitable real bet")
    print("at that confidence level -- even if the aggregate across all bands clears it.")

    print("\n" + "=" * 78)
    print("SAME BANDS, BROKEN DOWN BY REAL SOURCE (which data actually fills each band)")
    print("=" * 78)
    for band in BANDS:
        label = f"{band[0]*100:.0f}-{min(band[1],1.0)*100:.0f}%"
        print(f"\n  Band {label}:")
        sources_in_band = {src: stats for (b, src), stats in band_source_stats.items() if b == band}
        if not sources_in_band:
            print("    (no matches)")
            continue
        for src, (n, correct) in sorted(sources_in_band.items(), key=lambda x: -x[1][0]):
            acc = correct / n * 100 if n else 0
            print(f"    source={src!r:<20} n={n:>6}  accuracy={acc:.1f}%")


if __name__ == "__main__":
    run()
