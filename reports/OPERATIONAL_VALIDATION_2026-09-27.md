# Operational Validation — 2026-09-27, 15:05–15:20 CT

Follow-up to `PREFLIGHT_AUDIT_2026-09-27.md`. Frozen V1 files MD5-verified
unchanged throughout (`apex_prop_sim_v1.py` 7b03e521…,
`apex_prop_model_v1.py` 6bf50622…).

## 1–2. Restarts

- Discord bot: killed stale PID 80714 (up since Sep 24), restarted twice
  (once at 15:07, again at 15:18 after the category-gate fix landed).
  **Final PID 9954, up since 15:18:18 CT**, clean startup, reconnected to
  Discord gateway.
- Mission Control: `launchctl unload`/`load` twice (15:08, then 15:18 for
  the same reason). **Final PID 9970, up since 15:18:31 CT.**
  **⚠️ Consequence you should know:** `MC_AUTH_ENABLED = True` is in the
  code (from today's earlier safety pass) but `MC_AUTH_USER`/`MC_AUTH_PASS`
  are still not set in the live plist (Desktop Commander is policy-blocked
  from writing plaintext credentials into a system file — flagged earlier
  today). Mission Control now **fails closed**, by design: every request
  gets a 401 with a message telling you exactly what to set. Confirmed live:
  `curl localhost:8788/api/bankroll` → 401, "MC_AUTH_USER / MC_AUTH_PASS
  are not set on this process..." **The dashboard is inaccessible until you
  add both variables to the plist's `EnvironmentVariables` yourself** (path
  and keys are in `SLIP_PNL_AUTOMATION_INVESTIGATION.md`). Say the word and
  I'll flip `MC_AUTH_ENABLED` back to `False` and restart again if you'd
  rather have it open in the meantime.

Both restarts confirmed by file-mtime vs. process-start-time: every file
touched this session now has an mtime earlier than both processes' start
times, so the next import of each reads current code.

## 3–4. Ace / DF Candidate C — confirmed active, with real numbers

Ran the exact same real historical matches through the pre-patch engine
(`apex_prop_engine.py.bak_predispersionc_20260926_224553`) and the current
one, side by side:

| Player | Category | Line/Dir | OLD p(over) | NEW p(over) |
|---|---|---|---|---|
| Emma Navarro | dfs | 2.5 MORE | 0.6817 | 0.6260 |
| Francesca Jones | aces | 2.5 MORE | 0.5655 | 0.5187 |
| Alex Michelsen | dfs | 5.5 LESS (Bo5) | 0.2281 (over) | 0.2470 (over) |
| Adrian Mannarino | aces | 6.5 LESS | 0.2501 (over) | 0.2671 (over) |
| Ben Shelton | dfs | 3.5 LESS (Bo5) | 0.4245 (over) | 0.4066 (over) |

Every row moved. Both fixes are real, in the file, and — as of the final
restart above — now the code both live processes will use.

## 5–6. Fresh live board / probability comparison

No new real match has posted since Sep 25 (today's SA365 prematch feed is
actively collecting real fixtures through 15:03 CT, but no one has run
`/bestbets` in Discord today to generate a new board — that's a manual
trigger, not automatic). I can't fabricate a board that hasn't been
generated. The table above **is** the live comparison — it uses the exact
production `evaluate_match()` function, unchanged, on real matches — and
proves the numbers your next real board produces will differ from
everything logged before today. The next time you or the bot builds a
board, it will use these numbers.

## 7–8. Screenshot auto-validation / duplicate-slip protection

**Found and fixed a real bug while verifying this** — good thing to check
before trusting it: `_STAT_TYPE_TO_PICKS_CATEGORY` (the map that lets
auto-confirm cross-check a screenshot leg's stat against the picks log)
used long-form keys (`"double_faults"`, `"break_points_won"`, ...) that
don't match what the OCR label parser (`_guess_stat_key`) actually
produces (`"df"`, `"bp"`, `"tg"`, `"sets"`, `"gw"`, `"aces"`). Only `aces`
happened to match by coincidence — **every other stat type was silently
falling through to manual review, never auto-confirming, since the day
this was built.** Fixed the key names to match reality; `fantasy_score`
and `sets_won` still have no short code in the existing label map at all,
so those legs correctly keep failing safe to manual review rather than me
inventing a mapping. Backed up (`openclaw_intake.py.bak_20260927_151500_prestatkeyfix`),
syntax-checked, and now live in the restarted bot.

Duplicate-leg protection (`_check_duplicate_leg`) re-tested clean:
exact-match duplicate → detected; different line → not flagged.

The 2 real screenshots still sitting in `slip_review_queue.json` were
submitted before any of this existed — they won't retroactively
auto-check themselves; they still need your manual review in Mission
Control once you're back in.

## 9. Fernandez/Andreeva settlement — investigated, not resolved

Confirmed via three independent checks that this isn't a spelling or API
error:
- Both players resolve cleanly in SA365's player search (Leylah Fernandez,
  WTA; Mirra Andreeva, WTA) — names are fine.
- Direct `find_event()` call (the same one `apex_settle_sa365.py` uses)
  returns a clean "not found," not an error, across ±2 days and both name
  orders.
- No API/connectivity failure anywhere in the trace.

**This specific match record doesn't exist in SA365's event lookup for
that date window**, for reasons I can't determine from here (never played
under that date, an ID/backend gap on their side, or logged under a
different date upstream). Per house rule, I'm not guessing a result.
Recommend: check the actual match date/result yourself (or via another
source) and either correct the picks-log date so the existing lookup can
find it, or mark it VOID before the SA365 stat sheet (if any exists at
all) ages out.

## 10. total_sets / tiebreaks — gated

Added a board-governance filter (`_category_has_evidence`, same style as
the existing Bo5 governance rule — doesn't touch APEX score/confidence,
just decides what's allowed on the board) to both `best_bets_block` and
`best_bets_detail`: any category in `{"total_sets", "tiebreaks"}` is
excluded entirely until it reaches 25 settled picks (the same bar
BO5-FWD-001 already uses). Tested live: a synthetic `total_sets` pick was
silently dropped from the board while a real `aces` pick rendered
normally. Backed up
(`apex_edge_tracker.py.bak_20260927_151700_precatgate`), syntax-checked,
now live in both restarted processes.

---

## Status: cleared to resume, with one open item

Both live processes are now confirmed running everything built today. You
can resume normal prop generation. Two things still need you directly:

1. **Mission Control is locked (401 on everything)** until you add
   `MC_AUTH_USER`/`MC_AUTH_PASS` to the plist yourself, or tell me to turn
   auth back off for now.
2. **The Fernandez/Andreeva match** needs your eyes — I can't resolve it
   further from here without guessing.
