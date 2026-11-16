"""
apex_full_category_calibration_audit.py

Category-by-category calibration audit of the ENTIRE Apex simulator, per
user instruction after the Aces dispersion fix: do not assume aces is the
only category with this problem.

Ground truth confirmed by direct code read (apex_prop_sim_v1.py::simulate(),
lines ~211-280) before writing this script:
  - Only "aces" and "dfs" go through the NB(mean, r*disp_mult) dispersion
    mechanism. Every other category (holds, breaks, svgms, games_won,
    games_lost, sets_won, fantasy_score, and all MATCH_PROPS) is derived
    from ONE categorical draw per set from a combinatorial (a,b,pTB,f) game
    table, mixed over "gap_nodes" at gap_sigma=0.06 -- a structurally
    DIFFERENT variance mechanism with no "r"/"disp_mult" analog. Fantasy
    score is a deterministic linear combination of games/sets/aces/dfs.
  - DFs use the IDENTICAL mechanism as aces (same disp_mult, method-of-
    moments r fit) but were explicitly carved OUT of tonight's fix
    (aces-only scope) and have never been separately audited.

This script measures, per category, on the untouched year>=2024 holdout,
using the SAME candidate-C-aware simulation now actually live (aces uses
tour-specific r/dm; every other category uses production's own unmodified
settings, matching what apex_prop_engine.py now actually does):
  Phase 1: confidence-bucket calibration (predicted vs actual, gap)
  Phase 3: expected (simulated) variance vs observed (realized) variance
  Phase 2 is answered from the code read above + a report of fitted vs
  production settings for aces/dfs specifically (the only categories where
  the question is meaningful).

Read-only against the two frozen V1 files. MD5-checked before/after.
"""
import copy
import hashlib
import json
import time
import numpy as np
import pandas as pd

import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim

FROZEN = {
    "apex_prop_sim_v1.py": "7b03e521e804862b85804f8ac4db7346",
    "apex_prop_model_v1.py": "6bf50622a1761156a77ad0d35a2007f6",
}

def md5_check(tag):
    for fn, expected in FROZEN.items():
        got = hashlib.md5(open(fn, "rb").read()).hexdigest()
        status = "PASS" if got == expected else "FAIL"
        print("MD5 %s [%s]: %s" % (tag, fn, status))
        if status == "FAIL":
            raise SystemExit("MD5 MISMATCH -- aborting.")

md5_check("before")

FIT_END, HOLD_START = 2021, 2024
SACKMANN_DIR = "ATP & WTA, 1968-2026"
N_SIMS = 1000
RESULTS = {}


# ------------------------------------------------------------------
# Standard data-loading pipeline (identical pattern to every prior
# script this session).
# ------------------------------------------------------------------
m = v1.load_model()
coefs = sim.load_sim()
df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)

_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (
    np.isfinite(hf0) & np.isfinite(hd0)
    & np.isfinite(mu0["fav"][0]) & np.isfinite(mu0["fav"][1])
    & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1])
)
df = df[okmask].reset_index(drop=True)

fit_df = df[df["year"] <= FIT_END].reset_index(drop=True)
df_hold = df[df["year"] >= HOLD_START].reset_index(drop=True)
print("Rows: total=%d fit=%d holdout=%d" % (len(df), len(fit_df), len(df_hold)))

atp_hold = df_hold[df_hold["is_wta"] == 0].reset_index(drop=True)
wta_hold = df_hold[df_hold["is_wta"] == 1].reset_index(drop=True)
print("Holdout ATP=%d WTA=%d" % (len(atp_hold), len(wta_hold)))


# ------------------------------------------------------------------
# Frozen Candidate-C constants -- IDENTICAL to what is now live in
# apex_prop_engine.py::evaluate_match(). Aces only; DFs untouched
# (kept on production's own disp_mult path). Never re-fit here.
# ------------------------------------------------------------------
R_ATP = {"fav": 8.70148205269834, "dog": 5.885645957929439}
DM_ATP = 0.6
R_WTA = {"fav": 3.9866756061964232, "dog": 2.7971092624925418}
DM_WTA = 0.4

import math, sys, time as _time

