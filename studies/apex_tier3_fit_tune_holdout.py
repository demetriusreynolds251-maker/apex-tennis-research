#!/usr/bin/env python3
"""
TIER 3 SERVE-QUALITY SIGNAL INVESTIGATION -- Phases 1-6.

Merges apex_bps_v1_rows.csv (production-analog baseline features:
trailing ace_rate/df_rate/hold_rate/break_rate/bp_conv_rate at
W40_K15, plus the real actual_hold_rate / actual_break_rate targets)
with apex_tier3_serveq_rows.csv (the 6 candidate serve-quality metrics
x {raw N20, shrink-blended N30/K15} + one surface-specific variant) by
row position -- both were built from the identical
v1.load_sackmann(..., year_from=2005, challengers=False) call, same
sort order, verified same length and identical (date, tourney_id,
winner, loser) row-by-row.

BASELINE (the existing Apex feature set, trailing, pre-match):
  ace_rate, df_rate, hold_rate, break_rate, bp_conv_rate  (W40_K15)

For each candidate: BASE vs BASE+candidate, fit (<=2021) / tune
(2022-2023, refit for drift) / holdout (2024+, frozen fit coefficients).
Target = actual_hold_rate for serve-side candidates (FS%, FSPW%, SSPW%,
SPW%, Dominance Ratio), actual_break_rate for the return-side candidate
(RPW%) -- same target-choice logic used for BPS_V1.
"""
import numpy as np
import pandas as pd

BASE_COLS = ["ace_rate", "df_rate", "hold_rate", "break_rate", "bp_conv_rate"]
W, K = 40, 15

CANDIDATES = [
    ("FS%  (raw, last-20)",        "fs",   "N20",     "hold"),
    ("FS%  (shrink 30/15)",        "fs",   "shrink",  "hold"),
    ("FSPW% (raw, last-20)",       "fspw", "N20",     "hold"),
    ("FSPW% (shrink 30/15)",       "fspw", "shrink",  "hold"),
    ("SSPW% (raw, last-20)",       "sspw", "N20",     "hold"),
    ("SSPW% (shrink 30/15)",       "sspw", "shrink",  "hold"),
    ("SPW%  (raw, last-20)",       "spw",  "N20",     "hold"),
    ("SPW%  (shrink 30/15)",       "spw",  "shrink",  "hold"),
    ("SPW%  (Hard-only, last-30)", "spw",  "hardN30", "hold"),
    ("RPW%  (raw, last-20)",       "rpw",  "N20",     "break"),
    ("RPW%  (shrink 30/15)",       "rpw",  "shrink",  "break"),
    ("Dominance Ratio (raw, last-20)",   "dr", "N20",    "hold"),
    ("Dominance Ratio (shrink 30/15)",   "dr", "shrink", "hold"),
]


def load_merged():
    a = pd.read_csv("apex_bps_v1_rows.csv", low_memory=False)
    b = pd.read_csv("apex_tier3_serveq_rows.csv", low_memory=False)
    assert len(a) == len(b), "row count mismatch: %d vs %d" % (len(a), len(b))
    key_a = a[["date", "tourney_id", "winner", "loser"]].astype(str)
    key_b = b[["date", "tourney_id", "winner", "loser"]].astype(str)
    assert (key_a.values == key_b.values).all(), "row alignment mismatch"
    keep_a = ["year", "surface", "is_wta"] + \
             ["w_%s_W%d_K%d_%s" % ("", W, K, m) for m in []]  # placeholder, unused
    a_use = a[["year", "surface", "is_wta"] +
              ["w_W%d_K%d_%s" % (W, K, m) for m in BASE_COLS] +
              ["l_W%d_K%d_%s" % (W, K, m) for m in BASE_COLS] +
              ["w_hold_rate_actual", "l_hold_rate_actual",
               "w_break_rate_actual", "l_break_rate_actual", "stats_ok"]].copy()
    b_use = b.drop(columns=["date", "tourney_id", "winner", "loser", "surface", "is_wta", "year"], errors="ignore")
    merged = pd.concat([a_use.reset_index(drop=True), b_use.reset_index(drop=True)], axis=1)
    return merged


