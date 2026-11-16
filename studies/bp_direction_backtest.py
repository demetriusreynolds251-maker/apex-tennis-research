"""
bp_direction_backtest.py
2026-08-07 — real walk-forward test of props' Break Points direction
rule, confirmed from DEMETRIUS_PROPS_DECISION_TREE.txt: BP MORE keys
off the OPPONENT's hold rate (Q1, highest weight) -- a low opponent
hold rate ("fragility zone", <70%) should predict MORE real break
points won by the backed player.

Real target: like the TG extension test, this is CONTINUOUS (real
break points won by a player in a specific match), not binary -- so
this uses Pearson correlation, same as tg_extension_backtest.py, not
AUC.

Walk-forward, no lookahead: replays season_stats.py's accumulation
logic itself (not its final-state output) so each match only ever
sees the OPPONENT's hold rate as it stood BEFORE that match.
"""
from elo_ops import _conn
from elo_backtest import _auc  # unused here but keeps import style consistent if extended
from tg_extension_backtest import _pearson_r

MIN_SAMPLES_FOR_VERDICT = 30
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
        "SELECT player_a, player_b, match_date, "
        "player_a_svgms, player_a_bp_faced, player_a_bp_saved, "
        "player_b_svgms, player_b_bp_faced, player_b_bp_saved "
        "FROM matches "
        "WHERE match_date IS NOT NULL "
        "AND player_a_svgms IS NOT NULL AND player_a_bp_faced IS NOT NULL AND player_a_bp_saved IS NOT NULL "
        "AND player_b_svgms IS NOT NULL AND player_b_bp_faced IS NOT NULL AND player_b_bp_saved IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def run_bp_direction_backtest():
    """
    For each real match, computes: opponent's PRE-match season hold_pct
    (walk-forward), and the REAL break points the backed player won in
    THIS specific match (opponent's bp_faced - bp_saved, from this
    match's own row -- a real, directly observed number, no aggregation
    needed for the outcome side). Correlates the two: does a LOWER
    opponent hold rate predict MORE real break points won?

    Reports r for BOTH directions of the matchup (player_a's real BPs
    won vs player_b's pre-match hold rate, and vice versa) combined
    into one real pooled sample, since the underlying claim is
    symmetric (works the same for either player in a match).
    """
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_rows(conn)
    finally:
        conn.close()

    accum: dict = {}  # (player, year) -> _Accum
    pairs = []  # (opponent_hold_pct, real_bp_won_by_backed_player)

    for row in raw:
        pa, pb, year = row["player_a"], row["player_b"], row["match_date"][:4]
        pa_acc = accum.setdefault((pa, year), _Accum())
        pb_acc = accum.setdefault((pb, year), _Accum())

        pa_sv, pa_bpf, pa_bps = row["player_a_svgms"], row["player_a_bp_faced"], row["player_a_bp_saved"]
        pb_sv, pb_bpf, pb_bps = row["player_b_svgms"], row["player_b_bp_faced"], row["player_b_bp_saved"]

        pa_hold_before = pa_acc.hold_pct()
        pb_hold_before = pb_acc.hold_pct()

        # Real break points won THIS match: player_a's real BPs won =
        # player_b's real bp_faced minus bp_saved IN THIS MATCH (not
        # aggregated) -- a direct, real, observed number.
        pa_real_bp_won_this_match = pb_bpf - pb_bps
        pb_real_bp_won_this_match = pa_bpf - pa_bps

        # player_a backed: predictor = OPPONENT (pb)'s pre-match hold rate
        if pb_hold_before is not None:
            pairs.append((pb_hold_before, pa_real_bp_won_this_match))
        # player_b backed: predictor = OPPONENT (pa)'s pre-match hold rate
        if pa_hold_before is not None:
            pairs.append((pa_hold_before, pb_real_bp_won_this_match))

        pa_acc.svgms += pa_sv; pa_acc.bp_faced += pa_bpf; pa_acc.bp_saved += pa_bps
        pb_acc.svgms += pb_sv; pb_acc.bp_faced += pb_bpf; pb_acc.bp_saved += pb_bps

    result = {"status": "ok", "total_matches_seen": len(raw), "n_usable_pairs": len(pairs)}

    if len(pairs) < MIN_SAMPLES_FOR_VERDICT:
        result["pearson_r"] = None
        result["verdict"] = f"NOT ENOUGH DATA (n={len(pairs)})"
        return result

    r = _pearson_r(pairs)
    if r is None:
        result["pearson_r"] = None
        result["verdict"] = "UNDEFINED (zero variance)"
        return result

    result["pearson_r"] = round(r, 4)
    # Real, expected direction is NEGATIVE: lower opponent hold_pct
    # should correlate with MORE real break points won by the backed
    # player. A positive r would mean the rule points the wrong way.
    abs_r = abs(r)
    if abs_r < 0.1:
        strength = "NEGLIGIBLE"
    elif abs_r < 0.3:
        strength = "WEAK"
    elif abs_r < 0.5:
        strength = "MODERATE"
    else:
        strength = "STRONG"
    direction = "CORRECT direction (lower opponent hold -> more real BPs won)" if r < 0 else "WRONG direction (opposite of props' rule)"
    result["verdict"] = f"{strength} — {direction}"

    sorted_pairs = sorted(pairs, key=lambda p: p[0])
    q = max(1, len(sorted_pairs) // 4)
    low_hold_quartile_bp = [bp for _, bp in sorted_pairs[:q]]   # opponent hold rate LOW (fragile) -> should see MORE real BPs won
    high_hold_quartile_bp = [bp for _, bp in sorted_pairs[-q:]]  # opponent hold rate HIGH (tough) -> should see FEWER
    result["avg_real_bp_won_when_opponent_hold_LOW"] = round(sum(low_hold_quartile_bp) / len(low_hold_quartile_bp), 3)
    result["avg_real_bp_won_when_opponent_hold_HIGH"] = round(sum(high_hold_quartile_bp) / len(high_hold_quartile_bp), 3)

    return result


if __name__ == "__main__":
    print(run_bp_direction_backtest())
