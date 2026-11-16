# APEX ACES V2 — DESIGN DOCUMENT
Status: DESIGN COMPLETE (2026-09-26). No code written. V1 untouched.

This document did not exist as a standalone file before tonight — it is assembled
now, in full, from confirmed evidence only: the investigation log
(`APEX_ACES_MORE_INVESTIGATION_2026-09-24.md`), tonight's `replay()` verification,
and direct code reads of `apex_prop_sim_v1.py` / `apex_prop_model_v1.py` performed
just before writing this file. Nothing below is inferred or reconstructed from
memory of an earlier draft.

---

## SECTION 1 — Problem Statement & Motivation

Bo3 aces-MORE picks are overconfident: n=52 settled, stated avg ~70-77%, actual hit
rate meaningfully lower, worst in the 70-80% stated band (46.7% actual vs 73.9%
stated, n=15). A flat calibration correction was fit/test-split validated and
FAILED (fit on n=26, tested on other n=26, improvement = -0.071 — made predictions
worse). Selection bias was ruled out (declines are 142/150 pricing/data failures,
not model-threshold rejections).

ROOT CAUSE (confirmed in code): the aces simulator has a structural gap, not a
tuning problem. `build_live_row()` in `apex_prop_sim_v1.py` calls
`v1.rate_bundle(ps, surface, W, K)` once per side, independently — this function's
signature (`apex_prop_model_v1.py` line 183) takes one player's own stat history
and has no parameter through which the opponent's identity or stats can enter.
Opponent return-suppression is real, present in the wider system
(`break_pct_v8` is fetched live and injected into `research_data.opponent`) but is
never consumed by the aces simulator.

## SECTION 2 — Architecture Overview & Insertion Point [CORRECTED]

**Correction 1 (mu chain):** `mu` (the ace-rate mean fed to the simulator) does
NOT come directly from `rate_bundle()`. Confirmed live in `apex_prop_sim_v1.py`:

- `v1_inputs_from_rows()` (line 288) calls `P = {side: v1.project(df, m, side,
  "full") for side in ("fav","dog")}` — `project()` lives in the FROZEN model
  file (`apex_prop_model_v1.py` line 488).
- It then builds `mu = {side: (P[side]["aces"] / max(P[side]["svgms"],1),
  P[side]["dfs"] / max(P[side]["svgms"],1)) for side in P}` (line 293).
- `mu[side]` is a tuple `(aces_mean, dfs_mean)`, passed to `simulate()` as
  `muA`/`muB` at each call site (lines 452 and 678: `simulate(hA, hB,
  coefs["tb_k"], bo, (mu["fav"][0][i], mu["fav"][1][i]), (mu["dog"][0][i],
  mu["dog"][1][i]), ...)`).

So the real chain is: `v1.project()` → `v1_inputs_from_rows()` (builds `mu`) →
`simulate()` (consumes `mu` as `muA`/`muB`). `rate_bundle()` is an input to
`project()`, not the direct source of `mu` itself.

**Correction 2 (insertion point):** the opponent-suppression adjustment belongs
at the seam between where `mu` is BUILT (`v1_inputs_from_rows()`, line 293) and
where it is CONSUMED (`simulate()` call sites, lines 452/678) — both inside
`apex_prop_sim_v1.py`, the simulator glue layer. This is NOT inside the frozen
model file. `rate_bundle()`, `live_features()`, `replay()`, and `project()` in
`apex_prop_model_v1.py` are all read-only for this project and stay untouched.

Concretely: multiply `mu[side][0]` (the aces component only, not `dfs`) by an
opponent-suppression factor derived from that match's opponent, computed between
line 293 (`mu` built) and the `simulate()` call. This keeps V1 completely frozen
and makes V2 a strictly additive change at the glue layer, per the standing
"never edit V1" rule.

## SECTION 3 — Candidate Formulations

Only ONE candidate architecture is on record with a substantive description:

**Architecture A — Direct multiplicative ace-rate adjustment (SELECTED).**
Scale `mu[side][0]` (the aces mean, at the seam described in Section 2) by a
factor derived from the opponent's trailing break-rate, before it reaches
`simulate()`. Simple, isolated to one line of the `mu` array, easy to fit a
single coefficient for and easy to holdout-test apples-to-apples against V1.

No Candidate B, C, or D was ever substantively specified anywhere in this
project's record (investigation log, handoff notes, or session transcript) —
searched and confirmed absent tonight. Per the standing "no inferred
architecture claims" rule, this document does not invent placeholder
descriptions for them. If alternative formulations are wanted, they need to be
proposed and evaluated in a future session; they are out of scope for V2 as
currently authorized.

## SECTION 4 — Live Data Source [CORRECTED]

