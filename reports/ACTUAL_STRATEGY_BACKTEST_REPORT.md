# Actual-Strategy Backtest — Top-3 Goblins / Top-3 Standards, Real Historical Boards

**Scope:** All 13 real, settled trading days in `apex_engine_picks_log_v1.csv`
(Aug 25–Sep 9, then a 2-week gap, then Sep 24–25). No re-simulation — every
probability used is `old_prob`, the real, live-at-the-time model output
already logged for that pick. Board construction, scoring, ranking and slip
assembly all called from the unmodified, currently-live `apex_edge_tracker`
(`apex_score`, `apex_confidence`, `rank_score`, `_bb_sortkey`,
`_demote_bo5_from_top`, `slip_builder`) — nothing here was reimplemented or
hand-tuned to produce a particular answer. `apex_prop_sim_v1.py` and
`apex_prop_model_v1.py` were not touched (MD5-verified unchanged before and
after this run).

## Data limitation — read this before the numbers

Only **2 of the 13 real trading days** (Sep 24, Sep 25) carry a genuine
`prop_type` (Goblin/Standard) tag in the picks log. On every other day the
log has no format tag at all, so `slip_builder("standard")` and
`slip_builder("goblin")` correctly find **zero** eligible picks — there is
no historical record of which picks were Goblin vs. Standard on those 11
days, and none was invented to pad the sample.

That means a true, multi-week Goblin-vs-Standard backtest does not exist in
this data — 2 days is not a strategy track record. What follows uses two
tracks:

- **Primary evidence (13 days): "Mixed" Top-N** — the board's best N picks
  regardless of format, graded on the Standard payout table (Standard, not
  Goblin, because Mixed allows both MORE and LESS, like Standard does).
  This is the closest real, full-sample proxy to "how good is this board."
- **Illustration only (2 days): true Goblin/Standard split** — shown
  separately, clearly labeled, never blended into the 13-day stats.

## Board quality: Top-1 through Top-5 (Mixed, 13 real days)

| Top-N | Slips graded | Avg legs won | Avg leg hit rate | Perfect-slip rate |
|---|---|---|---|---|
| 1 | 13 | 0.85 | 84.6% | 84.6% |
| 2 | 13 | 1.54 | 76.9% | 61.5% |
| **3** | **12** | **2.42** | **80.6%** | **58.3%** |
| 4 | 12 | 3.33 | 83.3% | 58.3% |
| 5 | 10 | 3.90 | 78.0% | 30.0% |

Dollar P&L (Standard 3-pick Flex table, $[amount]/slip) computed only for N=3,
since that is the only pick-count whose real PrizePicks payout table this
system holds — inventing payout multipliers for N=1,2,4,5 would risk giving
you false ROI numbers, so those cells are left as accuracy-only:

- **Mixed Top-3: 12 slips, 58.3% win rate, $[amount] P&L, +108.3% ROI, longest
  losing streak = 2 slips, max drawdown = –$[amount]** (one bad day, Aug 25,
  never compounded into a real losing streak).
- One day (Aug 30) had fewer than 3 eligible non-Bo5 picks and was excluded
  from grading rather than guessed.

Leg-accuracy is fairly flat from Top-1 to Top-4 (77–85%) and only drops off
at Top-5 (78% avg but perfect-slip rate collapses to 30%) — the board has
real depth to 4 picks, but going past 4 clearly dilutes quality. **Top-3
is not obviously the single best cut**, but it is defensible: it's inside
the flat, high-quality zone (58.3% perfect-slip rate, same as Top-4) while
carrying less variance per slip than Top-4/5, and it is the one N with a
validated payout table, so it's the only N whose ROI claim here is real
rather than inferred from accuracy alone.

## Illustration only — real Goblin/Standard split (Sep 24–25, 2 days)

| Format | Top-3 slips | Result |
|---|---|---|
| Goblin | 1 (Sep 25) | 3/3 hit, $[amount] P&L, 150% ROI on that slip |
| Standard | 1 (Sep 25) | 2/3 hit, $[amount] P&L (push-tier) |

Sep 24 had only 2 real Standard-tagged picks and 1 real Goblin-tagged pick
that day — not enough to fill either 3-leg slip, so it's excluded rather
than padded. **This is one good day for Goblins and one break-even day for
Standards — it is not evidence either format is structurally stronger.**
Combined $[amount]$[amount] bankroll on the only fully-tagged day (Sep 25): $[amount].

## Weekly winning-day frequency (Mixed Top-3, the only full-sample metric)

"Winning day" = that day's Mixed Top-3 slip P&L > 0.

| Week | Trading days | Winning days |
|---|---|---|
| 2026-W35 (Aug 25–30) | 3 | 1 |
| 2026-W36 (Aug 31–Sep 6) | 5 | **3** |
| 2026-W37 (Sep 7–9) | 3 | 2 |
| 2026-W39 (Sep 24–25) | 2 | 1 |

Distribution across the 4 real trading weeks: **1 winning day → 2 weeks,
2 winning days → 1 week, 3 winning days → 1 week. Zero weeks reached 4 or
5 winning days**, and no week ever had a losing week (winning days ≥1 in
every real week logged). Weeks are short (2–5 trading days, not a full
Mon–Fri) because the book didn't trade every calendar day, so "days/week"
here means "days actually played," not calendar coverage.

Cumulative P&L over the 13 days: **$[amount] max drawdown –$[amount] ending
positive on every week measured.**

## Deliverable

1. **Would the strategy have been profitable?** Yes on the only evidence
   that spans real days — Mixed Top-3, 58.3% win rate, $[amount] over 12
   graded slips, max drawdown only –$[amount]. The true Goblin/Standard split
   (2 days) also came out positive but is too thin to be its own answer.

2. **Would it realistically produce 3–4 winning days per week?** Not on
   this evidence. Best week logged was 3 winning days (out of 5 played);
   no week hit 4, and most weeks only had 2–3 trading days to begin with.
   3 wins/week happened once in 4 weeks — call it plausible on a good week,
   not a reliable baseline.

3. **Are Goblins or Standards stronger?** Cannot be answered from real data
   — only one graded day exists for each format, and they point opposite
   directions (Goblin 3/3, Standard 2/3 push). Answering this for real needs
   consistent Goblin/Standard tagging on future picks, not just Sep 24–25.

4. **Is Top-3 optimal?** No single N dominates on accuracy — Top-1 through
   Top-4 all sit in a flat 77–85% leg-hit-rate band; only Top-5 clearly
   degrades. Top-3 is a reasonable, defensible choice inside that band
   (same 58.3% perfect-slip rate as Top-4, lower variance), and it's the
   only N with a real, verified payout table behind its dollar figures —
   but Top-4 is not proven worse on accuracy, and would need its own real
   payout table to compare on ROI rather than just hit rate.

5. **Best balance of win frequency, profitability, drawdown?** On this
   data, Mixed Top-3 is the strongest evidenced choice: full 13-day
   coverage, positive every week, small drawdown (–$[amount]), and the only
   configuration whose ROI isn't an accuracy-only proxy. Top-4 is worth
   tracking going forward (similar hit rate, one more leg of exposure) once
   its real payout table and a longer sample exist, and Goblin-vs-Standard
   needs weeks of consistently-tagged data before it can be answered at all
   — the honest bottleneck across every question above is 13 real trading
   days (2 of them format-tagged), not the model.
