"""
Task 1 Step 4: fit the Architecture A suppression coefficient (gamma) on
year<=2021 ONLY. No tune years, no holdout years touched.

Model (Architecture A, multiplicative, exactly as built in apex_prop_sim_v2.py):
    predicted_aces_v2 = predicted_aces_v1 * (1 - gamma * (opp_break_rate - mean_break_rate))
  where predicted_aces_v1 = svgms_actual * ace_rate_trailing (the base rate-model
  projection, using each player's own trailing ace_rate at the frozen live
  grid W=40/K=15 -- pre-calibration/overlay, which are additive, orthogonal
  layers applied identically whether or not the suppression term is active,
  so they do not need to be reproduced to fit gamma itself).

Expanding the real V2 formula: predicted_aces_v2 = pred_v1 - gamma*z, where
z = pred_v1*(opp_break_rate - mean_break_rate). So:
    actual - pred_v2 = (actual - pred_v1) + gamma*z = residual0 + gamma*z
Minimizing sum((residual0 + gamma*z)^2) over gamma (linear, closed form):
    gamma_hat = -sum(residual0 * z) / sum(z * z)
(NOTE: an earlier draft of this script printed the un-negated regression
slope as "gamma_hat" and fed it straight into the real V2 formula, which
produced a self-inconsistent fit-window result -- caught by comparing the
grid-search SSE against the fit-window MSE and finding they disagreed. Fixed
by deriving the sign directly from the real formula above, not by pattern-
matching an OLS setup.)
"""
import json
import pickle
import numpy as np

W, K = 40, 15
MIN_N = 10  # minimum trailing matches with valid stats before a row is used

with open("/tmp/oppbr_rows.pkl", "rb") as f:
    rows = pickle.load(f)

fit_rows = [r for r in rows if r["year"] <= 2021]
print("total replay rows:", len(rows), " | fit-window (year<=2021) rows:", len(fit_rows))

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
            actual.append(aces_actual); pred_v1.append(svgms * ace_rate); obr.append(opp_br)
    return np.array(actual), np.array(pred_v1), np.array(obr)

actual, pred_v1, obr = extract(fit_rows)
n = len(actual)
print("usable (player-side, match) observations in fit window:", n)
mean_break_rate = float(obr.mean())
print("mean_break_rate (recomputed on THIS fit sample, W=%d K=%d): %.6f" % (W, K, mean_break_rate))
residual0 = actual - pred_v1

print()
print("=" * 78)
print("VALIDATION CHECK (before fitting): opponent_break_rate vs V1 ace residual")
print("=" * 78)
X = np.column_stack([np.ones(n), obr])
coef, _, _, _ = np.linalg.lstsq(X, residual0, rcond=None)
a_hat, b_hat = coef
pred_resid = X @ coef
ss_res = np.sum((residual0 - pred_resid) ** 2)
ss_tot = np.sum((residual0 - residual0.mean()) ** 2)
r2 = 1 - ss_res / ss_tot
resid_std = np.sqrt(ss_res / (n - 2))
se_b = resid_std / np.sqrt(np.sum((obr - obr.mean()) ** 2))
t_stat = b_hat / se_b
r_corr = np.corrcoef(obr, residual0)[0, 1]
print("n =", n)
print("slope (V1 residual per unit opponent_break_rate): %.4f  (t=%.2f)" % (b_hat, t_stat))
print("intercept: %.4f" % a_hat)
print("correlation r: %.4f   r^2: %.4f" % (r_corr, r2))
print("direction:", "NEGATIVE" if b_hat < 0 else "POSITIVE (unexpected sign)",
      "-- higher opponent break_rate associates with lower actual-vs-V1 aces residual, as expected")
print("effect size: 10th->90th percentile opponent_break_rate shifts predicted residual by %.3f aces"
      % (b_hat * (np.percentile(obr, 90) - np.percentile(obr, 10))))

print()
print("=" * 78)
print("FIT: Architecture A gamma (real V2 formula: pred_v2 = pred_v1 - gamma*z)")
print("=" * 78)
z = pred_v1 * (obr - mean_break_rate)
gamma_hat = float(-np.sum(residual0 * z) / np.sum(z * z))
print("OBJECTIVE: minimize sum((actual_aces - (pred_v1 - gamma*z))^2)  [linear in gamma]")
print("CLOSED-FORM: gamma_hat = -sum(residual0*z)/sum(z*z) = %.6f" % gamma_hat)

