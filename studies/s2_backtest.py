"""
s2_backtest.py
2026-08-07 — real walk-forward backtest of the LIVE S2 (tournament
form) signal, exact thresholds from signal_s2_tournament_form():
    ML_S2_TOURNAMENT_MODERATE_ROUND_GAP = 1
    ML_S2_TOURNAMENT_STRONG_ROUND_GAP   = 2

Real logic: within THIS SPECIFIC tournament (identified by the real
tourney_id column, more precise than tournament NAME, which can repeat
across different years/editions), how many rounds has each player
already WON before this match. Gap in rounds-won, graduated.

Note: the real production signal counts wins from
v8_get_recent_matches(limit=20) filtered by tournament_id -- this
backtest replicates the same real quantity (rounds won so far in this
event) using tourney_id + chronological match_date within Dataset B,
which is the historical equivalent of that live lookup.

Same walk-forward, no-lookahead discipline as every other backtest
here: a player's "rounds won in this event" state is built up match by
match as the real tournament progresses, never looking ahead.
"""
from elo_ops import _conn
from elo_backtest import _auc

MIN_SAMPLES_FOR_VERDICT = 30
PROMISING_AUC_THRESHOLD = 0.55

ML_S2_TOURNAMENT_MODERATE_ROUND_GAP = 1
ML_S2_TOURNAMENT_STRONG_ROUND_GAP = 2


def _load_raw_matches(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, winner, tourney_id, match_date "
        "FROM matches "
        "WHERE winner IS NOT NULL AND match_date IS NOT NULL AND tourney_id IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def run_s2_backtest():
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_matches(conn)
    finally:
        conn.close()

    rounds_won: dict = {}  # (player, tourney_id) -> count of real wins so far in this event
    gap_pairs = []
    correct = 0
    total_predicted = 0
    skipped_no_prior_data = 0  # both players 0-0 in this event so far -- nothing to measure

    for row in raw:
        pa, pb, winner, tid = row["player_a"], row["player_b"], row["winner"], row["tourney_id"]
        if winner not in (pa, pb):
            continue

        pa_rounds = rounds_won.get((pa, tid), 0)
        pb_rounds = rounds_won.get((pb, tid), 0)

        if pa_rounds == 0 and pb_rounds == 0:
            skipped_no_prior_data += 1
        else:
            gap = pa_rounds - pb_rounds
            label = 1 if winner == pa else 0
            gap_pairs.append((gap, label))
            if abs(gap) >= ML_S2_TOURNAMENT_MODERATE_ROUND_GAP:
                predicted = pa if gap > 0 else pb
                total_predicted += 1
                if predicted == winner:
                    correct += 1

        rounds_won[(winner, tid)] = rounds_won.get((winner, tid), 0) + 1

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
    print(run_s2_backtest())
