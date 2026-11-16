# Apex "Build Better" Plan — Track A (soft arenas) + Track B (private-data layer)
**Date:** 2026-08-16 (session 4, late)  **Status:** scoped, first offline step delivered, NOT approved beyond step A0
**Goal (user's words):** a predictive Apex that beats the market. No excuses. Long haul accepted.
**Ground truth to build on:** Apex ≈ 93.5% ELO; ELO is already in Pinnacle's price; on the sharpest
market (main-tour closing line) Apex loses to the price (LL .632 vs .590). So "better" = new
information + softer arenas, measured by closing-line value (CLV), not "model harder".

---

## Track A — Soft arenas: where can the CURRENT Apex already compete?

Arenas, softest first (published/practitioner consensus, not measured by us yet):
1. **Opening lines** on the main tour (first hours after Pinnacle posts) — the market hasn't finished
   thinking. Score = does Apex's disagreement with the OPENER predict which way the line moves.
2. **Challengers / ITF / qualifying / doubles** — thinner markets, fewer sharps, lower limits.
3. **Live / in-play** — needs speed + a live model; park it.

**A0 (delivered, offline, 0 requests): `open_vs_close.py`** — from the 38 cached Cincinnati matches:
how far Pinnacle's fair prob moves open→close, share of matches moving ≥0.02 / ≥0.05, favourite flips,
hours in the window. This measures the SIZE of the opening-line opportunity before we test Apex in it.

**A1 (needs Apex's own numbers): opening-line CLV test.** For each upcoming main-tour match:
- record Apex's probability at the moment Pinnacle's opener appears (Apex must run BEFORE/AT open);
- record opener, then closer (RapidAPI "Get Last 10 Odds Movements"/"Biggest Movements" or OddsPapi
  history when quota allows);
- score: when Apex is ≥0.03 away from the opener, does the close move toward Apex? **PASS = 55%+ of
  the time on 200+ disagreements** (that is forecasting skill the price didn't have yet).
- cost: forward log for 2–3 weeks; a Rebet/Novig price at open makes it bettable, not just measurable.

**A2 (needs data): Challenger/ITF backtest.** Same `test_ingredients.py`-style ROI test, but on
Challenger/ITF matches. Blockers: (a) does Dataset B hold Challenger/ITF results + Apex features?
(check `SELECT tour_level, COUNT(*)`); (b) odds source — tennis-data.co.uk has NONE below main tour;
OddsPapi historical has them (560 fixtures/2 days incl. Challenger/ITF) but costs 2 req/match →
paid tier (~$[amount]/mo unverified) needed for a real sample. **First cheap step:** the DB query.

Track A pass/fail: Apex must beat the arena's Pinnacle price on log-loss OR beat the opener on CLV
55%+ over 200+ disagreements. Anything less = that arena is not soft enough for the current engine.

## Track B — Private-data layer: information the price doesn't have yet

Principle: every input must answer "why wouldn't Pinnacle already know this?" If the answer is
"they would", it's ELO in a costume. Candidates, ranked by plausibility × cost:

| # | Signal | Why the price may lag it | Source | Cost / effort | How to test |
|---|---|---|---|---|---|
| B1 | **Retirement / injury risk** (recent RET/WO, MTOs, matches since return) | Books price it late; RET-prone players get overpriced | Sackmann (already have RET flags), ATP/WTA injury news, prior-match MTO logs | Low (data in hand) | Feature → does it move Apex's LL toward Pinnacle's on held-out? CLV at open |
| B2 | **Fatigue / schedule load** (sets played last 7 days, 3-setters, days rest, back-to-back weeks, doubles played) | Public but rarely priced precisely; strong at Slams/back-to-back Masters | Sackmann results + tournament calendars | Low | Same |
| B3 | **Surface / speed transition** (first week on new surface, court-speed index of the specific event) | Priced roughly, not per-event | Match stats (aces/rally length per event), CPI where published | Medium | Same |
| B4 | **Travel / time zone** (long-haul in last 5 days) | Rarely priced | Tournament locations + calendar | Low | Same |
| B5 | **Opening-line timing** (bet at open, not close) | Not a data signal — an execution edge; pairs with A1 | RapidAPI odds-movement endpoints | Low | CLV |
| B6 | **Live-shape signals** (first-set stats → in-play prob) | Speed edge; heavy build | Live feed (RapidAPI live events count/points) | High | Park |
| B7 | **Match-fixing / motivation flags** (dead rubbers, retirement-heavy tours, prize-money incentives) | Sharps price it; soft books don't | News, ITF context | Medium | Later |
| B8 | **Player-specific priors** (H2H style matchups, lefty/righty, big-server vs returner) | Mostly in the price | Sackmann | Low | Low expectation |

**B-Step 1 (cheap, this week):** build B1+B2+B4 as features from data already on the Mini, add
them to the walk-forward rows, re-run the held-out log-loss test vs Pinnacle (`test_ingredients.py`
pattern, time split, fixed threshold, alarms). **PASS = LL improves toward .590 by ≥0.005 on 2024+**
(tiny but real; today's gap is .042). **FAIL** = features add ~0 → they're already priced.
**B-Step 2:** whichever features move LL, wire into A1 (opening-line CLV) — that's where a small
information edge is worth money.
**B-Step 3:** private pipeline (injury news scraping, court-speed per event) only if Steps 1–2 show
signal. Don't build the pipeline before proving the signal.

## Non-negotiables (both tracks)
Time-split only; thresholds fixed once; fake-data self-test before real data; alarms (LL beats book by
>0.02, ROI >+15% on 200+, hit >65% on totals) = leak; score by CLV first, ROI second; straight bets
only; keep the price screener as the money engine while the model earns its way back.

## What's blocked and on what
- OddsPapi quota (~250 used) → Challenger history and more open/close samples wait for month reset
  or paid tier.
- Apex must emit a timestamped probability at line-open for A1 (check openclaw scheduler timing).
- Dataset B tour-level coverage unknown for A2 (one SQL query).

## Files
- `open_vs_close.py` (SHA bf4bed22…1d42) — Track A0, offline, self-tested.
- This plan: `APEX_BUILD_BETTER_PLAN_2026-08-16.md`.
