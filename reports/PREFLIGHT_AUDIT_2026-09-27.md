# Apex Pre-Flight Audit — 2026-09-27

Read-only audit. Nothing was changed. Frozen V1 files MD5-verified
unchanged before and after (`apex_prop_sim_v1.py` 7b03e521…,
`apex_prop_model_v1.py` 6bf50622…).

## Headline finding — read this first

**Every code change from today's session, plus both dispersion fixes, is
sitting on disk but is NOT running in production yet.** Two long-running
processes serve real picks and the dashboard:

- Discord bot, PID 80714, **running continuously since Thu Sep 24, 02:36 AM**
- Mission Control, PID 984, **running continuously since Sun Aug 30, 4:44 PM**

`apex_prop_engine.py` is imported once per process lifetime
(`import apex_prop_engine` inside `openclaw_core.py`, no `importlib.reload`
anywhere) and then cached — Python does not re-read a `.py` file just
because it changed on disk. So:

- The **Aces dispersion Candidate C** fix (applied 09-26) and **DFs
  dispersion Candidate C** fix (applied 09-27) are both **newer than the
  bot's Sep-24 start time** — the running bot is still pricing aces/DFs
  with the OLD dispersion. Today's backtest, which showed the fix would be
  profitable, was run in fresh one-off Python processes (which do read the
  current file) — it never touched the live bot.
- The 4-priority slip-safety pass (duplicate-leg protection, manual/auto
  bankroll overlap check, screenshot auto-confirm) all live in
  `openclaw_core.py` / `openclaw_ops.py` / `openclaw_intake.py` /
  `discord_bot.py` — all edited **after** both processes started. None of
  it is active yet.
- Mission Control auth (`MC_AUTH_ENABLED = True`) is in the file but the
  running MC process still has the old `AUTH DISABLED` behavior in memory
  — confirmed live: `curl localhost:8788/api/bankroll` returns **200 with
  no credentials**, right now.

**Fix is simple — restart both processes — but until that happens, none of
this is protecting or improving anything real**, so it has to be the top
line of this audit rather than a footnote.

---

## Section 1 — System Health

