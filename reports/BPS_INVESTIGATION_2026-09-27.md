# Break Points Saved — Investigation
**2026-09-27 — evidence only, no model built, no production files touched**

Frozen files MD5-verified unchanged before and after
(`apex_prop_sim_v1.py` / `apex_prop_model_v1.py`). Source: the SA365
per-set pipeline built earlier today (`apex_sa365_stats_v1.db`). New file
`apex_sa365_bps_investigation.py` does the analysis and writes
`apex_sa365_bps_investigation_report.json`; nothing else was touched.
One small, necessary step before the analysis: 16 of the 19 captured
matches were missing `tour` (ATP/WTA) because they predated the tour-fill
fix built into today's daily-capture work — I re-ran the existing,
unmodified `capture_one()` against just those 19 (not the full 112-match
history) to backfill it. 18 of 19 now have tour; one match's picks-log
row uses a slightly different name spelling than the API record and
wasn't matched (a known, minor, and disclosed gap, not silently dropped).

**Sample size up front, because it governs every section below:** 19
matches, 38 player-match rows. This is a real, honest analysis of what
exists, not a padded one — but it is small, and every number here should
be read as directional, not settled. All 19 matches are Bo3; the ongoing
daily capture job will grow this.

## 1. Coverage

19 of 19 matches with a usable SA365 statistics sheet have
`break_points_saved` fully populated (100%) — consistent with the
earlier field audit's finding that once a stat sheet exists at all, every
field inside it is populated. This isn't a new finding, it's a
reconfirmation on the specific field in question.

## 2. Distribution

38 player-match observations. `break_points_saved_pct`: mean 50.4, std
28.8, min 0, max 100, median 55 (IQR 33-66). Five rows sit at exactly 0%
and two at exactly 100% — worth flagging rather than glossing over: those
extremes usually mean the player faced very few break points at all
(`break_points_saved_total` — the count of break points actually faced —
has its own median of only 6, min 0), not necessarily "defended terribly"
or "defended perfectly." A 0% on 1 break point faced and a 0% on 8 faced
are very different signals that the raw percentage alone doesn't
distinguish — worth carrying `break_points_saved_total` alongside the
percentage in any future use, not the percentage alone.

## 3. ATP / WTA splits

18 of 19 matches have a known tour (10 ATP, 8 WTA rows in the underlying
picks-log-matched set; 20/16 player-match rows respectively once both
sides are counted).

| | ATP (n=20) | WTA (n=16) |
|---|---|---|
| break_points_saved_pct (mean) | 52.7 | 47.4 |
| break_rate (mean) | 0.147 | 0.403 |
| hold_rate (mean) | 0.853 | 0.597 |

The break_rate/hold_rate gap between tours is large and matches known
tennis reality (WTA matches are more break-heavy; ATP servers hold far
more often) — a good sanity check that these derived rates are computing
correctly. **The interesting part:** `break_points_saved_pct` barely
moves between tours (52.7 vs 47.4) despite that huge gap in break_rate
and hold_rate. If BPS% were just a repackaging of hold rate, it would
track that ATP/WTA gap closely — it doesn't. That's early, small-sample
evidence toward the same conclusion Phase 3 reached: BPS% isn't just
restating information Apex already has elsewhere.

## 4. Surface splits

36 of 38 rows are Hard court; only 2 are Clay (one match). **The Clay
numbers are not usable as a surface finding** — n=1 match is a sample
size of one, not a surface effect — but are reported for completeness:
break_points_saved_pct mean 8.0 (both sides of that one match happened to
defend poorly), break_rate 0.417, hold_rate 0.583. A real surface split
needs the daily job to accumulate more clay/grass matches.

## 5. Correlation matrix

n=38 rows, all four fields present:

| | BPS% | BP Scored | Break Rate | Hold Rate |
|---|---|---|---|---|
| **BPS%** | 1.00 | -0.025 | -0.025 | 0.213 |
| **BP Scored** | -0.025 | 1.00 | 0.93 | -0.179 |
| **Break Rate** | -0.025 | 0.93 | 1.00 | -0.124 |
| **Hold Rate** | 0.213 | -0.179 | -0.124 | 1.00 |

Two things worth stating plainly:
- **Break Points Scored and Break Rate are near-collinear (0.93)** — expected,
  since break rate is just break points scored divided by return-game
  opportunities. This is not a BPS finding, it's confirmation the derived
  rate was computed sanely.
- **BPS% correlates near-zero with the offensive stats** (-0.025 with
  both) and only weakly with hold rate (0.213). If BPS% were redundant
  with what Apex already settles on, you'd expect a strong correlation
  somewhere in this row. There isn't one.

## 6. Residual analysis

Regressed `break_points_saved_pct ~ break_rate + hold_rate` (OLS, n=38,
evidence-only — this is not a deployed or proposed production model, it
exists purely to quantify "how much of BPS% is already explained by what
Apex has"):

- **R² = 0.046.** Break rate and hold rate together explain under 5% of
  the variance in break-points-saved%. If BPS% were mostly reconstructable
  from Apex's existing signals, this would be close to 1; it is close to
  0.
- Residual (the part of BPS% left over after removing what break_rate/
  hold_rate explain) correlates 0.013 with break_points_scored (essentially
  nothing left there either) and -0.133 with match win (weak, and with
  n=38 not distinguishable from noise — reported for completeness, not as
  a finding).

**Bottom line of the residual check:** break_points_saved is empirically
independent of the offensive/game-level signals Apex already uses. This
confirms Phase 3's earlier, cruder correlation check (-0.025 against
break_points_scored alone) with a proper multi-variable control, and the
conclusion strengthens rather than weakens: this is close to orthogonal
information, not a restated one.

## 7. Potential use cases (reasoning only — nothing built)

1. **Independent cross-check for the `breaks` settlement category.**
   `apex_settle_sa365.value_for()` settles `breaks` from
   `breakPointsScored` with only an arithmetic serve-parity sanity check
   against itself. BPS is a genuinely separate signal (per Sections 5-6)
   that could serve as an actual second data source rather than a
   self-consistency check on the same number.
2. **Serve-under-pressure feature for aces/dfs/games_won calibration.** A
   player with a normal hold rate but a low BPS% is winning service games
   narrowly, repeatedly facing and barely escaping break point — a
   distinction the current game-level hold rate cannot make on its own.
3. **Bo5 fatigue signal — blocked on data, not reasoning.** A within-match
   decline in BPS% across sets would be a more sensitive fatigue indicator
   than set-level hold rate, since it operates at the point level rather
   than the game level. Currently **zero Bo5 matches exist in the
   captured sample** (all 19 are Bo3, per the pipeline doc's Phase 4
   finding) — this use case is real reasoning, not yet real evidence, and
   needs the daily job to catch a Bo5 tournament while still inside the
   retention window before it can be tested.
4. **WTA-specific calibration.** This is the first time this project has
   had a real (if small) WTA-tagged sample — 8 of 18 tour-known matches.
   Given the pre-flight audit's finding that WTA model coverage is
   thinner than ATP's, and Section 3's finding that WTA break_rate/hold_rate
   differ substantially from ATP, a defensive point-level signal may carry
   more relative information for WTA specifically. This needs more than
   8 matches before it's more than a hypothesis.

## What this investigation does not claim

It does not claim BPS% predicts outcomes, is ready to feed a model, or
should change any ranking or probability today. It claims, on real data
(a small sample honestly labeled as such): BPS% is not redundant with
break_points_scored, break_rate, or hold_rate, by two independent checks
(a simple correlation and a controlled residual). That is the evidence
the user asked for — the modeling decision is a separate step, for later.
