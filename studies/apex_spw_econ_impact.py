#!/usr/bin/env python3
"""
SPW% ECONOMIC IMPACT & DEPLOYMENT DECISION.

Real, market-priced holdout only: `apex_batch_a_rows.csv` (a real,
separate historical batch already carrying real Pinnacle prices --
pinn_a, 100% coverage, 67,565 matches 2010-2026, from the earlier
edge-research effort) restricted to year>=2024 (n=11,594) -- genuine
market prices, not fabricated or assumed.

MODEL A = existing Apex baseline features (ace_rate, df_rate,
hold_rate, break_rate, bp_conv_rate, trailing W40/K15 -- identical to
the BASE spec used throughout BPS_V1 and the Tier-3 investigation).
MODEL B = MODEL A + SPW% (shrink 30/15) -- the single best performer
from the Tier-3 investigation, same spec, nothing else changed.

Both models' predicted service-hold "level" is combined with the real
market price via the frozen model's own, unmodified, read-only-imported
match-probability machinery (`solve_tilt`, `match_winprob_mix`,
`simulate` from apex_prop_sim_v1.py) exactly as production does it --
this machinery FORCES P(favorite wins the match) to equal the market
price for both models alike (see `solve_tilt`'s docstring: "find t so
that P(A wins match) = pinn"). That is a real, load-bearing
architectural fact, not an assumption of this script: it means no
service-hold feature, including SPW%, can ever move Apex's own
match-winner ("moneyline") probability -- that number is pinned to the
market by design. This script verifies that numerically rather than
asserting it, and focuses the actual economic-impact test on the prop
markets that DO respond to the "level" (service-hold quality) input:
Total Games, "goes the distance" (full-length match) probability, and
favorite's games-won distribution.

Simplifications, disclosed rather than hidden:
  - No market-price blending of the hold-rate "level" itself (alpha=1
    in the frozen model's own `level_from` convention) -- this is MY
    own, independent regression output, not a claim about what Apex's
    live production coefficients are (those are proprietary/frozen and
    not reused here).
  - A single, shared, fixed tiebreak-sensitivity constant (pTB_k=6.0)
    and shared placeholder ace/DF rates are used identically for BOTH
    models -- since these are nuisance parameters common to A and B,
    they cannot bias the A-vs-B comparison; this test is not about
    aces or double faults.
"""
import sys, math
import numpy as np
import pandas as pd

sys.path.insert(0, "/path/to/home/openclaw")
import apex_prop_model_v1 as v1          # read-only import
import apex_prop_sim_v1 as sim           # read-only import

W, K = 40, 15
BASE_COLS = ["ace_rate", "df_rate", "hold_rate", "break_rate", "bp_conv_rate"]
PTB_K = 6.0
N_SIMS = 2000


def fit_models(merged):
    """Refit MODEL A (BASE) and MODEL B (BASE+SPW% shrink) on year<=2021,
    predicting actual_hold_rate -- same construction as the Tier-3
    investigation, redone here for a self-contained, reproducible script."""
    parts = []
    for side in ("w", "l"):
        d = pd.DataFrame({"year": merged["year"], "stats_ok": merged["stats_ok"]})
        for bc in BASE_COLS:
            d[bc] = merged["%s_W%d_K%d_%s" % (side, W, K, bc)]
        d["spw_shrink"] = merged["%s_shrink_spw" % side]
        d["y"] = merged["%s_hold_rate_actual" % side]
        parts.append(d)
    long = pd.concat(parts, ignore_index=True)
    keep = (long["stats_ok"] == 1) & long["y"].notna() & long["spw_shrink"].notna()
    for bc in BASE_COLS:
        keep &= long[bc].notna()
    long = long[keep]
    fit_d = long[long["year"] <= 2021]

    def ols(cols):
        X = np.column_stack([np.ones(len(fit_d))] + [fit_d[c].values for c in cols])
        y = fit_d["y"].values
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        return coef

    coefA = ols(BASE_COLS)
    coefB = ols(BASE_COLS + ["spw_shrink"])
    print("MODEL A (BASE) fit-window coefficients:", np.round(coefA, 5))
    print("MODEL B (BASE+SPW% shrink) fit-window coefficients:", np.round(coefB, 5))
    return coefA, coefB


