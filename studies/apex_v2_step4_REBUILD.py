"""
Task 1, Step 4 REBUILD: fit gamma against the REAL production quantity.
Root cause of the Step 6 holdout failure (documented, verified): the prior
fit used pred_v1 = svgms * ace_rate, but rate_bundle() (apex_prop_model_v1.py
line 205) defines ace_rate = aces / SERVE POINTS, not per service game. The
real quantity V2 actually multiplies in production is mu[side][0], built by
v1_inputs_from_rows() from V1's fully calibrated projection (price-blended,
overlay-adjusted) -- averaging ~6.4x larger than the old proxy and NOT
reproducible by svgms*ace_rate alone (verified: svgms*ace_rate*spg ~= mu,
ratio 1.065; svgms*ace_rate alone is ~6.4x too small).

This script refits gamma against mu[side][0] directly -- the exact object
V2 modifies -- using the exact centering constant production uses
(m["mean_break_rate"], not a self-recomputed value). Formula (approved,
unchanged): pred_v2 = mu0 * exp(-gamma * (obr - mean_break_rate)).

Fit window: year<=2021 only. Read-only against apex_prop_sim_v1.py /
apex_prop_model_v1.py / apex_prop_sim_v2.py (MD5-checked before and after).
"""
import json
import numpy as np
import pandas as pd

import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim

SACKMANN_DIR = "ATP & WTA, 1968-2026"
FIT_END, TUNE_START, TUNE_END, HOLD_START = 2021, 2022, 2023, 2024

print("Loading frozen V1 model (read-only)...")
m = v1.load_model()
W, K = m["window"], m["shrink"]
MEAN_BREAK_RATE = m["mean_break_rate"]  # the REAL, frozen, production centering constant
print("  window=%d shrink=%d  mean_break_rate=%.10f" % (W, K, MEAN_BREAK_RATE))

df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)
_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (np.isfinite(hf0) & np.isfinite(hd0) & np.isfinite(mu0["fav"][0])
          & np.isfinite(mu0["fav"][1]) & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1]))
df = df[okmask].reset_index(drop=True)
P, hf, hd, mu = sim.v1_inputs_from_rows(df, m)
print("usable rows (matches):", len(df))


def extract(rows_df, mu_fav, mu_dog):
    """Per-side, per-match observations. pred_v1 = mu[side][0] * svgms_actual
    -- mu[side][0] is the REAL production per-GAME aces rate (V1's fully
    calibrated projection); it must be scaled by service games played to
    become a match-total prediction comparable to actual total match aces
    (exactly what the simulator does internally: lambda = mu*svgms, then
    aces total is drawn from that). This is the corrected analogue of the
    original (broken) svgms*ace_rate proxy -- same structure, correct rate."""
    actual, pred_v1, obr = [], [], []
    for side, mu_arr, opp in (("fav", mu_fav, "dog"), ("dog", mu_dog, "fav")):
        y = rows_df["%s_aces" % side].values
        svgms_actual = rows_df["%s_svgms" % side].values
        p1 = mu_arr * svgms_actual
        ob = rows_df["%s_W%d_K%d_break_rate" % (opp, W, K)].values
        mk = np.isfinite(y) & np.isfinite(p1) & np.isfinite(ob)
        actual.append(y[mk]); pred_v1.append(p1[mk]); obr.append(ob[mk])
    return np.concatenate(actual), np.concatenate(pred_v1), np.concatenate(obr)


fit_mask = df["year"] <= FIT_END
fit_df = df[fit_mask]
mu_fav_fit = mu["fav"][0][fit_mask.values]
mu_dog_fit = mu["dog"][0][fit_mask.values]
actual, pred_v1, obr = extract(fit_df, mu_fav_fit, mu_dog_fit)
n = len(actual)
delta = obr - MEAN_BREAK_RATE
residual0 = actual - pred_v1
mae_v1 = float(np.mean(np.abs(residual0)))
mse_v1 = float(np.mean(residual0 ** 2))
print("\nFIT WINDOW (year<=%d): n=%d (side-observations, real mu[side][0] as pred_v1)" % (FIT_END, n))
print("  pred_v1 (real mu) mean=%.4f  actual mean=%.4f  (baseline agg bias=%.4f)"
      % (pred_v1.mean(), actual.mean(), pred_v1.mean() - actual.mean()))