def build_long(merged, cand_col, target):
    parts = []
    for side in ("w", "l"):
        d = pd.DataFrame({"year": merged["year"], "surface": merged["surface"]})
        for bc in BASE_COLS:
            d[bc] = merged["%s_W%d_K%d_%s" % (side, W, K, bc)]
        d["cand"] = merged["%s_%s" % (side, cand_col)]
        d["stats_ok"] = merged["stats_ok"]
        if target == "hold":
            d["y"] = merged["%s_hold_rate_actual" % side]
        else:
            d["y"] = merged["%s_break_rate_actual" % side]
        parts.append(d)
    long = pd.concat(parts, ignore_index=True)
    keep = (long["stats_ok"] == 1) & long["y"].notna() & long["cand"].notna()
    for bc in BASE_COLS:
        keep &= long[bc].notna()
    return long[keep].copy()


def design(d, cols):
    X = np.column_stack([np.ones(len(d))] + [d[c].values for c in cols])
    return X, d["y"].values


def ols(X, y):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    sse, sst = float(np.sum(resid ** 2)), float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    return coef, r2, float(np.mean(np.abs(resid))), float(np.mean(resid ** 2))


def apply_coef(X, coef):
    return X @ coef


def run_candidate(name, cand_col, target, merged):
    long = build_long(merged, cand_col, target)
    fit_d = long[long["year"] <= 2021]
    tune_d = long[(long["year"] >= 2022) & (long["year"] <= 2023)]
    hold_d = long[long["year"] >= 2024]
    Xb_fit, y_fit = design(fit_d, BASE_COLS)
    Xf_fit, _ = design(fit_d, BASE_COLS + ["cand"])
    cb_fit, r2b_fit, maeb_fit, _ = ols(Xb_fit, y_fit)
    cf_fit, r2f_fit, maef_fit, _ = ols(Xf_fit, y_fit)

    Xb_tune, y_tune = design(tune_d, BASE_COLS)
    Xf_tune, _ = design(tune_d, BASE_COLS + ["cand"])
    cb_tune, r2b_tune, maeb_tune, _ = ols(Xb_tune, y_tune)
    cf_tune, r2f_tune, maef_tune, _ = ols(Xf_tune, y_tune)
    drift = cf_tune[-1] - cf_fit[-1]

    Xb_hold, y_hold = design(hold_d, BASE_COLS)
    Xf_hold, _ = design(hold_d, BASE_COLS + ["cand"])
    pb_hold = apply_coef(Xb_hold, cb_fit); pf_hold = apply_coef(Xf_hold, cf_fit)
    resb, resf = y_hold - pb_hold, y_hold - pf_hold
    sst_hold = float(np.sum((y_hold - y_hold.mean()) ** 2))
    r2b_hold = 1 - float(np.sum(resb ** 2)) / sst_hold
    r2f_hold = 1 - float(np.sum(resf ** 2)) / sst_hold
    maeb_hold, maef_hold = float(np.mean(np.abs(resb))), float(np.mean(np.abs(resf)))
    mseb_hold, msef_hold = float(np.mean(resb ** 2)), float(np.mean(resf ** 2))

    corr_break = float(np.corrcoef(long["cand"], long["break_rate"])[0, 1])
    corr_hold = float(np.corrcoef(long["cand"], long["hold_rate"])[0, 1])
    corr_ace = float(np.corrcoef(long["cand"], long["ace_rate"])[0, 1])
    corr_df = float(np.corrcoef(long["cand"], long["df_rate"])[0, 1])
    corr_bpc = float(np.corrcoef(long["cand"], long["bp_conv_rate"])[0, 1])


    holdout_improve = (maeb_hold - maef_hold) > 0 and (r2f_hold - r2b_hold) > 0
    sign_stable = np.sign(cf_fit[-1]) == np.sign(cf_tune[-1]) if cf_fit[-1] != 0 else False
    stable = sign_stable and abs(drift) < 0.5 * abs(cf_fit[-1]) if cf_fit[-1] != 0 else False
    econ_meaningful = abs(maeb_hold - maef_hold) > 0.0005  # >0.05 percentage points of hold/break rate
    verdict = "IMPLEMENT" if (holdout_improve and stable and econ_meaningful) else "DO NOT IMPLEMENT"

    print("\n=== %s -> target=actual_%s_rate (n_fit=%d n_tune=%d n_hold=%d) ===" %
          (name, target, len(fit_d), len(tune_d), len(hold_d)))
    print("  corr vs baseline: hold_rate=%.3f break_rate=%.3f ace_rate=%.3f df_rate=%.3f bp_conv_rate=%.3f" %
          (corr_hold, corr_break, corr_ace, corr_df, corr_bpc))
    print("  FIT   BASE R2=%.5f MAE=%.5f | FULL R2=%.5f MAE=%.5f | dR2=%.6f coef=%.5f" %
          (r2b_fit, maeb_fit, r2f_fit, maef_fit, r2f_fit - r2b_fit, cf_fit[-1]))
    print("  TUNE  BASE R2=%.5f MAE=%.5f | FULL R2=%.5f MAE=%.5f | coef=%.5f drift=%.5f" %
          (r2b_tune, maeb_tune, r2f_tune, maef_tune, cf_tune[-1], drift))
    print("  HOLD  BASE R2=%.5f MAE=%.5f MSE=%.5f | FULL R2=%.5f MAE=%.5f MSE=%.5f" %
          (r2b_hold, maeb_hold, mseb_hold, r2f_hold, maef_hold, msef_hold))
    print("  abs dMAE(holdout)=%.6f  rel dMAE=%.4f%%  abs dR2(holdout)=%.6f" %
          (maeb_hold - maef_hold, 100.0 * (maeb_hold - maef_hold) / maeb_hold, r2f_hold - r2b_hold))
    print("  criteria: holdout_improve=%s stable=%s econ_meaningful=%s -> %s" %
          (holdout_improve, stable, econ_meaningful, verdict))

    return {
        "name": name, "target": target, "verdict": verdict,
        "d_mae_hold": maeb_hold - maef_hold, "d_r2_hold": r2f_hold - r2b_hold,
        "d_r2_fit": r2f_fit - r2b_fit, "coef_fit": cf_fit[-1], "coef_tune": cf_tune[-1],
        "drift": drift, "stable": stable, "holdout_improve": holdout_improve,
        "corr_hold": corr_hold, "corr_break": corr_break, "corr_ace": corr_ace,
        "corr_df": corr_df, "corr_bpc": corr_bpc,
    }


