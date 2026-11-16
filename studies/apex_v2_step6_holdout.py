"""
Task 1, Step 6: HOLDOUT evaluation, year>=2024, V1 vs V2 (Formula C, gamma
LOCKED at 12.879686 per the Step 5 decision -- no tuning, no coefficient
changes here).

Reuses the REAL, unmodified apex_prop_sim_v1.holdout_report() / run_rows()
functions for BOTH V1 and V2 -- these are never edited. V2's aces-mu
generation is substituted only via a runtime monkeypatch of the
`v1_inputs_from_rows` name that run_rows() depends on, restored immediately
after each V2 call. The patch function is verified BIT-IDENTICAL to the
real, approved apex_prop_sim_v2.v2_inputs_from_rows() on a sample BEFORE it
is ever used for anything -- so the holdout numbers below are guaranteed to
reflect the actual approved V2 module, not a re-derived copy of it.

apex_prop_sim_v1.py, apex_prop_model_v1.py, apex_prop_sim_v2.py are all
imported read-only. MD5 of the two frozen V1 files is checked before and
after this script runs (see wrapper shell commands around this file).
"""
import json
import time
import numpy as np
import pandas as pd

import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim
import apex_prop_sim_v2 as sim2

N_SIMS = 2000
SACKMANN_DIR = "ATP & WTA, 1968-2026"

print("Loading frozen V1 model + frozen V1 sim coefficients (read-only)...")
m = v1.load_model()
coefs = sim.load_sim()
print("  model sha:", m["_sha"][:16], " sim marker:", coefs.get("marker"))
print("  V2 gamma (locked, Step 5 decision):", sim2.GAMMA_FIT)

df = pd.read_csv(v1.ROWS_OUT, low_memory=False)
df = sim.attach_scores(df, SACKMANN_DIR)
df = df[df["score"].notna() & df["n_sets"].notna()].reset_index(drop=True)
_, hf0, hd0, mu0 = sim.v1_inputs_from_rows(df, m)
okmask = (np.isfinite(hf0) & np.isfinite(hd0) & np.isfinite(mu0["fav"][0])
          & np.isfinite(mu0["fav"][1]) & np.isfinite(mu0["dog"][0]) & np.isfinite(mu0["dog"][1]))
df = df[okmask].reset_index(drop=True)
print("usable rows:", len(df), " holdout (year>=2024):", int((df["year"] >= 2024).sum()))


# ---------------------------------------------------------------------------
# ADAPTER for the V2 mu path. Saves the true, unpatched V1 function first,
# so this can never recurse into itself once installed.
# ---------------------------------------------------------------------------
TRUE_V1_INPUTS_FROM_ROWS = sim.v1_inputs_from_rows


def v2_adapter(df, m, gamma=sim2.GAMMA_FIT):
    P, hf, hd, mu = TRUE_V1_INPUTS_FROM_ROWS(df, m)
    W, K = m["window"], m["shrink"]
    mean_break_rate = m["mean_break_rate"]
    mu2 = {}
    for side in ("fav", "dog"):
        opp = "dog" if side == "fav" else "fav"
        opp_break_rate = df["%s_W%d_K%d_break_rate" % (opp, W, K)].values
        aces0, dfs0 = mu[side]
        suppression = np.exp(-gamma * (opp_break_rate - mean_break_rate))
        aces2 = aces0 * suppression
        mu2[side] = (aces2, dfs0)
    return P, hf, hd, mu2


# ---------------------------------------------------------------------------
# VERIFY the adapter is bit-identical to the real, approved
# apex_prop_sim_v2.v2_inputs_from_rows() BEFORE it is ever used for
# anything. Run with NO patch installed, so sim2's own internal
# `sim.v1_inputs_from_rows(df, m)` call still resolves to the true original.
# ---------------------------------------------------------------------------
sample = df[df["year"] >= 2024].head(500)
P_a, hf_a, hd_a, mu_a = sim2.v2_inputs_from_rows(sample, m)   # the real, approved module
P_b, hf_b, hd_b, mu_b = v2_adapter(sample, m)                 # this script's adapter
checks = []
for side in ("fav", "dog"):
    checks.append(np.array_equal(mu_a[side][0], mu_b[side][0]))  # aces
    checks.append(np.array_equal(mu_a[side][1], mu_b[side][1]))  # dfs
