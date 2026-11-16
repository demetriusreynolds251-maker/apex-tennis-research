# SPW% Economic Impact & Deployment Decision
**Date:** 2026-09-27
**Frozen files verified unchanged (MD5) before and during this analysis:**
- `apex_prop_model_v1.py` = `6bf50622a1761156a77ad0d35a2007f6`
- `apex_prop_sim_v1.py` = `7b03e521e804862b85804f8ac4db7346`
Neither file was modified. No real production write function was invoked at any point.

---

## 0. Framing

The Tier 3 investigation found SPW% (shrink 30/15) to be the best-performing
candidate of 13 tested: sign-stable, holdout-positive, ΔMAE=+0.000431 /
ΔR²=+0.002665 on `actual_hold_rate` directly — but below the self-chosen
0.0005 MAE economic-significance threshold. This report does not re-run that
test. It asks a different, deployment-level question: **does adding SPW%
change what a bettor using Apex would actually do, and does it do so for the
better?** Per the mission brief, MAE is reported but is not the primary
criterion.

---

## 1. Dataset Summary

- **Source:** `apex_batch_a_rows.csv` — a separate, pre-existing real market-priced
  research batch (not built for this mission; discovered and verified this
  session). 67,565 rows, 2010–2026, containing real Pinnacle closing prices
  (`pinn_a`) with **100% price coverage** and real match outcomes (`label`).
- **Filter applied:** `year >= 2024` → **11,594 candidate matches** (true holdout,
  matches production's own frozen fit/tune boundary).
- **Feature join:** trailing BASE features (ace/df/hold/break/bp_conv rates) +
  `spw_shrink` pulled from `apex_bps_v1_rows.csv` / `apex_tier3_serveq_rows.csv`
  (the same real trailing-feature rows built and used in the two prior
  investigations), matched by `(date, sorted(norm_name pair))`.
- **Real total-games ground truth:** parsed from the real Sackmann score string
  via the frozen model's own `parse_games()`.
- **Result:** 11,213 of 11,594 matches (**96.7%**) processed successfully.
  - 5 excluded: no feature-join match.
  - 376 excluded: missing/retired score (no valid real total-games ground truth).
- No synthetic, simulated, or hypothetical match data was used anywhere. The
  Monte Carlo `simulate()` calls are the frozen production simulator applied to
  real matches with real market prices — used to generate Apex's own
  prop-market outputs, exactly as production does, not to invent data.
- 2025/2026 were **not broken out separately** in this run; the 2024+ pool is
  treated as a single true-holdout block. This is a scope note, not an omission
  of evidence — sub-splitting would meaningfully shrink already-modest per-cell
  counts (see §8 robustness, where per-surface counts already run a few
  thousand each).

---

## 2. Model Construction

Both models were refit via OLS (`np.linalg.lstsq`) on the fit window (≤2021),
predicting `actual_hold_rate`, exactly mirroring the Tier 3 methodology.

- **MODEL A (baseline):** `[ace_rate, df_rate, hold_rate, break_rate, bp_conv_rate]`
  Coefficients: `[0.28603, 0.47224, -0.46400, 0.62160, -0.07149]`, intercept `-0.00578`
- **MODEL B (baseline + SPW%):** MODEL A's five features + `spw_shrink` (shrink 30/15)
  Coefficients: `[-0.01092, 0.27067, -0.33697, 0.19784, -0.07827, -0.01031]`, `spw_shrink` coef `+1.01705`

SPW% is the **only** variable difference between the two models, per the
mission's constraint. Both models feed the identical, unmodified
`apex_prop_sim_v1.py` simulation pipeline (`solve_tilt` → `match_winprob_mix`
→ `simulate`), with identical nuisance parameters shared across A and B for
every match: `PTB_K=6.0` (fixed), placeholder ace/DF rates `(0.08, 0.04)` for
both `muA`/`muB`, Poisson-only dispersion (`rA=rB=(None,None)`), and the same
random seed per match. None of these shared choices can create an artificial
difference between A and B — any gap in the results below comes from the
`hold_rate → level → simulated distribution` pathway alone, which is where
SPW% enters.

**Architectural finding (numerically confirmed, not assumed):** the frozen
`solve_tilt()` finds a tilt so that Apex's simulated match-winner probability
exactly equals the real market price (`pinn`) — "the sim never argues with
the price," per the production code's own comment. This means **Apex's
moneyline/match-winner probability is pinned to the market and is
architecturally identical for Model A and Model B.** Confirmed directly:
`|p_fav_A − p_fav_B|`: max = 0.000110, mean = 0.000022, across all 11,213
matches. **SPW% cannot move Apex's own match-winner confidence, calibration,
or edge — by construction, for any candidate feature, not just this one.**
What SPW% *can* influence is the "level" (blended average service/return
quality) that feeds prop-level markets: Total Games, distance probability,
and the favorite's projected games won. Total Games is used below as the
primary real, testable proxy for economic impact.

---

## 3. Holdout Results (Total Games, 2024+, n=11,213)

| Metric | Model A (baseline) | Model B (+SPW%) | Δ (B−A) |
|---|---|---|---|
| MAE | 5.5389 | 5.5408 | **−0.0020 (worse)** |
| RMSE | 6.4064 | 6.4095 | −0.0031 (worse) |

On this independent, real, market-priced holdout, Model B is very slightly
**worse**, not better, on the Total Games metric. This is the opposite
direction from the Tier3 investigation's own internal holdout (which measured
against `actual_hold_rate` directly and found +0.000431 MAE improvement). Both
results are real; they are not measuring the same thing. Tier3 asked "does
SPW% predict hold rate better." This asks "does SPW% predict the actual
prop-market outcome (Total Games) better," after passing through the level
blend and Monte Carlo simulation. The answer here is: on average, no —
by a very small margin, but in the wrong direction.

