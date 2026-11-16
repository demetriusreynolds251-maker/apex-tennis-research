"""
apex_v2_bo3bo5_split.py

Splits the entire Aces MORE / Aces V2 analysis into Bo3-only, Bo5-only, and
Combined slices, per explicit user request (2026-09-26):

  "Before calling the Aces MORE investigation complete: Split the entire
  analysis into: 1. Bo3 only 2. Bo5 only 3. Combined
  A) What is Bo3 calibration today?
  B) What is Bo5 calibration today?
  C) How much of the original overconfidence comes from Bo5?
  D) Apply the new V2 mechanism separately to Bo3 and Bo5.
  E) Does gamma differ materially between Bo3 and Bo5?
  F) Does the +1.29 Bo5 overshoot remain after suppression is added?"

Does NOT modify apex_prop_sim_v1.py or apex_prop_model_v1.py. MD5 of both is
checked before and after. Uses the same production pipeline, monkeypatch
adapter technique, and golden-section gamma-fit helper established in
apex_v2_step4_REBUILD.py / apex_v2_step5_REBUILD.py / apex_v2_step6_holdout.py.

best_of is a clean two-valued column in apex_prop_rows_v1.csv (3 / 5), no
inference needed.
"""
import hashlib, json
import numpy as np
import pandas as pd

import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim
import apex_prop_sim_v2 as sim2

FROZEN = {
    "apex_prop_sim_v1.py": "7b03e521e804862b85804f8ac4db7346",
    "apex_prop_model_v1.py": "6bf50622a1761156a77ad0d35a2007f6",
}

def md5_check(tag):
    for fn, expected in FROZEN.items():
        got = hashlib.md5(open(fn, "rb").read()).hexdigest()
        status = "PASS" if got == expected else "FAIL"
        print("MD5 %s [%s]: %s (expected %s, got %s)" % (tag, fn, status, expected, got))
        if status == "FAIL":
            raise SystemExit("MD5 MISMATCH on frozen file %s -- aborting." % fn)

md5_check("before")

FIT_END, TUNE_START, TUNE_END, HOLD_START = 2021, 2022, 2023, 2024
SACKMANN_DIR = "ATP & WTA, 1968-2026"
N_SIMS = 2000

RESULTS = {}

# ---------------------------------------------------------------------------
# Load production pipeline (identical to Step 6 holdout harness)
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

print("Full usable population:", df.shape, dict(df["best_of"].value_counts()))

df_fit = df[df["year"] <= FIT_END].reset_index(drop=True)
df_tune = df[(df["year"] >= TUNE_START) & (df["year"] <= TUNE_END)].reset_index(drop=True)
df_hold = df[df["year"] >= HOLD_START].reset_index(drop=True)

print("Fit window:", dict(df_fit["best_of"].value_counts()))
print("Tune window:", dict(df_tune["best_of"].value_counts()))
print("Holdout window:", dict(df_hold["best_of"].value_counts()))

RESULTS["population"] = {
    "full": {str(k): int(v) for k, v in df["best_of"].value_counts().items()},
    "fit": {str(k): int(v) for k, v in df_fit["best_of"].value_counts().items()},
    "tune": {str(k): int(v) for k, v in df_tune["best_of"].value_counts().items()},
    "hold": {str(k): int(v) for k, v in df_hold["best_of"].value_counts().items()},
}


# ---------------------------------------------------------------------------
# extract() -- identical corrected methodology to apex_v2_step4_REBUILD.py:
# pred_v1 = mu[side][0] (real, calibrated per-game rate) * svgms_actual.
# ---------------------------------------------------------------------------
def extract(rows_df, mu_fav, mu_dog):
    actual, pred_v1, obr = [], [], []
    for side, mu_arr, opp in (("fav", mu_fav, "dog"), ("dog", mu_dog, "fav")):
        y = rows_df["%s_aces" % side].values
        svgms_actual = rows_df["%s_svgms" % side].values
        p1 = mu_arr * svgms_actual
        ob = rows_df["%s_W%d_K%d_break_rate" % (opp, W, K)].values
        mk = np.isfinite(y) & np.isfinite(p1) & np.isfinite(ob)
        actual.append(y[mk]); pred_v1.append(p1[mk]); obr.append(ob[mk])
    return np.concatenate(actual), np.concatenate(pred_v1), np.concatenate(obr)

