#!/usr/bin/env python3
"""
BPS_V1 Phases 3-6: FIT (year<=2021) / TUNE (2022-2023) / HOLDOUT (2024+)
/ ROOT-CAUSE CHECK, run on real historical data from apex_bps_v1_rows.csv
(built by apex_bps_v1_build.py from the real "ATP & WTA, 1968-2026"
Sackmann-style source -- 122,373 real matches, 2005-2026).

Primary spec: W=40, K=15 (a mid-grid trailing window: 40 = medium
recency, 15 = medium shrinkage toward all-surface rate -- the same
grid point already load-bearing elsewhere in the production feature
set, e.g. fav_W40_K15_hold_rate). Chosen for tractability; the full
3x3 grid is present in the rows file for later extension.

Target: actual_hold_rate (this player's true fraction of service
games held, this match) -- BPS is mechanically a serve-preservation
stat (holds = SvGms - (bpFaced - bpSaved)), so hold-rate is the most
direct, least-derived target. By the mirror-image algebra already
established (breaks_by_opponent = bpFaced - bpSaved), the same signal
also feeds break projections via the opponent's BPS_V1 value -- see
written report for that argument; this script tests the primary,
most direct channel.

Baseline predictors (trailing, pre-match, no leakage): hold_rate,
break_rate, bp_conv_rate ("break points scored" -- BP won per BP
faced while returning; distinct from break_rate, which is breaks per
return GAME).
Candidate addition: bps_rate (trailing break-points-saved %).
"""
import numpy as np
import pandas as pd

W, K = 40, 15
BASE = ["hold_rate", "break_rate", "bp_conv_rate"]
CAND = "bps_rate"


def build_long(df):
    """Stack winner/loser sides into one player-observation-per-row frame."""
    parts = []
    for side in ("w", "l"):
        cols = {f: "%s_W%d_K%d_%s" % (side, W, K, f) for f in BASE + [CAND]}
        d = pd.DataFrame({
            "year": df["year"], "date": df["date"], "surface": df["surface"],
            "is_wta": df["is_wta"], "stats_ok": df["stats_ok"],
            "actual_hold_rate": df["%s_hold_rate_actual" % side],
        })
        for f, c in cols.items():
            d[f] = df[c]
        d["nsurf"] = df["%s_W%d_K%d_nsurf" % (side, W, K)]
        d["nall"] = df["%s_W%d_K%d_nall" % (side, W, K)]
        parts.append(d)
    long = pd.concat(parts, ignore_index=True)
    keep = (long["stats_ok"] == 1) & long["actual_hold_rate"].notna()
    for f in BASE + [CAND]:
        keep &= long[f].notna()
    long = long[keep].copy()
    return long


def design_matrix(d, cols):
    X = np.column_stack([np.ones(len(d))] + [d[c].values for c in cols])
    y = d["actual_hold_rate"].values
    return X, y


