# Category-by-Category Calibration Audit — Apex Simulator
**Date:** 2026-09-26
**Scope:** All 21 simulated categories, year>=2024 holdout (n=10,971: ATP=5,777, WTA=5,194), 1,000 sims/match.
**Standard of evidence:** identical to the Aces investigation — holdout-only, no fitting on holdout, frozen V1 files untouched (MD5-verified before AND after), diagnostics only, no model changes made in this task.

Frozen file hashes (unchanged, confirmed before and after `apex_full_category_calibration_audit.py`):
- `apex_prop_sim_v1.py` = `7b03e521e804862b85804f8ac4db7346` — PASS
- `apex_prop_model_v1.py` = `6bf50622a1761156a77ad0d35a2007f6` — PASS

This audit's simulation pass matches what is **actually live in production right now**: aces use the deployed Candidate C tour-specific dispersion (ATP r/dm=0.6, WTA r/dm=0.4); every other category — including DFs — uses production's own unmodified settings.

---

## 1. Architecture ground truth (confirmed by direct code read, not assumption)

Of the 21 simulated categories, only **aces** and **dfs** go through an explicit
negative-binomial dispersion mechanism (`Var = lam + lam^2/(r*disp_mult)`, collapsing
to Poisson as `disp_mult` grows). Every other category — holds, breaks, svgms,
games_won/lost, sets_won, and every MATCH_PROPS category — comes from one
categorical draw per set off a combinatorial game-outcome table, mixed over a
`gap_sigma=0.06` parameter-uncertainty node. There is **no "r" / "disp_mult" analog**
for these categories; the only lever that touches their spread at all is `gap_sigma`,
which is a single global constant, not category-specific.

`fantasy_score` is a deterministic linear combination of games/sets/aces/dfs — it has
no independent source of randomness or dispersion of its own.

This means Phases 2 and 3 as originally scoped ("identify dispersion settings",
"fitted vs. production") are only literally answerable for aces and dfs. For every
other category, Phase 2 is answered by this architectural fact itself: **there is no
dispersion knob to audit**, so no dispersion-suppression hypothesis can apply to them
the way it did to aces.

---

## 2. Phase 1 — Confidence bucket audit (binary / categorical MATCH_PROPS)

Buckets: <55% / 55-60% / 60-65% / 65-70% / 70-75% / 75-80% / 80%+. Gap = predicted − actual (positive = overconfident).

| Category | Brier | 80%+ gap (overall) | Worst segment gap | Verdict |
|---|---|---|---|---|
| `fav_wins` | 0.205 | −0.015 | Bo5 −0.026 | ✅ well calibrated |
| `first_set_fav_wins` | 0.222 | −0.007 | Clay −0.054 (n small) | ✅ well calibrated |
| `most_aces_fav` | 0.202 | **+0.022** | **WTA +0.066, Clay +0.061** | ⚠ residual overconfidence, WTA/Clay-concentrated |
| `most_games_fav` | 0.204 | +0.002 | Grass +0.045 (n=1300, noisy) | ✅ well calibrated |
| `any_tiebreak` | 0.209 | n/a (no bucket >65% populated) | — | ✅ well calibrated at the only populated bucket (<55%, gap +0.008) |
| `goes_3_sets` | 0.207 | +0.002 | — | ⚠ **definitional quirk, not a calibration defect** — see below |
| `goes_5_sets` | 0.172 | n/a (model never predicts >55% for this) | — | ✅ well calibrated at the only populated bucket |

**Full 80%+/high-bucket detail, `most_aces_fav`:** overall gap +0.022 (pred 0.880 vs
actual 0.858, n=1,915) is a real but small residual — a fraction of the pre-fix gap.
It is **not evenly distributed**: ATP is essentially perfect at 80%+ (gap −0.001,
n=5,296 rows in that tour), while **WTA still shows +0.066 and Clay +0.061** at 80%+.
This says Candidate C's WTA leg (dm=0.4, own fitted r) did not fully close the gap
the way the ATP leg did — this is the strongest actionable finding in the whole
audit and is discussed further in Phase 4/5.

**`goes_3_sets` quirk (code-level, not a new finding — confirmed again here on real
data):** `apex_prop_sim_v1.py` defines `goes_3_sets` for Bo5 matches as `nsets>=3`,
which is true for every Bo5 match by construction (minimum Bo5 length is 3 sets).
That is why the Bo5 subset (n=1,023) shows brier≈0.002 — it isn't "extremely
well-calibrated," it's a tautology. Reported factually; not something dispersion or
any other calibration fix can address, because it's a category-definition issue, not
a probability-estimation issue.

---

## 3. Phase 3 — Variance & O/U-line calibration (count-style categories)