checks.append(np.array_equal(hf_a, hf_b))
checks.append(np.array_equal(hd_a, hd_b))
print("ADAPTER VERIFICATION vs real apex_prop_sim_v2.v2_inputs_from_rows(): all_identical =", all(checks), checks)
if not all(checks):
    raise SystemExit("ADAPTER DOES NOT MATCH THE REAL V2 MODULE -- aborting before any holdout run")


# ---------------------------------------------------------------------------
# RUN 1: V1, unpatched -- the real, frozen, unmodified pipeline.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("RUNNING V1 HOLDOUT (real apex_prop_sim_v1.holdout_report(), unpatched, n_sims=%d)" % N_SIMS)
print("=" * 100)
t0 = time.time()
L1 = []
res_v1 = sim.holdout_report(df, m, coefs, N_SIMS, L1)
print("V1 holdout run took %.1fs" % (time.time() - t0))
with open("apex_v2_step6_holdout_v1_log.txt", "w") as f:
    f.write("\n".join(L1))

# ---------------------------------------------------------------------------
# RUN 2: V2 -- patch installed for the duration of this call only, then
# restored immediately. holdout_report() and run_rows() are never edited;
# they are called exactly as V1 calls them, with only the aces-mu dependency
# swapped out.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("RUNNING V2 HOLDOUT (same real apex_prop_sim_v1.holdout_report(), v1_inputs_from_rows patched to v2_adapter, n_sims=%d)" % N_SIMS)
print("=" * 100)
sim.v1_inputs_from_rows = v2_adapter
t0 = time.time()
L2 = []
try:
    res_v2 = sim.holdout_report(df, m, coefs, N_SIMS, L2)
finally:
    sim.v1_inputs_from_rows = TRUE_V1_INPUTS_FROM_ROWS  # restore immediately, success or failure
print("V2 holdout run took %.1fs" % (time.time() - t0))
with open("apex_v2_step6_holdout_v2_log.txt", "w") as f:
    f.write("\n".join(L2))

# sanity: confirm the patch really is reverted (points back at the true function)
assert sim.v1_inputs_from_rows is TRUE_V1_INPUTS_FROM_ROWS
print("\nPatch reverted -- sim.v1_inputs_from_rows restored to the true original.")


# ---------------------------------------------------------------------------
# COMPARISON TABLE -- means (MAE), coverage, calibration (Brier), for every
# category holdout_report() tracks. Non-aces categories are a REGRESSION
# CHECK (must be identical or near-identical -- only aces should move,
# exactly like the Step 3 architecture regression check).
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("V1 vs V2 HOLDOUT COMPARISON (year>=2024)")
print("=" * 100)
print("\n-- MEANS (MAE): key = side_category -- (V1, V2, delta)")
mean_keys = sorted(set(res_v1["means"]) | set(res_v2["means"]))
for k in mean_keys:
    a = res_v1["means"].get(k, {}); b = res_v2["means"].get(k, {})
    ma, mb = a.get("mae_sim"), b.get("mae_sim")
    if ma is None or mb is None:
        continue
    flag = "" if abs(ma - mb) < 1e-6 else ("  <-- DIFFERS" if "aces" not in k else "  <-- EXPECTED (aces)")
    print("  %-24s V1=%.4f  V2=%.4f  delta=%+.4f%s" % (k, ma, mb, mb - ma, flag))

print("\n-- COVERAGE (50%/80%/90% central-interval hit rate): key -- (V1, V2)")
cov_keys = sorted(set(res_v1["coverage"]) | set(res_v2["coverage"]))
for k in cov_keys:
    a = res_v1["coverage"].get(k, {}); b = res_v2["coverage"].get(k, {})
    if not a or not b:
        continue
    print("  %-24s V1: 50%%=%.3f 80%%=%.3f 90%%=%.3f   V2: 50%%=%.3f 80%%=%.3f 90%%=%.3f"
          % (k, a.get(50, float("nan")), a.get(80, float("nan")), a.get(90, float("nan")),
             b.get(50, float("nan")), b.get(80, float("nan")), b.get(90, float("nan"))))

