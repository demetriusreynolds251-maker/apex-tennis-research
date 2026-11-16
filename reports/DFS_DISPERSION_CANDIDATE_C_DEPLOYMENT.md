# DFs Dispersion Candidate C — Production Deployment
**Date:** 2026-09-27
**Authorized by:** explicit user decision, 2026-09-27 00:08 CT, after full investigation chain (historical decomposition → variance audit → confidence buckets → tune window → holdout confirmation → promotion analysis). No new fitting, retuning, or invented coefficients — values are copied verbatim from `apex_v2_dfs_promotion_analysis.py`'s holdout-confirmed Candidate C.

## 1. Pre-deployment verification

| Check | Result |
|---|---|
| Backup created | `apex_prop_engine.py.bak_predfsdispersionc_20260927_000924` |
| MD5 baseline — `apex_prop_sim_v1.py` (frozen) | `7b03e521e804862b85804f8ac4db7346` |
| MD5 baseline — `apex_prop_model_v1.py` (frozen) | `6bf50622a1761156a77ad0d35a2007f6` |
| MD5 baseline — `apex_prop_engine.py` (pre-edit) | `157f90b53603fdc97eb8351876ba4fdc` |
| Seam location | `apex_prop_engine.py::evaluate_match()`, lines 122-134 (aces Candidate C block, immediately before `sim.simulate()`) |

## 2. Exact diff applied

```diff
         # CANDIDATE-C-2026-09-26: tour-specific aces dispersion, aces-only scope.
         # Frozen, evidence-fit constants (method-of-moments, fit_df year<=2021;
         # reproduced identically in apex_v2_dispersion_calib_tune.py,
         # apex_v2_dispersion_calib_holdout.py, apex_v2_dispersion_promotion_analysis.py).
-        # DFs are intentionally left on production's own disp_mult path -- no DF
-        # calibration evidence exists for these dm values (DISPERSION_FWD_DESIGN.md S2).
         _R_ATP = {"fav": 8.70148205269834, "dog": 5.885645957929439}; _DM_ATP = 0.6
         _R_WTA = {"fav": 3.9866756061964232, "dog": 2.7971092624925418}; _DM_WTA = 0.4
         _r, _dm = (_R_WTA, _DM_WTA) if wta else (_R_ATP, _DM_ATP)
-        dfs_dm = z["c"].get("disp_mult", 1.0)
+        # CANDIDATE-C-2026-09-27: tour-specific DFs dispersion, holdout-confirmed
+        # (apex_v2_dfs_dispersion_partA.py / _partB_holdout.py /
+        # apex_v2_dfs_promotion_analysis.py). Same method-of-moments r fit
+        # convention as aces, fit_df year<=2021.
+        _RD_ATP = {"fav": 8.493509531006397, "dog": 9.163976729570685}; _DMD_ATP = 0.75
+        _RD_WTA = {"fav": 8.256973781128396, "dog": 9.500414039354514}; _DMD_WTA = 0.3
+        _rd, _dmd = (_RD_WTA, _DMD_WTA) if wta else (_RD_ATP, _DMD_ATP)
         s = sim.simulate(hA, hB, z["c"]["tb_k"], bo, (mu["fav"][0][0], mu["fav"][1][0]), (mu["dog"][0][0], mu["dog"][1][0]),
-                         (_r["fav"] * _dm, z["c"]["disp"]["fav"]["dfs"] * dfs_dm),
-                         (_r["dog"] * _dm, z["c"]["disp"]["dog"]["dfs"] * dfs_dm),
+                         (_r["fav"] * _dm, _rd["fav"] * _dmd),
+                         (_r["dog"] * _dm, _rd["dog"] * _dmd),
                          sims, sigma=z["c"].get("gap_sigma", 0.0))
```

Only these lines changed. Aces' own dispersion (`_r`, `_dm`) is untouched — same expression, same values as the 2026-09-26 deployment.

## 3. Post-deployment verification

| Check | Result |
|---|---|
| Compile check | `python3 -m py_compile apex_prop_engine.py` — PASS |
| MD5 recheck — `apex_prop_sim_v1.py` | `7b03e521e804862b85804f8ac4db7346` — **unchanged, PASS** |
| MD5 recheck — `apex_prop_model_v1.py` | `6bf50622a1761156a77ad0d35a2007f6` — **unchanged, PASS** |
| MD5 — `apex_prop_engine.py` (post-edit) | `4a4dff60e36cd07d0b167706b2f67f1c` — changed from baseline, as expected (this is the non-frozen adapter) |
| Selftest | `python3 apex_prop_engine.py --selftest` → `READY` / `SELFTEST PASS`, tier table still 21 categories |
| ATP live sanity check | see §4 |
| WTA live sanity check | see §4 |