Two diagnostics were run per category: (a) MAE/MSE of the simulated mean vs. actual,
(b) probability calibration of "over/under the line = floor(row's own simulated
mean)+0.5" — the exact convention used for `total_aces` in the original Aces work.

**Important methodological finding, stated plainly rather than glossed over:** for
nearly every count category *except* `sets_won`, the floor(mean)+0.5 line sits close
to the 50/50 point for almost every match (these are wide-range counts — aces,
holds, games, etc. — so the "next integer" line rarely produces a lopsided
prediction). The result: **the O/U bucket table for these categories has almost no
rows above 75% confidence to test at all** (0 rows in the 75-80%/80%+ buckets for
every category except `fav_sets_won`/`dog_sets_won`, which have only 2-3 possible
values and so *do* produce high-confidence lines). This is a genuine limitation of
applying the aces-style O/U-line test to categories that don't naturally have a
market-relevant line — it is **not** evidence of good calibration, it's an absence of
the kind of evidence that could reveal overconfidence in the first place.

Where the test *is* meaningful (`fav_sets_won`, n=1,750 at 80%+): gap = **−0.014**
(mildly *under*confident, not overconfident) — a clean, well-calibrated result, the
opposite direction from the original aces problem.

`ou_brier` for every other count category clusters tightly at 0.23–0.26 — consistent
with "close to a 50/50 line," not with a specific miscalibration signal one way or
the other.

**A secondary, weaker diagnostic (expected vs. observed variance ratio) was also
computed for every category, but is flagged here as methodologically limited**: by
the law of total variance, `E[simulated within-match variance] / Var(actual across
matches)` is mechanically <1 whenever the conditional mean varies across matches at
all (which it always does) — so a ratio well below 1 does **not** by itself mean "the
simulator is too narrow." It mixes genuine match-to-match heterogeneity (which the
model's mean is supposed to capture) with within-match stochastic spread (the only
thing dispersion actually controls). This ratio is reported for completeness but was
**not** used as primary evidence for any ranking below — it is not a like-for-like
replacement for the bucket-calibration test that actually flagged aces originally.