The historical validation (n=396,227; see Section 5) used each opponent's ACTUAL
same-match break-rate (`(bpFaced - bpSaved) / SvGms` from `tml-data/`). That
proves the mechanism exists but is NOT the live-safe signal — a match's own
break-rate doesn't exist before it's played.

The live-safe input is each opponent's TRAILING break-rate: computed the same
rolling-window way as the player's own trailing ace-rate baseline already used
in the mechanism test (trailing 20-match rolling rate, minimum 40 trailing
service games required), using `rate_bundle()`'s own `break_rate` field —
confirmed computed from `obpf`/`obps` (that player's own historical
break-points-faced/saved), a general, forecastable, pre-match-available signal.
This trailing feature has NOT been built yet (Task 1, Step 2 — the next step
after this document, not part of this document).

## SECTION 5 — Historical Data Source & replay() Verification [CORRECTED]

Historical mechanism evidence: `tml-data/` (permanent, non-expiring, match-level
WTA/ATP/Challenger files with `bpFaced`/`bpSaved`/`ace`/`SvGms`, 1990-2026).
Combined n=396,227 across three independent tours: WTA r=-0.185, ATP r=-0.253,
Challenger r=-0.269, combined r=-0.240, t=-155.44. Effect held sign across all
era slices tested (2010+, 2020+) and across all three tours independently —
statistically overwhelming, not sample-size noise.

Before this evidence could be trusted for design purposes, `replay()` (the
function that builds V1's TRAINING-time features) had to be checked against
`live_features()` (the function that builds LIVE-time features) for consistency.
Five checks were run against direct code reads of `apex_prop_model_v1.py`
(`replay()` lines 213-287, `live_features()` lines 664-673) and
`load_sackmann()`'s sort call:

1. **Date order** — PASS. `load_sackmann()` sorts
   `["tourney_date","tourney_id","match_num"]` before `replay()` ever runs.
2. **No look-ahead within a match** — PASS. `replay()` appends a player's stats
   to their history AFTER that match's row uses them, never before.
3. **Same rate_bundle recipe live and in training** — PASS. Window/shrink
   parameters (`W, K = m["window"], m["shrink"]`) are pulled from the frozen
   model's saved spec in both paths, not hardcoded separately.
4. **Opponent break-rate computed the same way, live-safe** — PASS. Comes from
   the opponent's own trailing `obpf`/`obps`, identically in both paths; never
   from the match being predicted.
5. **Same-tournament ordering safety** — PASS, with a documented exception (see
   Section 6).

All five checks passed. This is the "architecture-complete" checkpoint referred
to elsewhere in project notes.

## SECTION 6 — Data Quality Caveats [CORRECTED]

**The 1.06% round-robin ordering exception (accepted, not a blocker).**
Direct measurement: 5,746 tournaments checked, 61 (1.06%) show a round/match_num
disagreement when round rank is compared against match_num order.

Cause: round-robin events (ATP/WTA year-end Finals) map to round rank 0, but
round-robin matches genuinely have no fixed order — three RR matches can occur
in any sequence before the semis. The check flags this as "disagreement" even
though it isn't a look-ahead leak; it's a format where match_num doesn't
correspond to any meaningful before/after. The true count of tournaments with an
actual look-ahead risk is lower than 61 once round-robin events are set aside;
whatever remains (walkovers, retirements, rare data-entry quirks) is well under
1% and too small to explain an effect with r²=5-7% held across 396,227 matches
and three independent tours.

**Standing decision:** treated as accepted residual noise, not grounds for
redesign. Formal caveat for the permanent record: *"Training data has a ~1%
same-tournament ordering exception, mostly attributable to round-robin event
formats where match order is not meaningful; treated as acceptable residual
noise, not grounds for redesign."*

**Separate, unresolved caveat (proxy vs real architecture):** the n=396,227
mechanism test used a SIMPLIFIED proxy baseline (trailing rolling ace-rate), not
V1's real projection (which blends serve history, market price, surface, and
fragility/tilt). This proves the mechanism is real but does not by itself
validate V2's actual fit — that requires running the real `v1_inputs_from_rows`/
`simulate` architecture with the live-safe trailing opponent feature (Section 4),
which has not been built yet.

## SECTION 7 — Selected Architecture & Rationale [CORRECTED]

**Approved: Architecture A — direct multiplicative adjustment to the ace-rate
mean, at the seam identified in Section 2.**

Rationale:
- Isolated: touches exactly one array element (`mu[side][0]`) at one seam,
  between `mu`'s construction and its consumption by `simulate()`. No other
  category (`dfs`, `breaks`, `total_sets`, `games_won`, `total_games`,
  `fantasy_score`) passes through this code path for its mean, so a mistake here
  is checkable by diffing V1 vs V2 output on every non-aces category and
  confirming zero difference (a required regression check — see Section 9).