## 4. Before vs. after behavior (same two boards, same code path, only the DFs seam changed)

**ATP — Jannik Sinner vs. Alex Michelsen (Hard, Bo5, pinn=0.91):**

| | Before (production, dm=1e6) | After (Candidate C, ATP dm=0.75) |
|---|---|---|
| Sinner DFs mean / sd | 2.393 / 1.668 | 2.393 / **1.931** |
| Michelsen DFs mean / sd | 3.563 / 2.093 | 3.585 / **2.533** |

**WTA — Mirra Andreeva vs. Leylah Fernandez (Hard, Bo3, pinn=0.72):**

| | Before (production, dm=1e6) | After (Candidate C, WTA dm=0.3) |
|---|---|---|
| Andreeva DFs mean / sd | 3.642 / 2.098 | 3.661 / **3.203** |
| Fernandez DFs mean / sd | 3.504 / 2.088 | 3.527 / **3.036** |

Means are unchanged within Monte Carlo noise (as the holdout MAE/MSE evidence said they would be — ≤0.001 movement everywhere). Standard deviations widen meaningfully: **+16% to +21% in ATP**, **+45% to +53% in WTA** — the differential correction working exactly as sized (WTA needed, and got, a larger correction).

## 5. Confirmation: DFs changed, non-DF categories did not

Checked directly against the same two live boards, post-deployment:
- `aces`: Sinner mean=13.83 sd=7.93, Michelsen mean=8.07 sd=5.70 — same magnitude as the 2026-09-26 aces deployment sanity check, unaffected by tonight's change (aces expression in the diff is untouched).
- `holds`, `breaks`, `games_won`, `fantasy_score`: unaffected by construction — these categories have no dispersion mechanism at all (categorical per-set draw + `gap_sigma`, confirmed by code read in the category calibration audit), and the diff never touches that code path.
- Frozen files `apex_prop_sim_v1.py` and `apex_prop_model_v1.py`: MD5-identical before and after, at every checkpoint in this deployment.

## 6. Expected effect on calibration (from the holdout promotion analysis)

| | most_dfs_fav Brier: before → after | 80%+ bucket gap: before → after |
|---|---|---|
| Overall | 0.2331 → 0.2287 | +0.099 → +0.014 |
| ATP | 0.2168 → 0.2166 | +0.051 → −0.016 |
| WTA | 0.2503 → 0.2415 | +0.136 → +0.118* |

*The WTA 80%+ figure is the one caveat carried over from the promotion analysis: that specific bucket's sample shrinks sharply as dispersion increases (n=350→38), making it noisy at the extreme tail; Brier — the full-sample, robust metric — is the reliable comparator and it clearly favors the deployed candidate in WTA too (0.2503→0.2415).

**In plain terms:** ATP DFs confidence should now be close to honest at every level, including the top bucket. WTA DFs confidence should be meaningfully less overconfident than before, though (per the holdout evidence itself) probably not as fully resolved as ATP — this mirrors exactly what happened with aces, where WTA needed, and still shows a smaller residual after, a larger correction than ATP.

## 7. Rollback procedure

1. Confirm which file is live: `md5 apex_prop_engine.py` should show `4a4dff60e36cd07d0b167706b2f67f1c`. If it doesn't, something else has changed it since this deployment — investigate before rolling back.
2. Restore: `cp apex_prop_engine.py.bak_predfsdispersionc_20260927_000924 apex_prop_engine.py`
3. Verify restore: `md5 apex_prop_engine.py` should show `157f90b53603fdc97eb8351876ba4fdc` (pre-DFs-fix, i.e. the state with only the aces Candidate C fix live).
4. Compile check: `python3 -m py_compile apex_prop_engine.py`
5. Selftest: `python3 apex_prop_engine.py --selftest` → expect `SELFTEST PASS`.
6. Re-confirm frozen files unchanged: `md5 apex_prop_sim_v1.py apex_prop_model_v1.py` should still show `7b03e521e804862b85804f8ac4db7346` / `6bf50622a1761156a77ad0d35a2007f6` (rollback never touches these regardless).

This is a pure code-level rollback — no data, log, or state file is touched by either the deployment or the rollback.