def run_rows_candidate(df_sub, m, coefs, n_sims, r_aces, dm_aces, seed=1):
    """Mirrors sim.run_rows() exactly, except aces (fav+dog) use the
    supplied tour-specific r/dm, matching live production. DFs keep
    production's own disp_mult (unchanged -- out of scope)."""
    P, hf, hd, mu = sim.v1_inputs_from_rows(df_sub, m)
    pl = sim.price_level_pred(df_sub, coefs)
    dfs_dm = coefs.get("disp_mult", 1.0)
    rows = []; t0 = _time.time()
    for i in range(len(df_sub)):
        if i and i % 1000 == 0:
            print("  ... %d/%d (%.0fs)" % (i, len(df_sub), _time.time() - t0)); sys.stdout.flush()
        lv = sim.level_from(hf[i], hd[i], coefs, pl[i])
        bo = int(df_sub["best_of"].values[i])
        t, flag = sim.solve_tilt(lv, df_sub["pinn_fav"].values[i], coefs["tb_k"], bo, sigma=coefs.get("gap_sigma", 0.0))
        hA = min(max(lv + t, 0.2), 0.995); hB = min(max(lv - t, 0.2), 0.995)
        s = sim.simulate(
            hA, hB, coefs["tb_k"], bo,
            (mu["fav"][0][i], mu["fav"][1][i]), (mu["dog"][0][i], mu["dog"][1][i]),
            (r_aces["fav"] * dm_aces, coefs["disp"]["fav"]["dfs"] * dfs_dm),
            (r_aces["dog"] * dm_aces, coefs["disp"]["dog"]["dfs"] * dfs_dm),
            n_sims, seed=seed + i, sigma=coefs.get("gap_sigma", 0.0),
        )
        rows.append((s, hA, hB, flag))
    return rows

print("Running ATP holdout candidate-C simulation (n=%d, %d sims/match)..." % (len(atp_hold), N_SIMS))
sims_atp = run_rows_candidate(atp_hold, m, coefs, N_SIMS, R_ATP, DM_ATP, seed=1)
print("Running WTA holdout candidate-C simulation (n=%d, %d sims/match)..." % (len(wta_hold), N_SIMS))
sims_wta = run_rows_candidate(wta_hold, m, coefs, N_SIMS, R_WTA, DM_WTA, seed=1)
print("Simulation passes complete.")


# ------------------------------------------------------------------
# Build a single combined view: rows (ATP+WTA holdout) + matching sims.
# ------------------------------------------------------------------
combo_df = pd.concat([atp_hold, wta_hold], ignore_index=True)
combo_sims = sims_atp + sims_wta
tour = np.array(["ATP"] * len(atp_hold) + ["WTA"] * len(wta_hold))
assert len(combo_df) == len(combo_sims) == len(tour)

pbins = [0.0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01]
plabels = ["<55%", "55-60%", "60-65%", "65-70%", "70-75%", "75-80%", "80%+"]

def bucket_table(pred, act, seg_mask=None):
    """pred, act: 1-d float arrays (nan = excluded). Returns list of
    dicts: label, n, pred_mean, act_mean, gap, plus overall brier."""
    p = np.asarray(pred, dtype=float); a = np.asarray(act, dtype=float)
    ok = np.isfinite(p) & np.isfinite(a)
    if seg_mask is not None:
        ok = ok & seg_mask
    p, a = p[ok], a[ok]
    out = []
    if len(p) == 0:
        return out, float("nan"), 0
    brier = float(np.mean((p - a) ** 2))
    idx = np.digitize(p, pbins) - 1
    for bi, lab in enumerate(plabels):
        m = idx == bi
        n = int(m.sum())
        if n == 0:
            out.append({"label": lab, "n": 0, "pred": float("nan"), "act": float("nan"), "gap": float("nan")})
            continue
        pm = float(p[m].mean()); am = float(a[m].mean())
        out.append({"label": lab, "n": n, "pred": pm, "act": am, "gap": pm - am})
    return out, brier, len(p)


# ------------------------------------------------------------------
# Phase 1: build predicted-probability and actual arrays for every
# binary / categorical MATCH_PROPS category.
# ------------------------------------------------------------------
n = len(combo_df)
pred = {}; act = {}

pred["fav_wins"] = np.array([s["fav_wins"].mean() for s, _, _, _ in combo_sims])
act["fav_wins"] = combo_df["fav_won"].astype(float).values

pred["first_set_fav_wins"] = np.array([s["first_set_fav_wins"].mean() for s, _, _, _ in combo_sims])
act["first_set_fav_wins"] = combo_df["fav_first_set"].astype(float).values

def tie_pred(cat):
    out = np.full(n, np.nan)
    for i, (s, _, _, _) in enumerate(combo_sims):
        x = s[cat]
        pos = np.mean(x == 1); neg = np.mean(x == 0)
        d = pos + neg
        out[i] = pos / d if d > 0 else np.nan
    return out

