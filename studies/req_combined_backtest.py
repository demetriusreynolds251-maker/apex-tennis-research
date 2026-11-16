"""
req_combined_backtest.py
2026-08-07 — real test of props' ACTUAL TG MORE-path gate: REQ1 (both
CONFIRMED extenders) AND REQ2 (CONFIRMED two-sided holding) TOGETHER,
never either alone. Tonight's two individual tests told a mixed story:
REQ1 alone (tg_extension_backtest.py) was negligible/slightly wrong-
direction (r=-0.05). REQ2 alone, tested via the BP angle
(bp_direction_backtest.py), showed a real weak-but-correct-direction
effect on break points. Neither test alone answers the real question,
because props NEVER gates on REQ1 alone -- it requires all four
conditions together. This tests the real joint claim: do matches
where BOTH extend-rate AND hold-rate are genuinely high (the real
"PROVEN competitive" case per the decision tree) show a stronger,
more real relationship with total games than either factor alone?

Real design: walk-forward computes both predictors for every match
(combined extend rate 0-2, combined hold rate 0-1, requiring BOTH
players clear MIN_SVGMS_FOR_RATE), then does a real 2D subgroup
comparison -- tertile x tertile -- comparing average real total games
across NINE real groups (low/mid/high extend x low/mid/high hold),
with special attention to the two corner groups that matter most:
BOTH-HIGH ("PROVEN competitive" per the real doc) vs BOTH-LOW.

Reuses the validated real parsing/math from tonight's other scripts
rather than reimplementing it: _real_total_games() and _pearson_r()
from tg_extension_backtest.py, the hold_pct formula from season_stats.py.
"""
from elo_ops import _conn
from tg_extension_backtest import _real_total_games, _pearson_r

MIN_SAMPLES_FOR_VERDICT = 30
RECENT_WINDOW = 5
MIN_PRIOR_MATCHES = 3
MIN_SVGMS_FOR_RATE = 20


class _Accum:
    __slots__ = ("svgms", "bp_faced", "bp_saved")
    def __init__(self):
        self.svgms = 0
        self.bp_faced = 0
        self.bp_saved = 0

    def hold_pct(self):
        if self.svgms < MIN_SVGMS_FOR_RATE:
            return None
        return 1.0 - ((self.bp_faced - self.bp_saved) / self.svgms)


