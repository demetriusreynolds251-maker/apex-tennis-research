"""
Task 1, Step 5: TUNE the approved exponential suppression model on 2022-2023.
Formula (approved 2026-09-26): aces2 = aces0 * exp(-gamma * (obr - mean_break_rate))
mean_break_rate is the FROZEN fit-window (year<=2021) constant
(0.2564119721242022 at W=40,K=15) -- reused unchanged here, exactly as
production would use m["mean_break_rate"], to avoid any train/live
centering mismatch. TUNE_START=2022, TUNE_END=2023 per the frozen
boundaries shared by apex_prop_sim_v1.py / apex_prop_model_v1.py.

This step does NOT touch year>=2024 (holdout) and does NOT modify
apex_prop_sim_v1.py / apex_prop_model_v1.py (read-only, MD5-verified
unchanged before and after). It also does NOT overwrite GAMMA_FIT in
apex_prop_sim_v2.py -- this script only measures whether that fit-window
coefficient generalizes to 2022-2023 and what an independent tune-window
fit would look like, per the user's explicit request. No production file
is edited until the user reviews these results.
"""
import json
import pickle
import numpy as np

W, K = 40, 15
MIN_N = 10
FIT_END, TUNE_START, TUNE_END = 2021, 2022, 2023
MEAN_BREAK_RATE_FIT = 0.2564119721242022  # frozen fit-window constant
GAMMA_FIT = 12.879686                     # approved fit-window coefficient

with open("/tmp/oppbr_rows.pkl", "rb") as f:
    rows = pickle.load(f)

raw_fit_rows = [r for r in rows if r["year"] <= FIT_END]
raw_tune_rows = [r for r in rows if TUNE_START <= r["year"] <= TUNE_END]
print("raw rows: fit-window (<=%d) = %d, tune-window (%d-%d) = %d"
      % (FIT_END, len(raw_fit_rows), TUNE_START, TUNE_END, len(raw_tune_rows)))


def extract(rows):
    """Same extraction/filter logic used throughout Step 4 -- per-side,
    per-match observations with valid trailing ace_rate, opponent break
    rate, and a minimum trailing-match floor. Returns coverage counts too."""
    actual, pred_v1, obr = [], [], []
    n_candidates = 0
    n_dropped_missing = 0
    n_dropped_minn = 0
    for r in rows:
        for side, opp in (("w", "l"), ("l", "w")):
            n_candidates += 1
            ace_rate = r.get("%s_W%d_K%d_ace_rate" % (side, W, K))
            n_all = r.get("%s_W%d_K%d_nall" % (side, W, K))
            svgms = r.get("%s_svgms" % side)
            aces_actual = r.get("%s_aces" % side)
            opp_br = r.get("%s_W%d_K%d_break_rate" % (opp, W, K))
            vals = (ace_rate, n_all, svgms, aces_actual, opp_br)
            if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in vals):
                n_dropped_missing += 1
                continue
            if n_all < MIN_N or svgms <= 0:
                n_dropped_minn += 1
                continue
            actual.append(aces_actual)
            pred_v1.append(svgms * ace_rate)
            obr.append(opp_br)
    cov = {"n_candidates": n_candidates, "n_kept": len(actual),
           "n_dropped_missing": n_dropped_missing, "n_dropped_minn": n_dropped_minn,
           "coverage_pct": 100.0 * len(actual) / n_candidates if n_candidates else float("nan")}
    return np.array(actual, float), np.array(pred_v1, float), np.array(obr, float), cov


actual_fit, pred_v1_fit, obr_fit, cov_fit = extract(raw_fit_rows)
actual_tune, pred_v1_tune, obr_tune, cov_tune = extract(raw_tune_rows)

print("\nCOVERAGE (fraction of candidate player-side-match rows usable after filters)")
print("  fit-window  (<=%d):  candidates=%d  kept=%d  coverage=%.2f%%  (dropped missing=%d, dropped n<%d=%d)"
      % (FIT_END, cov_fit["n_candidates"], cov_fit["n_kept"], cov_fit["coverage_pct"],
         cov_fit["n_dropped_missing"], MIN_N, cov_fit["n_dropped_minn"]))
print("  tune-window (%d-%d): candidates=%d  kept=%d  coverage=%.2f%%  (dropped missing=%d, dropped n<%d=%d)"
      % (TUNE_START, TUNE_END, cov_tune["n_candidates"], cov_tune["n_kept"], cov_tune["coverage_pct"],
         cov_tune["n_dropped_missing"], MIN_N, cov_tune["n_dropped_minn"]))
print("  coverage delta: %.2f pct points" % (cov_tune["coverage_pct"] - cov_fit["coverage_pct"]))


# ---------------------------------------------------------------------------
# Golden-section minimizer (same method used in the formula comparison).
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


def grid_bracket(f, lo, hi, steps=80):
    xs = np.linspace(lo, hi, steps)
    ys = [f(x) for x in xs]
    i = int(np.argmin(ys))
    return xs[max(0, i - 2)], xs[min(len(xs) - 1, i + 2)]


