# BPS_V1 — Build → Implement → Test — 2026-09-27

Full Build → Implement → Test workflow for Break-Points-Saved% (BPS%)
as a real candidate feature, run with the same fit/tune/holdout
discipline used for Aces and Double Faults. Frozen files
(`apex_prop_model_v1.py`, `apex_prop_sim_v1.py`) verified byte-identical
(MD5 unchanged) before, during, and after every step below. Neither
file was modified.

## Important correction made mid-task

The investigation almost concluded — incorrectly — that no real
historical point-level BPS dataset exists in this environment. That
conclusion was based on two real, confirmed dead ends:
`data/sackmann/tennis_atp/atp_matches.csv` is a 14-byte broken stub
("404: Not Found"), and the assembled modeling file
`apex_prop_rows_v1.csv` does not retain raw `bpSaved`/`bpFaced` (only
the derived `holds`/`breaks` counts survive there).

A final, broader search (scanning every CSV in the project for a
`bpSaved`-style header) found the real source before that wrong
conclusion was delivered: a directory named **`ATP & WTA, 1968-2026`**
(with a duplicate/mirror copy at `tml-data/`), containing per-year ATP
and WTA main-tour, challenger, and qualifying match files from 1968
through 2026, each with genuine per-match `w_bpSaved`, `w_bpFaced`,
`l_bpSaved`, `l_bpFaced` columns — confirmed populated (96.4% coverage
in a spot-check of 2021 ATP main-tour matches). This is in fact the
exact directory the frozen model already reads by default
(`--sackmann-dir` defaults to `"ATP & WTA, 1968-2026"`, see
`apex_prop_model_v1.py` line 1076) — the raw historical BPS signal was
never missing from disk, only missing from the pre-built rows CSV.
This correction is what made a real Phase 3–5 fit/tune/holdout
possible at all.


## Phase 1 — Feature design (which projections should BPS influence?)

Evidence, not assumption, from the frozen code itself
(`apex_prop_model_v1.py`, read-only):

```
w_holds  = w_SvGms - (w_bpFaced - w_bpSaved)      # winner's own hold count
l_breaks = w_bpFaced - w_bpSaved                  # loser breaks winner via winner's bpSaved
```

BPS% is arithmetically embedded in **both** sides of a match at once:
a player's own BPS% mechanically determines their own **hold**
projection, and by the same equation it simultaneously determines
their **opponent's break** projection (mirror image). It has no direct
arithmetic path to Games Won or Match Winner except through hold/break,
which are themselves already downstream of BPS in the current
architecture (via the derived `w_holds`/`l_breaks` counts, not via
BPS% as a standalone feature).

**Conclusion: multiple categories — specifically Hold projections
(direct, own side) and Break projections (mirror image, opponent's
side) — not Games Won or Match Winner directly.** The test below uses
the direct channel (own hold-rate prediction); the mirror-image break
channel follows the identical math and is not separately re-tested.

## Phase 2 — Build BPS_V1

- **Formula**: for each player, at each (Window W, Shrink K) grid
  point already used in production (`W ∈ {20,40,80}`, `K ∈ {5,15,40}`),
  `bps_rate = shrinkage_blend(surface-specific trailing BPS%, all-surface
  trailing BPS%, shrink=K)`, using the **identical** trailing-window /
  surface-blend / shrinkage mechanism already governing
  `hold_rate`/`break_rate`/`ace_rate`/`df_rate` (`rate_bundle()` in the
  frozen model) — cloned into a new, separate function
  (`rate_bundle2()` in `apex_bps_v1_build.py`) rather than editing the
  frozen file.
- **Inputs**: trailing `bpSaved`/`bpFaced` counts only, from matches
  strictly before the match being predicted (no leakage by
  construction — computed inside a chronological replay, features
  read from player history *before* that match's own stats are
  appended to it).
- **A second, genuinely distinct baseline feature was also built**:
  `bp_conv_rate` ("break points scored" — BP won per BP faced while
  *returning*), which is not the same quantity as `break_rate` (breaks
  per return *game*). This gives the three named baselines (hold
  rate, break rate, break points scored) as three real, separately
  computed features, not two of them collapsing into the same number.
- **No scaling applied**: all rates are already bounded in [0,1] by
  construction, matching the convention of the existing rolling
  features.
- **Primary spec used for testing**: W=40, K=15 (a mid-grid point,
  already load-bearing elsewhere in production as `*_W40_K15_*`). The
  full 3×3 grid is computed and stored in `apex_bps_v1_rows.csv` for
  future extension; only one grid point was carried through the
  fit/tune/holdout to keep the test tractable.
- **Source**: `apex_bps_v1_build.py` replayed 122,373 real historical
  main-tour matches (2005-01-03 through 2026-09-21, ATP+WTA, no
  challengers/qualifying) from `ATP & WTA, 1968-2026/`, producing
  `apex_bps_v1_rows.csv` (164 columns).


## Phase 3 — FIT (year ≤ 2021)

Target: `actual_hold_rate` (this player's true fraction of service
games held, that match — computed post-hoc from real `bpSaved`/
`bpFaced`/`SvGms`, not modeled). n = 119,337 player-observations.

| Model | R² | MAE | MSE |
|---|---|---|---|
| BASE (hold_rate, break_rate, bp_conv_rate) | 0.15845 | 0.14155 | 0.03284 |
| FULL (BASE + bps_rate) | 0.15848 | 0.14154 | 0.03283 |

