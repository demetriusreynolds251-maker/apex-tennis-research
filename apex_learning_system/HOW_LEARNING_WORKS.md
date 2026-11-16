# How Apex learning works (plain words)

Updated Oct 24, 2026 (save point `before-learning-overhaul`).

## The nightly steps

| Time (CT) | Step | What goes in | What comes out | Can it change picks? |
|---|---|---|---|---|
| hourly | **props DB settle** (`apex_props_db.py`) | SportsAPI365 box scores | win/loss for every PrizePicks prop in `data/props_db.sqlite` | No |
| 11:00 PM | **Nightly grading** (`learning_agent` in `openclaw_core.py`) | the day's /fetch picks (`data/picks_archive/picks_<date>.json`) | each pick graded, first from props DB, then the results API. An AI note on why each one won or lost (log only). Picks it can't grade go to the waiting list. | No |
| 11:20 PM | **Retry** (`retry_pending_engine`) | the waiting list (`data/learning/pending_results.json`) | tries props DB, then the results API. A pick that keeps failing is set aside (`quarantine.json`, kept, never deleted). | No |
| 11:30 PM | **Catch-up + card** (`apex_learning_v2.py nightly`) | props DB, waiting list, manual review, set-aside list | grades whatever props DB can, labels what can never be graded, posts **one** #learning card | No: suggestions only |
| 6:55 AM | **ALIS report** (`apex_learning_engine.py`) | graded history | long report in #apex-learning-intelligence-system-report (unchanged) | No |
| 9:00 AM | **Alert cards** (`apex_alerts.py`) | background tests | PROMOTION CANDIDATE / TEST FAILURE cards when a test finishes | No |

## What the #learning card shows
- ✅ How many 70%+ picks settled today and how many won, plus the Top 3 / Elite 6 record for the day.
- 📊 What's working and ⚠️ what's slipping: hit rates for 70%+ picks over the last 14 days (Oct 9 or later), by stat and side, compared with what the engine said.
- 📏 Win Prob check: do 70-75%, 75-80% and 80%+ picks really win that often?
- ❌ Each Top 3 / Elite 6 pick that lost, in one line, using the real score (for example "16 games in the match, needed over 16.5 (6-2 6-2), one-sided match").
- 💡 Suggestions, if any. Each one has a number and its backtest ("would have taken out 4 Top 3/Elite 6 picks this week, 1 won, 3 lost"). **Nothing changes until owner says "go learn N".** The details are in `data/learning/suggestions.json`.
- 🗂️ One housekeeping line: how many picks are still waiting, how many can't be graded.

The full numbers (by line band, tour, Win Prob band, board, pick type) go to `apex_learning_system/reports/learning_numbers_<date>.md`. Internal counters (quarantine, retries, Serper) go to `data/logs/learning_health.log`, not Discord.

## Rules the learning follows
- It only learns from **Oct 9 or later** picks with a real result. Goblin/Demon LESS are left out because they can't be played.
- Every pick is counted once (same player, opponent, stat, line, side, date = one pick). `data/learning/graded_picks.json` is the ledger.
- It **never** changes picks, weights, floors or rules on its own, and never suggests lowering the 70% Win Prob / Apex 67 floors. The only kinds of suggestion are "hold a stat+side off Top 3/Elite 6" or "raise one stat's floor to 75%", and only with enough picks behind them (25+ picks, or 20+ in the 70-75% slice).
- If the hourly category gate already holds a stat, it is labelled that way and not suggested again.

## What was broken (fixed Oct 24)
1. **The repeating block in #learning.** `"="*38 + "\n" "🏁 SETTLEMENT HEALTH\n" "="*38` — Python glues the middle strings together *before* multiplying, so the block was repeated 38 times: 9 Discord messages every night. That block now goes to the log file.
2. **Behind on grading.** The 11 PM step only asked the results API, which missed about 2 of every 3 picks (64 of 195 on Oct 24), even though props DB already had the results. Missed picks piled up: 1,574 set aside, 23.4% resolution rate. Now props DB is checked first (131 of 195 on Oct 24), and the catch-up graded **306 old picks** from props DB.
3. **Set-aside list cleaned up (nothing deleted).** 633 rows are from before Oct 9 (mostly the Oct 4 "3 day limit" batch), labelled `BEFORE_LEARNING_WINDOW`. 520 have no result anywhere, labelled `UNRESOLVABLE_NO_RESULT_SOURCE`. 247 were graded, labelled `GRADED_FROM_PROPS_DB`. 222 retirements/walkovers stay as they were.
4. **Manual review emptied.** 35 stuck picks (Stearns v Siniakova, Xinyu Wang v Xiyu Wang, etc.): 12 were retirements/walkovers (void), 6 graded with full names (so the two Wangs can't be mixed up), 17 had no result source.
5. **AI loss notes all "?".** The AI wrote a sentence after its JSON, so every note failed to save. Now only the first JSON object is read.
6. **AI quoted card banner text** ("Total Games record 1066-650", "UNDERPERFORMING", "attention low") as evidence. It now gets only the real facts: player, stat, line, side, Win Prob, actual result.
7. **"GREEN only" filter threw out every pick.** Picks stopped carrying a color, so the learning history stayed empty since July. It now uses the 70% Win Prob floor (what GREEN used to mean).
8. **Weight proposals.** The prop weights in `weights.json` aren't used by scoring any more, so a weight proposal would change nothing. That is why `weights.json` hasn't changed since Jul 3. The new suggestions (hold a stat / raise a floor) are about things that really change the boards. They are still proposals only.
9. **Dataset A outcomes.** Retry results from props DB are saved with the source label Dataset A accepts (`pending_results_json`). 67 outcomes were written on Oct 24.

## Undo
Save point `before-learning-overhaul`: `backups/before-learning-overhaul_2026-10-24/` holds the old code and every learning file (pending, manual review, quarantine, signal history, both weights files, props DB). To go back, copy those files back and restart the bot and the scheduler.
