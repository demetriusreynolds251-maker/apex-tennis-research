"""
s4_refined_backtest.py
2026-08-07 — real refinements to S4 (fatigue), tried before deciding
to retire it. Original s4_backtest.py tested the EXACT live signal
(2-factor, fixed <48h threshold, single most-recent match only) and
found no real signal (AUC 0.5106 post-fix). This script tests two
research-motivated alternatives, both walk-forward/no-lookahead like
everything else:

  1. CONTINUOUS turnaround gap (days since each player's last match,
     no arbitrary 48h cutoff at all) -- tests whether ANY real
     relationship exists between rest and outcome, independent of
     where the original signal happened to draw its threshold.

  2. CUMULATIVE recent load (total real matches played in a trailing
     N-day window, not just the single most recent match) -- real
     NBA "match congestion" research found fatigue effects show up
     more from piling up several games close together than from one
     prior game alone. Tested at N=7 and N=14 days.

None of these are guaranteed to work -- this is honest exploration,
same bar-clearing discipline as everything else (PROMISING_AUC_
THRESHOLD=0.55, MIN_SAMPLES=30) before anything gets proposed as a
real signal change.
"""
from datetime import datetime

from elo_ops import _conn
from elo_backtest import _auc

MIN_SAMPLES_FOR_VERDICT = 30
PROMISING_AUC_THRESHOLD = 0.55


def _load_raw_matches(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, winner, match_date "
        "FROM matches WHERE winner IS NOT NULL AND match_date IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def _days_between(d1_str, d2_str):
    d1 = datetime.strptime(d1_str, "%Y-%m-%d")
    d2 = datetime.strptime(d2_str, "%Y-%m-%d")
    return (d2 - d1).days


def run_s4_refined_backtest():
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_matches(conn)
    finally:
        conn.close()

    last_match_date: dict = {}       # player -> their most recent match date
    match_history: dict = {}         # player -> list of all their past match dates (chronological)

    turnaround_pairs = []
    load7_pairs = []
    load14_pairs = []

    for row in raw:
        pa, pb, winner, date = row["player_a"], row["player_b"], row["winner"], row["match_date"]
        if winner not in (pa, pb):
            continue
        label = 1 if winner == pa else 0

        # Variant 1: continuous turnaround gap (no threshold)
        pa_last = last_match_date.get(pa)
        pb_last = last_match_date.get(pb)
        if pa_last and pb_last:
            pa_turnaround = _days_between(pa_last, date)
            pb_turnaround = _days_between(pb_last, date)
            gap = pa_turnaround - pb_turnaround  # positive = pa had MORE rest = favors pa
            turnaround_pairs.append((gap, label))

        # Variant 2/3: cumulative match load in trailing 7/14-day windows
        pa_hist = match_history.get(pa, [])
        pb_hist = match_history.get(pb, [])
        if pa_hist and pb_hist:
            pa_load7 = sum(1 for d in pa_hist if _days_between(d, date) <= 7)
            pb_load7 = sum(1 for d in pb_hist if _days_between(d, date) <= 7)
            load7_pairs.append((pb_load7 - pa_load7, label))  # positive = pb played more = favors pa

            pa_load14 = sum(1 for d in pa_hist if _days_between(d, date) <= 14)
            pb_load14 = sum(1 for d in pb_hist if _days_between(d, date) <= 14)
            load14_pairs.append((pb_load14 - pa_load14, label))

        last_match_date[pa] = date
        last_match_date[pb] = date
        match_history.setdefault(pa, []).append(date)
        match_history.setdefault(pb, []).append(date)

    def _verdict(pairs, label):
        n = len(pairs)
        if n < MIN_SAMPLES_FOR_VERDICT:
            return {"label": label, "n": n, "auc": None, "verdict": f"NOT ENOUGH DATA (n={n})"}
        auc = _auc(pairs)
        if auc is None:
            return {"label": label, "n": n, "auc": None, "verdict": "UNDEFINED"}
        v = "GENUINE SIGNAL" if auc >= PROMISING_AUC_THRESHOLD else "NO REAL SIGNAL"
        return {"label": label, "n": n, "auc": round(auc, 4), "verdict": v}

    return {
        "status": "ok",
        "total_matches_seen": len(raw),
        "turnaround_continuous": _verdict(turnaround_pairs, "continuous turnaround gap"),
        "cumulative_load_7d": _verdict(load7_pairs, "cumulative load, 7-day window"),
        "cumulative_load_14d": _verdict(load14_pairs, "cumulative load, 14-day window"),
    }


if __name__ == "__main__":
    print(run_s4_refined_backtest())
