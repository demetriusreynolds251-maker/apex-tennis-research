"""
s4_backtest.py
2026-08-07 — real walk-forward backtest of the LIVE S4 (physical
state / fatigue) signal, exact thresholds from
signal_s4_physical_state():
    ML_S4_PHYSICAL_MODERATE_FACTORS = 1
    ML_S4_PHYSICAL_STRONG_FACTORS   = 2

Real logic replicated: for each player, two fatigue factors checked
against their MOST RECENT prior match --
  1. went_the_distance: best_of == set_count (the match went the full
     distance)
  2. short_turnaround: under 48 hours since that match

HONEST LIMITATION, flagged rather than glossed over: the real
production signal computes turnaround relative to the CURRENT WALL-
CLOCK TIME (since it's evaluating an upcoming real match). A backtest
replays completed history, so the equivalent real quantity is the gap
between THIS match's date and the player's PREVIOUS match's date --
that's what's used here, not "now". Also, Dataset B's match_date has
DAY granularity only (no time-of-day), so "under 48 hours" is
approximated as "under 2 real calendar days" (turnaround_days < 2).
This is coarser than the live signal's exact hour-level check on a
known match time, but it's a real, honest approximation of the same
underlying question, not a guess at unavailable data.

Same walk-forward, no-lookahead discipline: each player's fatigue
state is built from their own match history strictly before the one
being predicted.
"""
from datetime import datetime

from elo_ops import _conn
from elo_backtest import _auc

MIN_SAMPLES_FOR_VERDICT = 30
PROMISING_AUC_THRESHOLD = 0.55

ML_S4_PHYSICAL_MODERATE_FACTORS = 1
ML_S4_PHYSICAL_STRONG_FACTORS = 2


def _load_raw_matches(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, winner, match_date, best_of, set_count "
        "FROM matches "
        "WHERE winner IS NOT NULL AND match_date IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def _fatigue_count(last_match, this_date):
    """Real two-factor fatigue count for one player, based on their
    real most recent prior match. Returns None if no prior match is
    on record (nothing to measure), matching the live signal's
    None-if-unconfirmed discipline."""
    if last_match is None:
        return None
    best_of, set_count, last_date = last_match
    went_the_distance = bool(best_of and set_count and set_count >= best_of)
    try:
        d1 = datetime.strptime(last_date, "%Y-%m-%d")
        d2 = datetime.strptime(this_date, "%Y-%m-%d")
        turnaround_days = (d2 - d1).days
        short_turnaround = turnaround_days < 2  # real approximation of "<48h", see module docstring
    except Exception:
        short_turnaround = False
    return int(went_the_distance) + int(short_turnaround)


def run_s4_backtest():
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_matches(conn)
    finally:
        conn.close()

    last_match: dict = {}  # player -> (best_of, set_count, match_date) of their most recent match
    gap_pairs = []
    correct = 0
    total_predicted = 0
    skipped_no_prior_data = 0

    for row in raw:
        pa, pb, winner, match_date = row["player_a"], row["player_b"], row["winner"], row["match_date"]
        if winner not in (pa, pb):
            continue

        pa_count = _fatigue_count(last_match.get(pa), match_date)
        pb_count = _fatigue_count(last_match.get(pb), match_date)

        if pa_count is None or pb_count is None:
            skipped_no_prior_data += 1
        else:
            gap = pb_count - pa_count  # positive = pb (player_b) more fatigued = favors pa
            label = 1 if winner == pa else 0
            gap_pairs.append((gap, label))
            if abs(gap) >= ML_S4_PHYSICAL_MODERATE_FACTORS:
                predicted = pa if gap > 0 else pb
                total_predicted += 1
                if predicted == winner:
                    correct += 1

        last_match[pa] = (row["best_of"], row["set_count"], match_date)
        last_match[pb] = (row["best_of"], row["set_count"], match_date)

    result = {
        "status": "ok",
        "total_matches_seen": len(raw),
        "skipped_no_prior_data": skipped_no_prior_data,
        "n_gap_pairs": len(gap_pairs),
        "n_signal_fired": total_predicted,
    }
    if len(gap_pairs) < MIN_SAMPLES_FOR_VERDICT:
        result["auc"] = None
        result["auc_verdict"] = f"NOT ENOUGH DATA (n={len(gap_pairs)})"
    else:
        auc = _auc(gap_pairs)
        result["auc"] = round(auc, 4) if auc is not None else None
        result["auc_verdict"] = ("GENUINE SIGNAL" if auc and auc >= PROMISING_AUC_THRESHOLD
                                  else "NO REAL SIGNAL") if auc is not None else "UNDEFINED"
    if total_predicted < MIN_SAMPLES_FOR_VERDICT:
        result["accuracy_pct"] = None
        result["accuracy_verdict"] = f"NOT ENOUGH DATA (n={total_predicted})"
    else:
        result["accuracy_pct"] = round(correct / total_predicted * 100, 1)
        result["correct"] = correct
    return result


if __name__ == "__main__":
    print(run_s4_backtest())