---

## 4. Confidence Bucket Analysis

Bucketed by real market `pinn_fav` (Apex's own predicted match-winner
probability is architecturally identical to this value for both models, per §2).

| Bucket | Match count | Pred A ≈ Pred B (win%) | MAE_A (Total Games) | MAE_B (Total Games) |
|---|---|---|---|---|
| 50–55% | ~2,240 | pinned, ≈ bucket midpoint | 5.435 | 5.433 |
| 55–60% | — | pinned | — | — |
| 60–65% | — | pinned | — | — |
| 65–70% | — | pinned | — | — |
| 70–75% | — | pinned | — | — |
| 75%+ | ~1,900 | pinned | 5.620 | 5.631 |

(Full 6-row table computed; endpoints shown — the pattern holds throughout:
predicted win-probability is identical between A and B in every bucket, and
Total-Games MAE differences are small and sign-inconsistent across buckets.)

**Finding:** SPW% produces **zero change** in win-probability calibration in
any confidence bucket, because match-winner probability is pinned to the
market by architecture. This directly answers the mission's confidence-bucket
question: SPW% cannot improve confidence calibration in the current Apex
architecture, regardless of its underlying signal quality.

---

## 5. Calibration Analysis

Because predicted win probability ≡ market price for both models (§2, §4),
the calibration gap (predicted win% − actual win%) is **identical between
Model A and Model B by construction** — there is no calibration difference to
report on the moneyline. The only calibration-relevant metric SPW% can move
is Total-Games MAE/RMSE (§3), where it is marginally worse, not better.

---

## 6. Edge Distribution Analysis

- **Decision flips (Total Games Over/Under, using Model A's own implied line
  for both models):** 2,387 of 11,213 matches (**21.29%**) change decision
  between A and B.
- **Accuracy on the flipped subset:** Model A correct on 1,185/2,387
  (**49.6%**), Model B correct on 1,202/2,387 (**50.4%**).
  Difference: +0.8 percentage points on n=2,387 — a margin consistent with
  noise (a coin-flip binomial standard error on this n is ≈1.0pp), not a
  reliable edge.
- **Distribution shift (Total Games projection, B − A):** mean shift
  +0.1186 games; quantiles range from p01 = −0.3554 to p99 = +0.4933 —
  a small, symmetric-ish nudge, not a systematic directional correction.
- **Distance probability shift:** +0.0099 (negligible).
- **Favorite's projected games-won shift:** +0.0610 games (negligible).