PHI = (np.sqrt(5) - 1) / 2

def golden_min(f, lo, hi, tol=1e-7, max_iter=300):
    a, b = lo, hi
    c = b - PHI * (b - a); d = a + PHI * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(max_iter):
        if abs(b - a) < tol:
            break
        if fc < fd:
            b, d, fd = d, c, fc; c = b - PHI * (b - a); fc = f(c)
        else:
            a, c, fc = c, d, fd; d = a + PHI * (b - a); fd = f(d)
    return (a + b) / 2

def grid_bracket(f, lo, hi, steps=100):
    xs = np.linspace(lo, hi, steps); ys = [f(x) for x in xs]
    i = int(np.argmin(ys))
    return xs[max(0, i - 2)], xs[min(len(xs) - 1, i + 2)]

def calib(actual, pred_v2, delta):
    resid = actual - pred_v2
    bias = float(np.mean(pred_v2) - np.mean(actual))
    ratio = float(np.mean(pred_v2) / np.mean(actual))
    denom = np.sum(delta * delta)
    leftover_slope = float(np.sum(resid * delta) / denom) if denom > 0 else float("nan")
    corr = float(np.corrcoef(resid, delta)[0, 1])
    return bias, ratio, leftover_slope, corr


# ---------------------------------------------------------------------------
# QUESTIONS C & E: fit gamma separately on Bo3-fit-window vs Bo5-fit-window
# vs Combined-fit-window (year<=2021), and decompose baseline V1 overconfidence
# (agg_bias at gamma=0) by best_of.
# ---------------------------------------------------------------------------
def fit_slice(rows_df, label):
    mask = rows_df["year"] <= FIT_END
    sub = rows_df[mask]
    _, hf_s, hd_s, mu_s = sim.v1_inputs_from_rows(sub, m)
    actual, pred_v1, obr = extract(sub, mu_s["fav"][0], mu_s["dog"][0])
    n = len(actual)
    delta = obr - mean_break_rate
    resid0 = actual - pred_v1
    baseline_bias = float(np.mean(pred_v1) - np.mean(actual))
    baseline_mae = float(np.mean(np.abs(resid0)))
    baseline_mse = float(np.mean(resid0 ** 2))
    baseline_corr = float(np.corrcoef(resid0, delta)[0, 1])

    def mse_exp(g):
        pv2 = pred_v1 * np.exp(-g * delta)
        return float(np.mean((actual - pv2) ** 2))

    lo, hi = grid_bracket(mse_exp, 0.01, 30.0, steps=150)
    gamma_fit = golden_min(mse_exp, lo, hi)
    pred_v2 = pred_v1 * np.exp(-gamma_fit * delta)
    mae2 = float(np.mean(np.abs(actual - pred_v2)))
    mse2 = float(np.mean((actual - pred_v2) ** 2))
    bias2, ratio2, slope2, corr2 = calib(actual, pred_v2, delta)

    print("\n--- %s (fit window, year<=%d) ---" % (label, FIT_END))
    print("  n=%d  actual_mean=%.4f  pred_v1_mean=%.4f" % (n, actual.mean(), pred_v1.mean()))
    print("  BASELINE V1 (gamma=0): agg_bias=%.4f  MAE=%.4f  MSE=%.4f  resid_vs_delta_corr=%.4f"
          % (baseline_bias, baseline_mae, baseline_mse, baseline_corr))
    print("  FITTED gamma=%.6f -> MAE=%.4f (%.2f%%)  MSE=%.4f (%.2f%%)  agg_bias=%.5f  resid_vs_delta_corr=%.4f"
          % (gamma_fit, mae2, 100*(baseline_mae-mae2)/baseline_mae, mse2,
             100*(baseline_mse-mse2)/baseline_mse, bias2, corr2))
    return {
        "n": n, "actual_mean": float(actual.mean()), "pred_v1_mean": float(pred_v1.mean()),
        "baseline_bias": baseline_bias, "baseline_mae": baseline_mae, "baseline_mse": baseline_mse,
        "baseline_resid_vs_delta_corr": baseline_corr,
        "gamma_fit": gamma_fit, "mae_after": mae2, "mse_after": mse2,
        "agg_bias_after": bias2, "resid_vs_delta_corr_after": corr2,
    }

