"""
Task 1 Step 4 (continued, phase 2): suppression FORMULA comparison.
Prior phase established: the effect size (gamma ~28-35 under the linear form)
is a real signal, not an outlier artifact -- but the linear multiplicative
form pred_v2 = pred_v1*(1 - gamma*delta) produces ~30-32% impossible negative
ace means at that effect size. This script does NOT pick a gamma. It tests
candidate FUNCTIONAL FORMS for the suppression term, each independently
gamma-fit on the SAME year<=2021 fit window (this is a "fit", per the
established Step 4 usage of that word -- NOT a "tune", which is reserved for
2022-2023 and is explicitly not run here). No holdout. No freeze. No V1/V2
source files touched -- read-only against apex_prop_sim_v1.py /
apex_prop_model_v1.py and against apex_prop_sim_v2.py.

delta := opponent_break_rate - mean_break_rate (fit-window mean, same
constant used throughout this investigation: 0.2564119721242022 at W=40,K=15).
"""
import json
import pickle
import numpy as np

W, K = 40, 15
MIN_N = 10

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
delta = obr - mean_break_rate
residual0 = actual - pred_v1
mae_v1 = float(np.mean(np.abs(residual0)))
mse_v1 = float(np.mean(residual0 ** 2))
print("n =", n, " mean_break_rate =", mean_break_rate)
print("BASELINE (V1): MAE=%.4f MSE=%.4f" % (mae_v1, mse_v1))

# ---------------------------------------------------------------------------
# Generic 1-parameter golden-section minimizer (no scipy dependency assumed).
# Used to gamma-fit every non-linear formula below by minimizing MSE(gamma)
# directly. Verified unimodal per-formula via a coarse grid scan first.
# ---------------------------------------------------------------------------
PHI = (np.sqrt(5) - 1) / 2


def golden_min(f, lo, hi, tol=1e-6, max_iter=200):
    a, b = lo, hi
    c = b - PHI * (b - a)
    d = a + PHI * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(max_iter):
        if abs(b - a) < tol:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - PHI * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + PHI * (b - a)
            fd = f(d)
    return (a + b) / 2


def grid_bracket(f, lo, hi, steps=60):
    xs = np.linspace(lo, hi, steps)
    ys = [f(x) for x in xs]
    i = int(np.argmin(ys))
    lo2 = xs[max(0, i - 2)]
    hi2 = xs[min(len(xs) - 1, i + 2)]
    return lo2, hi2, xs[i], ys[i]


def calibration_and_residual_signal(pred_v2):
    resid = actual - pred_v2
    bias = float(np.mean(pred_v2) - np.mean(actual))
    calib_ratio = float(np.mean(pred_v2) / np.mean(actual))
    denom = np.sum(delta * delta)
    leftover_slope = float(np.sum(resid * delta) / denom) if denom > 0 else float("nan")
    corr = float(np.corrcoef(resid, delta)[0, 1])
    return bias, calib_ratio, leftover_slope, corr


def report(name, pred_v2_fn, gamma, extra_note=""):
    pred_v2 = pred_v2_fn(gamma)
    mae = float(np.mean(np.abs(actual - pred_v2)))
    mse = float(np.mean((actual - pred_v2) ** 2))
    negfrac = float(np.mean(pred_v2 < 0))
    bias, calib_ratio, leftover_slope, corr = calibration_and_residual_signal(pred_v2)
    print("\n%s" % name)
    print("  gamma = %.6f  %s" % (gamma, extra_note))
    print("  MAE=%.4f  MSE=%.4f  %%neg=%.2f%%  MSE_improvement=%.2f%%"
          % (mae, mse, 100 * negfrac, 100 * (mse_v1 - mse) / mse_v1))
    print("  calibration: agg_bias=%.5f  agg_ratio=%.5f  leftover_delta_slope=%.4f  resid_vs_delta_corr=%.4f"
          % (bias, calib_ratio, leftover_slope, corr))
    return {"formula": name, "gamma": gamma, "mae": mae, "mse": mse, "negfrac": negfrac,
            "mse_improvement_pct": 100 * (mse_v1 - mse) / mse_v1, "agg_bias": bias,
            "agg_ratio": calib_ratio, "leftover_delta_slope": leftover_slope,
            "resid_vs_delta_corr": corr, "note": extra_note}


results = []

# ---------------------------------------------------------------------------
# FORMULA A: current linear multiplicative model (reference only)
# pred_v2 = pred_v1 * (1 - gamma*delta)
# Closed-form OLS gamma, reproduced from the prior stability investigation.
# ---------------------------------------------------------------------------
z_A = pred_v1 * delta
gamma_A = -float(np.sum(residual0 * z_A) / np.sum(z_A * z_A))


def pred_A(g):
    return pred_v1 * (1 - g * delta)


results.append(report("A: Linear multiplicative (reference, unclamped)", pred_A, gamma_A,
                       "closed-form OLS; carried over from Step 4 / stability investigation"))

# ---------------------------------------------------------------------------
# FORMULA B: clamped multiplicative model
# pred_v2 = pred_v1 * max(1 - gamma*delta, floor)
# floor is a fixed, documented positive constant (a suppression factor can
# never fully zero out a player's ace rate -- floor represents "the opponent
# absolutely cannot erase a server's aces to zero"). Tested at two floor
# values to show sensitivity to that choice.
# ---------------------------------------------------------------------------
def make_pred_B(floor):
    def pred_B(g):
        factor = np.maximum(1 - g * delta, floor)
        return pred_v1 * factor
    return pred_B


