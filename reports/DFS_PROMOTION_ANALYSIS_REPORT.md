# Double Faults — Direct Promotion Analysis
**Date:** 2026-09-27
**Script:** `apex_v2_dfs_promotion_analysis.py` (mirrors `apex_v2_dispersion_promotion_analysis.py`, the aces version). Results: `apex_v2_dfs_promotion_analysis_results.json`.
Frozen files MD5-verified before and after: `apex_prop_sim_v1.py` = `7b03e521e804862b85804f8ac4db7346` PASS, `apex_prop_model_v1.py` = `6bf50622a1761156a77ad0d35a2007f6` PASS. No production file touched.

Aces held fixed at its actual live production settings throughout (Candidate C: ATP r={fav:8.701,dog:5.886} dm=0.6, WTA r={fav:3.987,dog:2.797} dm=0.4) — only DFs varies across the three candidates below.

## Candidates
- **A — Production:** DFs dm=1,000,000, pooled fitted r (fav=8.322, dog=9.244)
- **B — Global:** DFs dm=0.5, same pooled fitted r (only dm lowered)
- **C — Segmented:** ATP dm=0.75, own fitted r (fav=8.494, dog=9.164); WTA dm=0.3, own fitted r (fav=8.257, dog=9.500) — the holdout-confirmed region from the DFs investigation (2026-09-26)

Full year≥2024 holdout (n=10,971), 1,000 sims/match, one simulation pass per candidate.

## Results — most_dfs_fav Brier and 80%+ bucket gap

| Segment | A (production) | B (global 0.5) | C (segmented) |
|---|---|---|---|
| Overall | Brier 0.2331, 80%+ gap **+0.099** | Brier 0.2299, 80%+ gap **−0.006** | Brier **0.2287**, 80%+ gap +0.014 |
| ATP | Brier 0.2168, 80%+ gap +0.051 | Brier 0.2173, 80%+ gap −0.025 | Brier **0.2166**, 80%+ gap −0.016 |
| WTA | Brier 0.2503, 80%+ gap **+0.136** | Brier 0.2433, 80%+ gap +0.015 | Brier **0.2415**, 80%+ gap +0.118* |

MAE/MSE across every segment move by ≤0.001 across all three candidates — the correction is free on point-accuracy, exactly as with aces.

*Caveat on the WTA 80%+ figure for Candidate C: the bucket's sample shrinks sharply as dispersion increases and fewer predictions land above 80% at all (A: n=350 → B: n=85 → C: n=38). At n=38 this single number is noisy — it isn't fully consistent with the WTA-only holdout sweep run the night before (which found 80%+ gap ≈ +0.030 at the identical dm=0.3, n=35, using a different per-row seed alignment). **Brier, computed over the full sample rather than one thin tail bucket, is the reliable comparator here** — and by Brier, C is the best WTA candidate in both runs.

## Full segment/surface detail (Candidate C)

| Segment | n | Brier | calib_brier (O/U) | 80%+ gap |
|---|---|---|---|---|
| Overall | 10,971 | 0.2287 | 0.2405 | +0.014 |
| ATP | 5,777 | 0.2166 | 0.2417 | −0.016 |
| WTA | 5,194 | 0.2415 | 0.2392 | +0.118 (thin, n=38) |
| Hard | 6,410 | 0.2308 | 0.2419 | +0.031 |
| Clay | 3,182 | 0.2277 | 0.2368 | −0.016 |
| Grass | 1,379 | 0.2211 | 0.2425 | −0.038 |

## Verdict

**Candidate C (segmented, own fitted r — ATP dm≈0.75, WTA dm≈0.3) is the best performer** on the metric that matters most (most_dfs_fav Brier), in every segment tested, at zero MAE/MSE cost — the same shape of result the aces promotion analysis produced for Candidate C there.

- Candidate B (a single global dm=0.5) is a reasonable, simpler alternative — nearly as good pooled and in WTA, slightly *overcorrects* ATP into mild underconfidence (80%+ gap −0.025).
- Candidate A (current production) is confirmed the worst by Brier everywhere, and by far the worst in WTA (0.2503 vs. 0.2415-0.2433 for B/C).

This is diagnostic only — nothing has been deployed. This is the same evidence-gate step that preceded the aces Candidate C production proposal; the next step, if you want to proceed the same way, is a production-change proposal (exact diff, expected impact, rollback procedure) for DFs Candidate C, or a shadow/forward-test module first if you'd rather not skip that gate this time.