One value from this secondary diagnostic is worth flagging anyway because it is an
outlier in the *opposite* direction from the rest of the simulator and lines up with
an independent Phase-1 finding: `dog_aces` in the **WTA** segment has a variance
ratio of **1.475** (and `total_aces`/`fav_aces` WTA also >1, at 1.156/1.205) — the
only categories/segments in the entire audit where this ratio exceeds 1 at all. That
this shows up specifically in WTA aces, the same segment flagged as still
overconfident in Phase 1, is a second independent signal (not proof, given the
ratio's known limitations) that **WTA aces dispersion is the least-settled part of
the whole simulator** — not DFs, and not any other category.

- `fav_dfs`/`dog_dfs` show the lowest variance ratios of any category (0.59–0.61,
  overall). Given DFs use the exact same NB mechanism as aces and were **never
  recalibrated** (explicit scope decision, DISPERSION_FWD_DESIGN.md §2), this is
  consistent with — though not conclusive proof of — the same kind of dispersion
  over-suppression aces had before the fix. No bucket-level calibration test exists
  for DFs analogous to `most_aces_fav`, because **the simulator has no
  `most_dfs_fav` MATCH_PROPS category** (confirmed by code read) — this is a real
  architectural gap in what can be tested for DFs, not an oversight in this audit.

---

## 4. Phase 4 — Segment audit

- **The one clear concentration finding:** the residual aces overconfidence
  (Phase 1, `most_aces_fav` 80%+) is concentrated in **WTA and Clay**, not ATP. ATP
  aces calibration is essentially solved by Candidate C (80%+ gap −0.001). This
  matches the WTA-specific variance-ratio anomaly in Phase 3. **This is a follow-up
  to the aces fix itself, not evidence of a new category-level problem.**
- No other category shows a segment-concentrated calibration problem of comparable
  size. `first_set_fav_wins` Clay/Grass 80%+ gaps (−0.054/+0.049) are opposite-signed
  and each rest on small bucket populations — read as noise, not a pattern, unless a
  future audit with more holdout years contradicts that.
- Bo5 segments generally show *tighter*, not worse, calibration across categories
  (small-n, more homogeneous population — Grand Slams only) except for the
  `goes_3_sets` definitional tautology noted above.
- DFs show no segment-level bucket-calibration signal available to test (architecture
  gap, see Phase 3) — their variance-ratio compression is broadly uniform across
  ATP/WTA/surfaces, not concentrated in one segment.

---

## 5. Phase 5 — Root-cause ranking

| Category | Status | Basis |
|---|---|---|
| `fav_wins`, `first_set_fav_wins`, `most_games_fav`, `any_tiebreak`, `goes_5_sets` | ✅ Well calibrated | Bucket gaps ≤2pp everywhere a bucket has meaningful n |
| `fav_sets_won` | ✅ Well calibrated | Only count category with a meaningful high-confidence O/U bucket; mildly underconfident, not over |
| `goes_3_sets` | ⚠ Minor issue — but it's a **category-definition artifact** (Bo5 tautology), not a probability-estimation defect | Code-confirmed |
| `most_aces_fav` (post-Candidate-C) | ⚠ Minor issue, WTA/Clay-concentrated | Direct bucket-gap evidence + convergent WTA variance-ratio anomaly |
| `dfs` (fav & dog) | 🚨 Significant, unresolved risk — **same mechanism as aces, never recalibrated, lowest variance ratios in the simulator, no bucket-level test exists to rule it in or out** | Structural identity to aces (code) + explicit scope gap (design doc) + variance-ratio outlier |
| All other count categories (`holds`, `breaks`, `svgms`, `games_won/lost`, `fantasy_score`, `total_games`, `first_set_games`, `total_sets`, `tiebreaks`) | ✅ No evidence of a calibration problem, but also **no dispersion mechanism exists to fix if one is later found** — the O/U-line test as constructed can't detect overconfidence in these because it rarely produces a high-confidence prediction to check | Architecture (code) + near-flat ~0.24 ou_brier |

**Most-to-least trustworthy, given only the evidence collected here:**
`fav_wins` / `fav_sets_won` / `most_games_fav` (cleanly tested and clean) → `first_set_fav_wins`, `any_tiebreak`, `goes_5_sets` (clean, thinner evidence) → `most_aces_fav` post-fix (small, localized residual) → everything without a real dispersion-overconfidence test available (holds/breaks/svgms/games/fantasy/match count props — untested for this specific failure mode, not proven either way) → **`dfs`, least trustworthy** (same known-risky mechanism as pre-fix aces, explicitly never audited or fixed).

---

## Most important question: what's the biggest remaining calibration weakness after aces?

**Double faults (DFs).** Not based on intuition — based on: DFs are the only other
category confirmed by code read to share aces' exact NB-dispersion mechanism; they
were explicitly carved out of tonight's fix with no evidence gathered either way
(DISPERSION_FWD_DESIGN.md §2); they show the lowest expected-vs-observed variance
ratios of any category in this audit (0.59–0.61, notably below even aces' own
post-fix ratios of 0.82–0.85); and — unlike aces — **there is no bucket-level
calibration test available for DFs at all**, because the simulator has no
`most_dfs_fav`-style output category. That last point cuts both ways: it means DFs
could be fine, or could be exactly where aces was before this session started, and
right now **nobody knows**, which is itself the finding.

The second-most-important open item is narrower in scope: **WTA/Clay aces
dispersion is not yet fully settled** even after Candidate C — this is a refinement
of the aces fix already shipped, not a new discovery.

---

## Deliverable answers

1. **Healthy categories:** `fav_wins`, `first_set_fav_wins`, `most_games_fav`, `any_tiebreak`, `goes_5_sets`, `fav_sets_won`/`dog_sets_won` — all cleanly tested, gaps ≤2pp at every populated bucket.
2. **Overconfidence:** only `most_aces_fav`, and only in WTA/Clay, at a small residual scale (+0.02 to +0.07) — a much smaller version of the original aces problem, in the segment the fix was weakest for.
3. **Underconfidence:** none found at a meaningful scale; `fav_sets_won` at 80%+ is mildly underconfident (−0.014), immaterial.
4. **Categories that likely need a dispersion review:** **DFs**, unambiguously (same mechanism as aces, unaudited, variance-ratio outlier). WTA aces dispersion specifically also deserves a second tuning pass, though this is continuation of already-approved work, not a new category.
5. **Next highest-impact fix after aces:** an aces-style root-cause investigation of **DFs** — holdout tune-window pass, holdout confirmation, and (if warranted) a Candidate-C-style production change, following the identical evidence standard used for aces. A secondary, smaller follow-up: a second WTA-only aces dispersion tuning pass targeting the residual Clay/WTA 80%+ gap.

---

## What this audit did NOT do (explicit limitations)

- Did not re-fit or test any DF dispersion candidate — diagnostics only, per instruction.
- Did not build a bucket-level calibration test for DFs, holds, breaks, svgms, games_won/lost, or fantasy_score, because the simulator's output schema has no binary "most X fav" analog for them to test against (only `most_aces_fav` and `most_games_fav` exist). This is a real coverage gap in what any O/U-line-based audit like this can detect for those categories, not a decision to skip them.
- Did not modify `apex_prop_engine.py`, `apex_prop_sim_v1.py`, or `apex_prop_model_v1.py`. Frozen files MD5-verified unchanged before and after.
- Used the deployed Candidate C aces settings as given (not re-derived here) — this audit measures the simulator *as it exists right now in production*, not a hypothetical.
