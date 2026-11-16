"""
Task 1 Step 4 (continued): gamma stability investigation.
Real V2 formula: pred_v2 = pred_v1 - gamma*z, z = pred_v1*(obr - mean_break_rate).
So: actual - pred_v2 = residual0 + gamma*z, where residual0 = actual - pred_v1.
Closed-form OLS (through-origin regression of residual0 on z, slope = -gamma):
    gamma_hat = -sum(residual0*z) / sum(z*z)
Fit window: year<=2021 only. Read-only against V1/V2 source files -- no source
files touched by this script. This script only reads apex_prop_sim_v2_fit.json
for cross-reference and writes its OWN results to
apex_v2_gamma_stability_results.json.
"""
import json
import pickle
import numpy as np

W, K = 40, 15
MIN_N = 10
RNG = np.random.default_rng(12345)

with open("/tmp/oppbr_rows.pkl", "rb") as f:
    rows = pickle.load(f)
fit_rows = [r for r in rows if r["year"] <= 2021]


def extract(rows):
    actual, pred_v1, obr = [], [], []
    for r in rows:
        for side, opp in (("w", "l"), ("l", "w")):
            ace_rate = r.get("%s_W%d_K%d_ace_rate" % (side, W, K))
            n_all = r.get("%s_W%d_K%d_nall" % (side, W, K))
            svgms = r.get("%s_svgms" % side)
            aces_actual = r.get("%s_aces" % side)
            opp_br = r.get("%s_W%d_K%d_break_rate" % (opp, W, K))
            vals = (ace_rate, n_all, svgms, aces_actual, opp_br)
            if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in vals):
                continue
            if n_all < MIN_N or svgms <= 0:
                continue
            actual.append(aces_actual)
            pred_v1.append(svgms * ace_rate)
            obr.append(opp_br)
    return np.array(actual, dtype=float), np.array(pred_v1, dtype=float), np.array(obr, dtype=float)

actual, pred_v1, obr = extract(fit_rows)
n = len(actual)
mean_break_rate = float(obr.mean())
residual0 = actual - pred_v1
z = pred_v1 * (obr - mean_break_rate)
leverage = z * z  # each point's contribution weight in OLS's sum(z*z)

print("n =", n, " mean_break_rate =", mean_break_rate)
print("z stats: mean=%.6f std=%.6f min=%.6f max=%.6f" % (z.mean(), z.std(), z.min(), z.max()))

mae_v1 = float(np.mean(np.abs(residual0)))
mse_v1 = float(np.mean(residual0 ** 2))
print("\nBASELINE (V1, gamma=0): MAE=%.4f MSE=%.4f %%neg=0.00%% (aces already >=0 by construction)" % (mae_v1, mse_v1))


def eval_gamma(name, gamma, note=""):
    pred_v2 = pred_v1 - gamma * z
    mae = float(np.mean(np.abs(actual - pred_v2)))
    mse = float(np.mean((actual - pred_v2) ** 2))
    negfrac = float(np.mean(pred_v2 < 0))
    print("\n%s" % name)
    print("  gamma = %.6f  %s" % (gamma, note))
    print("  [FULL fit-window, n=%d]  MAE=%.4f  MSE=%.4f  %%neg=%.2f%%" % (n, mae, mse, 100 * negfrac))
    return {"method": name, "gamma": gamma, "mae": mae, "mse": mse, "negfrac": negfrac, "note": note}


results = []

# ---------------------------------------------------------------------------
# METHOD 1: Current OLS fit (reproduction of Step 4's closed-form result)
# ---------------------------------------------------------------------------
gamma_ols = -float(np.sum(residual0 * z) / np.sum(z * z))
results.append(eval_gamma("METHOD 1: OLS (Step 4 reproduction)", gamma_ols,
                           "closed-form, unweighted, full sample"))