print("\n-- CALIBRATION (Brier score at line=floor(sim mean)+0.5): key -- (V1, V2)")
calib_keys = sorted(set(res_v1["calibration"]) | set(res_v2["calibration"]))
for k in calib_keys:
    a = res_v1["calibration"].get(k, {}); b = res_v2["calibration"].get(k, {})
    if not a or not b:
        continue
    flag = "" if "aces" in k else ("  <-- DIFFERS" if abs(a["brier"] - b["brier"]) > 1e-6 else "")
    print("  %-24s V1 Brier=%.4f (n=%d)  V2 Brier=%.4f (n=%d)  delta=%+.4f%s"
          % (k, a["brier"], a["n"], b["brier"], b["n"], b["brier"] - a["brier"], flag))

print("\n-- BINARY PROPS (Brier): key -- (V1, V2)  [most_aces_fav is the aces-relevant one]")
for k in sorted(set(res_v1["binary"]) | set(res_v2["binary"])):
    a = res_v1["binary"].get(k, {}); b = res_v2["binary"].get(k, {})
    if not a or not b:
        continue
    print("  %-20s V1: pred=%.3f actual=%.3f Brier=%.4f   V2: pred=%.3f actual=%.3f Brier=%.4f"
          % (k, a["pred"], a["actual"], a["brier"], b["pred"], b["actual"], b["brier"]))


# ---------------------------------------------------------------------------
# SUPPLEMENTARY: MSE on aces (holdout_report() itself only reports MAE).
# Computed from a direct run_rows() pass -- same coefs, same holdout rows,
# same n_sims -- so it is on equal footing with the MAE numbers above, just
# an additional statistic on the same simulated means.
# ---------------------------------------------------------------------------
print("\n" + "=" * 100)
print("SUPPLEMENTARY: MSE on aces (not part of the native holdout_report() output)")
print("=" * 100)
hold = df[df["year"] >= 2024]

sims_v1 = sim.run_rows(hold, m, coefs, N_SIMS, seed=1, progress=False)
sim.v1_inputs_from_rows = v2_adapter
try:
    sims_v2 = sim.run_rows(hold, m, coefs, N_SIMS, seed=1, progress=False)
finally:
    sim.v1_inputs_from_rows = TRUE_V1_INPUTS_FROM_ROWS
assert sim.v1_inputs_from_rows is TRUE_V1_INPUTS_FROM_ROWS

mse_summary = {}
for side in ("fav", "dog"):
    y = hold["%s_aces" % side].values
    sm1 = np.array([s[side]["aces"].mean() for s, _, _, _ in sims_v1])
    sm2 = np.array([s[side]["aces"].mean() for s, _, _, _ in sims_v2])
    mk = np.isfinite(y) & np.isfinite(sm1) & np.isfinite(sm2)
    mae1, mae2 = float(np.mean(np.abs(sm1[mk] - y[mk]))), float(np.mean(np.abs(sm2[mk] - y[mk])))
    mse1, mse2 = float(np.mean((sm1[mk] - y[mk]) ** 2)), float(np.mean((sm2[mk] - y[mk]) ** 2))
    mse_summary[side] = {"mae_v1": mae1, "mae_v2": mae2, "mse_v1": mse1, "mse_v2": mse2, "n": int(mk.sum())}
    print("  %s aces:  MAE V1=%.4f V2=%.4f (delta %+.4f)   MSE V1=%.4f V2=%.4f (delta %+.4f, %.2f%% change)  n=%d"
          % (side, mae1, mae2, mae2 - mae1, mse1, mse2, mse2 - mse1, 100 * (mse2 - mse1) / mse1, mk.sum()))

out = {
    "n_sims": N_SIMS, "n_holdout_matches": int(len(hold)),
    "gamma_locked": sim2.GAMMA_FIT,
    "means_v1": res_v1["means"], "means_v2": res_v2["means"],
    "coverage_v1": res_v1["coverage"], "coverage_v2": res_v2["coverage"],
    "calibration_v1": res_v1["calibration"], "calibration_v2": res_v2["calibration"],
    "binary_v1": res_v1["binary"], "binary_v2": res_v2["binary"],
    "aces_mse_supplementary": mse_summary,
}
with open("/path/to/home/openclaw/apex_v2_step6_holdout_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWrote apex_v2_step6_holdout_results.json, apex_v2_step6_holdout_v1_log.txt, apex_v2_step6_holdout_v2_log.txt")
