"""
ace_direction_backtest.py
2026-08-07 — real walk-forward test of props' Aces direction rule,
confirmed from DEMETRIUS_PROPS_DECISION_TREE.txt: MORE if confirmed
season/surface ace average is ABOVE the prop line, LESS if below.

Real target: like the TG and BP tests, this is CONTINUOUS (real aces
hit in a specific match), not binary -- Pearson correlation, not AUC.

Real predictor: each player's own season-to-date average aces per
match (walk-forward, no lookahead) -- simpler than the BP test since
this rule is about the PLAYER's own serving power, not the opponent.

Only usable now because historical_match_enrichment.py's 2026-08-07
update finally populated player_a/b_aces for historical rows (real
coverage: 256,504/531,403, ~48%) -- this test was blocked before that.
"""
from elo_ops import _conn
from tg_extension_backtest import _pearson_r

MIN_SAMPLES_FOR_VERDICT = 30
MIN_MATCHES_FOR_RATE = 5  # real prior matches with aces data required to trust a season average


class _AceAccum:
    __slots__ = ("total_aces", "n_matches")
    def __init__(self):
        self.total_aces = 0
        self.n_matches = 0

    def avg_aces(self):
        if self.n_matches < MIN_MATCHES_FOR_RATE:
            return None
        return self.total_aces / self.n_matches


def _load_raw_rows(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, match_date, player_a_aces, player_b_aces "
        "FROM matches "
        "WHERE match_date IS NOT NULL "
        "AND player_a_aces IS NOT NULL AND player_b_aces IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def run_ace_direction_backtest():
    """
    For each match, for EACH player (pooled together, both sides
    contribute a real data point): predictor = that player's real
    season-to-date average aces per match (pre-match, walk-forward);
    target = their REAL aces actually hit in THIS match. Real, direct
    test of the exact claim props' aces rule depends on.
    """
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_rows(conn)
    finally:
        conn.close()

    accum: dict = {}  # (player, year) -> _AceAccum
    pairs = []  # (season_avg_aces_pre_match, real_aces_this_match)

    for row in raw:
        pa, pb, year = row["player_a"], row["player_b"], row["match_date"][:4]
        pa_aces_real, pb_aces_real = row["player_a_aces"], row["player_b_aces"]

        pa_acc = accum.get((pa, year))
        pb_acc = accum.get((pb, year))
        pa_avg_before = pa_acc.avg_aces() if pa_acc else None
        pb_avg_before = pb_acc.avg_aces() if pb_acc else None

        if pa_avg_before is not None:
            pairs.append((pa_avg_before, pa_aces_real))
        if pb_avg_before is not None:
            pairs.append((pb_avg_before, pb_aces_real))

        pa_acc = accum.setdefault((pa, year), _AceAccum())
        pa_acc.total_aces += pa_aces_real
        pa_acc.n_matches += 1
        pb_acc = accum.setdefault((pb, year), _AceAccum())
        pb_acc.total_aces += pb_aces_real
        pb_acc.n_matches += 1

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
    abs_r = abs(r)
    if abs_r < 0.1:
        strength = "NEGLIGIBLE"
    elif abs_r < 0.3:
        strength = "WEAK"
    elif abs_r < 0.5:
        strength = "MODERATE"
    else:
        strength = "STRONG"
    direction = "CORRECT direction (higher season avg -> more real aces)" if r > 0 else "WRONG direction (opposite of props' rule)"
    result["verdict"] = f"{strength} — {direction}"

    sorted_pairs = sorted(pairs, key=lambda p: p[0])
    q = max(1, len(sorted_pairs) // 4)
    low_avg_quartile = [a for _, a in sorted_pairs[:q]]
    high_avg_quartile = [a for _, a in sorted_pairs[-q:]]
    result["avg_real_aces_when_season_avg_LOW"] = round(sum(low_avg_quartile) / len(low_avg_quartile), 3)
    result["avg_real_aces_when_season_avg_HIGH"] = round(sum(high_avg_quartile) / len(high_avg_quartile), 3)

    return result


if __name__ == "__main__":
    print(run_ace_direction_backtest())