for floor in (0.05, 0.15):
    pred_B = make_pred_B(floor)
    def mse_B(g, pred_B=pred_B):
        return float(np.mean((actual - pred_B(g)) ** 2))
    lo, hi, _, _ = grid_bracket(mse_B, 0.1, 200.0, steps=80)
    gamma_B = golden_min(mse_B, lo, hi)
    clamp_rate = float(np.mean((1 - gamma_B * delta) < floor))
    results.append(report("B: Clamped multiplicative (floor=%.2f)" % floor, pred_B, gamma_B,
                           "clamp active on %.2f%% of obs" % (100 * clamp_rate)))

# ---------------------------------------------------------------------------
# FORMULA C: exponential suppression
# pred_v2 = pred_v1 * exp(-gamma*delta)
# Never negative by construction (exp() > 0 always). Unbounded on the upside
# (delta very negative -> large boost) but that side is physically safe
# (aces can be arbitrarily elevated, just not negative), so this is the
# natural "always-positive" analogue of the linear model.
# ---------------------------------------------------------------------------
def pred_C(g):
    return pred_v1 * np.exp(-g * delta)


def mse_C(g):
    return float(np.mean((actual - pred_C(g)) ** 2))


lo, hi, _, _ = grid_bracket(mse_C, 0.1, 200.0, steps=80)
gamma_C = golden_min(mse_C, lo, hi)
results.append(report("C: Exponential suppression", pred_C, gamma_C,
                       "nonlinear least squares (golden-section on MSE)"))

# ---------------------------------------------------------------------------
# FORMULA D: logistic / bounded suppression
# factor(delta) = 2 / (1 + exp(gamma*delta))
# At delta=0, factor=1 (no adjustment). factor in bounded in (0, 2): never
# negative, and never more than a 2x boost either -- a hard physical ceiling
# and floor in one formula, with smooth saturation instead of a hard clamp.
# ---------------------------------------------------------------------------
def pred_D(g):
    factor = 2.0 / (1.0 + np.exp(g * delta))
    return pred_v1 * factor


def mse_D(g):
    return float(np.mean((actual - pred_D(g)) ** 2))


lo, hi, _, _ = grid_bracket(mse_D, 0.1, 400.0, steps=80)
gamma_D = golden_min(mse_D, lo, hi)
results.append(report("D: Logistic/bounded suppression (factor in (0,2))", pred_D, gamma_D,
                       "nonlinear least squares (golden-section on MSE)"))

# ---------------------------------------------------------------------------
# FORMULA E: winsorized-delta linear suppression + floor backstop
# Addresses the leverage problem at its source (the PREDICTOR, not just the
# output): delta is winsorized to its [1st, 99th] percentile range in the
# fit window BEFORE the linear suppression is applied, so a handful of
# extreme opponent-break-rate deviations can no longer single-handedly blow
# up the suppression term. A small floor (0.05) is kept as a backstop in
# case winsorizing alone isn't enough to guarantee positivity.
# ---------------------------------------------------------------------------
d_lo, d_hi = np.quantile(delta, [0.01, 0.99])
delta_w = np.clip(delta, d_lo, d_hi)
floor_E = 0.05


def pred_E(g):
    factor = np.maximum(1 - g * delta_w, floor_E)
    return pred_v1 * factor


def mse_E(g):
    return float(np.mean((actual - pred_E(g)) ** 2))


lo, hi, _, _ = grid_bracket(mse_E, 0.1, 200.0, steps=80)
gamma_E = golden_min(mse_E, lo, hi)
clamp_rate_E = float(np.mean((1 - gamma_E * delta_w) < floor_E))
winsor_rate = float(np.mean((delta < d_lo) | (delta > d_hi)))
results.append(report("E: Winsorized-delta (1st/99th pct) linear + floor=0.05", pred_E, gamma_E,
                       "winsorized %.2f%% of obs; floor active on %.2f%% of obs"
                       % (100 * winsor_rate, 100 * clamp_rate_E)))

# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
print("\n" + "=" * 110)
print("SUMMARY -- suppression formula comparison, year<=2021 fit window (n=%d)" % n)
print("=" * 110)
print("%-58s %9s %7s %7s %7s %8s" % ("formula", "gamma", "MAE", "MSE", "%neg", "%MSE_imp"))
print("%-58s %9s %7.4f %7.4f %7s %8s" % ("BASELINE (V1)", "-", mae_v1, mse_v1, "0.00%", "0.00%"))
for r in results:
    print("%-58s %9.4f %7.4f %7.4f %6.2f%% %7.2f%%"
          % (r["formula"][:58], r["gamma"], r["mae"], r["mse"], 100 * r["negfrac"], r["mse_improvement_pct"]))

print("\nInterpretability notes:")
print("  A (linear):    gamma directly = fractional ace-rate change per unit delta. Most intuitive,")
print("                 but not physically valid at its own fitted magnitude (negative predictions).")
print("  B (clamped):   same linear interpretation as A in the un-clamped region; floor is an extra,")
print("                 separately-justified constant (not data-fit) -- two parameters instead of one.")
print("  C (exponential): gamma = %% suppression per unit delta in log-space (compounding). Common,")
print("                   well-understood functional form (rate models, survival analysis); always positive.")
print("  D (logistic):  gamma controls steepness of an S-curve bounded to (0,2)x. Most physically")
print("                 conservative (hard ceiling AND floor) but least direct 1:1 reading of gamma.")
print("  E (winsorized+floor): same linear interpretation as A/B in the typical (non-extreme) range,")
print("                 explicitly documents where/how much of the input is being capped.")

out = {
    "n": n, "mean_break_rate": mean_break_rate,
    "baseline_mae": mae_v1, "baseline_mse": mse_v1,
    "results": results,
}
with open("/path/to/home/openclaw/apex_v2_formula_comparison_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWrote apex_v2_formula_comparison_results.json")
