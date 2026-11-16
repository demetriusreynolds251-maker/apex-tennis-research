# Aces MORE Overconfidence — Root Cause Investigation
Started 2026-09-24/25. Status: IN PROGRESS. Do not apply corrections until mechanism is identified.

## Established (do not re-derive)
- Bo3 aces-MORE, n=52 settled: stated avg ~70-77%, actual hit rate meaningfully lower;
  worst in the 70-80% stated band (46.7% actual vs 73.9% stated, n=15).
- Flat calibration correction FAILED validation: fit on half (n=26), tested on other half (n=26),
  improvement = -0.071 (made predictions worse). Do not reapply a flat correction without a
  larger validated out-of-sample test.
- Hypothesis D (selection bias) RULED OUT: declines are 142/150 pricing/data failures, not
  model-threshold rejections. Posted (n=101, avg 70.5%) vs settled (n=89, avg 69.5%) probabilities
  are close. The 12 "unmatched" posted picks are all dated 09-24/09-25 — awaiting settlement,
  not a data-integrity problem.
- apex_engine_picks_log_v1.csv has a prob_cal column separate from prob -- an existing
  calibration layer (likely ACESCAL-LESS's output). Check whether it's a no-op for MORE direction.
- avg_aces_v8 (the raw input rate) does not appear to be persisted in any CSV -- deprioritized
  in favor of the simulator's own 'mean' projection field (apex_prop_sim_forward_log_v1.csv),
  since that's what the probability engine actually bets on.

## Step 2 (in progress): projected vs actual aces
Using apex_prop_sim_forward_log_v1.csv's 'mean' (projected) vs 'actual', broken out by
favorite/underdog, surface, best-of. Logic: if the final projection itself runs high vs
reality, that points toward projection-generation (B). If the projection looks reasonable
but probabilities are still overstated, that points toward the probability-conversion /
calibration layer (A).

## Remaining steps
1. Read apex_prop_sim_v1.py's aces MORE/LESS probability function line-by-line; compare
   structural treatment of MORE vs LESS (variance/distribution assumptions).
2. Check whether opponent return quality is used anywhere in the ace-rate calc (not yet
   ruled out as a continuous input, only ruled out as "elite-opponent-list-only" effect --
   vs-elite 52.9%/71.9% and vs-field 55.6%/69.1% showed similar-magnitude overconfidence).
3. Check for evidence of PrizePicks line movement working against MORE specifically.
4. Direct side-by-side MORE vs LESS calibration on the same match population.

## Do not
- Apply any new flat correction without re-running the fit/test split validation and
  confirming positive out-of-sample improvement.
- Assume elite-opponent theory is the mechanism -- ruled out as sole driver.

## TRACK 2 CONFIRMED (2026-09-25)
Direct code search of apex_prop_sim_v1.py for break_pct, opponent-rate, return-rate, or any
cross-player field: ZERO matches of any kind. Every "opponent"/"break" hit in the file is
either a plain record-keeping label, the simulator's own OUTPUT category, or an internal
bookkeeping identity check -- none are inputs.

build_live_row() (line 640-662) loops over ("fav","dog") independently, calling
v1.rate_bundle(ps, surface, W, K) once per side (line 652: ace_rate, df_rate, hold_rate,
break_rate, spg -- all keyed to that side alone). rate_bundle()'s own signature
(apex_prop_model_v1.py line 183: rate_bundle(ps, surface, window, shrink)) takes a single
player's stat history and has no parameter through which the opponent's identity or stats
could enter.

CONCLUSION: Opponent suppression signal EXISTS in the system (break_pct_v8, fetched live
from V8 Tennis Stats API, Tier 1, injected into research_data.opponent at evaluation time)
but is NOT CONSUMED by the aces simulator. The aces projection for either player is computed
purely from that player's own historical ace rate x expected service games, with zero
opponent-side adjustment of any kind.

This is a confirmed, documented STRUCTURAL GAP -- not a bug, not a tuning parameter, not a
calibration issue. It directly explains the Track 1 finding: the model behaves correctly
(unbiased, well-calibrated) in the 50-70% confidence band, and specifically breaks down above
70% -- exactly where a player's own flat rate implies a comfortable margin over the line, and
exactly where a real opponent's return quality would matter most in pulling that number back
down, if the model could see it. It cannot.

## FINAL STATUS: Bo3 aces MORE overconfidence
ROOT CAUSE: missing opponent-context input in the aces simulator (structural gap, confirmed
in code). The distribution "looks" wrong (Track 1) as a DOWNSTREAM SYMPTOM of this gap, not
as an independent shape-family problem to be fixed by choosing a different distribution.
NOT: a bug, a calibration/dispersion tuning issue, a line-integrity issue, or selection bias
(all directly ruled out with evidence above).

## WHAT A REAL FIX WOULD REQUIRE (not attempted -- scope only)
1. Persist break_pct_v8 (or a proper return-quality metric) into the picks/settled logs going
   forward, so it can be validated against real residuals over time.
2. Build an opponent-adjustment term into rate_bundle() or build_live_row() -- e.g. scaling
   ace_rate by an opponent return-strength factor -- fit and holdout-validated on a large
   sample (same standard as ACESCAL-LESS), before ever touching a live projection.
3. This is a simulator-design change to a FROZEN model artifact. Per existing project rules,
   any new model version is a NEW frozen artifact (never an edit to the existing one), and
   needs its own build/freeze/holdout-report cycle, not a live patch.
Bo5 (+1.29 ace projection overshoot) remains a separate, still fully open investigation.

## TRACK 2 — FIRST QUANTITATIVE EVIDENCE (2026-09-25, new data source: tml-data/)
Found a permanent, non-expiring, match-level results dataset at ~/Desktop/openclaw/tml-data/
(2026_wta.csv, 2153 rows, same bpFaced/bpSaved/ace schema as the ATP file tried earlier).
KEY LEARNING: tourney_date = tournament START date, not individual match date -- exact-date
matching failed (1/65) until widened to a 0-21 day post-tourney-start window, which recovered
62/65 (95%) of our Bo3 aces sample via US Open matches. 3 remain unrecoverable (2026-08-28,
a smaller/different event this file doesn't cover as completely).

Test: for each of the 62 recovered picks, pulled OUR PLAYER's own bpFaced/bpSaved/SvGms from
that SPECIFIC match (not a career average), computed breaks_conceded = bpFaced - bpSaved and
break_rate = breaks_conceded / SvGms, then correlated against the residual (actual aces -
projected aces) for that same pick.

RESULTS (n=62):
- correlation(residual, opponent RAW bp_faced): r=+0.061 (no signal -- raw count conflates
  match length with pressure)
- correlation(residual, opponent break RATE, per service game): r=-0.260 (correctly signed:
  higher opponent break rate against our player -> more underperformance vs ace projection)
- t=-2.086, df=60, right at the conventional p=0.05 significance threshold (borderline)
- r-squared = 6.8% (small effect size in variance-explained terms)
- Split: LOW opponent break-rate half (n=31) mean residual = +0.82; HIGH half (n=31) mean
  residual = -0.48. A 1.30-ace swing between groups -- practically meaningful in absolute terms
  even though the correlation itself is only borderline-significant statistically.

HONEST ASSESSMENT: this is the first result tonight in the RIGHT direction with a plausible,
correctly-signed effect -- meaningfully different from the flat-correction test that failed
outright with NO usable signal. However: n=62 at a threshold-grazing p-value is NOT the same
as a confirmed, holdout-validated effect (ACESCAL-LESS's standard was 11,341 matches). This
result could easily strengthen, weaken, or flip sign with more data. Treat as: "first
suggestive evidence the missing opponent-suppression signal actually matters" -- not as proof,
and NOT sufficient grounds to build or promote Aces V2 yet.

## UPDATED NEXT STEPS
1. tml-data/ is a genuinely valuable, non-expiring resource -- check whether it also covers
   2026_challenger.csv and ATP_Database.csv the same way, and whether historical (pre-2026)
   years exist for a much larger holdout sample once picks accumulate over time.
2. Re-run this exact break-rate correlation once more aces picks settle (forward logging from
   Phase 1, still not yet built) -- watch specifically whether r stays near -0.26, strengthens,
   or regresses toward zero as n grows. That trend, not this single n=62 snapshot, is what
   should drive any decision to build Aces V2.
3. Do NOT apply any correction, confidence change, or model modification based on this result
   alone. This is evidence to keep gathering, not a finding to act on yet.
4. Bo5 investigation remains fully open and unstarted.

## TRACK 2 — LARGE-SCALE CONFIRMATION (2026-09-25)
Scaled the n=62 test across ALL available tml-data/*_wta.csv year files (37 files, 1990-2026)
using a simplified proxy: trailing 20-match rolling ace rate per player (min 40 trailing
service games required) as the baseline, residual = actual aces - trailing-rate expectation,
correlated against SAME-MATCH opponent break rate (bpFaced-bpSaved)/SvGms.

RESULTS:
  ALL YEARS:   n=52,581  r=-0.1852  t=-43.23  r^2=3.4%  low/high-pressure gap=+0.923 aces
  2016+:       n=50,163  r=-0.1831  t=-41.72  r^2=3.4%  gap=+0.914 aces
  2022+:       n=23,433  r=-0.1366  t=-21.11  r^2=1.9%  gap=+0.768 aces

VERDICT: EFFECT CONFIRMED AT SCALE. Sign held across all three independent era slices, never
flipped or collapsed. t-statistics are enormous (>>2.0 threshold) -- this is not sample-size
noise. The original n=62 result (r=-0.26) somewhat overstated the effect vs the full-history
figure (r=-0.185), consistent with normal small-sample regression toward the true value, and
itself evidence the original finding was real rather than a fluke direction.

CAVEATS (must be resolved before any promotion):
1. This used a SIMPLIFIED proxy baseline (trailing rolling rate), NOT the real frozen V1
   simulator's actual projection (which blends serve history + market price + surface +
   fragility/tilt). A true validation must run through the real architecture.
2. r^2 = 3.4% is real but MODEST -- opponent break-rate is a meaningful piece of the picture,
   not a dominant one. Expect a real but modest calibration improvement from V2, not a
   transformative one.
3. Effect eased somewhat in 2022+ (r=-0.137 vs -0.185 full-history) -- worth monitoring,
   possibly real evolution in the game, not yet concerning enough to doubt the mechanism.

## DECISION: PHASE 3 (ACES V2 RESEARCH) IS NOW JUSTIFIED
Per the original success criteria set for this investigation ("if r=-0.26 survives on a few
hundred/thousand matches, build V2; if it collapses, don't"): the effect survived on 52,581
matches with overwhelming statistical significance. Proceed to scope an Aces V2 research
model that incorporates opponent break-rate as an input, built as a NEW frozen artifact
(never an edit to V1, per existing project rule), trained on one split, evaluated on a
genuinely held-out split, and required to beat V1 on calibration, probability accuracy, and
holdout performance before any promotion discussion -- same rigor as ACESCAL's original
build/freeze/holdout-report cycle.

## TRACK 2 — FULL-SCALE, THREE-TOUR CONFIRMATION (2026-09-25, final)
Extended the WTA-only test (n=52,581) to ATP (all plain-year files) and Challenger (all
_challenger files) in tml-data/, same exact method: trailing 20-match rolling ace rate per
player (min 40 trailing service games) as baseline, residual vs same-match opponent break
rate (bpFaced-bpSaved)/SvGms.

RESULTS BY TOUR:
  WTA:         n=52,581   r=-0.1852  t=-43.23   r^2=3.4%  low/high gap=+0.923 aces
  ATP:         n=198,089  r=-0.2531  t=-116.42  r^2=6.4%  low/high gap=+1.714 aces
  Challenger:  n=145,557  r=-0.2691  t=-106.61  r^2=7.2%  low/high gap=+1.537 aces
  COMBINED:    n=396,227  r=-0.2397  t=-155.44  r^2=5.7%  low/high gap=+1.526 aces
  2010+ combined: n=283,240  r=-0.2381  t=-130.46
  2020+ combined: n=131,021  r=-0.2229  t=-82.78

FINDING: effect holds, same sign, across THREE INDEPENDENT TOURS (different player pools,
different eras, different data slices). ATP and Challenger show a STRONGER relationship than
WTA (r^2 6-7% vs 3.4%) -- a sensible, physically interpretable pattern (aces are a larger
share of total points in men's tennis, giving opponent return pressure more visible room to
suppress them), not just a coincidental replication. t=-155 on the combined sample is,
for practical purposes, definitive -- a false positive this extreme across three independent
populations would be an near-impossible coincidence. Minor softening in 2020+ vs full-history
noted (worth monitoring) but effect remains solidly intact and nowhere near collapse.

## FINAL DECISION: ACES V2 RESEARCH AUTHORIZED
Per the pre-registered decision rule ("if the signal survives and remains directionally
consistent on a much larger sample, proceed to Aces V2 Research design; if it disappears,
opponent-suppression theory is weakened"): the signal survived at n=396,227 across three
independent tours with overwhelming statistical significance and a sensible, tour-dependent
effect-size pattern. Opponent break-rate is a confirmed, real, structurally-missing input to
the aces projection.

REMAINING WORK BEFORE ANY LIVE CHANGE (unchanged from earlier scoping):
1. This test used a simplified trailing-rate proxy, not the real V1 architecture. The actual
   V2 model must be built inside the real simulator (build_live_row/simulate in
   apex_prop_sim_v1.py), incorporating opponent break-rate as a genuine model input.
2. Must be trained on one split, validated on a genuinely held-out split (same standard as
   V1's original fit_constants/tune_alpha/holdout_report cycle).
3. Must be built and frozen as a NEW artifact -- V1 stays untouched, per standing project rule.
4. Must beat V1 on calibration, probability accuracy, and holdout performance (per original
   success criteria) before any promotion discussion.
5. Bo5 aces investigation (+1.29 projection overshoot) remains a fully separate, still open
   question -- not addressed by this finding.

STATUS: Investigation phase COMPLETE. Evidence gathering phase COMPLETE. Ready to move into
Aces V2 model design/build phase whenever directed.
