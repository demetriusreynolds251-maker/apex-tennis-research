"""
run_confidence_engine_backtest.py
Real walk-forward backtest of the WHOLE blended confidence_engine.py,
against real Dataset B outcomes, using the real calibration tables
already built and saved to real_calibration_tables.json.

This is the last item on the redesign checklist before anything gets
wired into openclaw_core.py: same rigor ELO itself got before it was
trusted, applied to the new blended engine as a whole.

WHAT THIS DOES:
For every real match, in chronological order:
  1. Computes each of ELO/S5/S1/H2H's raw value using ONLY real state
     built from matches strictly BEFORE this one (same walk-forward,
     no-lookahead discipline as every backtest in this project).
  2. Feeds those raw values + the real calibration tables into the
     real, unmodified compute_moneyline_confidence().
  3. Records the blended probability against the real outcome.
  4. ALSO computes the OLD system's Phase 1 gate decision on the same
     match (dominance_score magnitude >= 8) so the two can be directly
     compared on the same real matches -- this is the concrete,
     measured answer to "does the new engine actually find real plays
     the old gate missed, and is it right when it does."

Run this ON THE MAC MINI, same folder as everything else, with
real_calibration_tables.json already present from the prior step.

USAGE:
    python3 run_confidence_engine_backtest.py
"""
import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elo_calculator import apply_match
from build_signal_calibration import CalibrationBucket, calibrated_probability
from confidence_engine import compute_moneyline_confidence, REAL_WEIGHTS

WAREHOUSE_PATH = "data/warehouse/tennis_warehouse.sqlite"
CALIBRATION_JSON = "real_calibration_tables.json"

MIN_SVGMS_FOR_RATE = 20
SERVE_WEIGHT, RETURN_WEIGHT, CLUTCH_WEIGHT, FORM_WEIGHT = 0.35, 0.25, 0.15, 0.25
ML_S5_CLASSIFICATION_MODERATE_MAGNITUDE = 8  # the real OLD Phase 1 hard-gate threshold
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