def predict_hold(row_feats, coefA, coefB):
    xa = np.array([1.0] + [row_feats[c] for c in BASE_COLS])
    xb = np.array([1.0] + [row_feats[c] for c in BASE_COLS] + [row_feats["spw_shrink"]])
    hA = float(np.clip(xa @ coefA, 0.05, 0.995))
    hB = float(np.clip(xb @ coefB, 0.05, 0.995))
    return hA, hB


def load_feature_lookup():
    """(date, sorted-norm-name-pair) -> dict of winner/loser identity +
    both sides' trailing BASE + SPW%-shrink features, from the same
    apex_bps_v1_rows.csv / apex_tier3_serveq_rows.csv used throughout
    this investigation (row-identical, verified previously)."""
    a = pd.read_csv("apex_bps_v1_rows.csv", low_memory=False)
    b = pd.read_csv("apex_tier3_serveq_rows.csv", low_memory=False)
    assert len(a) == len(b)
    lut = {}
    wcols = ["w_W%d_K%d_%s" % (W, K, c) for c in BASE_COLS]
    lcols = ["l_W%d_K%d_%s" % (W, K, c) for c in BASE_COLS]
    for i in range(len(a)):
        date = a["date"].iat[i]
        wn, ln = a["winner"].iat[i], a["loser"].iat[i]
        key = date + "|" + "|".join(sorted([v1.norm_name(wn), v1.norm_name(ln)]))
        w_feat = {c: a[wcols[j]].iat[i] for j, c in enumerate(BASE_COLS)}
        w_feat["spw_shrink"] = b["w_shrink_spw"].iat[i]
        l_feat = {c: a[lcols[j]].iat[i] for j, c in enumerate(BASE_COLS)}
        l_feat["spw_shrink"] = b["l_shrink_spw"].iat[i]
        lut[key] = {"winner": wn, "loser": ln, "w_feat": w_feat, "l_feat": l_feat,
                    "surface": a["surface"].iat[i], "best_of": a["best_of"].iat[i],
                    "stats_ok": a["stats_ok"].iat[i]}
    merged = a.copy()
    merged["w_shrink_spw"] = b["w_shrink_spw"].values
    merged["l_shrink_spw"] = b["l_shrink_spw"].values
    return lut, merged


def real_total_games_lookup():
    """(date, sorted-norm-name-pair) -> real, actual total games played,
    parsed from the real Sackmann score string via the frozen model's
    own parse_games() (read-only reuse)."""
    df = v1.load_sackmann("ATP & WTA, 1968-2026", year_from=2010, challengers=False)
    lut = {}
    for r in df.itertuples(index=False):
        games, retired = v1.parse_games(r.score)
        if games is None:
            continue
        d = r.tourney_date.date().isoformat()
        key = d + "|" + "|".join(sorted([v1.norm_name(r.winner_name), v1.norm_name(r.loser_name)]))
        lut[key] = {"total_games": games, "retired": retired}
    return lut


def run_one(level, pinn, best_of, seed):
    """Tilt-solve to the real market price, then Monte Carlo simulate.
    Shared placeholder ace/DF rates + PTB_K for both models (see module
    docstring) -- identical across A and B, so they cannot bias the
    comparison."""
    t, flag = sim.solve_tilt(level, pinn, PTB_K, best_of)
    hA = float(np.clip(level + t, 0.20, 0.995))
    hB = float(np.clip(level - t, 0.20, 0.995))
    p_fav = sim.match_winprob_mix(hA, hB, PTB_K, best_of, 0.0)
    out = sim.simulate(hA, hB, PTB_K, best_of, (0.08, 0.04), (0.08, 0.04),
                        (None, None), (None, None), N_SIMS, seed=seed, sigma=0.0)
    return {
        "p_fav_sim": p_fav,
        "total_games_mean": float(out["total_games"].mean()),
        "total_games_median": float(np.median(out["total_games"])),
        "goes_distance_prob": float(out["goes_5_sets"].mean() if best_of == 5 else out["goes_3_sets"].mean()),
        "fav_games_mean": float(out["fav"]["games_won"].mean()),
        "tilt_flag": flag,
    }


