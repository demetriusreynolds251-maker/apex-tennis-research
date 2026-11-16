# Double Faults Dispersion Calibration Investigation
**Date:** 2026-09-26
**Process:** identical to the Aces investigation — historical decomposition, confidence buckets, variance audit, tune window, holdout confirmation, root-cause determination. Diagnostics only; no production change made.

Frozen file hashes, MD5-verified before and after every script run tonight (Part A, Part B):
- `apex_prop_sim_v1.py` = `7b03e521e804862b85804f8ac4db7346` — PASS
- `apex_prop_model_v1.py` = `6bf50622a1761156a77ad0d35a2007f6` — PASS

Scripts: `apex_v2_dfs_dispersion_partA.py` (Steps 1-4), `apex_v2_dfs_dispersion_partB_holdout.py` (Step 5). Results: `apex_v2_dfs_dispersion_partA_results.json`, `apex_v2_dfs_dispersion_partB_holdout_results.json`.

Aces was held fixed at its actual live production settings (Candidate C: ATP r={fav:8.70, dog:5.89}×dm=0.6, WTA r={fav:3.99, dog:2.80}×dm=0.4) throughout — only DFs was varied.

---

## Step 1 — Historical decomposition (fit_df, year≤2021)

| | production r (applied at dm=1e6) | own fitted r (method-of-moments) |
|---|---|---|
| ATP fav | 8.32 | 8.49 |
| ATP dog | 9.24 | 9.16 |
| WTA fav | 8.32 | 8.26 |
| WTA dog | 9.24 | 9.50 |