def _load_raw_rows(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, winner, match_date, score, set_count, best_of, "
        "player_a_svgms, player_a_bp_faced, player_a_bp_saved, "
        "player_b_svgms, player_b_bp_faced, player_b_bp_saved "
        "FROM matches "
        "WHERE winner IS NOT NULL AND match_date IS NOT NULL AND score IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def _tertile_label(value, sorted_values):
    """Real tertile assignment based on the full real distribution of
    values seen (computed once, up front, from all usable values)."""
    n = len(sorted_values)
    lo_cut = sorted_values[n // 3]
    hi_cut = sorted_values[(2 * n) // 3]
    if value <= lo_cut:
        return "LOW"
    elif value <= hi_cut:
        return "MID"
    else:
        return "HIGH"


def run_req_combined_backtest():
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_rows(conn)
    finally:
        conn.close()

    extend_history: dict = {}
    hold_accum: dict = {}  # (player, year) -> _Accum

    # Pass 1: walk-forward, collect (extend_rate, hold_rate, real_total_games) triples
    triples = []
    for row in raw:
        pa, pb, year = row["player_a"], row["player_b"], row["match_date"][:4]
        real_games = _real_total_games(row["score"])

        pa_ext_hist = extend_history.get(pa, [])
        pb_ext_hist = extend_history.get(pb, [])
        pa_hold_acc = hold_accum.get((pa, year))
        pb_hold_acc = hold_accum.get((pb, year))
        pa_hold = pa_hold_acc.hold_pct() if pa_hold_acc else None
        pb_hold = pb_hold_acc.hold_pct() if pb_hold_acc else None

        if (real_games is not None
                and len(pa_ext_hist) >= MIN_PRIOR_MATCHES and len(pb_ext_hist) >= MIN_PRIOR_MATCHES
                and pa_hold is not None and pb_hold is not None):
            pa_rate = sum(pa_ext_hist[-RECENT_WINDOW:]) / len(pa_ext_hist[-RECENT_WINDOW:])
            pb_rate = sum(pb_ext_hist[-RECENT_WINDOW:]) / len(pb_ext_hist[-RECENT_WINDOW:])
            combined_extend = pa_rate + pb_rate  # 0-2
            combined_hold = (pa_hold + pb_hold) / 2  # 0-1
            triples.append((combined_extend, combined_hold, real_games))

        # Update state AFTER using it
        went_the_distance = bool(row["best_of"] and row["set_count"] and row["set_count"] >= row["best_of"])
        extend_history.setdefault(pa, []).append(went_the_distance)
        extend_history.setdefault(pb, []).append(went_the_distance)

        if row["player_a_svgms"] is not None and row["player_a_bp_faced"] is not None and row["player_a_bp_saved"] is not None:
            acc = hold_accum.setdefault((pa, year), _Accum())
            acc.svgms += row["player_a_svgms"]; acc.bp_faced += row["player_a_bp_faced"]; acc.bp_saved += row["player_a_bp_saved"]
        if row["player_b_svgms"] is not None and row["player_b_bp_faced"] is not None and row["player_b_bp_saved"] is not None:
            acc = hold_accum.setdefault((pb, year), _Accum())
            acc.svgms += row["player_b_svgms"]; acc.bp_faced += row["player_b_bp_faced"]; acc.bp_saved += row["player_b_bp_saved"]

    result = {"status": "ok", "total_matches_seen": len(raw), "n_usable_triples": len(triples)}

    if len(triples) < MIN_SAMPLES_FOR_VERDICT:
        result["verdict"] = f"NOT ENOUGH DATA (n={len(triples)})"
        return result

    # Individual correlations, for direct comparison to tonight's separate tests
    extend_pairs = [(e, g) for e, h, g in triples]
    hold_pairs = [(h, g) for e, h, g in triples]
    result["extend_alone_pearson_r"] = round(_pearson_r(extend_pairs), 4)
    result["hold_alone_pearson_r"] = round(_pearson_r(hold_pairs), 4)

    # Real 2D tertile subgroup comparison
    extend_sorted = sorted(e for e, h, g in triples)
    hold_sorted = sorted(h for e, h, g in triples)

    groups: dict = {}
    for e, h, g in triples:
        e_label = _tertile_label(e, extend_sorted)
        h_label = _tertile_label(h, hold_sorted)
        groups.setdefault((e_label, h_label), []).append(g)

    result["group_avg_total_games"] = {
        f"extend_{e}_hold_{h}": {"n": len(games), "avg_total_games": round(sum(games) / len(games), 2)}
        for (e, h), games in sorted(groups.items())
    }

    both_high = groups.get(("HIGH", "HIGH"), [])
    both_low = groups.get(("LOW", "LOW"), [])
    if both_high and both_low:
        result["BOTH_HIGH_avg_games"] = round(sum(both_high) / len(both_high), 2)
        result["BOTH_LOW_avg_games"] = round(sum(both_low) / len(both_low), 2)
        result["BOTH_HIGH_n"] = len(both_high)
        result["BOTH_LOW_n"] = len(both_low)
        gap = (sum(both_high) / len(both_high)) - (sum(both_low) / len(both_low))
        result["real_gap_both_high_minus_both_low"] = round(gap, 2)
        result["combined_verdict"] = ("REAL GAP FOUND — both-high genuinely differs from both-low"
                                       if abs(gap) >= 1.0 else
                                       "NO MEANINGFUL GAP — combining REQ1+REQ2 doesn't separate real total games either")

    return result


if __name__ == "__main__":
    print(run_req_combined_backtest())