**Finding:** SPW% moves roughly 1 in 5 Total-Games decisions, but on the
matches where it actually changes the pick, it is right about as often as it
is wrong (50.4% vs 49.6%) — not a demonstrated edge. On the match-winner /
moneyline market specifically, SPW% changes **zero** decisions, buckets, or
edges (§2, §4) — there is nothing to flip there.

---

## 7. Betting Impact Analysis

Interpreting "selections" as Total-Games Over/Under picks (the only market
where SPW% has any live effect at all, per the architectural finding):

- **Selections changed:** 2,387 / 11,213 (21.29%).
- **Selections added/removed from "pick territory":** not separable from
  "changed" in the current setup, since both models generate a pick on every
  match rather than passing/no-betting on some — this is a real limitation of
  what the two-model comparison as specified can show, not a hidden result.
- **Win rate on changed selections:** Model B 50.4% vs Model A 49.6% (§6) —
  functionally a coin flip.
- **Win rate overall (Total Games MAE as the practical proxy):** Model A
  is marginally better (5.5389 vs 5.5408 MAE, §3).
- **Average projected edge:** not materially different — the shift
  distribution (§6) is centered near zero with symmetric tails.
- **Calibration quality:** unchanged on moneyline (pinned), marginally worse
  on Total Games (§3).

**Direct answer to the mission's central question — "Would a bettor
following Apex have made better decisions with SPW% included? Show
evidence."**
On the real, market-priced 2024+ holdout: **no, not demonstrably.** Overall
Total-Games accuracy is very slightly worse with SPW% included (§3). On the
21.29% of matches where SPW% changes the pick, the change is right slightly
more than half the time, a margin indistinguishable from chance at this
sample size. On the moneyline market — the market Apex bettors most directly
care about — SPW% changes nothing at all, by construction. There is no
segment of real evidence in this analysis showing a bettor was better off.

---

## 8. Segment Analysis / Robustness Testing

ΔMAE (Total Games, B−A; negative = Model B worse) by segment, computed on the
same 11,213-match real holdout, restricted to each segment:

| Segment | ΔMAE (B−A) | Direction |
|---|---|---|
| ATP | −0.0092 | B worse |
| WTA | +0.0060 | B better |
| Hard | −0.0019 | B worse |
| Clay | −0.0026 | B worse |
| Grass | −0.0008 | B worse (negligible) |
| Favorite won | −0.0045 | B worse |
| High-confidence (pinn_fav ≥ 70%) | −0.0080 | B worse |
| Low-confidence (pinn_fav < 60%) | +0.0057 | B better |
| Best-of-5 | −0.0230 | B notably worse |
| Best-of-3 | +0.0004 | ~neutral |

**Finding:** results are **mixed and small in magnitude, not concentrated in a
favorable niche.** ATP, Hard/Clay/Grass, favorites, high-confidence, and
best-of-5 all lean slightly negative for SPW%; only WTA and low-confidence
lean (marginally) positive. There is no coherent story here of "SPW% helps in
X, so deploy it scoped to X" — the pattern looks like noise scattered around
zero rather than a real, exploitable regime.

---

## 9. Error Analysis (Top 100 improved vs. top 100 degraded, Total Games)

| | Most improved (top 100) | Most degraded (top 100) |
|---|---|---|
| ATP / WTA split | 96 / 4 | 98 / 2 |
| Surface (H/C/G) | 47 / 19 / 34 | 44 / 20 / 36 |
| Mean pinn_fav (confidence) | 0.684 | 0.731 |

**Finding:** the two groups look **nearly identical** in composition — same
tour mix, same surface mix, similar confidence range. If SPW% carried a real,
exploitable pattern, the improved and degraded groups should look
systematically different (different surfaces, different confidence levels,
different player profiles). They don't. This is evidence *against* a genuine
underlying mechanism and consistent with the gains/losses being close to
random noise around a near-zero average effect.

---

## 10. Incremental Contribution / Redundancy Analysis

- `corr(levelA, levelB)` on this independent real 2024+ sample: **0.9964**
  (near-total redundancy between the baseline-only level and the
  SPW%-enhanced level).
- Consistent with Tier3's own finding that SPW% correlates 0.72–0.76 with
  hold_rate/break_rate-family features already in production, and its
  incremental R² over the existing baseline was small (+0.0027 on
  `actual_hold_rate` directly).
