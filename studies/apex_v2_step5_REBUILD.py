"""
Task 1, Step 5 REBUILD: tune the corrected gamma (0.246189, fit on the real
production mu[side][0]*svgms target) on 2022-2023. Mirrors the original
Step 5 methodology exactly, on the corrected target. Read-only against
apex_prop_sim_v1.py / apex_prop_model_v1.py / apex_prop_sim_v2.py.
"""
import json
import numpy as np
import pandas as pd

import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim
import apex_prop_sim_v2 as sim2

SACKMANN_DIR = "ATP & WTA, 1968-2026"
FIT_END, TUNE_START, TUNE_END = 2021, 2022, 2023

m = v1.load_model()
W, K = m["window"], m["shrink"]
MEAN_BREAK_RATE = m["mean_break_rate"]
GAMMA_FIT = sim2.GAMMA_FIT
print("gamma_fit (locked from rebuilt Step 4) =", GAMMA_FIT)

df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)
_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (np.isfinite(hf0) & np.isfinite(hd0) & np.isfinite(mu0["fav"][0])
          & np.isfinite(mu0["fav"][1]) & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1]))
df = df[okmask].reset_index(drop=True)
P, hf, hd, mu = sim.v1_inputs_from_rows(df, m)


def extract(mask):
    rows_df = df[mask]
    mu_fav = mu["fav"][0][mask.values]; mu_dog = mu["dog"][0][mask.values]
    actual, pred_v1, obr = [], [], []
    for side, mu_arr, opp in (("fav", mu_fav, "dog"), ("dog", mu_dog, "fav")):
        y = rows_df["%s_aces" % side].values
        svgms_actual = rows_df["%s_svgms" % side].values
        p1 = mu_arr * svgms_actual
        ob = rows_df["%s_W%d_K%d_break_rate" % (opp, W, K)].values
        mk = np.isfinite(y) & np.isfinite(p1) & np.isfinite(ob)
        actual.append(y[mk]); pred_v1.append(p1[mk]); obr.append(ob[mk])
    return np.concatenate(actual), np.concatenate(pred_v1), np.concatenate(obr)


actual_fit, pred_v1_fit, obr_fit = extract(df["year"] <= FIT_END)
actual_tune, pred_v1_tune, obr_tune = extract((df["year"] >= TUNE_START) & (df["year"] <= TUNE_END))
delta_fit = obr_fit - MEAN_BREAK_RATE
delta_tune = obr_tune - MEAN_BREAK_RATE
print("n fit =", len(actual_fit), " n tune =", len(actual_tune))


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


def evaluate(actual, pred_v1, delta, gamma):
    pred_v2 = pred_v1 * np.exp(-gamma * delta)
    resid = actual - pred_v2
    mae = float(np.mean(np.abs(resid))); mse = float(np.mean(resid ** 2))
    negfrac = float(np.mean(pred_v2 < 0))
    bias = float(np.mean(pred_v2) - np.mean(actual))
    denom = np.sum(delta * delta)
    leftover_slope = float(np.sum(resid * delta) / denom) if denom > 0 else float("nan")
    corr = float(np.corrcoef(resid, delta)[0, 1])
    return {"gamma": gamma, "mae": mae, "mse": mse, "negfrac": negfrac,
            "agg_bias": bias, "leftover_delta_slope": leftover_slope, "resid_vs_delta_corr": corr}


base_tune = evaluate(actual_tune, pred_v1_tune, delta_tune, 0.0)
print("\nBASELINE (V1, gamma=0) on TUNE window: MAE=%.4f MSE=%.4f" % (base_tune["mae"], base_tune["mse"]))

asis_tune = evaluate(actual_tune, pred_v1_tune, delta_tune, GAMMA_FIT)
print("\nFIT-WINDOW GAMMA (%.6f) APPLIED AS-IS TO TUNE WINDOW" % GAMMA_FIT)
print("  MAE=%.4f MSE=%.4f  MSE improvement vs tune-baseline=%.3f%%"
      % (asis_tune["mae"], asis_tune["mse"], 100 * (base_tune["mse"] - asis_tune["mse"]) / base_tune["mse"]))
print("  calibration: agg_bias=%.5f leftover_delta_slope=%.4f resid_vs_delta_corr=%.4f"
      % (asis_tune["agg_bias"], asis_tune["leftover_delta_slope"], asis_tune["resid_vs_delta_corr"]))


def mse_tune(g):
    return evaluate(actual_tune, pred_v1_tune, delta_tune, g)["mse"]


lo, hi = grid_bracket(mse_tune, 0.001, 5.0, steps=150)
gamma_tuned = golden_min(mse_tune, lo, hi)
tuned_eval = evaluate(actual_tune, pred_v1_tune, delta_tune, gamma_tuned)
print("\nINDEPENDENT TUNE-WINDOW FIT: gamma_tuned=%.6f (fit-window was %.6f, %.2f%% relative change)"
      % (gamma_tuned, GAMMA_FIT, 100 * (gamma_tuned - GAMMA_FIT) / GAMMA_FIT))
print("  MAE=%.4f MSE=%.4f  MSE improvement vs tune-baseline=%.3f%%"
      % (tuned_eval["mae"], tuned_eval["mse"], 100 * (base_tune["mse"] - tuned_eval["mse"]) / base_tune["mse"]))
print("  calibration: agg_bias=%.5f leftover_delta_slope=%.4f resid_vs_delta_corr=%.4f"
      % (tuned_eval["agg_bias"], tuned_eval["leftover_delta_slope"], tuned_eval["resid_vs_delta_corr"]))

out = {"gamma_fit": GAMMA_FIT, "gamma_tuned": gamma_tuned, "baseline_tune": base_tune,
       "fit_gamma_as_is_on_tune": asis_tune, "tuned_gamma_on_tune": tuned_eval}
with open("/path/to/home/openclaw/apex_v2_step5_REBUILD_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWrote apex_v2_step5_REBUILD_results.json")