def ols_fit(X, y):
    coef, res, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ coef
    resid = y - yhat
    sse = float(np.sum(resid ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    mae = float(np.mean(np.abs(resid)))
    mse = float(np.mean(resid ** 2))
    return coef, r2, mae, mse


def apply_coef(X, coef):
    return X @ coef


def calibration_table(pred, actual, nbins=10):
    order = np.argsort(pred)
    p, a = pred[order], actual[order]
    edges = np.linspace(0, len(p), nbins + 1).astype(int)
    rows = []
    for i in range(nbins):
        sl = slice(edges[i], edges[i + 1])
        if edges[i + 1] > edges[i]:
            rows.append((float(p[sl].mean()), float(a[sl].mean()), int(edges[i + 1] - edges[i])))
    return rows


def report_split(name, d, cols_base, cols_full, coef_base=None, coef_full=None, refit=True):
    Xb, y = design_matrix(d, cols_base)
    Xf, _ = design_matrix(d, cols_full)
    out = {}
    if refit:
        cb, r2b, maeb, mseb = ols_fit(Xb, y)
        cf, r2f, maef, msef = ols_fit(Xf, y)
        out["coef_base"] = cb; out["coef_full"] = cf
        out["r2_base"] = r2b; out["r2_full"] = r2f
        out["mae_base"] = maeb; out["mae_full"] = maef
        out["mse_base"] = mseb; out["mse_full"] = msef
    else:
        pb = apply_coef(Xb, coef_base); pf = apply_coef(Xf, coef_full)
        resb = y - pb; resf = y - pf
        out["mae_base"] = float(np.mean(np.abs(resb))); out["mae_full"] = float(np.mean(np.abs(resf)))
        out["mse_base"] = float(np.mean(resb ** 2)); out["mse_full"] = float(np.mean(resf ** 2))
        sst = float(np.sum((y - y.mean()) ** 2))
        out["r2_base"] = 1 - float(np.sum(resb ** 2)) / sst
        out["r2_full"] = 1 - float(np.sum(resf ** 2)) / sst
        out["pred_base"] = pb; out["pred_full"] = pf; out["actual"] = y
    out["n"] = len(d)
    print("--- %s (n=%d) ---" % (name, len(d)))
    print("  BASE  R2=%.5f MAE=%.5f MSE=%.5f" % (out["r2_base"], out["mae_base"], out["mse_base"]))
    print("  FULL  R2=%.5f MAE=%.5f MSE=%.5f  (delta R2=%.5f, delta MAE=%.5f)" %
          (out["r2_full"], out["mae_full"], out["mse_full"],
           out["r2_full"] - out["r2_base"], out["mae_base"] - out["mae_full"]))
    return out


def main():
    df = pd.read_csv("apex_bps_v1_rows.csv", low_memory=False)
    long = build_long(df)
    print("usable player-observations (stats_ok, full trailing history at W%d_K%d): %d" % (W, K, len(long)))
    print("year range:", long["year"].min(), "-", long["year"].max())

    fit_d = long[long["year"] <= 2021]
    tune_d = long[(long["year"] >= 2022) & (long["year"] <= 2023)]
    hold_d = long[long["year"] >= 2024]
    print("fit(<=2021) n=%d  tune(2022-23) n=%d  holdout(2024+) n=%d" %
          (len(fit_d), len(tune_d), len(hold_d)))

    print("\n===== PHASE 3: FIT (year<=2021) =====")
    fit_res = report_split("FIT", fit_d, BASE, BASE + [CAND])
    print("  FIT coefficients (intercept, %s):" % ", ".join(BASE))
    print("    BASE:", np.round(fit_res["coef_base"], 5))
    print("  FIT coefficients (intercept, %s, %s):" % (", ".join(BASE), CAND))
    print("    FULL:", np.round(fit_res["coef_full"], 5))

    print("\n===== PHASE 4: TUNE (2022-2023), refit for drift check =====")
    tune_res = report_split("TUNE (refit)", tune_d, BASE, BASE + [CAND])
    print("  TUNE coefficients:")
    print("    BASE:", np.round(tune_res["coef_base"], 5))
    print("    FULL:", np.round(tune_res["coef_full"], 5))
    drift_base = tune_res["coef_base"] - fit_res["coef_base"]
    drift_full = tune_res["coef_full"] - fit_res["coef_full"]
    print("  coefficient drift (TUNE - FIT):")
    print("    BASE drift:", np.round(drift_base, 5))
    print("    FULL drift:", np.round(drift_full, 5))


    print("\n===== PHASE 5: HOLDOUT (2024+), frozen FIT-window coefficients =====")
    hold_res = report_split("HOLDOUT (frozen fit coef)", hold_d, BASE, BASE + [CAND],
                             coef_base=fit_res["coef_base"], coef_full=fit_res["coef_full"], refit=False)
    coverage = len(hold_d) / (df["year"] >= 2024).sum() / 2.0 if (df["year"] >= 2024).sum() else float("nan")
    print("  coverage (usable / total holdout match-sides incl. missing stats): %.3f" % coverage)
    print("  Brier-style score (MSE of prob-like [0,1] target) BASE=%.5f FULL=%.5f" %
          (hold_res["mse_base"], hold_res["mse_full"]))
    print("  Calibration (10 bins, mean predicted vs mean actual hold_rate) -- BASE:")
    for p, a, n in calibration_table(hold_res["pred_base"], hold_res["actual"]):
        print("    pred=%.4f actual=%.4f n=%d" % (p, a, n))
    print("  Calibration (10 bins) -- FULL (with bps_rate):")
    for p, a, n in calibration_table(hold_res["pred_full"], hold_res["actual"]):
        print("    pred=%.4f actual=%.4f n=%d" % (p, a, n))

    print("\n===== PHASE 6: ROOT-CAUSE / INCREMENTAL VALUE CHECK =====")
    print("  FIT in-sample delta R2 (FULL - BASE):        %.6f" % (fit_res["r2_full"] - fit_res["r2_base"]))
    print("  HOLDOUT out-of-sample delta R2 (FULL - BASE): %.6f" % (hold_res["r2_full"] - hold_res["r2_base"]))
    print("  HOLDOUT out-of-sample delta MAE (BASE - FULL, positive=improvement): %.6f" %
          (hold_res["mae_base"] - hold_res["mae_full"]))
    bps_coef_fit = fit_res["coef_full"][-1]
    print("  FIT-window bps_rate coefficient: %.5f" % bps_coef_fit)

    print("\n===== SUCCESS CRITERIA CHECK =====")
    print("  1. Real holdout improvement (delta MAE>0 and delta R2>0): %s" %
          (hold_res["mae_base"] > hold_res["mae_full"] and hold_res["r2_full"] > hold_res["r2_base"]))
    print("  2. Stable coefficients (|drift| < 0.5 * |fit coef| for bps_rate): %s" %
          (abs(drift_full[-1]) < 0.5 * abs(bps_coef_fit) if bps_coef_fit != 0 else "n/a"))
    print("  3. No future leakage: by construction (trailing pre-match features only) -- True")
    print("  4. Better calibration than baseline: see calibration tables above (visual/tabular check)")
    print("  5. Incremental value beyond hold/break/bp-scored rates: delta R2 above")


if __name__ == "__main__":
    main()
