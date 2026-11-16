# Slip PNL Automation — Investigation (read-only, no changes made)

## 1. Current workflow — there are actually TWO paths, not one

Messages in `#slips-pnl` are routed by `discord_bot.py::handle_slips_message`:

**Path A — typed text** (`"AJ Lopez MORE 22.5 games | ... "` style entries, and later
`"AJ Lopez ✅ WIN | ..."` results):
```
Discord message
 → discord_message_classifier.classify_slip_message()   (regex: WIN/LOSS/PUSH/VOID/✅/❌ → "result", MORE/LESS → "entry")
 → openclaw_core.parse_slip_entry() / parse_slip_result()
 → writes straight to slip_log.json
```
**Zero manual verification exists on this path today.** Slip ID assignment,
leg parsing, PENDING status, and later WIN/LOSS resolution all happen
automatically the instant you type the message. This already is what you're
asking for.

**Path B — screenshot** (you post a picture of the slip):
```
Discord message (image attachment)
 → discord_bot.py::handle_slip_screenshot()
 → openclaw_core.extract_slip_screenshot()   (vision model reads legs/stake/payout)
 → openclaw_intake.enqueue_slip_review()     (writes to slip_review_queue.json, status PENDING_REVIEW)
 → *** YOU manually confirm in Mission Control → Pick Intake → Slip Review ***
 → openclaw_intake.confirm_slip_review()     (only now calls parse_slip_entry(), same as Path A)
 → writes to slip_log.json
```
**This is the manual step you're thinking of.** It only exists on the
screenshot path.

Downstream of `slip_log.json` (same for both paths): `openclaw_ops.py::slip_roi_report()`
groups legs by `slip_id`, requires every leg to have resolved cleanly to
WIN/LOSS with stake+payout populated, and computes all-or-nothing profit.
Exposed at `GET /api/bankroll` → `auto_roi`.

**Important wrinkle:** there is a *second*, entirely separate bankroll
ledger — `openclaw_ops.py::add_slip()` / `POST /api/slip` — a hand-typed
"enter the final number yourself" tile in the Mission Control Bankroll tab.
It has no connection to `slip_log.json` at all. If you ever use both for the
same real slip, it double-counts. Worth knowing regardless of what you do
with the verification step.

## 2. Exact reason the manual step exists (A)

`openclaw_intake.py`, comment directly above `SLIP_REVIEW_QUEUE`:
> "a slip confirmation is different in kind — it's a claim about real money
> already staked, read by a vision model that can misread a dollar figure,
> so nothing gets written to slip_log.json until the operator has seen and
> (if needed) corrected what was read."

It exists **specifically to catch vision-OCR misreads of a screenshot**
(wrong stake, wrong payout, misread line/player), not because settlement or
PNL math themselves are untrusted.

## 3. Is it still needed? (B) / What's blocking full automation? (C)

- If you post slips as **typed text**, the manual step doesn't apply to you
  at all — that path is already fully automatic end-to-end, and always has
  been.
- If you post **screenshots**, the gate exists only because there's no
  automated cross-check today that the vision model read the stake/payout/
  line correctly. What's blocking automation isn't architecture — it's the
  absence of a validation layer that could safely auto-confirm the *common*
  case (extracted line matches the line Apex already evaluated and logged
  for that player/category/date in `apex_engine_picks_log_v1.csv`, stat
  abbreviation resolves cleanly, stake/payout are plausible numbers) and
  only route the *unusual* case (no match found, unrecognized stat, no
  stake, wildly out-of-range payout) to manual review.

## 4. Files/functions involved

| File | Function | Role |
|---|---|---|
| `discord_bot.py` | `handle_slips_message`, `handle_slip_screenshot` | ingress, routing, image dedup |
| `discord_message_classifier.py` | `classify_slip_message` | entry vs result vs ignore |
| `openclaw_core.py` | `extract_slip_screenshot`, `parse_slip_entry`, `parse_slip_result`, `_check_correlation` | vision extraction, leg parsing, logging, settlement |
| `openclaw_intake.py` | `enqueue_slip_review`, **`confirm_slip_review`**, `reject_slip_review` | the manual-review queue and gate |
| `openclaw_mission_control.py` | `/api/slip_review*` routes, `confirmSlipReview()` JS | UI for the manual step |
| `openclaw_ops.py` | `slip_roi_report()`, `add_slip()` | PNL/ROI aggregation (two separate ledgers) |

## 5. Safety-check findings (as requested)

| Check | Status |
|---|---|
| Duplicate screenshot | ✅ md5 image-hash, 10-min in-memory window — resets on bot restart |
| Duplicate typed slip | ❌ none — every typed entry gets a fresh slip_id, no identity check |
| Edited Discord message | ❌ not handled anywhere (`on_message_edit` doesn't exist in the codebase) |
| Deleted Discord message | ❌ not handled anywhere (`on_message_delete` doesn't exist) |
| Push/Void | ✅ handled, excluded from $ ROI (not zero-filled, just excluded) |
| Partial-win (mixed W/L legs) | ✅ detected, excluded from $ ROI — no partial-payout-tier math exists yet |
| Same slip posted twice (typed) | ❌ no protection |

## 6. Proposed change (NOT applied — you said don't change anything yet)

Two independent decisions, since the two paths are unrelated:

**If you use typed entries:** nothing to remove — already automatic. The
real gaps to close there are the ones with ❌ above (no dedup, no edit/delete
handling), which are a different ask than "remove manual verification."

**If you use screenshots and want to shrink the manual step (not eliminate
it blind):** add an auto-validate function in `openclaw_intake.py` that runs
*before* enqueueing:
- look up each extracted leg against `apex_engine_picks_log_v1.csv` (same
  player/category/date) — if line matches within tolerance and stat/direction
  resolve cleanly, auto-call `confirm_slip_review`-equivalent immediately;
- only enqueue to `slip_review_queue.json` (today's manual step) when a leg
  fails that check.
This keeps the gate for exactly the failure mode it was built for (bad
vision reads) while auto-clearing the common case.

## 7. Risks

- Mission Control's auth is currently **disabled** (`_require_auth` returns
  `True` unconditionally) — today the manual confirm step is also the only
  thing standing between a misread and money-tracking data being trusted.
  Full automation removes that backstop entirely; worth re-enabling
  `MC_AUTH_USER`/`MC_AUTH_PASS` first regardless of this decision.
- No line-level validation exists yet for the auto-confirm path proposed
  above — if built carelessly it could silently misfile a slip with a wrong
  stake with nobody ever looking at it again.
- Two-ledger double-counting (item 1) exists independent of this change and
  will get worse, not better, the more automated posting becomes.

## 8. Rollback plan (once/if a change is made)

- The proposed auto-validate function is additive — it only shortcuts the
  *confirm* call, using the exact same `confirm_slip_review()` →
  `parse_slip_entry()` path everything already goes through. Reverting is
  deleting the new function and its call site; `slip_review_queue.json` and
  `slip_log.json` schemas are untouched.
- Take a timestamped backup of `openclaw_intake.py` and `slip_review_queue.json`
  before any edit, MD5 before/after, same discipline as the dispersion work.