def evaluate(actual, pred_v1, delta, gamma):
    pred_v2 = pred_v1 * np.exp(-gamma * delta)
    resid = actual - pred_v2
    mae = float(np.mean(np.abs(resid)))
    mse = float(np.mean(resid ** 2))
    negfrac = float(np.mean(pred_v2 < 0))  # always 0.0 for this form; kept for audit symmetry
    bias = float(np.mean(pred_v2) - np.mean(actual))
    ratio = float(np.mean(pred_v2) / np.mean(actual))
    denom = np.sum(delta * delta)
    leftover_slope = float(np.sum(resid * delta) / denom) if denom > 0 else float("nan")
    corr = float(np.corrcoef(resid, delta)[0, 1])
    return {"gamma": gamma, "mae": mae, "mse": mse, "negfrac": negfrac,
            "agg_bias": bias, "agg_ratio": ratio, "leftover_delta_slope": leftover_slope,
            "resid_vs_delta_corr": corr}


delta_fit = obr_fit - MEAN_BREAK_RATE_FIT
delta_tune = obr_tune - MEAN_BREAK_RATE_FIT


# ---------------------------------------------------------------------------
# 1) Baseline (gamma=0) on both windows -- sanity anchor.
# ---------------------------------------------------------------------------
base_fit = evaluate(actual_fit, pred_v1_fit, delta_fit, 0.0)
base_tune = evaluate(actual_tune, pred_v1_tune, delta_tune, 0.0)
print("\nBASELINE (V1, gamma=0)")
print("  fit-window : MAE=%.4f MSE=%.4f" % (base_fit["mae"], base_fit["mse"]))
print("  tune-window: MAE=%.4f MSE=%.4f" % (base_tune["mae"], base_tune["mse"]))

# ---------------------------------------------------------------------------
# 2) Fit-window gamma (12.879686, frozen/approved) applied AS-IS to the
#    tune window -- does the already-fitted coefficient generalize?
# ---------------------------------------------------------------------------
asis_tune = evaluate(actual_tune, pred_v1_tune, delta_tune, GAMMA_FIT)
print("\nFIT-WINDOW GAMMA (%.6f) APPLIED AS-IS TO TUNE WINDOW (out-of-sample check)" % GAMMA_FIT)
print("  MAE=%.4f MSE=%.4f  MSE improvement vs tune-baseline=%.2f%%"
      % (asis_tune["mae"], asis_tune["mse"],
         100 * (base_tune["mse"] - asis_tune["mse"]) / base_tune["mse"]))
print("  calibration: agg_bias=%.5f agg_ratio=%.5f leftover_delta_slope=%.4f resid_vs_delta_corr=%.4f"
      % (asis_tune["agg_bias"], asis_tune["agg_ratio"], asis_tune["leftover_delta_slope"],
         asis_tune["resid_vs_delta_corr"]))

# ---------------------------------------------------------------------------
# 3) Independent re-fit (tune) of gamma on 2022-2023 ALONE, same centering
#    constant, same functional form -- this is the actual "tuning" step.
# ---------------------------------------------------------------------------
def mse_tune(g):
    return evaluate(actual_tune, pred_v1_tune, delta_tune, g)["mse"]


lo, hi = grid_bracket(mse_tune, 0.1, 60.0, steps=100)
gamma_tuned = golden_min(mse_tune, lo, hi)
tuned_eval = evaluate(actual_tune, pred_v1_tune, delta_tune, gamma_tuned)
print("\nINDEPENDENT TUNE-WINDOW FIT (gamma re-estimated on 2022-2023 alone)")
print("  gamma_tuned = %.6f  (fit-window gamma was %.6f, delta=%.6f, %.2f%% relative change)"
      % (gamma_tuned, GAMMA_FIT, gamma_tuned - GAMMA_FIT,
         100 * (gamma_tuned - GAMMA_FIT) / GAMMA_FIT))
print("  MAE=%.4f MSE=%.4f  MSE improvement vs tune-baseline=%.2f%%"
      % (tuned_eval["mae"], tuned_eval["mse"],
         100 * (base_tune["mse"] - tuned_eval["mse"]) / base_tune["mse"]))
print("  calibration: agg_bias=%.5f agg_ratio=%.5f leftover_delta_slope=%.4f resid_vs_delta_corr=%.4f"
      % (tuned_eval["agg_bias"], tuned_eval["agg_ratio"], tuned_eval["leftover_delta_slope"],
         tuned_eval["resid_vs_delta_corr"]))