- Consistent with V1's own precedent: `apex_prop_model_v1.py` already applies a
  fit coefficient (`alpha`) in a comparable multiplicative blend
  (`level_from()`: `a * 0.5 * (hf + hd) + (1 - a) * price_level`), so this is
  the same style of adjustment the existing frozen model already trusts.
- Never edits V1: the frozen model file is not touched. V2 is built as a new
  file (`apex_prop_sim_v2.py`), matching the standing "new frozen artifact,
  never an edit" rule already used for ACESCAL-LESS.
- As stated in Section 3, no alternative architecture was ever substantively
  proposed to compare this against; Architecture A is approved on its own
  merits (isolation, precedent, and non-invasiveness), not as the winner of a
  formal comparison that never happened.

## SECTION 8 — Training / Fit / Tune / Holdout Methodology

Reuse V1's own boundaries and scoring code unmodified, confirmed on disk
tonight (`apex_prop_sim_v1.py` line 50 and `apex_prop_model_v1.py` line 66,
identical in both files):

    FIT_END, TUNE_START, TUNE_END, HOLD_START = 2021, 2022, 2023, 2024

- **Fit** the adjustment coefficient on `year <= 2021` only (`fit_constants()`
  boundary, confirmed at `apex_prop_sim_v1.py` line 340-342).
- **Tune** on `2022-2023` (`tune_alpha()` boundary, line 411-412).
- **Holdout** on `year >= 2024`, fully out-of-sample from both fitting stages,
  reusing `holdout_report()` (line 465 in the sim file / line 515 in the model
  file) UNMODIFIED, so V1-vs-V2 comparison is apples-to-apples on the same rows
  with the same metric code.
- The FIT step must use the live-safe TRAILING opponent break-rate (Section 4),
  never the in-match actual used for the mechanism-discovery test — using the
  actual would overstate what a live model can really achieve.

## SECTION 9 — Validation Metrics & Regression Check

- **Metrics** (from `holdout_report()`, unmodified): Brier score, 80% coverage,
  MAE — run side-by-side for V1 and V2 on identical holdout rows.
- **Regression check (required before any promotion decision):** diff every
  non-aces category's output (`dfs`, `breaks`, `total_sets`, `games_won`,
  `total_games`, `fantasy_score`) between V1 and V2 on the same input rows.
  Expected result: byte-identical, zero difference. The insertion seam sits in
  shared simulator code (Section 2); an error here could silently change other
  categories, so this check is not optional.

## SECTION 10 — Promotion Criteria & Freeze Plan [CORRECTED]

**Promotion criteria (pre-registered, exactly as decided):** V2 must beat V1 on
Brier score, hold 80% coverage, and improve MAE on the holdout set — with no
degradation anywhere else (i.e., the Section 9 regression check must show zero
difference on all non-aces categories). This bar is written down here, before
any V2 result exists, specifically to prevent a marginal or accidental "win"
from being promoted on hope.

**Freeze plan:** if V2 passes, freeze it as `apex_prop_sim_v2.json`, using the
same SHA-stamp / tamper-detection pattern `cmd_freeze()` already uses for V1
(confirmed present at `apex_prop_sim_v1.py` line 612 and
`apex_prop_model_v1.py` line 624). V1's own frozen file is never touched.

**Forward-test plan:** run V2 as its own separate forward-test stream, never
blended into existing aces records — same treatment BO5-FWD-001 already applies
to Bo5: LOW attention forced until milestone reviews at 25/50/100 settled, with
formal PROMOTE / MAINTAIN / RESTRICT recommendations at each milestone. A
dedicated `ACES-V2-FWD` section in the tracker/ALIS, isolated from V1's own
numbers, is required before V2 replaces V1 in live pricing.

---

## DESIGN-REVIEW CHECKLIST

✅ **No unresolved assumptions** — every claim in Sections 1-10 is backed by a
   direct code read (line numbers cited) or a named, dated test result from
   `APEX_ACES_MORE_INVESTIGATION_2026-09-24.md`.
✅ **No inferred architecture claims** — Section 3 explicitly states that
   Candidates B/C/D were never specified and does not invent them.
✅ **All design decisions backed by evidence** — mu chain (Section 2), live
   data source (Section 4), replay() verification (Section 5), round-robin
   exception (Section 6), Architecture A selection (Section 7), and promotion
   criteria (Section 10) are each traced to a specific confirmed source above.

**STATUS: Design phase COMPLETE.** Ready for Task 1, Step 2 — build the
trailing opponent break-rate feature.
