"""
apex_v2_error_decomposition.py

Task: find the REAL root cause of the remaining Aces MORE overconfidence
that Aces V2 (opponent-suppression, gamma=0.246189) did NOT fix (<1%
holdout improvement). Per explicit user instruction (2026-09-26 18:00 CT):
do NOT build another model or fit another coefficient here -- this script
only decomposes and explains the existing error. It measures the CURRENTLY
DEPLOYED V1 model (Aces V2 promotion is on hold), using the real production
simulator (sim.run_rows(), unpatched, gamma=0), on the year>=2024 holdout
population -- i.e. today's live behavior.

Read-only against apex_prop_sim_v1.py / apex_prop_model_v1.py. MD5 of both
frozen files checked before and after; neither is ever modified.

IMPORTANT SCOPE NOTE (checked before writing this script): the frozen V1
row pipeline (apex_prop_rows_v1.csv) was built via
apex_prop_model_v1.load_sackmann(..., challengers=False) at every call site
-- it contains ATP + WTA only, ZERO Challenger matches. The "Challenger"
segment requested in Phase 1 cannot be measured from this model's own
production data; it is reported as N/A (not fabricated), same way the
original TRACK 2 Challenger stat came from a separate, non-frozen-model
data pull. WTA has zero Bo5 rows (confirmed: tour rule), so "WTA Bo5" is
not a real segment either.
"""
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
    import hashlib
    for fn, expected in FROZEN.items():
        got = hashlib.md5(open(fn, "rb").read()).hexdigest()
        status = "PASS" if got == expected else "FAIL"
        print("MD5 %s [%s]: %s" % (tag, fn, status))
        if status == "FAIL":
            raise SystemExit("MD5 MISMATCH on frozen file %s -- aborting." % fn)

md5_check("before")

FIT_END, TUNE_START, TUNE_END, HOLD_START = 2021, 2022, 2023, 2024
SACKMANN_DIR = "ATP & WTA, 1968-2026"
N_SIMS = 2000
RESULTS = {}


# ---------------------------------------------------------------------------
# Load production pipeline (identical to Step 6 / Bo3-Bo5-split harness)
# ---------------------------------------------------------------------------
m = v1.load_model()
coefs = sim.load_sim()
W, K = m["window"], m["shrink"]
mean_break_rate = m["mean_break_rate"]

df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)
_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (np.isfinite(hf0) & np.isfinite(hd0) & np.isfinite(mu0["fav"][0])
          & np.isfinite(mu0["fav"][1]) & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1]))
df = df[okmask].reset_index(drop=True)

df_hold = df[df["year"] >= HOLD_START].reset_index(drop=True)
print("Holdout population (year>=%d): %d matches" % (HOLD_START, len(df_hold)))
print("is_wta x best_of:\n", pd.crosstab(df_hold["is_wta"], df_hold["best_of"]))
print("surface:\n", df_hold["surface"].value_counts())
n_challenger = 0  # confirmed: pipeline never loads challengers (challengers=False everywhere)
RESULTS["scope_note"] = {
    "challenger_rows_in_pipeline": n_challenger,
    "wta_bo5_rows": int(((df_hold["is_wta"] == 1) & (df_hold["best_of"] == 5)).sum()),
}

# ---------------------------------------------------------------------------
# ONE production simulation pass over the holdout population. This is the
# CURRENTLY DEPLOYED behavior (Aces V2 / gamma=0.246189 promotion is on
# hold per standing instruction) -- unpatched sim.run_rows(), gamma=0.
# ---------------------------------------------------------------------------
print("\nRunning production simulation over holdout (n_sims=%d)..." % N_SIMS)
t0 = time.time()
sims = sim.run_rows(df_hold, m, coefs, N_SIMS, seed=1, progress=True)
print("done in %.1fs" % (time.time() - t0))

_, hf_h, hd_h, mu_h = sim.v1_inputs_from_rows(df_hold, m)


# ---------------------------------------------------------------------------
# Build per-side stacked observation arrays (fav+dog concatenated), and
# match-level arrays, all from this ONE simulation pass.
# ---------------------------------------------------------------------------
def side_arrays(side, opp):
    actual_aces = df_hold["%s_aces" % side].values.astype(float)
    actual_svgms = df_hold["%s_svgms" % side].values.astype(float)
    own_ace_rate = mu_h[side][0]
    opp_break_rate = df_hold["%s_W%d_K%d_break_rate" % (opp, W, K)].values
    pred_aces_sim = np.array([s[side]["aces"].mean() for s, _, _, _ in sims])
    pred_svgms_sim = np.array([s[side]["svgms"].mean() for s, _, _, _ in sims])
    return dict(actual_aces=actual_aces, actual_svgms=actual_svgms, own_ace_rate=own_ace_rate,
                opp_break_rate=opp_break_rate, pred_aces_sim=pred_aces_sim, pred_svgms_sim=pred_svgms_sim)

