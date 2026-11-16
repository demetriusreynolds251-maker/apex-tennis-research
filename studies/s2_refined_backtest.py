"""
s2_refined_backtest.py
2026-08-07 — real refinement to S2 (tournament form), tried before
deciding to retire it. Original s2_backtest.py tested the signal as
a blanket rule across all matches and found no real signal (AUC
0.4863 post-fix). Real "hot hand" research found momentum effects,
where they exist at all, tend to concentrate specifically when the
two competitors are closely matched -- a real gap wouldn't be
expected to matter when one player is simply much better regardless
of recent rounds won. This script re-tests S2's round-win-gap ONLY
among closely-matched pairs, at a few different closeness thresholds.

HONEST METHODOLOGICAL LIMITATION, flagged rather than hidden: "closely
matched" here is determined using each player's FINAL, fully-rebuilt
overall ELO rating (from the player_elo table) -- not a true point-in-
time historical rating as of the match date. Using the final rating to
decide which matches to INCLUDE in this exploratory subset is a mild
lookahead for the FILTER criterion only -- it does NOT affect the
labels or the round-win-gap calculation itself, which remain fully
walk-forward and correct. This is an acceptable simplification for
exploratory research (does a conditional effect exist at all) but
would need real point-in-time ELO snapshots before this could be
trusted as a real, production-grade backtest.
"""
from elo_ops import _conn
from elo_backtest import _auc

MIN_SAMPLES_FOR_VERDICT = 30
PROMISING_AUC_THRESHOLD = 0.55

ML_S2_TOURNAMENT_MODERATE_ROUND_GAP = 1

CLOSENESS_THRESHOLDS = [100, 150, 200]  # real ELO rating-point gaps to test


def _load_elo_ratings(conn):
    rows = conn.execute("SELECT player, overall_rating FROM player_elo").fetchall()
    return {r[0]: r[1] for r in rows}


def _load_raw_matches(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, winner, tourney_id, match_date "
        "FROM matches "
        "WHERE winner IS NOT NULL AND match_date IS NOT NULL AND tourney_id IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def run_s2_refined_backtest():
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        elo = _load_elo_ratings(conn)
        raw = _load_raw_matches(conn)
    finally:
        conn.close()

    rounds_won: dict = {}
    # one gap_pairs list per closeness threshold, built simultaneously
    gap_pairs_by_threshold = {t: [] for t in CLOSENESS_THRESHOLDS}

    for row in raw:
        pa, pb, winner, tid = row["player_a"], row["player_b"], row["winner"], row["tourney_id"]
        if winner not in (pa, pb):
            continue

        pa_rounds = rounds_won.get((pa, tid), 0)
        pb_rounds = rounds_won.get((pb, tid), 0)

        if not (pa_rounds == 0 and pb_rounds == 0):
            pa_elo = elo.get(pa)
            pb_elo = elo.get(pb)
            if pa_elo is not None and pb_elo is not None:
                elo_gap = abs(pa_elo - pb_elo)
                round_gap = pa_rounds - pb_rounds
                label = 1 if winner == pa else 0
                for threshold in CLOSENESS_THRESHOLDS:
                    if elo_gap <= threshold:
                        gap_pairs_by_threshold[threshold].append((round_gap, label))

        rounds_won[(winner, tid)] = rounds_won.get((winner, tid), 0) + 1

    def _verdict(pairs, label):
        n = len(pairs)
        if n < MIN_SAMPLES_FOR_VERDICT:
            return {"label": label, "n": n, "auc": None, "verdict": f"NOT ENOUGH DATA (n={n})"}
        auc = _auc(pairs)
        if auc is None:
            return {"label": label, "n": n, "auc": None, "verdict": "UNDEFINED"}
        v = "GENUINE SIGNAL" if auc >= PROMISING_AUC_THRESHOLD else "NO REAL SIGNAL"
        return {"label": label, "n": n, "auc": round(auc, 4), "verdict": v}

    result = {"status": "ok", "total_matches_seen": len(raw)}
    for threshold in CLOSENESS_THRESHOLDS:
        key = f"closeness_within_{threshold}_elo_pts"
        result[key] = _verdict(gap_pairs_by_threshold[threshold], key)
    return result


if __name__ == "__main__":
    print(run_s2_refined_backtest())
