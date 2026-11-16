# Tier 3 Serve-Quality Signal Investigation — 2026-09-27

Same evidence-only Build → Test discipline as BPS_V1 (which this
process rejected). Frozen files (`apex_prop_model_v1.py`,
`apex_prop_sim_v1.py`) MD5-verified unchanged before, during, and after
every step. Neither file was modified.

## 1. Dataset summary

Source: `ATP & WTA, 1968-2026/` (real, per-match, read via the frozen
model's own `load_sackmann()`, read-only import). 122,373 real main-tour
matches (ATP+WTA, challengers/qualifying excluded), 2005-01-03 through
2026-09-21.

**Coverage of the raw fields these candidates are built from:**

| field | coverage |
|---|---|
| w_1stIn / w_1stWon / w_2ndWon / w_svpt | 87.21% |
| l_1stIn / l_svpt | 87.21% |
| l_1stWon / l_2ndWon | 87.08% |

(Lower than BPS_V1's bpSaved/bpFaced coverage of ~96%, because these
serve-in/serve-won columns are recorded slightly less consistently in
the older/lower-tier portion of the source than break-point columns
are — a real, disclosed gap, not filled or estimated.) One numeric-
coercion bug was caught and fixed during the build: `load_sackmann()`'s
own coercion pass covers ace/df/svpt/svgms/bpSaved/bpFaced but not
1stIn/1stWon/2ndWon, and a stray non-numeric token in the raw CSVs
caused a `TypeError` on first run; fixed by adding an explicit
`pd.to_numeric(..., errors="coerce")` pass for those columns before
use (see `apex_tier3_serveq_build.py`).

**Sample counts** after joining to usable trailing-history rows
(same-length, same-order merge with `apex_bps_v1_rows.csv`, verified
row-by-row identical on date/tourney_id/winner/loser):
fit (≤2021) n=119,337 · tune (2022–2023) n=20,990 · holdout (2024+)
n=29,608 player-observations (matches identical BPS_V1's population,
since it's the same match set).


## 2. Candidates and methodology

Six real, independently-computed metrics (5 named + Dominance Ratio),
each tested as its own standalone addition, never pre-combined:

| Metric | Formula |
|---|---|
| FS% | 1stIn / svpt |
| FSPW% | 1stWon / 1stIn |
| SSPW% | 2ndWon / (svpt − 1stIn) |
| SPW% | (1stWon + 2ndWon) / svpt |
| RPW% | 1 − opponent's SPW% (this player's own return outcome) |
| Dominance Ratio (DR) | RPW% / (1 − SPW%) — standard tennis-analytics combined serve/return metric |

Each was tested in two forms (features A–D of the mission collapsed
into these two, explicitly, to bound scope):
- **raw, last-20 matches**: pooled (sum-of-counts) trailing rate over
  the player's last 20 matches, all surfaces combined, no shrinkage.
- **shrink-blended, 30/15**: surface-specific pooled rate (last 30
  matches on the match's own surface) blended toward the same-recency
  all-surface rate, shrink=15 — the *identical* match-count-weighted
  blend formula the frozen model already uses for hold_rate/break_rate.
- **Window sweep** (item B, SPW% only, informational): correlation
  against trailing hold_rate at N=10/20/30/50 rises monotonically
  (0.883 → 0.923 → 0.939 → 0.950) — longer windows are noisier-to-recency
  but more stable, as expected; N=20 (used for "raw") sits in the
  middle of that range, not at either extreme.
- **Surface-specific** (item D): SPW% only, Hard-court pooled rate,
  last 30 Hard-court matches — the one candidate with enough
  surface-specific sample depth to test alone (Clay/Grass per-player
  history is thinner; see `BPS_INVESTIGATION_2026-09-27.md`).

**Anti-leakage**: every trailing feature is a pooled sum over a
player's matches strictly *before* the match being predicted; that
match's own stats are appended to history only after its features are
computed (identical mechanism to BPS_V1 and to the frozen model's own
hold_rate/break_rate). No rolling window crosses into future matches;
no retrospective adjustment. Verified by construction (same replay
order as `load_sackmann()`'s own chronological sort), not by inspection
alone.

**Baseline (the existing Apex feature set)**: trailing `ace_rate,
df_rate, hold_rate, break_rate, bp_conv_rate` at W40/K15 — the same
production-analog features used for the BPS_V1 test, reused here by
merging `apex_bps_v1_rows.csv` (row-identical, same source/sort/build)
rather than recomputing.

**Targets**: `actual_hold_rate` for the four serve-side candidates
(FS%, FSPW%, SSPW%, SPW%) and Dominance Ratio; `actual_break_rate` for
the one return-side candidate (RPW%) — the same target-selection logic
used for BPS_V1 (each metric tested against the outcome it mechanically
feeds).


## 3. Phase 1 — Correlation matrix (candidate vs. existing production features)

Pearson correlation, pooled across fit+tune+holdout observations:

| Candidate | hold_rate | break_rate | ace_rate | df_rate | bp_conv_rate ("BP scored") |
|---|---|---|---|---|---|
| FS% (raw) | −0.042 | 0.151 | −0.188 | −0.285 | 0.083 |
| FSPW% (raw) | **0.870** | −0.490 | **0.794** | −0.203 | −0.332 |
| SSPW% (raw) | 0.711 | −0.286 | 0.374 | −0.478 | −0.191 |
| SPW% (raw) | **0.923** | −0.457 | 0.714 | −0.383 | −0.311 |
| SPW% (shrink) | **0.965** | −0.478 | 0.747 | −0.393 | −0.325 |
| RPW% (raw) | −0.450 | **0.914** | −0.542 | 0.241 | 0.620 |
| RPW% (shrink) | −0.470 | **0.962** | −0.574 | 0.237 | 0.651 |
| Dominance Ratio | 0.470–0.508 | 0.369–0.402 | 0.216–0.228 | −0.146…−0.163 | 0.247–0.269 |

Per the mission's explicit instruction, correlation is reported and
**not** used alone to conclude usefulness — SPW% and RPW% are strongly
correlated with hold_rate and break_rate respectively (unsurprising:
they are close mechanical cousins of those production features), which
is exactly why the fit/tune/holdout test below, not this table, is
what actually decided each verdict.

## 4. Phases 2–4 — Fit / Tune / Holdout (full numbers)

All values: BASE = the 5-feature existing Apex set; FULL = BASE +
candidate. Holdout uses FIT-window coefficients frozen (no peeking).

| Candidate | FIT ΔR² | TUNE coef (drift) | HOLD ΔMAE (abs / rel) | HOLD ΔR² | sign-stable |
|---|---|---|---|---|---|
| FS% (raw) | +0.000006 | 0.004 (−0.007) | +0.000013 (0.009%) | −0.000046 | **No** |
| FS% (shrink) | +0.000014 | −0.012 (−0.029) | +0.000020 (0.013%) | −0.000073 | **No** |
| FSPW% (raw) | +0.001128 | 0.327 (+0.066) | +0.000097 (0.066%) | +0.001191 | Yes |
| FSPW% (shrink) | +0.001918 | 0.421 (−0.032) | +0.000114 (0.077%) | +0.001749 | Yes |
| SSPW% (raw) | +0.000610 | 0.197 (+0.029) | **−0.000008** (−0.005%) | +0.000209 | Yes |
| SSPW% (shrink) | +0.000457 | 0.160 (−0.016) | **−0.000045** (−0.030%) | −0.000118 | Yes |
| SPW% (raw) | +0.002081 | 0.604 (+0.117) | +0.000261 (0.176%) | +0.001721 | Yes |
| **SPW% (shrink)** | +0.003933 | 1.111 (+0.094) | **+0.000431 (0.292%)** | +0.002665 | Yes |
| SPW% (Hard-only) | +0.001337 | 0.409 (+0.053) | +0.000258 (0.176%) | +0.001144 | Yes |
| RPW% (raw) | +0.000701 | 0.274 (−0.012) | +0.000052 (0.034%) | +0.000425 | Yes |
| RPW% (shrink) | +0.003255 | 1.188 (+0.272) | +0.000212 (0.139%) | +0.002306 | Yes |
| Dominance Ratio (raw) | +0.001948 | 0.136 (+0.027) | +0.000164 (0.111%) | +0.001029 | Yes |
| Dominance Ratio (shrink) | +0.002104 | 0.151 (+0.006) | +0.000200 (0.135%) | +0.000909 | Yes |

("abs" ΔMAE is in hold-rate/break-rate units, both bounded [0,1];
"rel" is that as a percentage of the baseline holdout MAE, ~0.148–0.152.)


## 5. Phase 5 — Redundancy analysis (why each fails)

- **FS%**: fails because it never had real signal to begin with —
  correlation with hold_rate is near zero (−0.04) and the sign of its
  own fit coefficient flips between fit and tune windows. Root cause:
  hitting more first serves in says nothing about whether those serves
  are *winning* points (that's FSPW%'s job) — quantity without quality.
  **Explanation D (insufficient stability) + a weak-signal variant of
  A (already captured, in this case by nothing at all).**
- **SSPW%**: fails at the holdout gate itself — ΔMAE goes slightly
  *negative* on real 2024+ data (both raw and shrink versions), despite
  a small positive in-sample FIT R². **Explanation E: signal disappears
  out of sample** — classic in-sample-only pattern.
- **FSPW%, SPW%, RPW%, Dominance Ratio**: all show genuine, sign-stable,
  holdout-positive improvement — these are **not** redundancy failures
  in the BPS_V1 sense (BPS_V1's holdout was flat/negative; these are
  real and positive). They fail only criterion 6, **economic
  magnitude**: the largest, SPW% (shrink), improves holdout MAE by
  0.000431 (0.29% relative) and R² by 0.0027 — real, but small enough
  that whether it clears a "worth shipping" bar is a business judgment,
  not a fact this test can settle by itself. **Explanation: partial A/B
  (SPW%/FSPW% correlate 0.87–0.97 with hold_rate, RPW% correlates 0.91–
  0.96 with break_rate) — most of what they'd add is already captured,
  and what's left over is real but thin.**
- **SPW% (Hard-only)**: same pattern as SPW% (raw/shrink), slightly
  weaker (fewer observations, thinner history per player) — surface
  restriction did not unlock additional signal beyond the all-surface
  version.

## 6. Phase 6 — Feature ranking

1. **SPW% (shrink 30/15)** — largest real, stable, holdout-positive
   effect (ΔMAE +0.000431, ΔR² +0.0027) — the strongest candidate found,
   but below the 0.05-percentage-point economic-significance bar used
   here (see below).
2. SPW% (raw, last-20) — same direction, smaller magnitude.
3. SPW% (Hard-only, last-30) — same, thinner sample.
4. RPW% (shrink 30/15) — real return-side analogue, similar magnitude.
5. Dominance Ratio (shrink / raw) — real but smaller than its own
   components (SPW%, RPW%) individually, i.e. combining them didn't
   help beyond the better of the two parts.
6. FSPW% (shrink / raw) — real, smallest of the "genuine" group.
7. RPW% (raw, last-20) — real, small.
8. FS% (raw / shrink) — no real signal, unstable sign.
9. SSPW% (raw / shrink) — signal present in-sample, gone out-of-sample.


## 7. Final recommendation

Applying the six promotion criteria exactly as specified, with one
explicit judgment call flagged: **"economically meaningful" was
operationalized here as a holdout MAE improvement greater than 0.0005
(half a percentage point of hold-rate/break-rate)** — a threshold I
chose, not one the mission specified numerically. That choice is the
one thing separating a clean "reject all" from "one borderline pass,"
so it's stated plainly rather than buried in a script constant.

| Candidate | Result |
|---|---|
| FS% (raw / shrink) | ❌ DO NOT IMPLEMENT — no real signal, unstable |
| FSPW% (raw / shrink) | ❌ DO NOT IMPLEMENT — real but sub-threshold |
| SSPW% (raw / shrink) | ❌ DO NOT IMPLEMENT — signal vanishes out of sample |
| **SPW% (raw / shrink / Hard-only)** | ❌ DO NOT IMPLEMENT — real, stable, holdout-positive, but **below the 0.0005 bar** (shrink version: 0.000431) |
| RPW% (raw / shrink) | ❌ DO NOT IMPLEMENT — real but sub-threshold |
| Dominance Ratio (raw / shrink) | ❌ DO NOT IMPLEMENT — real but smaller than SPW%/RPW% alone |

**0 of 13 tested variants clear all six promotion criteria as I
operationalized them. Recommendation across the board: DO NOT
IMPLEMENT.**

SPW% (shrink 30/15) is the one genuine near-miss: real, sign-stable
across fit→tune, positive on frozen-coefficient 2024+ holdout, and the
largest effect found in this investigation — it simply lands at
roughly 86% of the (self-chosen) bar for "worth shipping." If a lower
bar is the right one for how Apex actually uses hold-rate projections,
that is a call only you can make with the full economic context
(bet-sizing, edge thresholds, how much MAE improvement translates to
real P&L) — I did not lower the bar myself to manufacture a pass.

## What this does not claim

No production file was modified (MD5s verified identical throughout).
This is a real, disclosed-coverage, no-leakage test of 6 serve-quality
metrics in 2 forms each (plus one surface variant) against real
2005–2026 match data — it found one near-miss and twelve clear
rejections, and that is the deliverable, not a launch decision made on
your behalf.