print("\n" + "=" * 90)
print("QUESTIONS C & E -- fit-window (year<=%d) gamma and bias by best_of" % FIT_END)
print("=" * 90)
res_bo3_fit = fit_slice(df[df["best_of"] == 3], "Bo3-only")
res_bo5_fit = fit_slice(df[df["best_of"] == 5], "Bo5-only")
res_combined_fit = fit_slice(df, "Combined (all best_of)")

RESULTS["fit_window"] = {"bo3": res_bo3_fit, "bo5": res_bo5_fit, "combined": res_combined_fit}


# Exact linear decomposition of combined agg_bias into Bo3/Bo5 contributions
# (agg_bias = mean(pred)-mean(actual) is a linear statistic, so the combined
# value is exactly the n-weighted average of the per-slice values).
n3, n5 = res_bo3_fit["n"], res_bo5_fit["n"]
ntot = n3 + n5
w3, w5 = n3 / ntot, n5 / ntot
contrib3 = w3 * res_bo3_fit["baseline_bias"]
contrib5 = w5 * res_bo5_fit["baseline_bias"]
recon = contrib3 + contrib5
print("\n--- QUESTION C: decomposition of combined baseline agg_bias ---")
print("  n_bo3=%d (%.1f%%)  n_bo5=%d (%.1f%%)" % (n3, 100*w3, n5, 100*w5))
print("  Bo3 contribution = w_bo3 * bias_bo3 = %.4f * %.4f = %.5f" % (w3, res_bo3_fit["baseline_bias"], contrib3))
print("  Bo5 contribution = w_bo5 * bias_bo5 = %.4f * %.4f = %.5f" % (w5, res_bo5_fit["baseline_bias"], contrib5))
print("  Reconstructed combined bias = %.5f  (actual combined = %.5f, diff=%.2e)"
      % (recon, res_combined_fit["baseline_bias"], recon - res_combined_fit["baseline_bias"]))
if recon != 0:
    print("  => Bo5 share of combined bias = %.1f%%  |  Bo3 share = %.1f%%"
          % (100*contrib5/recon, 100*contrib3/recon))
print("  Per-match-observation, Bo5's baseline bias magnitude is %.2fx Bo3's (%.4f vs %.4f)"
      % (abs(res_bo5_fit["baseline_bias"])/max(abs(res_bo3_fit["baseline_bias"]),1e-9),
         res_bo5_fit["baseline_bias"], res_bo3_fit["baseline_bias"]))
print("  Signal strength (resid_vs_delta_corr): Bo3=%.4f  Bo5=%.4f  Combined=%.4f"
      % (res_bo3_fit["baseline_resid_vs_delta_corr"], res_bo5_fit["baseline_resid_vs_delta_corr"],
         res_combined_fit["baseline_resid_vs_delta_corr"]))

RESULTS["question_C_decomposition"] = {
    "n_bo3": n3, "n_bo5": n5, "w_bo3": w3, "w_bo5": w5,
    "contrib_bo3": contrib3, "contrib_bo5": contrib5, "reconstructed_combined": recon,
    "actual_combined": res_combined_fit["baseline_bias"],
    "bo5_share_pct": 100*contrib5/recon if recon != 0 else None,
    "bo3_share_pct": 100*contrib3/recon if recon != 0 else None,
}