pred["most_aces_fav"] = tie_pred("most_aces_fav")
fa, da = combo_df["fav_aces"].values, combo_df["dog_aces"].values
act["most_aces_fav"] = np.where(fa > da, 1.0, np.where(fa < da, 0.0, np.nan))

pred["most_games_fav"] = tie_pred("most_games_fav")
fg, dg = combo_df["fav_games_won"].values, combo_df["dog_games_won"].values
act["most_games_fav"] = np.where(fg > dg, 1.0, np.where(fg < dg, 0.0, np.nan))

pred["any_tiebreak"] = np.array([s["any_tiebreak"].mean() for s, _, _, _ in combo_sims])
act["any_tiebreak"] = (combo_df["n_tb"].values > 0).astype(float)

pred["goes_3_sets"] = np.array([s["goes_3_sets"].mean() for s, _, _, _ in combo_sims])
bo = combo_df["best_of"].values
nsets = combo_df["n_sets"].values
act["goes_3_sets"] = np.where(bo == 3, (nsets == 3).astype(float), (nsets >= 3).astype(float))

pred["goes_5_sets"] = np.array([s["goes_5_sets"].mean() for s, _, _, _ in combo_sims])
act["goes_5_sets"] = (nsets == 5).astype(float)
bo5_mask = bo == 5

BINARY_CATS = ["fav_wins", "first_set_fav_wins", "most_aces_fav", "most_games_fav",
               "any_tiebreak", "goes_3_sets", "goes_5_sets"]
print("Phase 1 arrays built for:", BINARY_CATS)


# ------------------------------------------------------------------
# Segments for Phase 4 (reused for both Phase 1 binary cats and
# Phase 3 count cats).
# ------------------------------------------------------------------
surface = combo_df["surface"].astype(str).values
SEGMENTS = {
    "overall": np.ones(n, dtype=bool),
    "ATP": tour == "ATP",
    "WTA": tour == "WTA",
    "Bo3": bo == 3,
    "Bo5": bo == 5,
    "Hard": surface == "Hard",
    "Clay": surface == "Clay",
    "Grass": surface == "Grass",
}

RESULTS["phase1"] = {}
for cat in BINARY_CATS:
    RESULTS["phase1"][cat] = {}
    base_mask = bo5_mask if cat == "goes_5_sets" else np.ones(n, dtype=bool)
    for seg_name, seg_mask in SEGMENTS.items():
        m = base_mask & seg_mask
        table, brier, ntot = bucket_table(pred[cat], act[cat], seg_mask=m)
        mae = float(np.nanmean(np.abs(pred[cat][m] - act[cat][m]))) if ntot else float("nan")
        RESULTS["phase1"][cat][seg_name] = {"buckets": table, "brier": brier, "mae": mae, "n": ntot}
    print("Phase 1 done:", cat)


# ------------------------------------------------------------------
# Phase 3 (+ O/U line calibration, same bucket-table machinery as
# Phase 1): count-style categories. 9 PLAYER_PROPS (fav+dog each) +
# 5 count-style MATCH_PROPS.
# ------------------------------------------------------------------
def count_arrays(sim_key, side=None, actual=None):
    """Returns (pred_mean, pred_var, pred_p_over_line, actual) arrays, len n.
    Line for the O/U calibration is floor(this row's own simulated mean)+0.5,
    exactly the convention used throughout the earlier aces work."""
    pm = np.empty(n); pv = np.empty(n); pover = np.empty(n)
    for i, (s, _, _, _) in enumerate(combo_sims):
        x = s[sim_key] if side is None else s[side][sim_key]
        pm[i] = x.mean(); pv[i] = x.var()
        line = math.floor(x.mean()) + 0.5
        pover[i] = float(np.mean(x > line))
    return pm, pv, pover, np.asarray(actual, dtype=float)

COUNT_RESULTS = {}

PLAYER_COUNT_CATS = ["aces", "dfs", "holds", "breaks", "svgms", "games_won", "games_lost", "sets_won", "fantasy_score"]
for side in ("fav", "dog"):
    other = "dog" if side == "fav" else "fav"
    for cat in PLAYER_COUNT_CATS:
        if cat == "games_lost":
            actual_col = combo_df["%s_games_won" % other].values
        else:
            actual_col = combo_df["%s_%s" % (side, cat)].values
        pm, pv, pover, av = count_arrays(cat, side=side, actual=actual_col)
        COUNT_RESULTS["%s_%s" % (side, cat)] = (pm, pv, pover, av)

