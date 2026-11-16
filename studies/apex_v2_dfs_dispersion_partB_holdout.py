"""
apex_v2_dfs_dispersion_partB_holdout.py -- STEP 5 of the DFs investigation.

Confirms Part A's tune-window candidate region for DFs disp_mult on the
year>=2024 HOLDOUT (data not selected on), mirroring
apex_v2_dispersion_calib_holdout.py's methodology exactly: same GRID,
same N_SIMS, same metrics (MAE/MSE, total-dfs O/U line-Brier,
most_dfs_fav Brier, confidence-bucket tail gaps), pooled/ATP/WTA
separately, each with its own fitted r. Aces held fixed at live
production (Candidate C) settings throughout -- only DFs varies.

Read-only against the two frozen V1 files. MD5-checked before/after.
Nothing written to production. Evidence only -- no promotion decision
is made by this script.
"""
import copy
import hashlib
import json
import math
import sys
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

FIT_END, HOLD_START = 2021, 2024
SACKMANN_DIR = "ATP & WTA, 1968-2026"
GRID = [1e6, 1.0, 0.75, 0.6, 0.5, 0.4, 0.3]
N_SIMS = 1000
RESULTS = {}


m = v1.load_model()
coefs = sim.load_sim()
df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)
_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (np.isfinite(hf0) & np.isfinite(hd0) & np.isfinite(mu0["fav"][0])
          & np.isfinite(mu0["fav"][1]) & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1]))
df = df[okmask].reset_index(drop=True)
fit_df = df[df["year"] <= FIT_END].reset_index(drop=True)
df_hold = df[df["year"] >= HOLD_START].reset_index(drop=True)
df_hold_atp = df_hold[df_hold["is_wta"] == 0].reset_index(drop=True)
df_hold_wta = df_hold[df_hold["is_wta"] == 1].reset_index(drop=True)
print("holdout n_pooled=%d n_atp=%d n_wta=%d" % (len(df_hold), len(df_hold_atp), len(df_hold_wta)))

R_ATP_ACES = {"fav": 8.70148205269834, "dog": 5.885645957929439}; DM_ATP_ACES = 0.6
R_WTA_ACES = {"fav": 3.9866756061964232, "dog": 2.7971092624925418}; DM_WTA_ACES = 0.4

def moment_r(base_df, mask, side, cat="dfs"):
    _, hf_, hd_, mu_ = sim.v1_inputs_from_rows(base_df, m)
    idx = {"aces": 0, "dfs": 1}[cat]
    lam = mu_[side][idx][mask] * base_df.loc[mask, "%s_svgms" % side].values
    y = base_df.loc[mask, "%s_%s" % (side, cat)].values
    mk = np.isfinite(lam) & np.isfinite(y) & (lam > 0)
    excess = np.mean((y[mk] - lam[mk]) ** 2) - np.mean(lam[mk])
    return float(np.mean(lam[mk]) ** 2 / excess) if excess > 0 else float("inf")

r_pooled_dfs = {"fav": coefs["disp"]["fav"]["dfs"], "dog": coefs["disp"]["dog"]["dfs"]}
all_mask = np.ones(len(fit_df), dtype=bool)
atp_mask = (fit_df["is_wta"] == 0).values
wta_mask = (fit_df["is_wta"] == 1).values
r_all_dfs = {s: moment_r(fit_df, all_mask, s) for s in ("fav", "dog")}
r_atp_dfs = {s: moment_r(fit_df, atp_mask, s) for s in ("fav", "dog")}
r_wta_dfs = {s: moment_r(fit_df, wta_mask, s) for s in ("fav", "dog")}
print("fitted r -- pooled=%s atp=%s wta=%s" % (r_all_dfs, r_atp_dfs, r_wta_dfs))