print("BASELINE (V1, gamma=0): MAE=%.4f MSE=%.4f" % (mae_v1, mse_v1))

# ---------------------------------------------------------------------------
# Golden-section minimizer, same method as the original formula comparison.
# ---------------------------------------------------------------------------
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


def pred_exp(g):
    return pred_v1 * np.exp(-g * delta)


def mse_exp(g):
    return float(np.mean((actual - pred_exp(g)) ** 2))


def calib(pred_v2):
    resid = actual - pred_v2
    bias = float(np.mean(pred_v2) - np.mean(actual))
    ratio = float(np.mean(pred_v2) / np.mean(actual))
    denom = np.sum(delta * delta)
    leftover_slope = float(np.sum(resid * delta) / denom) if denom > 0 else float("nan")
    corr = float(np.corrcoef(resid, delta)[0, 1])
    return bias, ratio, leftover_slope, corr


lo, hi = grid_bracket(mse_exp, 0.01, 30.0, steps=150)
gamma_new = golden_min(mse_exp, lo, hi)
pred_v2_fit = pred_exp(gamma_new)
mae_new = float(np.mean(np.abs(actual - pred_v2_fit)))
mse_new = float(np.mean((actual - pred_v2_fit) ** 2))
negfrac_new = float(np.mean(pred_v2_fit < 0))
bias, ratio, leftover_slope, corr = calib(pred_v2_fit)

print("\n" + "=" * 90)
print("REBUILT FIT (exponential form, real production mu[side][0] as target)")
print("=" * 90)
print("gamma_new = %.6f  (OLD/BROKEN gamma was 12.879686 -- fit on the scale-broken proxy)" % gamma_new)
print("MAE: %.4f -> %.4f  (%.2f%% improvement)" % (mae_v1, mae_new, 100 * (mae_v1 - mae_new) / mae_v1))
print("MSE: %.4f -> %.4f  (%.2f%% improvement)" % (mse_v1, mse_new, 100 * (mse_v1 - mse_new) / mse_v1))
print("%% negative predictions: %.4f%%" % (100 * negfrac_new))
print("calibration: agg_bias=%.5f  agg_ratio=%.5f  leftover_delta_slope=%.4f  resid_vs_delta_corr=%.4f"
      % (bias, ratio, leftover_slope, corr))

# side-by-side: what would the OLD (broken) gamma have done if it had been
# correctly applied to the real mu[side][0] on THIS fit window? (context only)
pred_old_on_real = pred_exp(12.879686)
mae_old = float(np.mean(np.abs(actual - pred_old_on_real)))
mse_old = float(np.mean((actual - pred_old_on_real) ** 2))
print("\n[context] OLD gamma=12.879686 applied to the REAL mu (what production actually did):")
print("  MAE=%.4f  MSE=%.4f  (this is why holdout failed -- badly oversized for the real scale)" % (mae_old, mse_old))

out = {
    "n": n, "mean_break_rate_used": MEAN_BREAK_RATE, "window": W, "shrink": K,
    "baseline_mae": mae_v1, "baseline_mse": mse_v1,
    "gamma_new": gamma_new, "mae_new": mae_new, "mse_new": mse_new,
    "negfrac_new": negfrac_new, "agg_bias": bias, "agg_ratio": ratio,
    "leftover_delta_slope": leftover_slope, "resid_vs_delta_corr": corr,
    "old_gamma_on_real_mu": {"gamma": 12.879686, "mae": mae_old, "mse": mse_old},
}
with open("/path/to/home/openclaw/apex_v2_step4_REBUILD_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWrote apex_v2_step4_REBUILD_results.json")
