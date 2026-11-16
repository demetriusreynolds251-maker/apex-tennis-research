"""
apex_v2_dispersion_deep_audit.py

Follow-up to apex_v2_dispersion_audit.py, per explicit user instruction
(2026-09-26 18:40 CT). Evidence only -- no coefficient fit, no deployment,
no promotion. Four things:

1. WHY was disp_mult set to 1,000,000? Read the original fit log
   (apex_prop_sim_report_v1.txt) directly -- the exact original numbers.
2. REPRODUCE the original tuning process verbatim (same tune sample
   construction, same n_sims, same seed, same coverage metric as
   tune_alpha() in apex_prop_sim_v1.py), extended to the requested 8-point
   grid: 1e6, 10, 4, 2, 1, 0.75, 0.5, 0.25.
3. Check whether that aggregate central-80%-band coverage target masked
   confidence-bucket calibration problems.
4. Run the same 8-point grid on the year>=2024 holdout, measuring MAE,
   MSE, calibration (total-aces line-Brier, most_aces_fav Brier), and the
   7 confidence-bucket gaps -- for the pooled dispersion AND, on the WTA
   subset only, for a WTA-SPECIFIC fitted r -- to test whether WTA needs
   its own dispersion value.

Read-only against the two frozen V1 files. MD5 checked before/after.
Counterfactual coefs are local, in-memory copies only.
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

FIT_END, TUNE_START, TUNE_END, HOLD_START = 2021, 2022, 2023, 2024
SACKMANN_DIR = "ATP & WTA, 1968-2026"
GRID = [1e6, 10, 4, 2, 1, 0.75, 0.5, 0.25]
RESULTS = {}


# ---------------------------------------------------------------------------
# Q1: WHY disp_mult=1,000,000? -- the exact original log, verbatim.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("Q1 -- ORIGINAL FIT LOG (apex_prop_sim_report_v1.txt), dispersion section, verbatim")
print("=" * 100)
with open("apex_prop_sim_report_v1.txt") as f:
    lines = f.readlines()
start = next(i for i, l in enumerate(lines) if "tuning dispersion multiplier" in l)
for l in lines[start - 1:start + 8]:
    print("  " + l.rstrip())
RESULTS["q1_original_log_excerpt"] = [l.rstrip() for l in lines[start - 1:start + 8]]

# ---------------------------------------------------------------------------
# Load production pipeline
# ---------------------------------------------------------------------------
m = v1.load_model()
coefs = sim.load_sim()
print("\nProduction disp (fitted r):", coefs["disp"])
print("Production disp_mult:", coefs.get("disp_mult"))

df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)
_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (np.isfinite(hf0) & np.isfinite(hd0) & np.isfinite(mu0["fav"][0])
          & np.isfinite(mu0["fav"][1]) & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1]))
df = df[okmask].reset_index(drop=True)
fit_df = df[df["year"] <= FIT_END].reset_index(drop=True)
df_hold = df[df["year"] >= HOLD_START].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Q2/Q3: REPRODUCE the original tune_alpha() dispersion search verbatim --
# identical tune-sample construction (year 2022-2023, sample<=1000,
# random_state=11), identical n_sims=300, seed=6, identical coverage metric
# (central 80% band, aces+dfs, both sides, pooled) -- extended to the full
# requested 8-point grid instead of the original 5-point one. If this
# reproduces disp_mult=1e6/0.823 exactly, the methodology match is verified.
# We ALSO compute, on this SAME exact tune sample/sims, the confidence-bucket
# most_aces_fav gap -- the metric the original tuning never looked at -- to
# show directly whether the aggregate metric masked it.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("Q2/Q3 -- REPRODUCING original tuning (2022-2023 tune sample, n_sims=300, seed=6), extended grid")
print("=" * 100)
tune = df[(df["year"] >= TUNE_START) & (df["year"] <= TUNE_END)]
tune = tune.sample(min(len(tune), 1000), random_state=11) if len(tune) > 1000 else tune
tune = tune.reset_index(drop=True)
print("tune sample n=%d (matches original: year 2022-2023, sample(1000, random_state=11))" % len(tune))

tune_fav_aces = tune["fav_aces"].values
tune_dog_aces = tune["dog_aces"].values
tie_mask_tune = tune_fav_aces == tune_dog_aces
actual_win_tune = (tune_fav_aces > tune_dog_aces).astype(float)

repro = {}
for dm in GRID:
    coefs_cf = copy.deepcopy(coefs)
    coefs_cf["disp_mult"] = dm
    sims = sim.run_rows(tune, m, coefs_cf, 300, seed=6, progress=False)
    # exact original coverage metric: central 80% band, aces+dfs, both sides, pooled
    cov = []
    for (s, _, _, _), (_, r) in zip(sims, tune.iterrows()):
        for side in ("fav", "dog"):
            for cat in ("aces", "dfs"):
                x = s[side][cat]; y = r["%s_%s" % (side, cat)]
                if np.isfinite(y):
                    cov.append(np.percentile(x, 10) <= y <= np.percentile(x, 90))
    c80 = float(np.mean(cov))
    # extra: most_aces_fav confidence-bucket gap on this SAME tune sample/sims
    fav_samp = np.stack([s["fav"]["aces"] for s, _, _, _ in sims])
    dog_samp = np.stack([s["dog"]["aces"] for s, _, _, _ in sims])
    gt = fav_samp > dog_samp; ne = fav_samp != dog_samp
    pred_prob = gt.mean(axis=1) / np.maximum(ne.mean(axis=1), 1e-9)
    valid = ~tie_mask_tune
    hi_mask = valid & (pred_prob >= 0.80)
    hi_gap = float(np.mean(pred_prob[hi_mask]) - np.mean(actual_win_tune[hi_mask])) if hi_mask.sum() > 0 else float("nan")
    print("  disp_mult=%-8g  80%%-band coverage=%.3f (target 0.80, |diff|=%.3f)   80%%+ bucket gap=%+.3f (n=%d)"
          % (dm, c80, abs(c80 - 0.80), hi_gap, int(hi_mask.sum())))
    repro[str(dm)] = {"coverage_80band": c80, "diff_from_target": abs(c80 - 0.80), "bucket_80plus_gap": hi_gap, "n_80plus": int(hi_mask.sum())}
    del fav_samp, dog_samp

RESULTS["q2_q3_reproduction"] = repro
best_dm = min(GRID, key=lambda dm: repro[str(dm)]["diff_from_target"])
print("\n  => Best-matching disp_mult by the ORIGINAL aggregate metric: %g (matches production's chosen 1e6: %s)"
      % (best_dm, best_dm == 1e6))


# ---------------------------------------------------------------------------
# STEP 4/5: STRUCTURED SWEEP on year>=2024 HOLDOUT (n=10971), full 8-point
# grid. Measures MAE, MSE, calibration (total-aces line-Brier, matching
# holdout_report()'s own line=floor(mean)+0.5 method), most_aces_fav Brier,
# and all 7 confidence-bucket gaps. WTA-only and ATP-only slices are pulled
# from this SAME run (no extra simulation needed) for direct comparison.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("HOLDOUT SWEEP (year>=%d, n=%d, n_sims=1000), pooled dispersion, full grid" % (HOLD_START, len(df_hold)))
print("=" * 100)

N_SIMS = 1000
fav_aces_actual = df_hold["fav_aces"].values
dog_aces_actual = df_hold["dog_aces"].values
is_wta = df_hold["is_wta"].values
pbins = [0.0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01]
plabels = ["<55%", "55-60%", "60-65%", "65-70%", "70-75%", "75-80%", "80%+"]

def bucket_table(pred_prob, actual_win, valid_mask, mk_extra=None):
    out = {}
    m2 = valid_mask if mk_extra is None else (valid_mask & mk_extra)
    for lo, hi, lab in zip(pbins[:-1], pbins[1:], plabels):
        mask = m2 & (pred_prob >= lo) & (pred_prob < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        pp = float(np.mean(pred_prob[mask])); ap = float(np.mean(actual_win[mask]))
        out[lab] = {"n": n, "predicted": pp, "actual": ap, "gap": pp - ap}
    return out

pooled_sweep = {}
for dm in GRID:
    coefs_cf = copy.deepcopy(coefs)
    coefs_cf["disp_mult"] = dm
    t0 = time.time()
    sims = sim.run_rows(df_hold, m, coefs_cf, N_SIMS, seed=1, progress=False)
    dt = time.time() - t0

    fav_samp = np.stack([s["fav"]["aces"] for s, _, _, _ in sims])
    dog_samp = np.stack([s["dog"]["aces"] for s, _, _, _ in sims])
    fav_mean = fav_samp.mean(axis=1); dog_mean = dog_samp.mean(axis=1)
    aces_actual = np.concatenate([fav_aces_actual, dog_aces_actual]).astype(float)
    aces_pred = np.concatenate([fav_mean, dog_mean])
    ok = np.isfinite(aces_actual) & np.isfinite(aces_pred)
    resid = aces_actual[ok] - aces_pred[ok]
    mae = float(np.mean(np.abs(resid))); mse = float(np.mean(resid ** 2))

    # total-aces line-Brier, matching holdout_report()'s own line=floor(mean)+0.5 method
    total_samp = fav_samp + dog_samp
    total_actual = fav_aces_actual + dog_aces_actual
    lines_ = np.floor(total_samp.mean(axis=1)) + 0.5
    phat = np.mean(total_samp > lines_[:, None], axis=1)
    actual_over = (total_actual > lines_).astype(float)
    okc = np.isfinite(total_actual)
    calib_brier = float(np.mean((phat[okc] - actual_over[okc]) ** 2))

    gt = fav_samp > dog_samp; ne = fav_samp != dog_samp
    pred_prob = gt.mean(axis=1) / np.maximum(ne.mean(axis=1), 1e-9)
    tie_mask = fav_aces_actual == dog_aces_actual
    actual_win = (fav_aces_actual > dog_aces_actual).astype(float)
    valid = ~tie_mask
    maf_brier = float(np.mean((pred_prob[valid] - actual_win[valid]) ** 2))

    buckets_all = bucket_table(pred_prob, actual_win, valid)
    buckets_wta = bucket_table(pred_prob, actual_win, valid, mk_extra=(is_wta == 1))
    buckets_atp = bucket_table(pred_prob, actual_win, valid, mk_extra=(is_wta == 0))

    print("\n-- disp_mult=%g  (%.1fs) --" % (dm, dt))
    print("   MAE=%.4f  MSE=%.4f  calib_total_aces_brier=%.4f  most_aces_fav_brier=%.4f" % (mae, mse, calib_brier, maf_brier))
    print("   ALL: 75-80%% gap=%+.3f  80%%+ gap=%+.3f" % (buckets_all.get("75-80%", {}).get("gap", float("nan")), buckets_all.get("80%+", {}).get("gap", float("nan"))))
    print("   WTA: 75-80%% gap=%+.3f (n=%d)  80%%+ gap=%+.3f (n=%d)"
          % (buckets_wta.get("75-80%", {}).get("gap", float("nan")), buckets_wta.get("75-80%", {}).get("n", 0),
             buckets_wta.get("80%+", {}).get("gap", float("nan")), buckets_wta.get("80%+", {}).get("n", 0)))
    print("   ATP: 75-80%% gap=%+.3f (n=%d)  80%%+ gap=%+.3f (n=%d)"
          % (buckets_atp.get("75-80%", {}).get("gap", float("nan")), buckets_atp.get("75-80%", {}).get("n", 0),
             buckets_atp.get("80%+", {}).get("gap", float("nan")), buckets_atp.get("80%+", {}).get("n", 0)))

    pooled_sweep[str(dm)] = {"mae": mae, "mse": mse, "calib_total_aces_brier": calib_brier,
                             "most_aces_fav_brier": maf_brier, "buckets_all": buckets_all,
                             "buckets_wta": buckets_wta, "buckets_atp": buckets_atp}
    del fav_samp, dog_samp, total_samp

RESULTS["pooled_holdout_sweep"] = pooled_sweep


# ---------------------------------------------------------------------------
# WTA SECTION: does WTA need its OWN fitted dispersion (not just a lower
# disp_mult applied to the pooled r)? Refit r on WTA-only fit-window data
# (same method-of-moments formula as fit_constants()), substitute it into a
# coefs copy (aces only; dfs left as pooled), then sweep the SAME grid on
# the WTA-only holdout subset. Compare directly against the WTA slice of
# the pooled-r sweep above (same dm values, same holdout matches).
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("WTA-SPECIFIC DISPERSION: refit r on WTA-only fit window, sweep on WTA-only holdout")
print("=" * 100)

_, hf_fit, hd_fit, mu_fit = sim.v1_inputs_from_rows(fit_df, m)
def moment_r(mask, side):
    lam = mu_fit[side][0][mask] * fit_df.loc[mask, "%s_svgms" % side].values
    y = fit_df.loc[mask, "%s_aces" % side].values
    mk = np.isfinite(lam) & np.isfinite(y) & (lam > 0)
    excess = np.mean((y[mk] - lam[mk]) ** 2) - np.mean(lam[mk])
    return float(np.mean(lam[mk]) ** 2 / excess) if excess > 0 else float("inf")

r_wta_fav = moment_r((fit_df["is_wta"] == 1).values, "fav")
r_wta_dog = moment_r((fit_df["is_wta"] == 1).values, "dog")
print("WTA-specific fitted r: fav=%.4f dog=%.4f  (pooled: fav=%.4f dog=%.4f)"
      % (r_wta_fav, r_wta_dog, coefs["disp"]["fav"]["aces"], coefs["disp"]["dog"]["aces"]))
RESULTS["wta_specific_r"] = {"fav": r_wta_fav, "dog": r_wta_dog, "pooled_fav": coefs["disp"]["fav"]["aces"], "pooled_dog": coefs["disp"]["dog"]["aces"]}

df_hold_wta = df_hold[df_hold["is_wta"] == 1].reset_index(drop=True)
fav_aces_actual_w = df_hold_wta["fav_aces"].values
dog_aces_actual_w = df_hold_wta["dog_aces"].values
tie_mask_w = fav_aces_actual_w == dog_aces_actual_w
actual_win_w = (fav_aces_actual_w > dog_aces_actual_w).astype(float)
valid_w = ~tie_mask_w

wta_specific_sweep = {}
for dm in GRID:
    coefs_cf = copy.deepcopy(coefs)
    coefs_cf["disp"]["fav"]["aces"] = r_wta_fav
    coefs_cf["disp"]["dog"]["aces"] = r_wta_dog
    coefs_cf["disp_mult"] = dm
    t0 = time.time()
    sims = sim.run_rows(df_hold_wta, m, coefs_cf, N_SIMS, seed=1, progress=False)
    dt = time.time() - t0

    fav_samp = np.stack([s["fav"]["aces"] for s, _, _, _ in sims])
    dog_samp = np.stack([s["dog"]["aces"] for s, _, _, _ in sims])
    fav_mean = fav_samp.mean(axis=1); dog_mean = dog_samp.mean(axis=1)
    aces_actual = np.concatenate([fav_aces_actual_w, dog_aces_actual_w]).astype(float)
    aces_pred = np.concatenate([fav_mean, dog_mean])
    ok = np.isfinite(aces_actual) & np.isfinite(aces_pred)
    resid = aces_actual[ok] - aces_pred[ok]
    mae = float(np.mean(np.abs(resid))); mse = float(np.mean(resid ** 2))

    gt = fav_samp > dog_samp; ne = fav_samp != dog_samp
    pred_prob = gt.mean(axis=1) / np.maximum(ne.mean(axis=1), 1e-9)
    maf_brier = float(np.mean((pred_prob[valid_w] - actual_win_w[valid_w]) ** 2))
    buckets = bucket_table(pred_prob, actual_win_w, valid_w)

    print("\n-- WTA-specific r, disp_mult=%g  (%.1fs) --" % (dm, dt))
    print("   MAE=%.4f  MSE=%.4f  most_aces_fav_brier=%.4f" % (mae, mse, maf_brier))
    print("   75-80%% gap=%+.3f (n=%d)   80%%+ gap=%+.3f (n=%d)"
          % (buckets.get("75-80%", {}).get("gap", float("nan")), buckets.get("75-80%", {}).get("n", 0),
             buckets.get("80%+", {}).get("gap", float("nan")), buckets.get("80%+", {}).get("n", 0)))
    # side-by-side vs the pooled-r-on-WTA-slice already computed above
    pooled_wta_bucket = pooled_sweep[str(dm)]["buckets_wta"]
    g75_pool = pooled_wta_bucket.get("75-80%", {}).get("gap")
    g80_pool = pooled_wta_bucket.get("80%+", {}).get("gap")
    print("   [vs pooled-r on same WTA holdout slice at this dm]: 75-80%% gap=%s   80%%+ gap=%s"
          % (("%+.3f" % g75_pool) if g75_pool is not None else "n/a",
             ("%+.3f" % g80_pool) if g80_pool is not None else "n/a"))

    wta_specific_sweep[str(dm)] = {"mae": mae, "mse": mse, "most_aces_fav_brier": maf_brier, "buckets": buckets}
    del fav_samp, dog_samp

RESULTS["wta_specific_sweep"] = wta_specific_sweep


# ---------------------------------------------------------------------------
# FINAL SUMMARY: suppressed overdispersion vs WTA-specific mismatch vs both
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("SUMMARY -- suppressed overdispersion vs WTA-specific mismatch vs both")
print("=" * 100)
base = pooled_sweep[str(1e6)]["buckets_all"].get("80%+", {}).get("gap")
print("Baseline (production, disp_mult=1e6) ALL 80%%+ gap: %+.3f" % base)
for dm in GRID:
    g_all = pooled_sweep[str(dm)]["buckets_all"].get("80%+", {}).get("gap")
    g_wta_pooled = pooled_sweep[str(dm)]["buckets_wta"].get("80%+", {}).get("gap")
    g_wta_specific = wta_specific_sweep[str(dm)]["buckets"].get("80%+", {}).get("gap")
    pct_all = 100 * (1 - abs(g_all) / abs(base)) if (g_all is not None and base) else None
    print("  dm=%-8g  ALL closed=%s%%   WTA(pooled-r) gap=%s   WTA(own-r) gap=%s"
          % (dm, ("%.0f" % pct_all) if pct_all is not None else "n/a",
             ("%+.3f" % g_wta_pooled) if g_wta_pooled is not None else "n/a",
             ("%+.3f" % g_wta_specific) if g_wta_specific is not None else "n/a"))

md5_check("after")
with open("/path/to/home/openclaw/apex_v2_dispersion_deep_audit_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2, default=str)
print("\nWrote apex_v2_dispersion_deep_audit_results.json")
print("\nDONE.")