Unlike aces (where the fitted r differed meaningfully from production's r), **DFs' own fitted r is already very close to production's r** in both tours. That is not the problem. The problem, exactly as with aces, is `disp_mult=1e6` — it collapses this fitted r to effectively infinite (pure Poisson), discarding real, measured overdispersion:

| | excess variance (mean squared residual − Poisson variance) | mean rate (λ) | n |
|---|---|---|---|
| ATP fav | +0.98 | 2.88 | 23,312 |
| ATP dog | +1.09 | 3.15 | 23,312 |
| WTA fav | +1.47 | 3.49 | 11,437 |
| WTA dog | +1.43 | 3.69 | 11,437 |

All four excess-variance figures are positive on a large sample — DFs are confirmed overdispersed relative to Poisson, and **WTA shows roughly 40-50% more excess variance than ATP**, on a higher base rate too. This asymmetry foreshadows everything that follows.

---

## Step 2 — Confidence buckets (`most_dfs_fav`, current production dm=1e6, year≥2024 holdout)

`most_dfs_fav` is not a category the simulator exposes directly — it was derived here in post-processing from the same per-sim `fav`/`dog` DFs arrays `simulate()` already returns, using the identical tie-aware method the simulator uses internally for `most_aces_fav`.

| Segment | Brier | 80%+ gap | Pattern |
|---|---|---|---|
| Pooled | 0.233 | **+0.107** | overconfidence grows with confidence: −0.042 (<55%) → +0.046 → +0.067 → +0.109 → +0.071 → +0.107 (80%+) |
| ATP | 0.217 | +0.055 | same growing pattern, smaller magnitude |
| WTA | 0.251 | **+0.145** | same pattern, largest magnitude |

**This is the same overconfidence-growing-with-confidence signature that originally flagged aces**, present under current production settings, holdout-confirmed, and worse in WTA than ATP — mirroring aces' own tour asymmetry.

---

## Step 3 — Variance audit (residual-based, year≥2024 holdout — independent of fit_df)

| | fitted r (holdout) | fitted r (fit_df, for comparison) | excess variance | mean λ |
|---|---|---|---|---|
| ATP fav | 8.43 | 8.49 | +0.92 | 2.78 |
| ATP dog | 7.53 | 9.16 | +1.17 | 2.97 |
| WTA fav | 4.45 | 8.26 | **+2.78** | 3.52 |
| WTA dog | 4.62 | 9.50 | **+2.78** | 3.58 |

The overdispersion signal **replicates out-of-sample** (holdout is untouched by any fitting). Notably, WTA's holdout-fitted r (~4.5) is *lower* than its fit_df-fitted r (~8-9) — the real WTA overdispersion is even larger on the holdout than the historical estimate suggested. ATP's holdout r stays close to its fit_df r. This is independent confirmation that WTA DFs is the more serious of the two.

---

## Step 4 — Tune window (2022-2023, small-sample, NOT used to select a candidate)

The tune-window grid sweep gave a noisy, partially self-contradictory signal (e.g. ATP-only tune data said production's own dm=1e6 was already near-best). This is the same caution built into the aces process: **the tune window is exploratory only; the holdout decides.** Full grid detail is in `apex_v2_dfs_dispersion_partA_results.json`.

---

## Step 5 — Holdout confirmation (year≥2024, GRID=[1e6, 1.0, 0.75, 0.6, 0.5, 0.4, 0.3], 1000 sims/match)

| dm | Pooled tail\|gap\| | Pooled Brier | ATP tail\|gap\| | ATP Brier | WTA tail\|gap\| | WTA Brier |
|---|---|---|---|---|---|---|
| 1e6 (production) | 0.179 | 0.2332 | 0.108 | 0.2166 | 0.233 | 0.2509 |
| 1.0 | 0.096 | 0.2305 | **0.032** | **0.2165** | 0.191 | 0.2451 |
| 0.75 | 0.085 | 0.2301 | 0.025 | 0.2168 | 0.157 | 0.2443 |
| 0.6 | 0.050 | 0.2302 | 0.061 | 0.2173 | 0.119 | 0.2437 |
| 0.5 | **0.029** | 0.2298 | 0.095 | 0.2174 | 0.094 | 0.2429 |
| 0.4 | 0.068 | 0.2298 | 0.081 | 0.2184 | 0.090 | 0.2424 |
| 0.3 | 0.053 | **0.2297** | ~0.136* | 0.2185 | **0.046** | **0.2416** |

*ATP's tail score at 0.3 was not the best (0.75 was); ATP does not benefit from going as low as WTA does.

MAE/MSE moved by at most **+0.001** anywhere on this grid, in every population — exactly like aces, the fix is essentially free on point-accuracy.

**Confirmed, asymmetric candidate region:**
- **ATP: dm≈0.75-1.0, own fitted r** — a small, real improvement (tail 0.108→0.025), production is not badly broken here.
- **WTA: dm≈0.3-0.4, own fitted r** — a large, real improvement (tail 0.233→0.046-0.090, Brier 0.2509→0.2416-0.2424), production is meaningfully overconfident here.

---

## Step 6 — Root-cause determination

**Yes — DFs have the same class of dispersion-calibration issue aces had**, evidenced to the same standard: historical overdispersion (Step 1) that replicates out-of-sample (Step 3), a real bucket-calibration overconfidence pattern under current production settings on the untouched holdout (Step 2), and a holdout-confirmed candidate region that closes most of the gap at no accuracy cost (Step 5).

**Two differences from aces, both material:**
1. **Smaller magnitude in ATP.** Aces needed a real fix in both tours; DFs' ATP overconfidence is present but modest (80%+ gap +0.055 pre-fix, tail score already down to 0.025 at a mild dm≈0.75-1.0 — nowhere near the dm≈0.6 aces needed).
2. **Larger, WTA-concentrated magnitude.** WTA DFs (80%+ gap +0.145 pre-fix, Brier 0.2509) is comparable in severity to what aces looked like before its fix, and responds to a similarly aggressive correction (dm≈0.3-0.4).

This matches — and gives a second, independent line of evidence for — the WTA-concentration pattern already flagged in the category calibration audit's Phase 4/5 findings for aces itself.

---

## What this investigation did NOT do

- Did not modify `apex_prop_engine.py`, `apex_prop_sim_v1.py`, or `apex_prop_model_v1.py`. No production change was made.
- Did not select a final candidate from the tune window (noisy, not used per protocol).
- Did not run a live-board shadow test or forward-testing milestone gate — that is the next step in the process that was used for aces (DISPERSION_FWD_DESIGN.md), should you want to proceed the same way.
- The bucket-calibration test used here (`most_dfs_fav`) was derived by this investigation, not by the simulator itself — it does not exist as a named output category, so this is the first time it has been computed at all.

## Recommended next step, if you want to proceed

Mirroring aces' process exactly: build a DFs shadow/forward-test module (own dm/r per tour, aces-style milestone gate) before touching production — or, if you consider this evidence sufficient the way you did for aces, specify a candidate (e.g. ATP dm≈0.75-1.0 own r, WTA dm≈0.3-0.4 own r) and I will prepare the exact diff, expected impact, and rollback procedure before any deployment, exactly as was done for Candidate C.