| Check | Status | Evidence |
|---|---|---|
| Settlements processing | ⚠️ Mostly, with a live gap | Sim log: 790 rows, 766 settled, **24 unsettled**. See breakdown below. |
| No settlement backlog | ⚠️ Partial backlog | 13 of the 24 unsettled rows are Aug 28–Sep 1 matches already known to need VOID (Cilic/Rublev, Jodar/Kokkinakis, O'Connell, Potapova/Valentova — "Cancelled"/RET per project history) — voided in the hand CSV already, but **never removed from the sim log itself**, so the grader keeps re-flagging them daily. Cosmetic, not a live risk. |
| No duplicate settlements | ✅ Confirmed | 0 duplicate rows on (match_id, player, category) in the sim log. |
| No unresolved review queues | 🚨 Fails | `data/ops_center/slip_review_queue.json`: **2 real slips stuck at PENDING_REVIEW** (6-leg slips, $[amount] and $[amount] stake, submitted 12:12 AM, source=Discord screenshot) — never resolved. Auto-validation (built today) hasn't touched them because the bot process running is older than that code (see headline). |
| PNL automation functioning | 🚨 Not live | Code built + unit-tested today, confirmed present on disk, **not loaded into the running bot/Mission Control processes** (see headline). |
| Slip logging functioning | 🚨 Dormant | The real ledger (`data/slips/slip_log.json`, confirmed via `SLIP_LOG_FILE` constant) has **2 entries total, both PENDING, both dated 2026-07-03** — no real slip has been logged in ~3 months. A stale, unused duplicate file (`data/slip_log.json`, no `/slips/`) also exists with 2 old July WIN/LOSS rows — dead clutter, not read by any code path (confirmed via grep), worth deleting for hygiene. |
| Bankroll tracking functioning | 🚨 Empty | `data/ops_center/slip_ledger.json` (manual ledger): **0 entries**. Auto-ROI report (`slip_roi_report()`) has nothing to report given slip_log.json's dormancy. Real bankroll performance isn't currently observable anywhere in the system — only the backtest reconstruction exists. |

**Exceptions to flag:** the settlement pipeline itself (SA365-based) is
running daily and successfully as of this morning (6:41 AM cycle log shows
a full, real run) — the problem isn't that it's broken, it's that (a) a
few old rows were never cleaned up, and (b) the two safety-relevant ledgers
(slip log, bankroll) have had no real activity logged in months, so this
audit can't confirm real-money performance independent of the backtest.

## Section 2 — Data Health

| Check | Status | Evidence |
|---|---|---|
| SportsAPI365 feed healthy | ✅ | `BET365_PREMATCH_ENABLED = True` (since 09-23); `data/sa365_gap/live` and `/prematch` both actively populated through **today, 14:33** — collector is running. |
| No stale lines | ✅ (for what's priced) | No evidence of stale-line reuse found. |
| No missing categories | 🚨 Partial | `sets_won`, `first_set_games`, `any_tiebreak`, `first_set_fav_wins`, `goes_3_sets`, `goes_5_sets` all show **0 tracked / 0 settled** (`et.records()['coverage']`: "tracked": 14, "covered": 6 — only 6 of 14 defined categories have ANY track record). |
| No pricing mismatches | — not directly testable this pass | No mismatch evidence found, but not exhaustively checked against a second book this session. |
| No broken scrapers | ✅ | SA365 gap collector actively writing today. |
| No failed daily imports | ⚠️ | See settlement gap below — one specific match import/lookup is currently failing. |

**Category coverage, last 2 real trading days (Sep 24–25):** aces 24,
breaks 23, games_won 22, total_games 17, fantasy_score 15, **dfs only 3** —
DFs coverage is thin relative to the others even setting the dispersion
fix aside.

🚨 **New finding — categories with zero evidence are already live on the
board.** The most recent board render (`apex_bb_rank_log_v1.csv`,
2026-09-26 10:23) includes **`total_sets`** and **`tiebreaks`** props —
both of which show **0 settled picks ever** (`status: "never"` in
`et.records()`). These categories are being ranked and could be recommended
with zero calibration evidence behind them.

🚨 **Active settlement gap:** `apex_settle_sa365.py --check` (run live
during this audit) on rows since 09-23 found:
- 2 rows need VOID (Maria Timofeeva/Gabriela Knutson, RET, score 6-1,5-2) — identified correctly, not yet applied.
- **7 rows "NO MATCH"** — Leylah Fernandez vs. Mirra Andreeva (Sep 25) is not findable in SA365 by name+date even with the ±2-day/both-order retry. Per project history, SA365 stat sheets get deleted after "some days" — this match is already 2 days old, so there is real time pressure to resolve this before the data becomes permanently unrecoverable.
- 4 rows "HELD" — Katie Volynets/Kimberly Birrell (Sep 24), stat sheet's games total disagrees with the final score. Correctly held rather than zero-filled, but stuck until manually reconciled.

## Section 3 — ALIS Health

| Check | Status | Evidence |
|---|---|---|
| New settlements entering ALIS | ✅ | Today's cycle (06:41 AM): 272-168 settled (61.8%), up to date. |
| Projection joins functioning | ⚠️ Partial | Overall MAE computes (3.43) — this is fixed from the 09-06 "empty" state. But of the loss post-mortems shown in today's report, **14 carry "projection unavailable,"** concentrated in `games_won` and `total_games` — the join isn't wired for every category yet. |
| Projection errors calculating | ✅ (where projection exists) | MAE 3.43 overall. |
| Learning reports updating | ✅ | `apex_learning_system/reports/2026-09-27_cycle.md` generated today. |
| No unexpected "projection unavailable" | ⚠️ | 14 occurrences today — not "unexpected" (known partial gap), but not resolved either. |

**Coverage:** Accuracy 61.8% (vs 55% band +6.8%, vs 65% band −3.2%, vs 88%
band −26.2%). **Prop-type (Goblin/Standard) learning is still not
possible** — today's report states plainly "no settled picks carry a prop
type yet" for the ALIS learning path; tagging only exists for 2 real days
total, matching every earlier finding this session.

## Section 4 — Model Health by Category

Live snapshot via `et.records()`, called during this audit (not the
backtest cache):

| Category | Record | Win rate | Calibration | Status | Evidence |
|---|---|---|---|---|---|
| Games Won ("Most Games") | 61-26 | 70.1% | +10.24 | ✅ Healthy | Best category on the board (`rec['top']`). |
| Breaks | 40-22 | 64.5% | +2.41 | ✅ Healthy | |
| Double Faults | 50-29 | 63.3% | −3.16 ("under") | ⚠️ Monitor | Mildly overconfident; only 3 fresh picks last 2 real days (thin); the Sep-27 DFs fix that targets this **isn't live yet** (headline). |
| Fantasy Score | 35-24 | 59.3% | +2.52 | ✅ Healthy | Note: Bet365 pricing for this category is "gated separately" per a price-feed comment — current gate status wasn't independently re-verified this pass. |
| Total Games | 50-35 | 58.8% | +1.89 | ✅ Healthy | |
| Aces | 49-38 | 56.3% | **−10.57** ("under") | 🚨 Active Concern | Worst category on the board (`rec['worst']`); the exact problem the Sep-26 fix targets — and that fix **isn't live yet** (headline). |
| Bo5 (all categories, cross-cut) | 196-149 | 56.8% | −11.18 | 🚨 Active Concern | Weaker than Bo3 across the board; ALIS's standing recommendation has been RESTRICT; current mitigation is the "demote Bo5 from top slots" board rule, not a hard cap. |
| Bo3 | Not cleanly separable from the live snapshot this pass | — | — | ⚠️ Monitor | Should be split out explicitly in a follow-up ALIS run. |
| Sets Won | 0 settled ("never") | — | — | ⚠️ Monitor | No track record at all — can't be assessed, shouldn't be trusted yet. |
| Tiebreaks | 0 settled ("never") | — | — | 🚨 Active Concern | Same as Sets Won, but **already appearing on live board renders** (see Section 2) — zero evidence, already being ranked. |
| Match Winner (moneyline) | Not tracked | — | — | ℹ️ Out of scope? | No moneyline entries anywhere in `apex_edge_tracker.py`'s evidence system — either this system doesn't currently evaluate moneyline at all, or it's tracked somewhere this audit didn't find. Worth a direct answer from you on whether Apex is expected to cover moneyline right now.

## Section 5 — Recent Deployments

| Deployment | Code on disk | Live in running process | Notes |
|---|---|---|---|
| 1. Ace Dispersion Candidate C | ✅ Confirmed (`CANDIDATE-C-2026-09-26` marker) | 🚨 **NOT LIVE** | Bot started before this patch. |
| 2. DF Dispersion Candidate C | ✅ Confirmed (`CANDIDATE-C-2026-09-27` marker) | 🚨 **NOT LIVE** | Same reason. |
| 3. PNL Automation Improvements | ✅ Confirmed (dup-leg + overlap functions present) | 🚨 **NOT LIVE** | Bot + Mission Control both predate the edit. |
| 4. Duplicate Slip Protection | ✅ Confirmed | 🚨 **NOT LIVE** | Same. |
| 5. Screenshot Auto-Validation | ✅ Confirmed (`try_auto_confirm_slip` wired into `discord_bot.py`) | 🚨 **NOT LIVE** | This is why the 2 pending review-queue slips were never auto-checked. |
| Mission Control auth re-enable | ✅ `MC_AUTH_ENABLED = True` in file | 🚨 **NOT LIVE** | Dashboard confirmed wide open right now (`curl` 200, no creds) — deliberately left this way pending your manual credential step from the earlier priority-3 work. |

**None of the five are "functioning as expected" in production right now**
— they're all correctly built and tested in isolation, but inert until a
restart.

## Section 6 — Board Quality

1. **Rankings behaving normally?** Mostly yes for the established
   categories — Games Won, Breaks, Total Games all show sane, positive
   calibration. The Aces/Bo5 weakness is a real, known model issue, not a
   ranking-logic bug.
2. **Unusual category dominance?** Not on this small a sample — the
   Sep 24/25 boards spread fairly evenly across aces/breaks/games_won/
   total_games/fantasy_score; DFs is thin (3 picks) but not because of a
   ranking bug, more a coverage/count issue upstream.
3. **Obvious low-quality recommendations?** Yes — `total_sets` and
   `tiebreaks` props rendered on the Sep 26 board with **zero** settled
   history behind them (Section 2/4). These shouldn't be ranked alongside
   evidence-backed categories without a clear "unproven" flag.
4. **Residual RANK/APEX issues?** Project history notes a 2026-09-26
   revert to legacy-APEX-first ordering in `_bb_sortkey` — this audit
   didn't find evidence it's currently broken, but it's a recent enough
   change (same week as the dispersion fixes) to deserve one direct
   verification pass rather than an assumption.

## Section 7 — Goblin + Standard Strategy

Reusing today's full actual-strategy backtest (13 real days, `old_prob`
only, no hindsight, live scoring functions):

| | Slips | Win rate | ROI | Drawdown | Reliability |
|---|---|---|---|---|---|
| Mixed Top-3 (full 13-day proxy) | 12 | 58.3% | +108.3% | $[amount] | Best-evidenced number we have, still only 12 slips |
| Standard Top-3 (true tag) | 1 | 0% (2/3) | $[amount] | — | 1 data point — not a track record |
| Goblin Top-3 (true tag) | 1 | 100% (3/3) | +150% | — | 1 data point — not a track record |

**Do I currently see a reason this strategy should NOT be used?**

Not a fundamental one — the one full-sample proxy (Mixed Top-3) is
real-data positive with a small drawdown. But two things should make you
size it cautiously right now rather than go all-in:

- The Aces fix and DFs fix — both aimed at categories that feed this exact
  slip — **aren't live in production yet** (Section 5). Whatever board
  you'd see today is still running the pre-fix numbers.
- The true Goblin/Standard split is 1 real day each — the 58.3%/100%/0%
  figures above are all too small to trust as a rate; treat them as "not
  disproven," not "confirmed."

## Section 8 — Open Risks, Ranked

| # | Issue | Severity | Impact | Probability (already true) | Recommended action |
|---|---|---|---|---|---|
| 1 | Bot + Mission Control both running pre-patch code; today's dispersion fixes + safety pass are inert | 🚨 Critical | All of today's fixes/protections are not protecting anything real | 100% (confirmed) | Restart both processes deliberately, then re-verify with a live picks-log spot check that new aces/DFs probabilities differ from the backtest's "old_prob" |
| 2 | Fernandez/Andreeva (Sep 25) unsettleable — SA365 "NO MATCH" | 🚨 High | One real match's props may become permanently ungraded if sheets expire | High, time-sensitive | Investigate today — try direct SA365 event-id lookup instead of name+date; if truly gone, VOID rather than leave open indefinitely |
| 3 | `total_sets`/`tiebreaks` ranked on live boards with 0 settled history | 🚨 High | Real recommendations with zero calibration backing | 100% (confirmed) | Gate these categories from Best Bets/Slip Builder until ≥25 settled picks exist, matching the Bo5 precedent |
| 4 | Aces calibration −10.57, worst category, fix not live | ⚠️ Medium | Continued overconfidence on aces picks until restart | 100% (confirmed) | Same restart as #1; re-measure after ~2 weeks live |
| 5 | Bo5 calibration −11.18, ALIS recommends RESTRICT, only soft-demoted today | ⚠️ Medium | Weaker picks still reach Top-5 (though not Top-3) | Ongoing | Decide explicitly: keep soft demotion, or hard-restrict Bo5 from Standard/Goblin slips entirely |
| 6 | Real slip/bankroll ledgers dormant ~3 months | ⚠️ Medium | No real-money track record exists outside the backtest reconstruction | 100% (confirmed) | Once automation is live (#1), confirm real slips start landing in `data/slips/slip_log.json` within the first week |
| 7 | 2 real screenshot slips stuck in review queue | ⚠️ Medium | Real wagers with unresolved outcomes | 100% (confirmed) | Resolve manually now; will auto-clear going forward once #1 is fixed |
| 8 | DFs coverage thin (3 picks/2 days) | ⚠️ Low-Medium | Current 63.3% win rate isn't a stable estimate | Ongoing | Re-check after 2-3 more weeks of live data |
| 9 | ~13 old sim-log rows never marked VOID (cosmetic) | ⚠️ Low | Daily grader keeps re-flagging harmlessly | 100% (confirmed) | One-time cleanup script, low priority |
| 10 | Duplicate unused `data/slip_log.json` file | ℹ️ Low | Housekeeping only, not read by any code | 100% (confirmed) | Delete or archive |
| 11 | Match Winner (moneyline) not tracked by the evidence system | ℹ️ Info | Unknown whether in current scope | Unclear | Confirm with you whether moneyline is currently part of Apex's job |

---

## Final Answer

**1. Is Apex ready for daily prop generation?**

**NO** — not as currently running. The model and code are in good shape on
disk (both dispersion fixes are sound per today's backtest, the safety
pass is tested), but the two processes that actually generate boards and
handle slips are running code from before every one of today's changes.
Nothing you'd see on a real board today reflects the work done this
session. This is a same-day fix (restart + verify), not a rebuild — but
until that restart happens, the honest answer is no.

**2. What is the single largest remaining risk?**

That the fixes aren't live. Every other finding in this audit (aces
calibration, DFs thinness, safety-pass gaps) is either caused by or masked
by the fact that the running bot and Mission Control processes are weeks
stale relative to the code on disk.

**3. What should be the next investigation after all recent work?**

Restart both processes, then run a same-day live verification: pull a
fresh board through the running bot (not a one-off script) and confirm the
aces/DFs probabilities actually differ from what the pre-fix backtest
called "old_prob." Immediately after that, resolve the Fernandez/Andreeva
settlement gap before its stat sheet ages out, and gate `total_sets`/
`tiebreaks` off the board until they have real settled history.