print("\n--- QUESTION E: gamma comparison ---")
print("  gamma_bo3=%.6f  gamma_bo5=%.6f  gamma_combined=%.6f" %
      (res_bo3_fit["gamma_fit"], res_bo5_fit["gamma_fit"], res_combined_fit["gamma_fit"]))
rel_diff_bo3 = 100*(res_bo3_fit["gamma_fit"]-res_combined_fit["gamma_fit"])/res_combined_fit["gamma_fit"]
rel_diff_bo5 = 100*(res_bo5_fit["gamma_fit"]-res_combined_fit["gamma_fit"])/res_combined_fit["gamma_fit"]
print("  Bo3 vs combined: %+.1f%%   Bo5 vs combined: %+.1f%%" % (rel_diff_bo3, rel_diff_bo5))
RESULTS["question_E_gamma_comparison"] = {
    "gamma_bo3": res_bo3_fit["gamma_fit"], "gamma_bo5": res_bo5_fit["gamma_fit"],
    "gamma_combined": res_combined_fit["gamma_fit"],
    "bo3_vs_combined_pct": rel_diff_bo3, "bo5_vs_combined_pct": rel_diff_bo5,
}


# ---------------------------------------------------------------------------
# QUESTIONS A, B, D, F -- HOLDOUT (year>=2024), split by best_of.
# Reuses the exact monkeypatch-adapter technique from Step 6: the real,
# unmodified sim.holdout_report()/run_rows() are called; only the aces-mu
# generation is substituted, verified bit-identical to the approved
# apex_prop_sim_v2.v2_inputs_from_rows() before any patch is installed.
# ---------------------------------------------------------------------------
TRUE_V1_INPUTS_FROM_ROWS = sim.v1_inputs_from_rows

def make_adapter(gamma):
    def v2_adapter(df_, m_):
        P, hf, hd, mu = TRUE_V1_INPUTS_FROM_ROWS(df_, m_)
        opp_break_rate = {
            "fav": df_["dog_W%d_K%d_break_rate" % (W, K)].values,
            "dog": df_["fav_W%d_K%d_break_rate" % (W, K)].values,
        }
        mu2 = {}
        for side in ("fav", "dog"):
            aces0, dfs0 = mu[side]
            suppression = np.exp(-gamma * (opp_break_rate[side] - mean_break_rate))
            mu2[side] = (aces0 * suppression, dfs0)
        return P, hf, hd, mu2
    return v2_adapter

# verify combined-gamma adapter is bit-identical to the real, approved module
sample = df_hold.head(500)
adapter_combined = make_adapter(sim2.GAMMA_FIT)
P_a, hf_a, hd_a, mu_a = sim2.v2_inputs_from_rows(sample, m)
P_b, hf_b, hd_b, mu_b = adapter_combined(sample, m)
checks = []
for side in ("fav", "dog"):
    checks.append(np.array_equal(mu_a[side][0], mu_b[side][0]))
    checks.append(np.array_equal(mu_a[side][1], mu_b[side][1]))
print("\nADAPTER VERIFICATION vs real apex_prop_sim_v2.v2_inputs_from_rows(): all_identical =", all(checks))
if not all(checks):
    raise SystemExit("ADAPTER MISMATCH -- aborting before any holdout run")


def aces_bias_mae_mse(hold_subset, gamma=None):
    """Direct aces bias/MAE/MSE via run_rows(), patched or unpatched."""
    if gamma is not None:
        sim.v1_inputs_from_rows = make_adapter(gamma)
    try:
        sims = sim.run_rows(hold_subset, m, coefs, N_SIMS, seed=1, progress=False)
    finally:
        sim.v1_inputs_from_rows = TRUE_V1_INPUTS_FROM_ROWS
    out = {}
    for side in ("fav", "dog"):
        y = hold_subset["%s_aces" % side].values
        sm = np.array([s[side]["aces"].mean() for s, _, _, _ in sims])
        mk = np.isfinite(y) & np.isfinite(sm)
        bias = float(np.mean(sm[mk] - y[mk]))
        mae = float(np.mean(np.abs(sm[mk] - y[mk])))
        mse = float(np.mean((sm[mk] - y[mk]) ** 2))
        out[side] = {"bias": bias, "mae": mae, "mse": mse, "n": int(mk.sum())}
    return out