- **Finding:** SPW% is overwhelmingly redundant with information the
  production model already has. What little unique variance it contributes
  is not translating into better real-world prop-market accuracy on this
  independent test (§3), and is not concentrated in any identifiable segment
  (§8, §9).

---

## 11. Promotion Standard — scored against the 6 explicit criteria

| # | Criterion | Result |
|---|---|---|
| 1 | Holdout improvement remains positive | ❌ Negative on the real market-priced Total-Games holdout (§3), though positive on Tier3's internal hold-rate-direct holdout. Mixed, and the deployment-relevant metric is negative. |
| 2 | Coefficient remains stable | ⚠️ Partial — SPW% coefficient sign is stable (+1.017), but several baseline coefficients shift meaningfully between Model A and B (e.g. hold_rate coefficient moves from −0.464 to −0.337), indicating real redundancy/collinearity, not a clean additive signal. |
| 3 | Calibration improves or remains unchanged | ⚠️ Unchanged on moneyline (architecturally, not by merit); slightly worse on Total Games. |
| 4 | Betting decisions improve | ❌ No — flip-subset accuracy (50.4% vs 49.6%) is not a demonstrated improvement at this sample size, and overall Total-Games accuracy is slightly worse. |
| 5 | Edge ranking improves | ❌ No evidence of improvement — distribution shift is centered near zero, segment results are mixed, error-analysis composition is indistinguishable between improved/degraded groups. |
| 6 | Benefit justifies added complexity | ❌ No — adds a full shrinkage-blended feature, redundant at 0.996+ correlation with existing signal, for a net-negative real-world holdout result. |

Criteria 1, 4, 5, and 6 fail outright on the real, deployment-relevant
evidence. Criterion 2 is only partially met. Criterion 3 is neutral at best.
Per the mission's own decision rule: *"If improvement is negligible in
practical betting terms: Recommendation = DO NOT IMPLEMENT."*

---

## 12. Final Recommendation

# ❌ DO NOT IMPLEMENT

**Reasoning, grounded in the real evidence above, not solely on MAE thresholds:**

1. **Zero moneyline impact by architecture.** Apex's match-winner probability
   is pinned to the real market price by the frozen simulator's own design.
   SPW% cannot move confidence, calibration, or edge on the market bettors
   care about most — this alone caps its practical value regardless of the
   underlying signal's quality.
2. **Net-negative on the one market it can touch.** On the independent,
   real, market-priced 2024+ holdout (11,213 matches), adding SPW% makes
   Total-Games predictions very slightly *worse* (MAE 5.5408 vs 5.5389), the
   opposite direction from Tier3's internal hold-rate-direct test.
3. **No demonstrated betting edge.** On the 21.29% of matches where SPW%
   changes the pick, it is correct 50.4% of the time versus 49.6% for the
   baseline — a margin indistinguishable from chance at this sample size.
4. **No favorable niche.** Segment and robustness results are small and
   inconsistent in sign across ATP/WTA/surfaces/confidence tiers/best-of —
   there is no scoped deployment (e.g., "WTA only") supported by a coherent
   pattern rather than noise.
5. **Near-total redundancy.** SPW%-enhanced and baseline-only levels
   correlate at 0.9964 on this sample; the feature is overwhelmingly
   reinforcing signal the production model already has via hold_rate/
   break_rate, not adding genuinely new information that shows up in
   real outcomes.
6. **No error-analysis pattern.** The most-improved and most-degraded
   prediction groups are compositionally indistinguishable (tour, surface,
   confidence) — inconsistent with a real, exploitable mechanism.

The Tier3 investigation's own finding stands: SPW% shows a small, real,
sign-stable statistical signal against `actual_hold_rate` directly. This
report does not contradict that. What it finds is that the signal does not
survive the trip through Apex's actual deployment pipeline into a real,
independently-priced holdout, in a way that changes betting outcomes for the
better. Per the mission's own standard — "if improvement is negligible in
practical betting terms, recommendation = DO NOT IMPLEMENT" — the verdict is
**DO NOT IMPLEMENT.**

No production files were modified. No rollback is required.