fav_d = side_arrays("fav", "dog")
dog_d = side_arrays("dog", "fav")

is_wta = df_hold["is_wta"].values
best_of = df_hold["best_of"].values
surface = df_hold["surface"].values

# match-level: probability fav has more aces (conditional on non-tie, exactly
# matching production's own most_aces_fav definition in holdout_report())
fav_samp = np.stack([s["fav"]["aces"] for s, _, _, _ in sims])   # (n_matches, n_sims)
dog_samp = np.stack([s["dog"]["aces"] for s, _, _, _ in sims])
gt = fav_samp > dog_samp
ne = fav_samp != dog_samp
pred_prob_fav_more = gt.mean(axis=1) / np.maximum(ne.mean(axis=1), 1e-9)
actual_fav_aces = df_hold["fav_aces"].values
actual_dog_aces = df_hold["dog_aces"].values
actual_fav_more = (actual_fav_aces > actual_dog_aces).astype(float)
tie_mask = actual_fav_aces == actual_dog_aces
del fav_samp, dog_samp

print("\nArrays built. n_matches=%d" % len(df_hold))


# ---------------------------------------------------------------------------
# PHASE 1 -- decompose error by segment. For each segment, report:
#   MAE, MSE, agg_bias (calibration), most_aces_fav overconfidence
#   (pred_prob - actual_win_rate, non-tie matches only), sample size.
# Side-stacked segments (surface, high/low ace players) pool fav+dog rows.
# Match-level segments (tour/best_of) use the match mask directly for the
# overconfidence stat, and the same mask applied to both sides for MAE/MSE.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("PHASE 1 -- ERROR DECOMPOSITION BY SEGMENT")
print("=" * 100)

def segment_stats(match_mask, label):
    mk = match_mask
    n_matches = int(mk.sum())
    # side-stacked aces error
    aces_actual = np.concatenate([fav_d["actual_aces"][mk], dog_d["actual_aces"][mk]])
    aces_pred = np.concatenate([fav_d["pred_aces_sim"][mk], dog_d["pred_aces_sim"][mk]])
    ok = np.isfinite(aces_actual) & np.isfinite(aces_pred)
    resid = aces_actual[ok] - aces_pred[ok]
    mae = float(np.mean(np.abs(resid))); mse = float(np.mean(resid ** 2))
    bias = float(np.mean(aces_pred[ok]) - np.mean(aces_actual[ok]))
    # most_aces_fav overconfidence (match-level, non-tie only)
    mk2 = mk & ~tie_mask
    overconf = float(np.mean(pred_prob_fav_more[mk2]) - np.mean(actual_fav_more[mk2])) if mk2.sum() > 0 else float("nan")
    pred_p = float(np.mean(pred_prob_fav_more[mk2])) if mk2.sum() > 0 else float("nan")
    act_p = float(np.mean(actual_fav_more[mk2])) if mk2.sum() > 0 else float("nan")
    print("  %-22s n_matches=%-6d MAE=%.4f MSE=%.4f agg_bias=%+.4f | most_aces_fav pred=%.3f actual=%.3f overconf=%+.3f"
          % (label, n_matches, mae, mse, bias, pred_p, act_p, overconf))
    return {"n_matches": n_matches, "mae": mae, "mse": mse, "agg_bias": bias,
            "most_aces_fav_pred": pred_p, "most_aces_fav_actual": act_p, "overconfidence": overconf}

phase1 = {}
phase1["ATP_Bo3"] = segment_stats((is_wta == 0) & (best_of == 3), "ATP Bo3")
phase1["ATP_Bo5"] = segment_stats((is_wta == 0) & (best_of == 5), "ATP Bo5")
phase1["WTA"] = segment_stats(is_wta == 1, "WTA (all Bo3)")
phase1["Challenger"] = {"note": "N/A -- 0 rows in this model's production pipeline (challengers=False at every load_sackmann call site)"}
print("  %-22s N/A -- 0 rows in production pipeline (challengers=False)" % "Challenger")
phase1["Surface_Hard"] = segment_stats(surface == "Hard", "Surface: Hard")
phase1["Surface_Clay"] = segment_stats(surface == "Clay", "Surface: Clay")
phase1["Surface_Grass"] = segment_stats(surface == "Grass", "Surface: Grass")
phase1["All_matches"] = segment_stats(np.ones(len(df_hold), dtype=bool), "All (combined)")