HOLDOUT_RESULTS = {}
subset_gammas = {"Bo3": res_bo3_fit["gamma_fit"], "Bo5": res_bo5_fit["gamma_fit"]}

for label, bo_val in (("Bo3", 3), ("Bo5", 5)):
    print("\n" + "=" * 90)
    print("HOLDOUT (year>=%d), %s only, n=%d" % (HOLD_START, label, int((df_hold["best_of"] == bo_val).sum())))
    print("=" * 90)
    hold_sub = df_hold[df_hold["best_of"] == bo_val].reset_index(drop=True)

    # Q A/B: today's V1 calibration -- real holdout_report(), unpatched
    Lv1 = []
    res_v1_sub = sim.holdout_report(hold_sub, m, coefs, N_SIMS, Lv1)
    print("-- V1 (today, no suppression) calibration --")
    for k in sorted(res_v1_sub["means"]):
        if "aces" in k:
            print("  means[%s] mae_sim=%.4f" % (k, res_v1_sub["means"][k]["mae_sim"]))
    for k in sorted(res_v1_sub["calibration"]):
        if "aces" in k:
            c = res_v1_sub["calibration"][k]
            print("  calibration[%s] brier=%.4f n=%d" % (k, c["brier"], c["n"]))
    if "most_aces_fav" in res_v1_sub["binary"]:
        b = res_v1_sub["binary"]["most_aces_fav"]
        print("  binary[most_aces_fav] pred=%.3f actual=%.3f brier=%.4f" % (b["pred"], b["actual"], b["brier"]))

    # direct bias/MAE/MSE, V1 baseline (gamma=0, i.e. unpatched)
    base = aces_bias_mae_mse(hold_sub, gamma=None)
    # V2, combined gamma
    v2_combined = aces_bias_mae_mse(hold_sub, gamma=sim2.GAMMA_FIT)
    # V2, subset-specific gamma
    v2_specific = aces_bias_mae_mse(hold_sub, gamma=subset_gammas[label])

    print("\n-- direct aces bias/MAE/MSE (V1 vs V2-combined-gamma vs V2-%s-specific-gamma) --" % label)
    for side in ("fav", "dog"):
        b0, bc, bs = base[side], v2_combined[side], v2_specific[side]
        print("  %s: V1 bias=%+.4f MAE=%.4f MSE=%.4f  |  V2(combined g=%.4f) bias=%+.4f MAE=%.4f MSE=%.4f  |  V2(%s g=%.4f) bias=%+.4f MAE=%.4f MSE=%.4f"
              % (side, b0["bias"], b0["mae"], b0["mse"],
                 sim2.GAMMA_FIT, bc["bias"], bc["mae"], bc["mse"],
                 label, subset_gammas[label], bs["bias"], bs["mae"], bs["mse"]))

    HOLDOUT_RESULTS[label] = {
        "n": int(len(hold_sub)),
        "v1_holdout_report_means": {k: v for k, v in res_v1_sub["means"].items() if "aces" in k},
        "v1_holdout_report_calibration": {k: v for k, v in res_v1_sub["calibration"].items() if "aces" in k},
        "v1_holdout_report_binary_most_aces_fav": res_v1_sub["binary"].get("most_aces_fav"),
        "direct_v1_baseline": base,
        "direct_v2_combined_gamma": v2_combined,
        "direct_v2_subset_specific_gamma": v2_specific,
        "subset_specific_gamma": subset_gammas[label],
    }

assert sim.v1_inputs_from_rows is TRUE_V1_INPUTS_FROM_ROWS
RESULTS["holdout"] = HOLDOUT_RESULTS


