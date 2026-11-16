"""
rule30_props_backtest.py
2026-08-07 — real walk-forward test of props' Rule 30 (rest-day
deduction), confirmed from DEMETRIUS_PROPS_DECISION_TREE.txt:
24-48h turnaround = -4% confidence, 48h+ = 0% (no deduction), <24h =
full CFEF suppression.

GENUINELY DIFFERENT QUESTION from moneyline's S4 test (which asked
"does turnaround predict WHO WINS" and found no real signal, AUC
0.51). Props' Rule 30 is about STAT-LINE PERFORMANCE, not win/loss --
does a short turnaround predict a player hitting FEWER real aces or
playing FEWER real total games, independent of whether they win?
This is a real, separate hypothesis, not assumed dead just because
S4's different question came back null.

Tests turnaround against TWO real targets separately: real aces hit
(now available after tonight's enrichment fix) and real total games
in the match (available since the TG test). Continuous predictor (no
arbitrary 24h/48h cutoff baked in) -- reports the raw correlation
first, so the real Rule 30 thresholds can be evaluated against
whatever the real relationship actually looks like, not assumed to
match the current cutoffs.

Same walk-forward, no-lookahead discipline, same real
_real_total_games()/_pearson_r() helpers already validated tonight.
"""
from datetime import datetime

from elo_ops import _conn
from tg_extension_backtest import _real_total_games, _pearson_r

MIN_SAMPLES_FOR_VERDICT = 30


def _load_raw_rows(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, match_date, score, player_a_aces, player_b_aces "
        "FROM matches "
        "WHERE match_date IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def _days_between(d1_str, d2_str):
    d1 = datetime.strptime(d1_str, "%Y-%m-%d")
    d2 = datetime.strptime(d2_str, "%Y-%m-%d")
    return (d2 - d1).days


def _verdict(pairs, label):
    n = len(pairs)
    if n < MIN_SAMPLES_FOR_VERDICT:
        return {"label": label, "n": n, "pearson_r": None, "verdict": f"NOT ENOUGH DATA (n={n})"}
    r = _pearson_r(pairs)
    if r is None:
        return {"label": label, "n": n, "pearson_r": None, "verdict": "UNDEFINED (zero variance)"}
    abs_r = abs(r)
    if abs_r < 0.1:
        strength = "NEGLIGIBLE"
    elif abs_r < 0.3:
        strength = "WEAK"
    elif abs_r < 0.5:
        strength = "MODERATE"
    else:
        strength = "STRONG"
    # Real expected direction: MORE rest (higher turnaround_days) should
    # predict BETTER real performance (more aces, more competitive/longer
    # games) -- i.e. a POSITIVE correlation is the direction Rule 30 assumes.
    direction = ("direction matches Rule 30's assumption (more rest -> better real performance)"
                 if r > 0 else
                 "OPPOSITE of Rule 30's assumption")
    return {"label": label, "n": n, "pearson_r": round(r, 4), "verdict": f"{strength} — {direction}"}


def run_rule30_props_backtest():
    """
    For each match, for EACH player (pooled, both sides contribute a
    real data point): predictor = real days since that player's
    previous match (walk-forward, no cap/threshold); targets = their
    REAL aces hit (when available) and the match's REAL total games
    (shared across both players in that match, so counted once per
    player-side pairing with their own turnaround).
    """
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_rows(conn)
    finally:
        conn.close()

    last_match_date: dict = {}
    turnaround_vs_aces = []
    turnaround_vs_games = []

    for row in raw:
        pa, pb, date, score = row["player_a"], row["player_b"], row["match_date"], row["score"]
        real_games = _real_total_games(score)
        pa_aces, pb_aces = row["player_a_aces"], row["player_b_aces"]

        pa_last = last_match_date.get(pa)
        pb_last = last_match_date.get(pb)

        if pa_last:
            pa_turnaround = _days_between(pa_last, date)
            if pa_aces is not None:
                turnaround_vs_aces.append((pa_turnaround, pa_aces))
            if real_games is not None:
                turnaround_vs_games.append((pa_turnaround, real_games))
        if pb_last:
            pb_turnaround = _days_between(pb_last, date)
            if pb_aces is not None:
                turnaround_vs_aces.append((pb_turnaround, pb_aces))
            if real_games is not None:
                turnaround_vs_games.append((pb_turnaround, real_games))

        last_match_date[pa] = date
        last_match_date[pb] = date

    return {
        "status": "ok",
        "total_matches_seen": len(raw),
        "turnaround_vs_real_aces": _verdict(turnaround_vs_aces, "turnaround_days -> real aces"),
        "turnaround_vs_real_total_games": _verdict(turnaround_vs_games, "turnaround_days -> real total games"),
    }


if __name__ == "__main__":
    print(run_rule30_props_backtest())