Δ R² from adding `bps_rate` = **+0.00003** (in-sample). FIT coefficients:
BASE `[int=0.205, hold=0.767, break=-0.138, bp_conv=-0.002]`; FULL adds
`bps_rate = -0.0244`. The candidate coefficient is small and, notably,
**negative** — the opposite sign naive intuition (higher trailing
BPS% → higher trailing hold_rate, positive correlation, r≈0.76) would
suggest, once hold_rate/break_rate/bp_conv_rate are already in the
model. This is the signature of a feature carrying no independent
information: what correlation it has with the target is already fully
explained by the other three predictors.

## Phase 4 — TUNE (2022–2023), stability check

n = 20,990. Refit (not applying FIT coefficients) to see how the
parameters move on fresh data:

- BASE coefficients: `[int=0.168, hold=0.817, break=-0.143, bp_conv=0.004]`
- FULL coefficients: `[int=0.159, hold=0.799, break=-0.143, bp_conv=0.003, bps_rate=+0.0365]`

**The `bps_rate` coefficient flips sign between FIT (−0.024) and TUNE
(+0.037)** — a swing larger than the coefficient's own magnitude in
either window. That is textbook parameter instability: the estimate
is not resolving a real, stable effect, it is bouncing around a true
value indistinguishable from zero.


## Phase 5 — HOLDOUT (2024+), frozen FIT-window coefficients

n = 29,608 player-observations (coverage = 93.7% of 2024+ matches had
full trailing history at W40/K15 on both sides). FIT-window
coefficients applied as-is (no peeking, no refitting on holdout):

| Model | R² | MAE | MSE (= Brier-style, target ∈ [0,1]) |
|---|---|---|---|
| BASE | 0.13821 | 0.14812 | 0.05304 |
| FULL (+ bps_rate) | 0.13819 | 0.14813 | 0.05305 |

FULL is **marginally worse** than BASE on every metric out-of-sample
(Δ R² = −0.00002, Δ MAE = −0.000006, i.e. MAE goes up not down).

**Calibration** (10 equal-count bins, mean predicted vs. mean actual
hold_rate) is visually and numerically indistinguishable between BASE
and FULL — e.g. bin 5: BASE pred 0.7189/actual 0.7190 vs. FULL pred
0.7188/actual 0.7184; bin 9: BASE pred 0.8157/actual 0.8254 vs. FULL
pred 0.8156/actual 0.8255. Adding `bps_rate` changes calibration by
less than 0.001 in every bin — no meaningful improvement, in either
direction.

## Phase 6 — Root-cause check (not correlation-only)

- Trailing `bps_rate` vs. trailing `hold_rate` correlation: **0.759**
  (winner side, n=92,292), **0.719** (loser side, n=90,064) — real,
  substantial, but far from collinear duplication (leaves ~42-45% of
  `bps_rate`'s variance genuinely independent of `hold_rate`).
- Despite that independent variance, incremental in-sample R² = 0.00003
  and incremental out-of-sample R² = **−0.00002** (negative).
- Conclusion: BPS% is correlated with hold-rate outcomes only because
  it is correlated with hold_rate itself (both are trailing summaries
  of the same underlying serve-hold ability) — not because it carries
  additional signal about *future* holds beyond what hold_rate,
  break_rate, and break-points-scored-rate already capture. This
  matches and substantially strengthens the earlier, small-sample
  (n=38) SA365 finding (R²=0.046, same direction) with a real,
  22-year, 169,935-observation historical test.


## Phase 7 — Implementation review

**Holdout did not pass. BPS_V1 is NOT recommended for promotion.**
Per your own stated Success Criteria, a pass requires all five; it
fails at least three outright:

| # | Criterion | Result |
|---|---|---|
| 1 | Real holdout improvement | **FAIL** — MAE/R² both marginally worse out-of-sample |
| 2 | Stable coefficients | **FAIL** — sign flips FIT→TUNE, drift exceeds coefficient magnitude |
| 3 | No future leakage | PASS — trailing/pre-match only, by construction |
| 4 | Better calibration than production | FAIL — indistinguishable from baseline, not better |
| 5 | Clear incremental value beyond hold/break/BP-scored | **FAIL** — Δ R² ≈ 0, negative out-of-sample |

Because the holdout failed, there is no production implementation to
review: no file changes, no lines to touch in `apex_prop_model_v1.py`
or `apex_prop_sim_v1.py`, no rollback plan needed since nothing was
deployed. Files created this task (`apex_bps_v1_build.py`,
`apex_bps_v1_fit_tune_holdout.py`, `apex_bps_v1_rows.csv`,
`apex_bps_v1_build.log`, `apex_bps_v1_fit_tune_holdout.log`, this
report) are all new, additive, and outside the production code path —
none of them are read by `apex_prop_model_v1.py`/`apex_prop_sim_v1.py`.

**What would justify revisiting this**: a different, non-collinear
operationalization of BPS (e.g. break-point-count *volume* per match
rather than a rate, or BPS% conditioned on score-state/pressure
situations not captured by hold_rate) might carry independent signal
that a simple trailing rate does not. That is a new hypothesis, not
this one, and was not tested here.

## What this does not claim

No change to Apex's live rankings, probabilities, or settlement logic
was made or is recommended. No production file was modified (MD5s
verified identical throughout). This is a single, real, evidence-based
test of one specific formulation of BPS% as a trailing feature — it
returned a clean negative result, which is itself the deliverable.
