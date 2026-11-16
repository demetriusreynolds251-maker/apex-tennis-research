# Dispersion Fix — Real-World Profitability Backtest

**2026-09-27. Read-only. Frozen V1 files untouched (MD5-verified before/after).**
Scripts: `apex_v2_dispersion_profitability_backtest_partA_resim.py` (re-simulation),
`apex_v2_dispersion_profitability_backtest_partB_score.py` (scoring/slip/grading).
Results: `apex_v2_dispersion_profitability_backtest_results.json`.

## What this is, honestly

This is **not** a live before/after A/B test. Aces Candidate C went live 2026-09-26
evening; DFs Candidate C went live 2026-09-27 00:09 CT — about 8 hours before this
report, with zero new settled results. So instead: every real, settled aces/dfs
pick your engine ever logged (Aug 25 – Sep 25, 2026) was re-run through the
**current, live** `apex_prop_engine.evaluate_match()` (same match, same date, same
requested line) to get the NEW-model probability, holding everything else —
board-ranking formula, category track record, settled ground truth — exactly as
it is in production today. Non-aces/dfs categories are mathematically identical
under both models (the fix touches only aces/dfs), so they serve as their own
control.

## Data reality check (must be stated up front)

- Your engine only has **13 real trading days** of logged picks: Aug 25, 28, 30,
  31, Sep 1, 4-9, and Sep 24-25. There is a 2-week gap (Sep 10–23) with nothing
  logged.
- **Goblin/Standard tagging (`prop_type`) only exists for 2 of those 13 days**
  (Sep 24-25). Every earlier day has no prop_type at all. That means a genuine
  multi-week "Top 3 Goblin vs Top 3 Standard" backtest is **not possible** from
  what's on disk — there's one real Standard slip and one real Goblin slip in
  the whole history.
- 296 aces/dfs picks were logged; 287 have real settled outcomes; all 287
  re-simulated cleanly under the new model (0 failures).

Given that, this report leads with the **Mixed Top-3 (APEX Best 3)** strategy —
13 real days, the only sample size worth drawing a conclusion from — and reports
Standard/Goblin as a 1-slip-each illustration, clearly flagged as too thin to
generalize.

## Mixed Top-3 (13 real days, $[amount]/slip, Standard Flex payout: 3x/1x/0x)

| | OLD (pre-fix) | NEW (Candidate C, live) |
|---|---|---|
| Slips | 12 | 12 |
| Win rate | 58.3% | 58.3% |
| Loss rate | 41.7% | 41.7% |
| ROI | +108.3% | +108.3% |
| Profit/Loss | $[amount] | $[amount] |
| Avg slip hit rate | 80.6% | 80.6% |
| Avg confidence | 45.3/70 | 45.3/70 |
| Avg edge | 0.167 | 0.162 |

**Identical results.** Board membership changed on **1 of 13 days** (Aug 28):
Rei Sakamoto DFs LESS 2.5 (old stated prob 81.2%) was displaced by a Total Games
MORE pick (prob 63.2%) once the DFs dispersion fix pulled Sakamoto's stated
probability down to 73.8%. Both legs actually won (Sakamoto: 1 DF, well under
2.5; Total Games: 30 vs line 20.5), so this single swap had **zero P&L effect**
in the historical record — but it is real proof the fix *can* move board
membership, it's just rare, because your Top-3 is dominated by `games_won`
(elite-tier, heavily evidence-weighted) far more often than by aces/dfs.

## Standard / Goblin (1 real day each — Sep 25, illustrative only)

| | Standard OLD | Standard NEW | Goblin OLD | Goblin NEW |
|---|---|---|---|---|
| Slips | 1 | 1 | 1 | 1 |
| Result | 2/3 (push, $[amount] P&L) | 2/3 (push, $[amount] P&L) | 3/3 ($[amount]) | 3/3 ($[amount]) |
| Legs | Tabilo breaks, Rublev fantasy, Faria games_won | identical | Jacquet/Gaston games_won, Gibson breaks | identical |

No aces/dfs picks appear in either slip on either day, so the fix could not
have changed these regardless of dispersion — the composition is identical
old vs new.

## Category-level calibration (all 287 real settled aces/dfs picks, not just Top-3)

| | n | Actual hit rate | Old avg stated prob | New avg stated prob | Old Brier | New Brier |
|---|---|---|---|---|---|---|
| Aces | 148 | 56.8% | 69.3% (+12.5 over) | 59.2% (+2.4 over) | 0.2618 | **0.2411** |
| DFs | 139 | 59.0% | 65.7% (+6.7 over) | 60.8% (+1.8 over) | 0.2347 | 0.2401 |

Aces calibration improved sharply in this live sample (consistent with the
holdout study). DFs Brier ticked up slightly here — a small, real, honestly-
reported divergence from the larger holdout study (which favored the new DFs
config on average); 139 live rows is a much noisier sample than the holdout's
thousands, and this is the kind of result that should be watched, not hidden.
Both categories became **much less overconfident** either way — the actual
purpose of the fix.

## Answers to your specific questions

1. **Expected win rate before:** 58.3% on Top-3 slips (12 real days), 80.6% avg
   leg hit rate.
2. **Expected win rate after:** identical — 58.3% / 80.6%. The fix does not
   change your realized win rate, because aces/dfs picks essentially never
   dominate your Top-3 board membership in the real history you have.
3. **Does the dispersion fix improve profitability?** Not measurably, in the
   picks you'd actually have played (Top-3/slip level) — P&L is dollar-for-
   dollar identical across 12 real days. Where it helps is the accuracy of the
   *stated* probability and CONFIDENCE number on aces/dfs picks specifically
   (aces overconfidence cut from +12.5pts to +2.4pts) — real, but invisible at
   the slip-selection level because those picks rarely reach your Top 3 anyway.
4. **Should the Top-3 strategy change?** No evidence to change it from this
   backtest. The one day board membership changed, both outcomes were wins
   either way.
5. **Goblin vs Standard — which benefits more?** Can't be answered with
   confidence from real data — only 1 real day of each exists. Structurally,
   neither benefited in that 1 day (no aces/dfs legs in either slip).

**Verdict on your A–E menu: (C) Similar win rate, with (B)'s "better
calibration" true underneath it but not yet visible at the slip level** —
confidence numbers and stated probabilities on aces/dfs picks are now much
closer to what actually happens; realized win rate and bankroll growth on your
actual Top-3 Goblin/Standard strategy are, in the real history available,
unchanged.
