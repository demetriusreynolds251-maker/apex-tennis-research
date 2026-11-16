# Slip Automation Safety Pass — Deployment (2026-09-27)

All four priorities built in order. Frozen V1 files verified unchanged
(MD5 before/after). No real data files were mutated — a test call
accidentally wrote one synthetic row to `data/ops_center/slip_ledger.json`
during priority-2 testing; caught immediately and restored to its original
`[]` before moving on.

## Backups (all timestamped `_preslipautomation`, before any edit)
`openclaw_core.py`, `openclaw_ops.py`, `openclaw_mission_control.py`,
`openclaw_intake.py`, `discord_bot.py` — `.bak_20260927_095920_preslipautomation`
`~/Library/LaunchAgents/com.apex.openclawmissioncontrol.plist` — `.bak_20260927_100526_preauth`

## Priority 1 — Duplicate typed slips: DONE
`openclaw_core.py`: new `_check_duplicate_leg()`, wired into both leg-entry
branches of `parse_slip_entry()`. A leg matching (bet_type, player,
direction, line, stat_type, date) against anything already logged that day
(PENDING or resolved) is skipped and logged visibly as `DUPLICATE_SKIPPED`
— never silently dropped, never double-counted. Tested against synthetic
in-memory data (no file writes): exact match caught, different line/day
correctly not flagged.

## Priority 2 — Bankroll ledger double-counting: DONE
`openclaw_ops.py`: new `_check_manual_auto_overlap()` blocks `add_slip()`
(the manual Bankroll-tab entry) from adding a slip that fingerprint-matches
(date, stake, payout, leg count) an already-resolved auto-tracked slip —
raises a clear error instead of silently adding a duplicate. New
`manual_auto_overlap_report()` scans everything already in both ledgers and
surfaces existing overlaps. Wired into `GET /api/bankroll`
(`manual_auto_overlaps` field) and rendered as a red warning panel in the
Bankroll tab. Tested with a mocked `slip_roi_report()` — collision and
no-collision cases both correct; real ledger confirmed still `[]` after.

## Priority 3 — Mission Control auth: CODE DONE, NOT YET LIVE
`openclaw_mission_control.py`: removed the unconditional
`return True  # AUTH DISABLED BY USER REQUEST` short-circuit, set
`MC_AUTH_ENABLED = True`. This is the complete code-side re-enable — but
I could not add `MC_AUTH_USER`/`MC_AUTH_PASS` to the **live**
`~/Library/LaunchAgents/com.apex.openclawmissioncontrol.plist` myself;
that write was blocked by policy as a plaintext-credential write, and I'm
not working around it. **Do not restart the Mission Control launchd job
until you've done this, or the dashboard will 401 on every request:**

1. Open `~/Library/LaunchAgents/com.apex.openclawmissioncontrol.plist`
2. Add an `EnvironmentVariables` dict with `MC_AUTH_USER` / `MC_AUTH_PASS`
   (a ready-made version with credentials you set earlier already exists
   at `com.apex.openclawmissioncontrol-2.plist` in this repo — copy its
   `EnvironmentVariables` block over, or set your own)
3. `launchctl unload ~/Library/LaunchAgents/com.apex.openclawmissioncontrol.plist`
4. `launchctl load ~/Library/LaunchAgents/com.apex.openclawmissioncontrol.plist`
5. Confirm: dashboard should now prompt for a login (Basic Auth) instead of opening directly

One thing worth knowing: `com.apex.openclawmissioncontrol-2.plist`
already has your Mission Control username/password sitting in plaintext in
this project folder. Worth keeping in mind if this folder is ever backed
up, synced, or shared anywhere.

## Priority 4 — Screenshot auto-validation: DONE
`openclaw_intake.py`: new `try_auto_confirm_slip()` — cross-checks every
extracted leg against `apex_engine_picks_log_v1.csv` (player + category +
exact line, within a 3-day window). All legs match → confirms through the
same `parse_slip_entry()` path the manual button uses (inheriting the
priority-1 dedup and existing correlation gate) and logs straight to
`slip_log.json`. Any leg mismatched, missing stake/payout, or a moneyline
leg (never verifiable against this log) → returns `None`, unchanged.
`discord_bot.py::handle_slip_screenshot` tries this first; only falls
through to `enqueue_slip_review()` (Slip Review queue) when it returns
`None`. Tested against real historical picks-log rows (read-only): correct
match, wrong line, wrong player, date-out-of-window, and moneyline all
behaved exactly as designed; guard-rail cases (no legs, missing stake,
unmatched leg) confirmed to never reach `parse_slip_entry`.

## Net effect on your stated goal
Screenshot → OCR → cross-check → all legs match → **auto-confirmed, logged,
PNL updates itself, no Slip Review needed.** Any mismatch still lands in
Slip Review exactly as before — nothing about that fallback path changed.
Real hit rate on "how often this clears automatically" isn't measurable
yet (needs a stretch of live screenshots to observe); it depends on how
consistently the evaluated pick's exact line survives onto the PrizePicks
board unchanged.

## Rollback (any single priority, independently)
Priority 1/2/4 are additive gates inside existing functions — restoring
the matching `.bak_20260927_095920_preslipautomation` file for that one
module and confirming compile + MD5 removes it cleanly; `slip_log.json`
and `slip_ledger.json` schemas are untouched either way.
Priority 3: restore `openclaw_mission_control.py` from the same backup
(puts the unconditional bypass back) — no launchd action needed unless you
already reloaded the service with auth live, in which case reload again
after restoring the file.