def main():
    merged = load_merged()
    print("merged rows:", len(merged), "year range:", merged["year"].min(), "-", merged["year"].max())

    print("\n===== PHASE-1-STYLE WINDOW SWEEP (SPW%, all N, no shrink, informational) =====")
    for n in (10, 20, 30, 50):
        long = build_long(merged, "N%d_spw" % n, "hold")
        c = float(np.corrcoef(long["cand"], long["hold_rate"])[0, 1])
        print("  N=%-3d  n_obs=%-7d  corr(SPW%%, trailing hold_rate)=%.4f" % (n, len(long), c))

    results = []
    for name, base, variant, target in CANDIDATES:
        col = "%s_%s" % (variant, base) if variant != "hardN30" else "hardN30_spw"
        results.append(run_candidate(name, col, target, merged))

    print("\n===== PHASE 6: FEATURE RANKING =====")
    ranked = sorted(results, key=lambda r: (r["verdict"] != "IMPLEMENT", -r["d_mae_hold"]))
    print("%-32s %-16s %10s %10s %8s %s" % ("candidate", "target", "dMAE_hold", "dR2_hold", "stable", "verdict"))
    for i, r in enumerate(ranked, 1):
        print("%2d. %-28s %-16s %10.6f %10.6f %8s %s" %
              (i, r["name"], r["target"], r["d_mae_hold"], r["d_r2_hold"], r["stable"], r["verdict"]))

    n_impl = sum(1 for r in results if r["verdict"] == "IMPLEMENT")
    print("\n===== FINAL: %d of %d candidate variants -> IMPLEMENT =====" % (n_impl, len(results)))


if __name__ == "__main__":
    main()