# ---------------------------------------------------------------------------
# METHOD 2: Trimmed fit -- remove extreme-leverage observations
# Leverage here = z^2 (each point's raw contribution to OLS's denominator).
# Trim the top 5% by leverage (both fit AND recompute gamma on the remainder),
# then report performance on the FULL sample so it's comparable to Method 1.
# ---------------------------------------------------------------------------
trim_pct = 0.05
thresh = np.quantile(leverage, 1 - trim_pct)
keep = leverage <= thresh
n_trim = int(keep.sum())
gamma_trim = -float(np.sum(residual0[keep] * z[keep]) / np.sum(z[keep] * z[keep]))
results.append(eval_gamma("METHOD 2: Trimmed OLS (top 5%% leverage removed, n_fit=%d)" % n_trim,
                           gamma_trim,
                           "fit on %d/%d obs after dropping top 5%% |z|-leverage" % (n_trim, n)))

# also try a more aggressive 10% trim to see sensitivity of the trim level itself
thresh10 = np.quantile(leverage, 0.90)
keep10 = leverage <= thresh10
gamma_trim10 = -float(np.sum(residual0[keep10] * z[keep10]) / np.sum(z[keep10] * z[keep10]))
results.append(eval_gamma("METHOD 2b: Trimmed OLS (top 10%% leverage removed, n_fit=%d)" % int(keep10.sum()),
                           gamma_trim10,
                           "sensitivity check on trim threshold"))

# ---------------------------------------------------------------------------
# METHOD 3: Huber / robust fit (IRLS through origin)
# Model: y = residual0, x = -z, target slope beta = gamma (since
# residual0 = -gamma*z + eps  <=>  y = beta*x with beta=gamma).
# IRLS with Huber weights: w_i = 1 if |resid_i| <= delta, else delta/|resid_i|.
# delta chosen via the standard 1.345*MAD(residuals) rule, re-estimated each
# iteration. Iterate to convergence.
# ---------------------------------------------------------------------------
x_h = -z
y_h = residual0
beta = gamma_ols  # start from OLS solution
for iteration in range(50):
    resid = y_h - beta * x_h
    mad = np.median(np.abs(resid - np.median(resid))) / 0.6745
    mad = max(mad, 1e-8)
    delta = 1.345 * mad
    absr = np.abs(resid)
    w = np.ones_like(resid)
    mask_out = absr > delta
    w[mask_out] = delta / absr[mask_out]
    num = np.sum(w * x_h * y_h)
    den = np.sum(w * x_h * x_h)
    beta_new = num / den
    if abs(beta_new - beta) < 1e-8:
        beta = beta_new
        break
    beta = beta_new
gamma_huber = float(beta)
results.append(eval_gamma("METHOD 3: Huber/IRLS robust fit (%d iterations)" % (iteration + 1),
                           gamma_huber,
                           "Huber delta=1.345*MAD(resid), reweighted each iter, converged on full sample"))

# ---------------------------------------------------------------------------
# METHOD 4: Bounded fit -- largest gamma such that %negative predictions
# stays under a defensible operational cap (1%), found via bisection.
# Assumes negfrac(gamma) is monotonically non-decreasing in gamma over [0, gamma_ols]
# (checked empirically below before trusting the bisection result).
# ---------------------------------------------------------------------------
CAP = 0.01


def negfrac(g):
    return float(np.mean((pred_v1 - g * z) < 0))


probe_gammas = np.linspace(0, gamma_ols, 11)
probe_negfracs = [negfrac(g) for g in probe_gammas]
monotonic = all(probe_negfracs[i] <= probe_negfracs[i + 1] + 1e-9 for i in range(len(probe_negfracs) - 1))

lo, hi = 0.0, gamma_ols
for _ in range(60):
    mid = (lo + hi) / 2
    if negfrac(mid) <= CAP:
        lo = mid
    else:
        hi = mid
