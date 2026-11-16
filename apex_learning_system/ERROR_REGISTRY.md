# ERROR REGISTRY
Append-only.

---
# Entry 2026-08-29 23:13
## Error registry / lessons  (ALIS-L4 Phase 3)
INFRASTRUCTURE: BUILT / VALIDATION: NOT STARTED

| pattern | occ | state | evidence | root cause | recommendation |
|---|---|---|---|---|---|
| `bias:total_games` | 5 | **Observed** | Low | Systematic projection bias in total_games | Adjust total_games projection weighting (Purpose 1) |
| `cause:VARIANCE:total_games` | 2 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in total_games |
| `cause:VARIANCE:games_won` | 1 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in games_won |

**Gates:** Hypothesis <3 occ / Observed >=3 / Supported >=8 / Validated only via Phase 4.

---
# MANUAL HYPOTHESES ENTERED 2026-08-30 16:16
State: Hypothesis only. Not promoted. Not validated. Entered for future testing.

## `bo5_scaling:player_level`
- **State:** Hypothesis   **Evidence:** Very Low
- **Observation:** match total_games 23.51->37.75 (1.61); Gaston dfs 3.03->3.85 (1.27); Gaston games_won 12.47->14.15 (1.13)
- **Concern:** Bo5 match projections expand ~60% while player-level categories expand substantially less
- **Question:** Are player-level projections under-scaling relative to match-level projections?
- **Potential impact:** Overconfident unders; underprojected player accumulation stats
- **Status:** Unverified. n=1 player observed in both formats. Requires additional Bo5 settlements.
- **Action:** TEST ONLY -- do not act. Compare Bo5 player-level actuals vs projections as settlements arrive.

## `dispersion:poisson_tails`
- **State:** Hypothesis   **Evidence:** Very Low
- **Observation:** sd ~= 1.06 * sqrt(mean) across 21 sampled dfs projections, both formats, no exceptions
- **Concern:** Variance may be too narrow; upper tails underestimated
- **Question:** Do actual outcomes exceed modeled p90 more often than ~10% of the time?
- **Potential impact:** Overconfidence; excessive UNDER recommendations; poor tail calibration
- **Status:** Unverified. n=21 projections, 0 settled. Requires settlement evidence.
- **Action:** TEST ONLY -- do not act. Track in-band %% (actual within p10-p90) per category.

**Promotion rules unchanged:** Hypothesis -> Observed requires repeated evidence;
Observed -> Supported requires the evidence gate; Supported -> Validated requires
settled results demonstrating the pattern via Phase 4. Neither entry may be promoted on intuition.

---
# Entry 2026-08-30 17:56
## Error registry / lessons  (ALIS-L4 Phase 3)
INFRASTRUCTURE: BUILT / VALIDATION: NOT STARTED

| pattern | occ | state | evidence | root cause | recommendation |
|---|---|---|---|---|---|
| `bias:total_games` | 5 | **Observed** | Low | Systematic projection bias in total_games | Adjust total_games projection weighting (Purpose 1) |
| `cause:VARIANCE:total_games` | 2 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in total_games |
| `cause:VARIANCE:games_won` | 1 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in games_won |
| `cause:MODEL_ERROR:dfs` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in dfs |
| `cause:MODEL_ERROR:aces` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in aces |

**Gates:** Hypothesis <3 occ / Observed >=3 / Supported >=8 / Validated only via Phase 4.

---
# Entry 2026-08-30 22:16
## Error registry / lessons  (ALIS-L4 Phase 3)
INFRASTRUCTURE: BUILT / VALIDATION: NOT STARTED

| pattern | occ | state | evidence | root cause | recommendation |
|---|---|---|---|---|---|
| `bias:total_games` | 5 | **Observed** | Low | Systematic projection bias in total_games | Adjust total_games projection weighting (Purpose 1) |
| `cause:VARIANCE:total_games` | 2 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in total_games |
| `cause:VARIANCE:games_won` | 1 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in games_won |
| `cause:MODEL_ERROR:dfs` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in dfs |
| `cause:MODEL_ERROR:aces` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in aces |

**Gates:** Hypothesis <3 occ / Observed >=3 / Supported >=8 / Validated only via Phase 4.

---
# Entry 2026-08-30 22:39
## Error registry / lessons  (ALIS-L4 Phase 3)
INFRASTRUCTURE: BUILT / VALIDATION: NOT STARTED

| pattern | occ | state | evidence | root cause | recommendation |
|---|---|---|---|---|---|
| `bias:total_games` | 5 | **Observed** | Low | Systematic projection bias in total_games | Adjust total_games projection weighting (Purpose 1) |
| `cause:VARIANCE:total_games` | 2 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in total_games |
| `cause:VARIANCE:games_won` | 1 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in games_won |
| `cause:MODEL_ERROR:dfs` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in dfs |
| `cause:MODEL_ERROR:aces` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in aces |

**Gates:** Hypothesis <3 occ / Observed >=3 / Supported >=8 / Validated only via Phase 4.

---
# Entry 2026-08-30 22:40
## Error registry / lessons  (ALIS-L4 Phase 3)
INFRASTRUCTURE: BUILT / VALIDATION: NOT STARTED

| pattern | occ | state | evidence | root cause | recommendation |
|---|---|---|---|---|---|
| `bias:dfs` | 10 | **Supported** | Moderate | Systematic projection bias in dfs | Adjust dfs projection weighting (Purpose 1) |
| `bias:games_won` | 5 | **Observed** | Low | Systematic projection bias in games_won | Adjust games_won projection weighting (Purpose 1) |
| `cause:VARIANCE:dfs` | 4 | **Observed** | Very Low | VARIANCE | Investigate VARIANCE in dfs |
| `cause:VARIANCE:total_games` | 2 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in total_games |
| `cause:VARIANCE:games_won` | 1 | **Hypothesis** | Very Low | VARIANCE | Investigate VARIANCE in games_won |
| `cause:MODEL_ERROR:total_games` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in total_games |
| `cause:CATEGORY_ERROR:games_won` | 1 | **Hypothesis** | Very Low | CATEGORY_ERROR | Investigate CATEGORY_ERROR in games_won |
| `cause:MODEL_ERROR:dfs` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in dfs |
| `cause:MODEL_ERROR:aces` | 1 | **Hypothesis** | Very Low | MODEL_ERROR | Investigate MODEL_ERROR in aces |

**Gates:** Hypothesis <3 occ / Observed >=3 / Supported >=8 / Validated only via Phase 4.