# Favorite vs Underdog (side-level, not match-level; use all holdout matches)
def side_stats(d, label):
    ok = np.isfinite(d["actual_aces"]) & np.isfinite(d["pred_aces_sim"])
    resid = d["actual_aces"][ok] - d["pred_aces_sim"][ok]
    mae = float(np.mean(np.abs(resid))); mse = float(np.mean(resid ** 2))
    bias = float(np.mean(d["pred_aces_sim"][ok]) - np.mean(d["actual_aces"][ok]))
    print("  %-22s n=%-6d MAE=%.4f MSE=%.4f agg_bias=%+.4f" % (label, int(ok.sum()), mae, mse, bias))
    return {"n": int(ok.sum()), "mae": mae, "mse": mse, "agg_bias": bias}

phase1["Favorite_side"] = side_stats(fav_d, "Favorite (side)")
phase1["Underdog_side"] = side_stats(dog_d, "Underdog (side)")

# High/Low ace-rate players (server strength), tercile split on own_ace_rate,
# pooled across both sides and all holdout matches.
own_rate_all = np.concatenate([fav_d["own_ace_rate"], dog_d["own_ace_rate"]])
aces_actual_all = np.concatenate([fav_d["actual_aces"], dog_d["actual_aces"]])
aces_pred_all = np.concatenate([fav_d["pred_aces_sim"], dog_d["pred_aces_sim"]])
ok_all = np.isfinite(own_rate_all) & np.isfinite(aces_actual_all) & np.isfinite(aces_pred_all)
q1, q2 = np.percentile(own_rate_all[ok_all], [33.3, 66.7])
print("  (server-strength terciles: own_ace_rate cutpoints q33=%.4f q67=%.4f)" % (q1, q2))

def bucket_stats(mask, label):
    resid = aces_actual_all[mask] - aces_pred_all[mask]
    mae = float(np.mean(np.abs(resid))); mse = float(np.mean(resid ** 2))
    bias = float(np.mean(aces_pred_all[mask]) - np.mean(aces_actual_all[mask]))
    n = int(mask.sum())
    print("  %-22s n=%-6d MAE=%.4f MSE=%.4f agg_bias=%+.4f" % (label, n, mae, mse, bias))
    return {"n": n, "mae": mae, "mse": mse, "agg_bias": bias}

phase1["Low_ace_players"] = bucket_stats(ok_all & (own_rate_all <= q1), "Low ace-rate players")
phase1["Mid_ace_players"] = bucket_stats(ok_all & (own_rate_all > q1) & (own_rate_all <= q2), "Mid ace-rate players")
phase1["High_ace_players"] = bucket_stats(ok_all & (own_rate_all > q2), "High ace-rate players")

RESULTS["phase1_segments"] = phase1


# ---------------------------------------------------------------------------
# PHASE 2 -- SERVICE-GAME ASSUMPTION AUDIT.
# pred_svgms_sim = the simulator's OWN mean simulated service-games count
# (drawn internally from hold-rate/tiebreak assumptions, NOT fed the real
# actual svgms). Compares that to the real actual svgms, and checks how
# much of the aces residual is explained by the svgms residual.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("PHASE 2 -- SERVICE-GAME ASSUMPTION AUDIT")
print("=" * 100)

svgms_actual_all = np.concatenate([fav_d["actual_svgms"], dog_d["actual_svgms"]])
svgms_pred_all = np.concatenate([fav_d["pred_svgms_sim"], dog_d["pred_svgms_sim"]])
aces_resid_all = aces_actual_all - aces_pred_all
svgms_resid_all = svgms_actual_all - svgms_pred_all
okv = np.isfinite(svgms_actual_all) & np.isfinite(svgms_pred_all) & np.isfinite(aces_resid_all)

def svgms_bias_report(mask, label):
    mm = mask & okv
    b = float(np.mean(svgms_pred_all[mm]) - np.mean(svgms_actual_all[mm]))
    mae = float(np.mean(np.abs(svgms_resid_all[mm])))
    n = int(mm.sum())
    print("  %-22s n=%-6d svgms_bias(pred-actual)=%+.4f  svgms_MAE=%.4f" % (label, n, b, mae))
    return {"n": n, "svgms_bias": b, "svgms_mae": mae}

phase2 = {}
phase2["overall"] = svgms_bias_report(np.ones(len(svgms_actual_all), dtype=bool), "Overall")
is_wta_all = np.concatenate([is_wta, is_wta])
best_of_all = np.concatenate([best_of, best_of])
phase2["ATP"] = svgms_bias_report(is_wta_all == 0, "ATP")
phase2["WTA"] = svgms_bias_report(is_wta_all == 1, "WTA")
phase2["Bo3"] = svgms_bias_report(best_of_all == 3, "Bo3")
phase2["Bo5"] = svgms_bias_report(best_of_all == 5, "Bo5")

