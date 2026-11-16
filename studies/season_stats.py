"""
season_stats.py
2026-08-07 — real, walk-forward season-to-date hold%/break%/bp-save%
per player, derived from the real box-score columns
(player_a/b_svgms, bp_faced, bp_saved) that historical_match_enrichment.py
already populated. This is the one shared building block that unlocks
TWO pending real tests: S5's dominance_score formula (confirmed from
compute_ml_dominance_score() this session: 0.35*hold_gap + 0.25*
break_gap + 0.15*bp_save_gap + 0.25*win_gap) and props' BP direction
rule (keyed on the OPPONENT's season hold rate).

Real derivations, standard tennis-analytics convention (same one
Sackmann-style archives use):
  hold_pct   = 1 - (bp_faced - bp_saved) / svgms          [own serving]
  break_pct  = 1 - (opp_bp_faced - opp_bp_saved) / opp_svgms, INVERTED
               -- i.e. breaks THIS player achieved / opponent's real
               return-games-faced. Computed from the OTHER side's row
               in the same match (a player's return dominance is the
               opponent's serve vulnerability, there is no separate
               "return" box-score column to pull this from directly).
  bp_save_pct = bp_saved / bp_faced                        [own serving]

WALK-FORWARD, no lookahead: for any match, a player's season-to-date
rate is built ONLY from real matches strictly before that one, in the
same calendar year. A minimum real service-games floor
(MIN_SVGMS_FOR_RATE) gates when a rate is trusted at all -- a rate
built on 2 real service games is not a real season rate.
"""
from elo_ops import _conn

MIN_SVGMS_FOR_RATE = 20  # roughly 2-3 real matches' worth of service games


class _PlayerYearAccum:
    __slots__ = ("svgms", "bp_faced", "bp_saved", "opp_svgms_faced",
                 "opp_bp_faced_by_me", "opp_bp_saved_by_opp")

    def __init__(self):
        self.svgms = 0
        self.bp_faced = 0
        self.bp_saved = 0
        # For break_pct: sum of the OPPONENT's svgms across matches
        # (= this player's own return games played), and the real
        # breaks this player achieved (opponent's bp_faced - bp_saved
        # in each of those matches).
        self.opp_svgms_faced = 0
        self.opp_bp_faced_by_me = 0  # opponent's bp_faced, summed
        self.opp_bp_saved_by_opp = 0  # opponent's bp_saved, summed

    def hold_pct(self):
        if self.svgms < MIN_SVGMS_FOR_RATE:
            return None
        breaks_against = self.bp_faced - self.bp_saved
        return 1.0 - (breaks_against / self.svgms)

    def break_pct(self):
        if self.opp_svgms_faced < MIN_SVGMS_FOR_RATE:
            return None
        breaks_achieved = self.opp_bp_faced_by_me - self.opp_bp_saved_by_opp
        return breaks_achieved / self.opp_svgms_faced

    def bp_save_pct(self):
        if self.bp_faced < 5:  # need at least a few real break points faced
            return None
        return self.bp_saved / self.bp_faced


def _load_raw_rows(conn):
    rows = conn.execute(
        "SELECT player_a, player_b, winner, match_date, "
        "player_a_svgms, player_a_bp_faced, player_a_bp_saved, "
        "player_b_svgms, player_b_bp_faced, player_b_bp_saved "
        "FROM matches "
        "WHERE winner IS NOT NULL AND match_date IS NOT NULL "
        "AND player_a_svgms IS NOT NULL AND player_a_bp_faced IS NOT NULL AND player_a_bp_saved IS NOT NULL "
        "AND player_b_svgms IS NOT NULL AND player_b_bp_faced IS NOT NULL AND player_b_bp_saved IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def build_season_stats():
    """
    Real walk-forward build. Returns
    {(player, year): {"hold_pct":.., "break_pct":.., "bp_save_pct":..,
                       "svgms":.., "opp_svgms_faced":..}}
    -- the PRE-match state at each point is what real callers should
    snapshot as they walk; this function itself returns the FINAL
    state per (player, year) after processing all real rows, for
    inspection/coverage-checking. Real backtests that need point-in-
    time values should replay this same accumulation logic themselves
    (see bp_direction_backtest.py) rather than use this final-state
    output directly, to avoid lookahead.
    """
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}
    try:
        raw = _load_raw_rows(conn)
    finally:
        conn.close()

    accum: dict = {}  # (player, year) -> _PlayerYearAccum

    for row in raw:
        pa, pb, year = row["player_a"], row["player_b"], row["match_date"][:4]
        pa_key, pb_key = (pa, year), (pb, year)
        pa_acc = accum.setdefault(pa_key, _PlayerYearAccum())
        pb_acc = accum.setdefault(pb_key, _PlayerYearAccum())

        pa_sv, pa_bpf, pa_bps = row["player_a_svgms"], row["player_a_bp_faced"], row["player_a_bp_saved"]
        pb_sv, pb_bpf, pb_bps = row["player_b_svgms"], row["player_b_bp_faced"], row["player_b_bp_saved"]

        # Own serving stats
        pa_acc.svgms += pa_sv
        pa_acc.bp_faced += pa_bpf
        pa_acc.bp_saved += pa_bps
        pb_acc.svgms += pb_sv
        pb_acc.bp_faced += pb_bpf
        pb_acc.bp_saved += pb_bps

        # Return stats: pa's return dominance is measured against pb's serve, and vice versa
        pa_acc.opp_svgms_faced += pb_sv
        pa_acc.opp_bp_faced_by_me += pb_bpf
        pa_acc.opp_bp_saved_by_opp += pb_bps
        pb_acc.opp_svgms_faced += pa_sv
        pb_acc.opp_bp_faced_by_me += pa_bpf
        pb_acc.opp_bp_saved_by_opp += pa_bps

    result = {}
    for (player, year), acc in accum.items():
        result[(player, year)] = {
            "hold_pct": acc.hold_pct(),
            "break_pct": acc.break_pct(),
            "bp_save_pct": acc.bp_save_pct(),
            "svgms": acc.svgms,
        }
    return {"status": "ok", "n_player_years": len(result), "data": result}


if __name__ == "__main__":
    r = build_season_stats()
    if r["status"] == "ok":
        n_with_hold = sum(1 for v in r["data"].values() if v["hold_pct"] is not None)
        n_with_break = sum(1 for v in r["data"].values() if v["break_pct"] is not None)
        print({"status": "ok", "n_player_years": r["n_player_years"],
               "n_with_real_hold_pct": n_with_hold, "n_with_real_break_pct": n_with_break})
    else:
        print(r)