gamma_bounded = lo
results.append(eval_gamma("METHOD 4: Bounded fit (max gamma with %%neg<=1%%, monotonic=%s)" % monotonic,
                           gamma_bounded,
                           "bisection on [0, gamma_ols], cap=1%% negative predictions"))

# ---------------------------------------------------------------------------
# METHOD 5: Theil-Sen-style median-of-ratios (through origin)
# Each observation individually implies: residual0_i + gamma*z_i = 0
#   => gamma_i = -residual0_i / z_i   (when z_i is not near zero)
# Unlike OLS (which weights each point's contribution by z_i^2, so a few
# extreme-|z| leverage points can dominate the whole sum), this estimator
# gives every point EQUAL weight via the median. It directly tests whether
# gamma=35.24 survives when leverage weighting is removed entirely.
# Points with |z| in the bottom 10th percentile are excluded first, since a
# tiny denominator makes gamma_i numerically explosive and uninformative
# regardless of true signal.
# ---------------------------------------------------------------------------
z_abs_thresh = np.quantile(np.abs(z), 0.10)
valid = np.abs(z) > z_abs_thresh
gamma_i_all = -residual0[valid] / z[valid]
gamma_median = float(np.median(gamma_i_all))
results.append(eval_gamma("METHOD 5: Median-of-ratios (Theil-Sen style, n=%d, |z|>p10 kept)" % int(valid.sum()),
                           gamma_median,
                           "per-observation gamma_i = -residual0_i/z_i, median taken -> equal weight per point"))

# For comparison for anyone auditing: also report the *mean* of ratios (not
# robust, included only to show how much a plain mean differs from the median
# under the same equal-weighting scheme -- if mean and median disagree a lot,
# that itself is more evidence of outlier-driven instability).
gamma_ratio_mean = float(np.mean(gamma_i_all))
print("\n  [diagnostic only, not a candidate] mean-of-ratios (same set) = %.4f  vs median = %.4f"
      % (gamma_ratio_mean, gamma_median))

# ---------------------------------------------------------------------------
# SUMMARY TABLE
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("SUMMARY -- all methods evaluated on the FULL year<=2021 fit-window sample (n=%d)" % n)
print("=" * 100)
print("%-70s %10s %8s %8s %8s" % ("method", "gamma", "MAE", "MSE", "%neg"))
print("%-70s %10s %8.4f %8.4f %8s" % ("BASELINE (V1, gamma=0)", "0.0000", mae_v1, mse_v1, "0.00%"))
for r in results:
    print("%-70s %10.4f %8.4f %8.4f %7.2f%%" % (r["method"][:70], r["gamma"], r["mae"], r["mse"], 100 * r["negfrac"]))

gammas_all = [r["gamma"] for r in results if "b" not in r["method"].split(":")[0]]  # exclude 2b sensitivity check
core_gammas = {
    "OLS": gamma_ols,
    "Trimmed(5%)": gamma_trim,
    "Huber": gamma_huber,
    "Bounded(1% cap)": gamma_bounded,
    "Median-of-ratios": gamma_median,
}
print("\nCore method gammas: " + ", ".join("%s=%.2f" % (k, v) for k, v in core_gammas.items()))
robust_vals = [gamma_trim, gamma_huber, gamma_bounded, gamma_median]
print("Robust-method range (trimmed/Huber/bounded/median-of-ratios): %.2f to %.2f"
      % (min(robust_vals), max(robust_vals)))
print("OLS vs robust-median-of-robust-methods: OLS=%.2f, median-of-4-robust=%.2f"
      % (gamma_ols, float(np.median(robust_vals))))

out = {
    "n": n,
    "mean_break_rate_fit_window": mean_break_rate,
    "baseline_mae": mae_v1,
    "baseline_mse": mse_v1,
    "results": results,
    "core_gammas": core_gammas,
    "monotonic_negfrac_check": monotonic,
}
with open("/path/to/home/openclaw/apex_v2_gamma_stability_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWrote apex_v2_gamma_stability_results.json")
