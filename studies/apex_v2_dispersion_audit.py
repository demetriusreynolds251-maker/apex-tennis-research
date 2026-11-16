"""
apex_v2_dispersion_audit.py

Audits coefs["disp"]["aces"] and the NB variance assumptions, per explicit
user instruction (2026-09-26 18:16 CT). Goal: determine whether the
remaining Aces MORE overconfidence (Phase 5's growing calibration gap in
the 80%+ bucket) is a VARIANCE-model problem rather than a MEAN-model
problem (which Aces V2's suppression already targeted and barely helped).

Read-only against apex_prop_sim_v1.py / apex_prop_model_v1.py. MD5 checked
before and after. Counterfactual dispersion values are tested ONLY inside
local, in-memory copies of the coefs dict passed into sim.run_rows() --
run_rows()/simulate() are pure functions of their coefs argument (no global
monkeypatching needed here, unlike the aces-mu substitution used for V2).
Nothing is written back to apex_prop_sim_v1.json. No coefficient is fit or
promoted -- this is diagnostic only, per standing instruction.
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
RESULTS = {}


# ---------------------------------------------------------------------------
# Load production pipeline + frozen coefs
# ---------------------------------------------------------------------------
m = v1.load_model()
coefs = sim.load_sim()
print("\nPRODUCTION coefs[\"disp\"] (fitted NB r, method-of-moments, pooled FIT<=%d):" % FIT_END)
print(json.dumps(coefs["disp"], indent=2))
print("PRODUCTION disp_mult:", coefs.get("disp_mult"))
print("(NB parameterization: Var = lam + lam^2/r_effective, r_effective = r * disp_mult)")
print("(disp_mult=1e6 -> r_effective ~ millions -> lam^2/r_effective ~ 0 -> effectively POISSON, near-zero added overdispersion)")
RESULTS["production_disp"] = coefs["disp"]
RESULTS["production_disp_mult"] = coefs.get("disp_mult")

df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)
_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (np.isfinite(hf0) & np.isfinite(hd0) & np.isfinite(mu0["fav"][0])
          & np.isfinite(mu0["fav"][1]) & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1]))
df = df[okmask].reset_index(drop=True)
fit_df = df[df["year"] <= FIT_END].reset_index(drop=True)
df_hold = df[df["year"] >= HOLD_START].reset_index(drop=True)
print("\nFit window (year<=%d): %d matches. Holdout (year>=%d): %d matches." % (FIT_END, len(fit_df), HOLD_START, len(df_hold)))


# ---------------------------------------------------------------------------
# Q2/Q3: is dispersion fit separately by tour/surface? (Answer from reading
# fit_constants(): NO -- one r per side, pooled over the whole fit window,
# regardless of tour/best_of/surface.) Independently recompute the SAME
# method-of-moments formula production uses, per segment, on the identical
# fit window, to check whether the pooled r masks real segment differences.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("Q2/Q3 -- IS DISPERSION FIT SEPARATELY BY TOUR/SURFACE? (segment-level r, same formula as fit_constants())")
print("=" * 100)
print("Production fit_constants() computes ONE r per side (fav/dog) x category (aces/dfs), pooled over the")
print("ENTIRE fit window (all tours/best_of/surfaces mixed) -- confirmed by reading the code directly. Below:")
print("the same moment-matching formula applied PER SEGMENT, to see what the pooled r is hiding.\n")

_, hf_fit, hd_fit, mu_fit = sim.v1_inputs_from_rows(fit_df, m)

def moment_r(mask, side, label):
    lam = mu_fit[side][0][mask] * fit_df.loc[mask, "%s_svgms" % side].values
    y = fit_df.loc[mask, "%s_aces" % side].values
    mk = np.isfinite(lam) & np.isfinite(y) & (lam > 0)
    var_over_mean = float(np.mean((y[mk] - lam[mk]) ** 2) / np.mean(lam[mk]))
    excess = np.mean((y[mk] - lam[mk]) ** 2) - np.mean(lam[mk])
    r = float(np.mean(lam[mk]) ** 2 / excess) if excess > 0 else float("inf")
    print("  %-24s n=%-7d mean_lam=%.3f  var/mean=%.3f  r=%.3f" % (label, int(mk.sum()), float(np.mean(lam[mk])), var_over_mean, r))
    return {"n": int(mk.sum()), "mean_lam": float(np.mean(lam[mk])), "var_over_mean": var_over_mean, "r": r}

q3 = {"pooled": {}, "by_tour": {}, "by_best_of": {}, "by_surface": {}}
for side in ("fav", "dog"):
    q3["pooled"][side] = moment_r(np.ones(len(fit_df), dtype=bool), side, "POOLED %s" % side)
print()
mask_atp = (fit_df["is_wta"] == 0).values
mask_wta = (fit_df["is_wta"] == 1).values
for side in ("fav", "dog"):
    q3["by_tour"]["ATP_%s" % side] = moment_r(mask_atp, side, "ATP %s" % side)
    q3["by_tour"]["WTA_%s" % side] = moment_r(mask_wta, side, "WTA %s" % side)
print()
for side in ("fav", "dog"):
    q3["by_best_of"]["Bo3_%s" % side] = moment_r((fit_df["best_of"] == 3).values, side, "Bo3 %s" % side)
    q3["by_best_of"]["Bo5_%s" % side] = moment_r((fit_df["best_of"] == 5).values, side, "Bo5 %s" % side)
print()
for side in ("fav", "dog"):
    for surf in ("Hard", "Clay", "Grass"):
        q3["by_surface"]["%s_%s" % (surf, side)] = moment_r((fit_df["surface"] == surf).values, side, "%s %s" % (surf, side))

RESULTS["q2_q3_segment_dispersion"] = q3
r_wta_fav = q3["by_tour"]["WTA_fav"]["r"]; r_pooled_fav = q3["pooled"]["fav"]["r"]
r_wta_dog = q3["by_tour"]["WTA_dog"]["r"]; r_pooled_dog = q3["pooled"]["dog"]["r"]
print("\n  => WTA fav r=%.3f is %.1f%% of pooled r=%.3f (lower r = more overdispersion than pooled assumes)"
      % (r_wta_fav, 100 * r_wta_fav / r_pooled_fav, r_pooled_fav))
print("  => WTA dog r=%.3f is %.1f%% of pooled r=%.3f" % (r_wta_dog, 100 * r_wta_dog / r_pooled_dog, r_pooled_dog))
print("  => BUT production's disp_mult=%g multiplies ANY of these r's toward ~infinity anyway --" % coefs.get("disp_mult"))
print("     in practice neither the pooled r NOR a WTA-specific r matters: production runs near-Poisson regardless.")


# ---------------------------------------------------------------------------
# Q1/Q4: COUNTERFACTUAL SIMULATION SWEEP on the year>=2024 holdout.
# Re-run the REAL, unmodified sim.run_rows() with local, in-memory copies of
# coefs where ONLY disp_mult is changed (never touching the frozen JSON on
# disk, never monkeypatching a module attribute -- run_rows() takes coefs
# as a plain argument). Same grid production's own tune_alpha() searched:
# (0.5, 1.0, 2.0, 4.0), plus the actual production value (1e6) as baseline.
# For each, rebuild the Phase-5 most_aces_fav calibration table and measure
# how much the 75-80% / 80%+ bucket gap changes.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("Q1/Q4 -- COUNTERFACTUAL DISPERSION SWEEP (holdout year>=%d, n=%d matches)" % (HOLD_START, len(df_hold)))
print("=" * 100)

N_SIMS_SWEEP = 1000  # halved from the 2000 used elsewhere, for a 5-point sweep in reasonable time
DM_GRID = [1e6, 4.0, 2.0, 1.0, 0.5]  # 1e6 first = current production baseline

fav_aces_actual = df_hold["fav_aces"].values
dog_aces_actual = df_hold["dog_aces"].values

pbins = [0.0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01]
plabels = ["<55%", "55-60%", "60-65%", "65-70%", "70-75%", "75-80%", "80%+"]

sweep_results = {}
for dm in DM_GRID:
    coefs_cf = copy.deepcopy(coefs)
    coefs_cf["disp_mult"] = dm
    print("\n-- disp_mult=%g (r_effective_fav=%.2f, r_effective_dog=%.2f) --"
          % (dm, coefs["disp"]["fav"]["aces"] * dm, coefs["disp"]["dog"]["aces"] * dm))
    t0 = time.time()
    sims = sim.run_rows(df_hold, m, coefs_cf, N_SIMS_SWEEP, seed=1, progress=False)
    print("   simulated in %.1fs" % (time.time() - t0))

    fav_samp = np.stack([s["fav"]["aces"] for s, _, _, _ in sims])
    dog_samp = np.stack([s["dog"]["aces"] for s, _, _, _ in sims])
    gt = fav_samp > dog_samp
    ne = fav_samp != dog_samp
    pred_prob = gt.mean(axis=1) / np.maximum(ne.mean(axis=1), 1e-9)
    tie_mask = fav_aces_actual == dog_aces_actual
    actual_win = (fav_aces_actual > dog_aces_actual).astype(float)
    valid = ~tie_mask
    del fav_samp, dog_samp

    buckets = {}
    for lo, hi, lab in zip(pbins[:-1], pbins[1:], plabels):
        mask = valid & (pred_prob >= lo) & (pred_prob < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        pp = float(np.mean(pred_prob[mask])); ap = float(np.mean(actual_win[mask])); gap = pp - ap
        print("   %-8s n=%-6d predicted=%.3f actual=%.3f gap=%+.3f" % (lab, n, pp, ap, gap))
        buckets[lab] = {"n": n, "predicted": pp, "actual": ap, "gap": gap}

    # overall Brier on most_aces_fav (matches production's own binary metric)
    brier = float(np.mean((pred_prob[valid] - actual_win[valid]) ** 2))
    print("   overall most_aces_fav Brier = %.4f" % brier)
    sweep_results[str(dm)] = {"buckets": buckets, "brier": brier}

RESULTS["q1_q4_dispersion_sweep"] = sweep_results


# ---------------------------------------------------------------------------
# Summary: how much of the 80%+ (and 75-80%) gap disappears vs baseline?
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("SUMMARY -- 75-80%% / 80%%+ bucket gap vs disp_mult")
print("=" * 100)
base_75 = sweep_results[str(1e6)]["buckets"].get("75-80%", {}).get("gap")
base_80 = sweep_results[str(1e6)]["buckets"].get("80%+", {}).get("gap")
for dm in DM_GRID:
    b = sweep_results[str(dm)]["buckets"]
    g75 = b.get("75-80%", {}).get("gap"); g80 = b.get("80%+", {}).get("gap")
    pct75 = 100 * (1 - abs(g75) / abs(base_75)) if (g75 is not None and base_75) else None
    pct80 = 100 * (1 - abs(g80) / abs(base_80)) if (g80 is not None and base_80) else None
    print("  disp_mult=%-8g 75-80%% gap=%+.3f (%s%% closed)   80%%+ gap=%+.3f (%s%% closed)   Brier=%.4f"
          % (dm, g75 if g75 is not None else float('nan'),
             ("%.0f" % pct75) if pct75 is not None else "n/a",
             g80 if g80 is not None else float('nan'),
             ("%.0f" % pct80) if pct80 is not None else "n/a",
             sweep_results[str(dm)]["brier"]))

md5_check("after")
with open("/path/to/home/openclaw/apex_v2_dispersion_audit_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2, default=str)
print("\nWrote apex_v2_dispersion_audit_results.json")
print("\nDONE.")