MATCH_COUNT_CATS = {
    "total_games": ("total_games", combo_df["total_games"].values),
    "first_set_games": ("first_set_games", combo_df["first_set_games"].values),
    "total_aces": ("total_aces", (combo_df["fav_aces"] + combo_df["dog_aces"]).values),
    "total_sets": ("total_sets", combo_df["n_sets"].values),
    "tiebreaks": ("tiebreaks", combo_df["n_tb"].values),
}
for label, (sim_key, actual_col) in MATCH_COUNT_CATS.items():
    pm, pv, pover, av = count_arrays(sim_key, side=None, actual=actual_col)
    COUNT_RESULTS[label] = (pm, pv, pover, av)

print("Phase 3 raw arrays built for", len(COUNT_RESULTS), "categories")


RESULTS["phase3"] = {}
for label, (pm, pv, pover, av) in COUNT_RESULTS.items():
    RESULTS["phase3"][label] = {}
    ok_all = np.isfinite(pm) & np.isfinite(av)
    line = np.floor(pm) + 0.5
    actual_over = (av > line).astype(float)
    for seg_name, seg_mask in SEGMENTS.items():
        m = ok_all & seg_mask
        ntot = int(m.sum())
        if ntot == 0:
            RESULTS["phase3"][label][seg_name] = {"n": 0}
            continue
        mae = float(np.mean(np.abs(pm[m] - av[m])))
        mse = float(np.mean((pm[m] - av[m]) ** 2))
        exp_var = float(np.mean(pv[m]))
        obs_var = float(np.var(av[m]))
        var_ratio = exp_var / obs_var if obs_var > 0 else float("nan")
        table, brier, nb_ = bucket_table(pover, actual_over, seg_mask=m)
        RESULTS["phase3"][label][seg_name] = {
            "n": ntot, "mae": mae, "mse": mse,
            "exp_var": exp_var, "obs_var": obs_var, "var_ratio": var_ratio,
            "ou_brier": brier, "ou_buckets": table,
        }
    print("Phase 3 var/MAE/OU done:", label)


# ------------------------------------------------------------------
# Phase 2 (dispersion audit) is largely a static report, not a
# computation -- captured here from the confirmed production coefs
# dump + code-read ground truth, so it rides along in the same
# results file for the report-writing step.
# ------------------------------------------------------------------
RESULTS["phase2"] = {
    "disp_mult_production": coefs.get("disp_mult"),
    "gap_sigma_production": coefs.get("gap_sigma"),
    "disp_fitted_production": coefs.get("disp"),
    "categories_with_nb_dispersion": ["aces", "dfs"],
    "categories_with_gap_sigma_mixture_only": [
        "holds", "breaks", "svgms", "games_won", "games_lost", "sets_won",
        "total_games", "first_set_games", "total_sets", "tiebreaks",
        "any_tiebreak", "goes_3_sets", "goes_5_sets", "most_games_fav",
        "fav_wins", "first_set_fav_wins",
    ],
    "categories_deterministic": ["fantasy_score"],
    "candidate_c_now_live": {
        "R_ATP": R_ATP, "DM_ATP": DM_ATP, "R_WTA": R_WTA, "DM_WTA": DM_WTA,
        "scope": "aces only -- dfs left on production's own disp_mult=1e6 path",
    },
}

# Save before any summary print (lesson from the earlier format-string bug).
with open("apex_full_category_calibration_audit_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2, default=lambda o: None)
print("Wrote apex_full_category_calibration_audit_results.json")

try:
    print("\n=== PHASE 1 SUMMARY (overall segment) ===")
    for cat in BINARY_CATS:
        d = RESULTS["phase1"][cat]["overall"]
        print("  %-20s n=%-6d brier=%.4f mae=%.4f" % (cat, d["n"], d["brier"], d["mae"]))
        for b in d["buckets"]:
            if b["n"] > 0:
                print("      %-8s n=%-5d pred=%.3f act=%.3f gap=%+.3f" % (b["label"], b["n"], b["pred"], b["act"], b["gap"]))
    print("\n=== PHASE 3 SUMMARY (overall segment) ===")
    for label in COUNT_RESULTS:
        d = RESULTS["phase3"][label]["overall"]
        print("  %-20s n=%-6d mae=%.4f mse=%.4f var_ratio=%.3f ou_brier=%.4f"
              % (label, d["n"], d["mae"], d["mse"], d["var_ratio"], d["ou_brier"]))
except Exception as e:
    print("Summary print error (non-fatal, results already saved to JSON):", e)

md5_check("after")
print("DONE.")