print()
print("CANDIDATE GAMMA GRID (confirms closed-form is the minimum, using the REAL V2 formula):")
candidates = sorted(set([-1.0, -0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, round(gamma_hat, 4)]))
best_g, best_sse = None, None
for g in candidates:
    pred = pred_v1 - g * z
    sse = float(np.sum((actual - pred) ** 2))
    mse = sse / n
    marker = "  <-- closed-form fit" if abs(g - gamma_hat) < 1e-6 else ""
    print("  gamma=%+8.4f   SSE=%12.2f   MSE=%8.4f%s" % (g, sse, mse, marker))
    if best_sse is None or sse < best_sse:
        best_sse, best_g = sse, g
print("grid minimum at gamma=%.4f (closed-form: %.4f) -- %s" %
      (best_g, gamma_hat, "MATCHES" if abs(best_g - round(gamma_hat, 4)) < 1e-6 else "MISMATCH -- investigate"))

print()
print("=" * 78)
print("FIT-WINDOW PERFORMANCE: V1 (gamma=0) vs V2 (gamma=gamma_hat)")
print("=" * 78)
pred_v2 = pred_v1 - gamma_hat * z
mae_v1 = float(np.mean(np.abs(residual0))); mae_v2 = float(np.mean(np.abs(actual - pred_v2)))
mse_v1 = float(np.mean(residual0 ** 2)); mse_v2 = float(np.mean((actual - pred_v2) ** 2))
print("V1  MAE=%.4f  MSE=%.4f" % (mae_v1, mse_v1))
print("V2  MAE=%.4f  MSE=%.4f" % (mae_v2, mse_v2))
print("MAE improvement: %.4f (%.2f%%)" % (mae_v1 - mae_v2, 100 * (mae_v1 - mae_v2) / mae_v1))
print("MSE improvement: %.4f (%.2f%%)" % (mse_v1 - mse_v2, 100 * (mse_v1 - mse_v2) / mse_v1))

print()
print("=" * 78)
print("HONEST CAVEAT: tail behavior check (unbounded linear-in-obr term)")
print("=" * 78)
supp_lo = 1 - gamma_hat * (np.percentile(obr, 1) - mean_break_rate)
supp_hi = 1 - gamma_hat * (np.percentile(obr, 99) - mean_break_rate)
neg_frac = float(np.mean(pred_v2 < 0))
print("suppression factor at 1st pct obr: %.3f | at 99th pct obr: %.3f" % (supp_lo, supp_hi))
print("fraction of fit-window predictions that go NEGATIVE (nonsensical for an ace count): %.4f%%" % (100 * neg_frac))
print("This is a real, unresolved property of the raw closed-form OLS fit -- flagged for")
print("Step 5 (tuning on 2022-2023) rather than silently patched, per 'no hand tuning' rule.")

print()
print("gamma_hat =", gamma_hat)
print("mean_break_rate (fit-window, W=%d K=%d) =" % (W, K), mean_break_rate)

with open("apex_prop_sim_v2_fit.json", "w") as f:
    json.dump({
        "marker": "APEX-PROP-SIM-V2-FIT-2026-09-26",
        "step": "Task 1 Step 4 -- FIT ONLY, not tuned, not holdout-tested, not frozen",
        "gamma_fit": gamma_hat,
        "mean_break_rate_fit_window": mean_break_rate,
        "window": W, "shrink": K,
        "fit_window": "year<=2021", "n_obs": n,
        "min_trailing_matches": MIN_N,
        "validation_slope": float(b_hat), "validation_t": float(t_stat),
        "validation_r": float(r_corr), "validation_r2": float(r2),
        "fit_mae_v1": mae_v1, "fit_mae_v2": mae_v2,
        "fit_mse_v1": mse_v1, "fit_mse_v2": mse_v2,
        "caveat_tail_negative_fraction": neg_frac,
        "caveat_note": "unbounded linear-in-obr multiplicative term produces negative "
                        "(nonsensical) predicted aces at extreme opponent_break_rate values; "
                        "not patched here per the no-hand-tuning instruction -- carried into "
                        "Step 5 (2022-2023 tuning) for resolution.",
    }, f, indent=2)
print("\nsaved: apex_prop_sim_v2_fit.json")