def _auc(pairs):
    """Real, efficient rank-based AUC (Mann-Whitney U via rank sums,
    O(n log n)) -- equivalent to the pairwise formulation used
    elsewhere in this project, but tractable at 500K+ real points."""
    pos_n = sum(1 for _, l in pairs if l == 1)
    neg_n = len(pairs) - pos_n
    if pos_n == 0 or neg_n == 0:
        return None
    ordered = sorted(pairs, key=lambda p: p[0])
    n = len(ordered)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and ordered[j][0] == ordered[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j
    rank_sum_pos = sum(ranks[k] for k in range(n) if ordered[k][1] == 1)
    return (rank_sum_pos - pos_n * (pos_n + 1) / 2.0) / (pos_n * neg_n)


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

    ratings = {}                 # ELO: name -> PlayerRating
    hold_accum, return_accum = {}, {}   # S5-specific accumulators
    season_record = {}           # SHARED by S5 form_edge and S1 -- same real quantity
    h2h_record = {}               # frozenset({p1,p2}) -> {name: wins}

    blended_pairs = []           # (blended_probability, label) -- new engine, ALL matches with any signal
    legacy_pairs = []            # (dominance_score, label) -- old Phase 1 gate's own signal, for direct comparison
    legacy_fired_correct = 0
    legacy_fired_total = 0
    new_fired_total = 0          # new engine produced a confident call (outside 45-55%)
    new_fired_correct = 0
    new_found_legacy_missed = 0   # new engine confident, legacy gate did NOT fire -- the direct "found a real play" metric
    new_found_legacy_missed_correct = 0
    conflicts_detected = 0
    too_close_count = 0
    total_with_any_signal = 0

    for row in rows:
        pa, pb, winner, surface, date = row["player_a"], row["player_b"], row["winner"], row["surface"], row["match_date"]
        if winner not in (pa, pb):
            continue
        year = date[:4]
        label_a_won = 1 if winner == pa else 0

        # ── ELO (walk-forward, state BEFORE this match) ──
        p, o = ratings.get(pa), ratings.get(pb)
        elo_gap = None
        if p is not None and o is not None and p.overall_matches > 0 and o.overall_matches > 0:
            elo_gap = p.overall - o.overall

        # ── S5 dominance_score (also = the real OLD Phase 1 gate signal) ──
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
        legacy_fired = False
        if all(v is not None for v in (pa_hold, pb_hold, pa_return, pb_return, pa_bp_save, pb_bp_save, pa_win_pct, pb_win_pct)):
            serve_edge = pa_hold - pb_hold
            return_edge = pa_return - pb_return
            clutch_edge = pa_bp_save - pb_bp_save
            form_edge = pa_win_pct - pb_win_pct
            s5_raw = (SERVE_WEIGHT * serve_edge + RETURN_WEIGHT * return_edge
                      + CLUTCH_WEIGHT * clutch_edge + FORM_WEIGHT * form_edge)
            legacy_pairs.append((s5_raw, label_a_won))
            if abs(s5_raw) >= ML_S5_CLASSIFICATION_MODERATE_MAGNITUDE:
                legacy_fired = True
                legacy_fired_total += 1
                legacy_predicted_a = s5_raw > 0
                if legacy_predicted_a == bool(label_a_won):
                    legacy_fired_correct += 1

        # ── S1 (uses the SAME season_record as S5's form_edge) ──
        s1_raw = None
        if pa_rec and pb_rec and (pa_rec[0] + pa_rec[1]) > 0 and (pb_rec[0] + pb_rec[1]) > 0:
            s1_raw = pa_win_pct - pb_win_pct  # identical real quantity to S5's form_edge

        # ── H2H (derived, walk-forward) ──
        h2h_key = frozenset((pa, pb))
        h2h_rec = h2h_record.get(h2h_key)
        h2h_raw = None
        if h2h_rec is not None:
            pa_wins, pb_wins = h2h_rec.get(pa, 0), h2h_rec.get(pb, 0)
            total = pa_wins + pb_wins
            if total >= MIN_H2H_SAMPLE:
                h2h_raw = 2 * (pa_wins / total) - 1

        # ── Run the real, unmodified engine ──
        if any(v is not None for v in (elo_gap, s5_raw, s1_raw, h2h_raw)):
            total_with_any_signal += 1
            result = compute_moneyline_confidence(
                elo_gap=elo_gap,
                s5_raw=s5_raw, s5_table=s5_table,
                s1_raw=s1_raw, s1_table=s1_table,
                h2h_raw=h2h_raw, h2h_table=h2h_table,
            )
            if result.win_probability is not None:
                blended_pairs.append((result.win_probability, label_a_won))
                if result.conflict_detected:
                    conflicts_detected += 1
                if result.advisory_label is not None:
                    too_close_count += 1
                else:
                    new_fired_total += 1
                    predicted_a = result.win_probability > 0.5
                    correct = predicted_a == bool(label_a_won)
                    if correct:
                        new_fired_correct += 1
                    if not legacy_fired:
                        new_found_legacy_missed += 1
                        if correct:
                            new_found_legacy_missed_correct += 1

        # ── Update all real state AFTER using it ──
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
    print(f"\n{len(rows)} real matches scanned.")
    print(f"{total_with_any_signal} matches had at least one real signal available.\n")

    print("=" * 70)
    print("OLD SYSTEM (Phase 1 hard gate, dominance_score magnitude >= 8)")
    print("=" * 70)
    if legacy_fired_total > 0:
        print(f"  Fired on {legacy_fired_total} real matches")
        print(f"  Accuracy when fired: {legacy_fired_correct / legacy_fired_total * 100:.1f}% ({legacy_fired_correct}/{legacy_fired_total})")
    else:
        print("  Never fired -- check data.")
    legacy_auc = _auc(legacy_pairs)
    print(f"  Real AUC (continuous dominance_score vs outcome, all matches with real S5 data): {legacy_auc:.4f}" if legacy_auc else "  AUC: n/a")

    print("\n" + "=" * 70)
    print("NEW BLENDED ENGINE (confidence_engine.py, real calibration tables)")
    print("=" * 70)
    print(f"  Produced a confident call (outside 45-55%%) on {new_fired_total} real matches")
    if new_fired_total > 0:
        print(f"  Accuracy on those calls: {new_fired_correct / new_fired_total * 100:.1f}% ({new_fired_correct}/{new_fired_total})")
    print(f"  'Too close to call' (45-55%%) on {too_close_count} real matches -- honest, not hidden")
    print(f"  Real conflicts detected (top 2 signals disagree): {conflicts_detected}")
    blended_auc = _auc(blended_pairs)
    print(f"  Real AUC (blended probability vs outcome, all matches with any real signal): {blended_auc:.4f}" if blended_auc else "  AUC: n/a")

    print("\n" + "=" * 70)
    print("DIRECT COMPARISON: real plays the OLD gate would have missed entirely")
    print("=" * 70)
    print(f"  New engine gave a confident call on {new_found_legacy_missed} real matches where the OLD gate did NOT fire")
    if new_found_legacy_missed > 0:
        acc = new_found_legacy_missed_correct / new_found_legacy_missed * 100
        print(f"  Accuracy on THOSE specific matches: {acc:.1f}% ({new_found_legacy_missed_correct}/{new_found_legacy_missed})")
        print("  This is the real, measured answer to the Darderi-style problem: how many")
        print("  real plays existed that the old hard gate silently blocked, and whether")
        print("  the new engine is actually right about them often enough to be worth it.")


if __name__ == "__main__":
    run()