corr = float(np.corrcoef(aces_resid_all[okv], svgms_resid_all[okv])[0, 1])
r2 = corr ** 2
print("\n  corr(aces_residual, svgms_residual) = %.4f   R^2 = %.4f (%.1f%% of ace-residual variance explained by svgms residual)"
      % (corr, r2, 100 * r2))
phase2["aces_resid_vs_svgms_resid_corr"] = corr
phase2["aces_resid_vs_svgms_resid_r2"] = r2
RESULTS["phase2_svgms_audit"] = phase2


# ---------------------------------------------------------------------------
# PHASE 3 -- PLAYER-TYPE AUDIT. Big/small servers = own_ace_rate terciles
# (already computed in Phase 1). Elite/weak returners = OPPONENT break_rate
# terciles -- this is the exact same axis Aces V2's suppression targets, so
# this directly checks whether V2's signal was even the right shape.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("PHASE 3 -- PLAYER-TYPE AUDIT")
print("=" * 100)
print("-- by own server strength (own_ace_rate tercile) --")
phase3 = {"server_strength": {
    "low": phase1["Low_ace_players"], "mid": phase1["Mid_ace_players"], "high": phase1["High_ace_players"]}}

opp_break_all = np.concatenate([fav_d["opp_break_rate"], dog_d["opp_break_rate"]])
ok_ret = ok_all & np.isfinite(opp_break_all)
rq1, rq2 = np.percentile(opp_break_all[ok_ret], [33.3, 66.7])
print("-- by opponent returner strength (opp_break_rate tercile: q33=%.4f q67=%.4f) --" % (rq1, rq2))
phase3["returner_strength"] = {
    "weak_returner_opp": bucket_stats(ok_ret & (opp_break_all <= rq1), "vs Weak returner"),
    "mid_returner_opp": bucket_stats(ok_ret & (opp_break_all > rq1) & (opp_break_all <= rq2), "vs Mid returner"),
    "elite_returner_opp": bucket_stats(ok_ret & (opp_break_all > rq2), "vs Elite returner"),
}
RESULTS["phase3_player_type"] = phase3


# ---------------------------------------------------------------------------
# PHASE 4 -- LINE-SPECIFIC AUDIT. Bucket by the model's own projected ace
# level (pred_aces_sim), side-stacked. Does overconfidence increase as
# projection rises?
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("PHASE 4 -- LINE-SPECIFIC AUDIT (bucketed by projected ace level)")
print("=" * 100)
bins = [0, 2, 4, 6, 8, 10, np.inf]
labels = ["0-2", "2-4", "4-6", "6-8", "8-10", "10+"]
phase4 = {}
for lo, hi, lab in zip(bins[:-1], bins[1:], labels):
    mask = ok_all & (aces_pred_all >= lo) & (aces_pred_all < hi)
    phase4[lab] = bucket_stats(mask, "proj %s" % lab)
RESULTS["phase4_line_audit"] = phase4

# ---------------------------------------------------------------------------
# PHASE 5 -- CALIBRATION AUDIT. Bucket match-level predicted probability of
# most_aces_fav (non-tie matches only) and compare to actual hit rate.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("PHASE 5 -- CALIBRATION AUDIT (most_aces_fav probability buckets)")
print("=" * 100)
pbins = [0.0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01]
plabels = ["<55%", "55-60%", "60-65%", "65-70%", "70-75%", "75-80%", "80%+"]
valid = ~tie_mask
phase5 = {}
for lo, hi, lab in zip(pbins[:-1], pbins[1:], plabels):
    mask = valid & (pred_prob_fav_more >= lo) & (pred_prob_fav_more < hi)
    n = int(mask.sum())
    if n == 0:
        continue
    pp = float(np.mean(pred_prob_fav_more[mask]))
    ap = float(np.mean(actual_fav_more[mask]))
    gap = pp - ap
    print("  %-8s n=%-6d predicted=%.3f actual=%.3f gap=%+.3f" % (lab, n, pp, ap, gap))
    phase5[lab] = {"n": n, "predicted": pp, "actual": ap, "gap": gap}
RESULTS["phase5_calibration"] = phase5


md5_check("after")

with open("/path/to/home/openclaw/apex_v2_error_decomposition_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2, default=str)
print("\nWrote apex_v2_error_decomposition_results.json")
print("\nDONE.")