# ---------------------------------------------------------------------------
# 4) Distribution of suppression factors on the TUNE window, using the
#    fit-window (production-candidate) gamma -- directly investigates the
#    "large positive boost" behavior flagged in the Step 4 spot check
#    (Tatjana Maria: 0.377 -> 2.468, a 6.55x factor).
# ---------------------------------------------------------------------------
factor_tune = np.exp(-GAMMA_FIT * delta_tune)
pcts = [1, 5, 10, 25, 50, 75, 90, 95, 99, 99.5, 99.9]
pvals = np.percentile(factor_tune, pcts)
print("\nSUPPRESSION FACTOR DISTRIBUTION (tune window, gamma=%.6f, factor=exp(-gamma*delta))" % GAMMA_FIT)
for p, v in zip(pcts, pvals):
    print("  p%-5s = %.4fx" % (str(p), v))
print("  min=%.4fx  max=%.4fx  mean=%.4fx  std=%.4fx"
      % (factor_tune.min(), factor_tune.max(), factor_tune.mean(), factor_tune.std()))
for thresh in (1.5, 2.0, 3.0, 5.0, 8.0):
    frac_above = float(np.mean(factor_tune > thresh))
    print("  fraction of tune-window obs with factor > %.1fx : %.3f%%" % (thresh, 100 * frac_above))
for thresh in (0.5, 0.3, 0.15, 0.05):
    frac_below = float(np.mean(factor_tune < thresh))
    print("  fraction of tune-window obs with factor < %.2fx : %.3f%%" % (thresh, 100 * frac_below))

# same distribution on the fit window, for direct side-by-side comparison
factor_fit = np.exp(-GAMMA_FIT * delta_fit)
pvals_fit = np.percentile(factor_fit, pcts)
print("\nSAME DISTRIBUTION ON FIT WINDOW (year<=2021), for comparison")
for p, v in zip(pcts, pvals_fit):
    print("  p%-5s = %.4fx" % (str(p), v))
print("  max=%.4fx (fit)  vs  max=%.4fx (tune)" % (factor_fit.max(), factor_tune.max()))


# ---------------------------------------------------------------------------
# 5) Stability check on the TUNE-WINDOW fit itself: does gamma_tuned move
#    much if the most extreme |delta| observations are trimmed? (same idea
#    as the Step-4 stability investigation, applied here to make sure the
#    tuned value isn't itself an artifact of a handful of extreme-delta
#    matches in 2022-2023.)
# ---------------------------------------------------------------------------
for trim_pct in (0.05, 0.10):
    thresh = np.quantile(np.abs(delta_tune), 1 - trim_pct)
    keep = np.abs(delta_tune) <= thresh

    def mse_trim(g, keep=keep):
        return evaluate(actual_tune[keep], pred_v1_tune[keep], delta_tune[keep], g)["mse"]

    lo, hi = grid_bracket(mse_trim, 0.1, 60.0, steps=100)
    g_trim = golden_min(mse_trim, lo, hi)
    print("\nTUNE-WINDOW STABILITY: top %.0f%% |delta| trimmed (n=%d/%d) -> gamma=%.6f (vs untrimmed %.6f, %.2f%% change)"
          % (100 * trim_pct, int(keep.sum()), len(delta_tune), g_trim, gamma_tuned,
             100 * (g_trim - gamma_tuned) / gamma_tuned))

# ---------------------------------------------------------------------------
# SUMMARY + JSON
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("STEP 5 SUMMARY")
print("=" * 100)
print("Coverage:      fit=%.2f%%  tune=%.2f%%  (delta %.2f pts)"
      % (cov_fit["coverage_pct"], cov_tune["coverage_pct"],
         cov_tune["coverage_pct"] - cov_fit["coverage_pct"]))
print("Gamma:         fit=%.4f  tuned=%.4f  (%.2f%% relative change)"
      % (GAMMA_FIT, gamma_tuned, 100 * (gamma_tuned - GAMMA_FIT) / GAMMA_FIT))
print("MSE (tune win): baseline=%.4f  fit-gamma-as-is=%.4f  tuned-gamma=%.4f"
      % (base_tune["mse"], asis_tune["mse"], tuned_eval["mse"]))
print("Calibration (resid_vs_delta_corr): fit-gamma-as-is=%.4f  tuned-gamma=%.4f"
      % (asis_tune["resid_vs_delta_corr"], tuned_eval["resid_vs_delta_corr"]))
print("Max suppression factor observed: fit-window=%.2fx  tune-window=%.2fx" % (factor_fit.max(), factor_tune.max()))

out = {
    "coverage_fit": cov_fit, "coverage_tune": cov_tune,
    "gamma_fit": GAMMA_FIT, "gamma_tuned": gamma_tuned,
    "baseline_tune": base_tune, "fit_gamma_as_is_on_tune": asis_tune,
    "tuned_gamma_on_tune": tuned_eval,
    "factor_percentiles_tune": dict(zip([str(p) for p in pcts], pvals.tolist())),
    "factor_percentiles_fit": dict(zip([str(p) for p in pcts], pvals_fit.tolist())),
}
with open("/path/to/home/openclaw/apex_v2_step5_tune_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWrote apex_v2_step5_tune_results.json")