# ---------------------------------------------------------------------------
# QUESTION F -- does the previously-documented Bo5 "+1.29 ace projection
# overshoot" remain after suppression? NOTE: the +1.29 figure in
# APEX_ACES_MORE_INVESTIGATION_2026-09-24.md is not re-derived anywhere in
# that document (it is cited there as an already-known, separately-tracked
# open finding, with no worked derivation attached). We do not assume it
# matches our methodology -- we measure the actual current Bo5 aces
# bias/overshoot directly on the real holdout population (both sides
# combined, i.e. the same "match-total aces" quantity the +1.29 figure
# describes) and report the real measured number alongside it.
# ---------------------------------------------------------------------------
print("\n" + "=" * 90)
print("QUESTION F -- Bo5 aces overshoot: V1 (today) vs V2 (suppression applied)")
print("=" * 90)
b5 = HOLDOUT_RESULTS["Bo5"]
combined_bias_v1 = (b5["direct_v1_baseline"]["fav"]["bias"] * b5["direct_v1_baseline"]["fav"]["n"]
                     + b5["direct_v1_baseline"]["dog"]["bias"] * b5["direct_v1_baseline"]["dog"]["n"]) / \
                    (b5["direct_v1_baseline"]["fav"]["n"] + b5["direct_v1_baseline"]["dog"]["n"])
combined_bias_v2c = (b5["direct_v2_combined_gamma"]["fav"]["bias"] * b5["direct_v2_combined_gamma"]["fav"]["n"]
                      + b5["direct_v2_combined_gamma"]["dog"]["bias"] * b5["direct_v2_combined_gamma"]["dog"]["n"]) / \
                     (b5["direct_v2_combined_gamma"]["fav"]["n"] + b5["direct_v2_combined_gamma"]["dog"]["n"])
combined_bias_v2s = (b5["direct_v2_subset_specific_gamma"]["fav"]["bias"] * b5["direct_v2_subset_specific_gamma"]["fav"]["n"]
                      + b5["direct_v2_subset_specific_gamma"]["dog"]["bias"] * b5["direct_v2_subset_specific_gamma"]["dog"]["n"]) / \
                     (b5["direct_v2_subset_specific_gamma"]["fav"]["n"] + b5["direct_v2_subset_specific_gamma"]["dog"]["n"])
print("  Measured Bo5 aces bias, V1 (today, no suppression):           %+.4f aces/match" % combined_bias_v1)
print("  Measured Bo5 aces bias, V2 (combined gamma=%.4f):             %+.4f aces/match" % (sim2.GAMMA_FIT, combined_bias_v2c))
print("  Measured Bo5 aces bias, V2 (Bo5-specific gamma=%.4f):         %+.4f aces/match" % (subset_gammas["Bo5"], combined_bias_v2s))
print("  [context] previously-cited figure elsewhere: +1.29 (not independently re-derived in the source doc)")
print("  Overshoot reduction (combined gamma):      %+.4f -> %+.4f  (%.1f%% of V1 magnitude remains)"
      % (combined_bias_v1, combined_bias_v2c, 100*abs(combined_bias_v2c)/abs(combined_bias_v1) if combined_bias_v1 else float('nan')))
print("  Overshoot reduction (Bo5-specific gamma):  %+.4f -> %+.4f  (%.1f%% of V1 magnitude remains)"
      % (combined_bias_v1, combined_bias_v2s, 100*abs(combined_bias_v2s)/abs(combined_bias_v1) if combined_bias_v1 else float('nan')))

RESULTS["question_F"] = {
    "bo5_bias_v1_today": combined_bias_v1,
    "bo5_bias_v2_combined_gamma": combined_bias_v2c,
    "bo5_bias_v2_specific_gamma": combined_bias_v2s,
    "previously_cited_figure_context": 1.29,
}

# ---------------------------------------------------------------------------
# Final MD5 check + write results
# ---------------------------------------------------------------------------
md5_check("after")

with open("/path/to/home/openclaw/apex_v2_bo3bo5_split_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2, default=str)
print("\nWrote apex_v2_bo3bo5_split_results.json")
print("\nDONE.")
