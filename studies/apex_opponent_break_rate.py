"""
APEX ACES V2 -- Task 1, Step 2: Trailing Opponent Break-Rate Feature
=====================================================================
Per APEX_ACES_V2_DESIGN.md (Section 4/7): the opponent-suppression signal
must be each opponent's TRAILING (pre-match) break rate, using the exact
same rolling-window + shrink methodology V1 already uses for a player's own
rates (rate_bundle(), apex_prop_model_v1.py). No new methodology is invented
here -- "opponent_break_rate" for player A in a match is just rate_bundle()
evaluated on player B (A's opponent), at the same point in time A's own rate
is evaluated.

STRICT SCOPE: this file only computes and validates the feature.
- Does NOT modify apex_prop_model_v1.py or apex_prop_sim_v1.py (imported
  read-only; every call below is one that code already makes elsewhere).
- Does NOT build Aces V2.
- Does NOT touch mu, probabilities, or any live pricing path.
"""
import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim  # noqa: F401  (imported to prove no collision; unused directly)


# ---------------------------------------------------------------- historical
def historical_opponent_break_rates(rows, grids=None):
    """Given replay()'s existing per-match `rows` (already computed, already
    verified leak-free -- design doc Section 5), derive opponent_break_rate
    for BOTH sides of every match, for every (window, shrink) grid pair.

    Pure cross-reference, not a new computation: the winner's
    opponent_break_rate is the LOSER's own (already-trailing) break_rate
    column from that same row, and vice versa. No new history is built, no
    new leakage risk introduced -- this inherits replay()'s already-verified
    no-look-ahead guarantee (see design doc Section 5, checks 1-5).
    """
    grids = grids or [(w, k) for w in v1.WINDOW_GRID for k in v1.SHRINK_GRID]
    out = []
    for row in rows:
        r = dict(row)
        for (w, k) in grids:
            w_key = "w_W%d_K%d_break_rate" % (w, k)
            l_key = "l_W%d_K%d_break_rate" % (w, k)
            r["w_opp_break_rate_W%d_K%d" % (w, k)] = row.get(l_key)
            r["l_opp_break_rate_W%d_K%d" % (w, k)] = row.get(w_key)
        out.append(r)
    return out


# ---------------------------------------------------------------- live
def live_opponent_break_rate(state, fav_name, dog_name, surface, today, window, shrink):
    """Live-path mirror of the historical derivation. Calls the same,
    unmodified v1.live_features()/v1.rate_bundle() that build_live_row()
    already calls for each player's OWN rate -- the only difference is this
    reads the OTHER player's rate_bundle output. Read-only: does not call
    build_live_row(), does not touch mu, does not touch any pricing/probability
    path."""
    fav_ps, _, _, _ = v1.live_features(state, fav_name, surface, today)
    dog_ps, _, _, _ = v1.live_features(state, dog_name, surface, today)
    fav_rb = v1.rate_bundle(fav_ps, surface, window, shrink)
    dog_rb = v1.rate_bundle(dog_ps, surface, window, shrink)
    return {
        "fav_opp_break_rate": dog_rb["break_rate"] if dog_rb else None,
        "dog_opp_break_rate": fav_rb["break_rate"] if fav_rb else None,
        "fav_own_break_rate": fav_rb["break_rate"] if fav_rb else None,
        "dog_own_break_rate": dog_rb["break_rate"] if dog_rb else None,
        "fav_n_all": fav_rb["n_all"] if fav_rb else None,
        "dog_n_all": dog_rb["n_all"] if dog_rb else None,
    }