def run_rows_dfs_candidate(df_sub, r_aces, dm_aces, r_dfs, dm_dfs, n_sims, seed=1):
    P, hf, hd, mu = sim.v1_inputs_from_rows(df_sub, m)
    pl = sim.price_level_pred(df_sub, coefs)
    rows = []; t0 = time.time()
    for i in range(len(df_sub)):
        if i and i % 1000 == 0:
            print("  ... %d/%d (%.0fs)" % (i, len(df_sub), time.time() - t0)); sys.stdout.flush()
        lv = sim.level_from(hf[i], hd[i], coefs, pl[i])
        bo = int(df_sub["best_of"].values[i])
        t, flag = sim.solve_tilt(lv, df_sub["pinn_fav"].values[i], coefs["tb_k"], bo, sigma=coefs.get("gap_sigma", 0.0))
        hA = min(max(lv + t, 0.2), 0.995); hB = min(max(lv - t, 0.2), 0.995)
        s = sim.simulate(
            hA, hB, coefs["tb_k"], bo,
            (mu["fav"][0][i], mu["fav"][1][i]), (mu["dog"][0][i], mu["dog"][1][i]),
            (r_aces["fav"] * dm_aces, r_dfs["fav"] * dm_dfs),
            (r_aces["dog"] * dm_aces, r_dfs["dog"] * dm_dfs),
            n_sims, seed=seed + i, sigma=coefs.get("gap_sigma", 0.0),
        )
        rows.append((s, hA, hB, flag))
    return rows

def aces_for_tour(is_wta):
    return (R_WTA_ACES, DM_WTA_ACES) if is_wta else (R_ATP_ACES, DM_ATP_ACES)

pbins = [0.0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01]
plabels = ["<55%", "55-60%", "60-65%", "65-70%", "70-75%", "75-80%", "80%+"]


def sweep_holdout(pop_df, r_dfs, label):
    print("\n" + "=" * 100)
    print("DFs HOLDOUT CONFIRMATION -- %s (n=%d, r_fav=%.3f r_dog=%.3f)" % (label, len(pop_df), r_dfs["fav"], r_dfs["dog"]))
    print("=" * 100)
    fa = pop_df["fav_dfs"].values; da = pop_df["dog_dfs"].values
    tie = fa == da; actual_win = (fa > da).astype(float); valid = ~tie
    is_wta_col = pop_df["is_wta"].values
    out = {}
    for dm in GRID:
        t0 = time.time()
        fav_mean = np.full(len(pop_df), np.nan); dog_mean = np.full(len(pop_df), np.nan)
        pred_prob = np.full(len(pop_df), np.nan)
        cov = []
        for wta_flag in (0, 1):
            sub_idx = np.where(is_wta_col == wta_flag)[0]
            if len(sub_idx) == 0:
                continue
            sub_df = pop_df.iloc[sub_idx].reset_index(drop=True)
            r_aces, dm_aces = aces_for_tour(bool(wta_flag))
            sims = run_rows_dfs_candidate(sub_df, r_aces, dm_aces, r_dfs, dm, N_SIMS, seed=1)
            fav_samp = np.stack([s["fav"]["dfs"] for s, _, _, _ in sims])
            dog_samp = np.stack([s["dog"]["dfs"] for s, _, _, _ in sims])
            fav_mean[sub_idx] = fav_samp.mean(axis=1); dog_mean[sub_idx] = dog_samp.mean(axis=1)
            gt = fav_samp > dog_samp; ne = fav_samp != dog_samp
            pred_prob[sub_idx] = gt.mean(axis=1) / np.maximum(ne.mean(axis=1), 1e-9)
            total_samp = fav_samp + dog_samp
            lines_ = np.floor(total_samp.mean(axis=1)) + 0.5
            phat = np.mean(total_samp > lines_[:, None], axis=1)
            total_actual_sub = fa[sub_idx] + da[sub_idx]
            actual_over_sub = (total_actual_sub > lines_).astype(float)
            if wta_flag == 0:
                phat_atp, actual_over_atp = phat, actual_over_sub
            else:
                phat_wta, actual_over_wta = phat, actual_over_sub
            for j in range(len(sub_df)):
                for side, arr in (("fav", fa[sub_idx]), ("dog", da[sub_idx])):
                    x = sims[j][0][side]["dfs"]; y = arr[j]
                    if np.isfinite(y):
                        cov.append(np.percentile(x, 10) <= y <= np.percentile(x, 90))
            del fav_samp, dog_samp, total_samp
        dt = time.time() - t0
        dfs_actual = np.concatenate([fa, da]).astype(float)
        dfs_pred = np.concatenate([fav_mean, dog_mean])
        okv = np.isfinite(dfs_actual) & np.isfinite(dfs_pred)
        resid = dfs_actual[okv] - dfs_pred[okv]
        mae = float(np.mean(np.abs(resid))); mse = float(np.mean(resid ** 2))
        phat_all = np.concatenate([phat_atp, phat_wta]) if len(pop_df[is_wta_col == 0]) and len(pop_df[is_wta_col == 1]) else (phat_atp if len(pop_df[is_wta_col == 0]) else phat_wta)
        aover_all = np.concatenate([actual_over_atp, actual_over_wta]) if len(pop_df[is_wta_col == 0]) and len(pop_df[is_wta_col == 1]) else (actual_over_atp if len(pop_df[is_wta_col == 0]) else actual_over_wta)
        okc = np.isfinite(aover_all)
        calib_brier = float(np.mean((phat_all[okc] - aover_all[okc]) ** 2))
        c80 = float(np.mean(cov))
        maf_brier = float(np.mean((pred_prob[valid] - actual_win[valid]) ** 2))
        buckets = {}
        for lo, hi, lab in zip(pbins[:-1], pbins[1:], plabels):
            mask = valid & (pred_prob >= lo) & (pred_prob < hi)
            nb = int(mask.sum())
            if nb == 0:
                continue
            buckets[lab] = {"n": nb, "gap": float(np.mean(pred_prob[mask]) - np.mean(actual_win[mask]))}
        tail_score = abs(buckets.get("75-80%", {}).get("gap", 0)) + abs(buckets.get("80%+", {}).get("gap", 0))
        print("-- dm=%g (%.1fs) -- MAE=%.4f MSE=%.4f old_coverage=%.3f calib_brier=%.4f most_dfs_fav_brier=%.4f tail|gap|sum=%.3f"
              % (dm, dt, mae, mse, c80, calib_brier, maf_brier, tail_score))
        print("   75-80%%=%+.3f (n=%d)   80%%+=%+.3f (n=%d)"
              % (buckets.get("75-80%", {}).get("gap", float("nan")), buckets.get("75-80%", {}).get("n", 0),
                 buckets.get("80%+", {}).get("gap", float("nan")), buckets.get("80%+", {}).get("n", 0)))
        out[str(dm)] = {"mae": mae, "mse": mse, "old_coverage": c80, "calib_brier": calib_brier,
                        "most_dfs_fav_brier": maf_brier, "tail_score": tail_score, "buckets": buckets}
    return out