def main():
    feat_lut, merged = load_feature_lookup()
    tg_lut = real_total_games_lookup()
    coefA, coefB = fit_models(merged)

    batch = pd.read_csv("apex_batch_a_rows.csv", low_memory=False)
    hold = batch[batch["year"] >= 2024].copy()
    print("\nreal market-priced 2024+ candidate matches (apex_batch_a_rows.csv): %d" % len(hold))

    rows = []
    n_join_ok = n_feat_missing = n_tg_missing = 0
    import time as _time
    _t0 = _time.time()
    for i, r in enumerate(hold.itertuples(index=False)):
        if i and i % 1000 == 0:
            print("  ... %d/%d (%.0fs)" % (i, len(hold), _time.time() - _t0)); sys.stdout.flush()
        key = str(r.date) + "|" + "|".join(sorted([v1.norm_name(r.player_a), v1.norm_name(r.player_b)]))
        f = feat_lut.get(key)
        tg = tg_lut.get(key)
        if f is None:
            n_feat_missing += 1; continue
        if tg is None or tg["retired"]:
            n_tg_missing += 1; continue
        a_is_winner = v1.norm_name(r.player_a) == v1.norm_name(f["winner"])
        a_feat = f["w_feat"] if a_is_winner else f["l_feat"]
        b_feat = f["l_feat"] if a_is_winner else f["w_feat"]
        pinn_a = float(r.pinn_a)
        a_is_fav = pinn_a >= 0.5
        fav_feat, dog_feat = (a_feat, b_feat) if a_is_fav else (b_feat, a_feat)
        pinn = pinn_a if a_is_fav else 1 - pinn_a
        best_of = 5 if getattr(r, "is_bo5", 0) else 3
        if any(not np.isfinite(fav_feat[c]) for c in BASE_COLS + ["spw_shrink"]) or \
           any(not np.isfinite(dog_feat[c]) for c in BASE_COLS + ["spw_shrink"]):
            n_feat_missing += 1; continue
        hfA, hfB = predict_hold(fav_feat, coefA, coefB)
        hdA, hdB = predict_hold(dog_feat, coefA, coefB)
        levelA, levelB = 0.5 * (hfA + hdA), 0.5 * (hfB + hdB)
        if not (np.isfinite(levelA) and np.isfinite(levelB)):
            n_feat_missing += 1; continue
        seed = i
        resA = run_one(levelA, pinn, best_of, seed)
        resB = run_one(levelB, pinn, best_of, seed)
        a_won = int(r.label)
        rows.append({
            "date": r.date, "surface": r.surface, "is_wta": r.is_wta, "best_of": best_of,
            "pinn_fav": pinn, "a_is_fav": a_is_fav, "a_won": a_won,
            "real_total_games": tg["total_games"],
            "p_fav_A": resA["p_fav_sim"], "p_fav_B": resB["p_fav_sim"],
            "tg_mean_A": resA["total_games_mean"], "tg_mean_B": resB["total_games_mean"],
            "tg_med_A": resA["total_games_median"], "tg_med_B": resB["total_games_median"],
            "dist_A": resA["goes_distance_prob"], "dist_B": resB["goes_distance_prob"],
            "favgames_A": resA["fav_games_mean"], "favgames_B": resB["fav_games_mean"],
            "hfA": hfA, "hfB": hfB, "hdA": hdA, "hdB": hdB,
        })
        n_join_ok += 1
    print("joined to real trailing features + real outcome: %d  (feature-join miss=%d, total-games miss/retired=%d)" %
          (n_join_ok, n_feat_missing, n_tg_missing))
    out = pd.DataFrame(rows)
    out.to_csv("apex_spw_econ_rows.csv", index=False)
    print("wrote apex_spw_econ_rows.csv: %d rows" % len(out))


if __name__ == "__main__":
    main()