RESULTS["pooled"] = sweep_holdout(df_hold, r_all_dfs, "POOLED")
RESULTS["atp"] = sweep_holdout(df_hold_atp, r_atp_dfs, "ATP-only")
RESULTS["wta"] = sweep_holdout(df_hold_wta, r_wta_dfs, "WTA-only")


md5_check("after")
with open("/path/to/home/openclaw/apex_v2_dfs_dispersion_partB_holdout_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2, default=str)
print("\nWrote apex_v2_dfs_dispersion_partB_holdout_results.json")

try:
    print("\n" + "=" * 100)
    print("SUMMARY -- best dm by Brier and by tail score, per population, on HOLDOUT")
    print("=" * 100)
    for label in ("pooled", "atp", "wta"):
        r = RESULTS[label]
        best_brier = min(GRID, key=lambda dm: r[str(dm)]["most_dfs_fav_brier"])
        best_tail = min(GRID, key=lambda dm: r[str(dm)]["tail_score"])
        mae_at_1e6 = r[str(1e6)]["mae"]
        mae_at_best = r[str(best_brier)]["mae"]
        print("%-8s best_by_brier=%-6s (MAE %.4f -> %.4f, delta %+.4f)   best_by_tail=%-6s"
              % (label, best_brier, mae_at_1e6, mae_at_best, mae_at_best - mae_at_1e6, best_tail))
except Exception as e:
    print("Summary print failed (non-fatal, JSON already saved):", e)

print("\nDONE PART B.")
