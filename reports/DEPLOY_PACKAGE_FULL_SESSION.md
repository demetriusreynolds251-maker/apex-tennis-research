# DEPLOY PACKAGE — FULL SESSION — 2026-07-19/21
Everything built, fixed, and verified since SESSION_HANDOFF_2026-07-19.md.
Seven files. All additive or backward-compatible — no existing caller's
behavior changes unless it was a confirmed bug.

**⚠️ IMPORTANT — Mission Control now requires authentication to start.**
See the new "ACCESS CONTROL" item below before restarting the
LaunchAgent, or the dashboard will refuse every request.

---

## FILES & HASHES (final, after every round this session)

| File | Before | After |
|---|---|---|
| `openclaw_core.py` | `919ac2eb...` | `dec090f5...` |
| `openclaw_ops.py` | `d597f3ee...` | `00341f5b...` |
| `openclaw_mission_control.py` | `881726bd...` | `0a82030b...` |
| `openclaw_intake.py` | `dd10c57e...` | `babeeae2...` |
| `discord_bot.py` | `a362d487...` | `6f657147...` |
| `command_chat_writer.py` | `19aa01ce...` | `8e23390c...` |
| `DEMETRIUS_v7_9_6_HANDOFF.txt` | `f2090507...` | `58f23e13...` |

Full hashes are in each file's own `.diff` — included alongside this

package for review before overwriting anything on the Mac Mini.

---

## WHAT'S IN THIS BATCH

### 1. Five real data-integrity bugs found and fixed (`openclaw_core.py`)
All five are the same species: a Dataset A capture line reading a dict
key that was never actually set, so it silently wrote `None` forever.
**None affected the live pick** — scoring reads the correct keys
everywhere it matters. All five corrupted the *historical record* your
Rule Command Center and calibration tools depend on:
- `dominance_level`, `req_count`, `reasoning_text` — reading nonexistent
  keys at the `EVALUATION_COMPLETE` capture.
- `gate11b_dominance_key` — captured *before* evaluation even runs, when
  dominance can't exist yet under any key.
- `classification` — same two-part failure; real value lives under
  `match_type`, only knowable after evaluation.
Found via a systematic sweep of all 31 Dataset A capture points in the
file, not just the one caught by accident.

### 2. A real mislabel from earlier in this session, caught and fixed
The props-side calibration hook was firing `ML_Gate14_HomeCourtLean`
(moneyline's registry entry) from *props* citations — wrong source.
Corrected to `Gate14_Props_Procedural`. `ML_Gate14_HomeCourtLean` is now
fed from its real source for the first time — moneyline's own
compliance audit.

### 3. Calibration tracking — real measurement for previously-unverified rules
`PROVISIONAL_RULES` now includes RBMD, LPAB_PSAR, Gate14 (both props and
moneyline versions, separately), Rule 9, CFEF, and the new Rule30/CFEF
stacking check — nine rules whose real hit rate can now be measured over
time instead of just hoped for. Moneyline's compliance pass now feeds
this too (`openclaw_core.py`), not just props.

### 4. Four new compliance checklist items (18 total, was 14)
- **15 — Rule 9**: flags market/odds/seeding used as evidence for
  direction or dominance.
- **16 — Gate 14 (props)**: procedural-only check (per-player home data
  still isn't wired in — see below), verifies it was never used to flip
  direction or override HARD dominance.
- **17 — CFEF**: verifies extender/fatigue evidence wasn't silently
  ignored on TG LESS picks.
- **18 — Rule30/CFEF stacking**: verifies the model doesn't charge one
  tired match twice under two different rule names.

### 5. Two real duplication bugs fixed
- **Correction 24 / Competition-Context Filter**: were asking the model
  the same three questions twice, under different names, every time the
  rank gap hit ≥100. Merged into one instruction.
- **Rule 30 / CFEF stacking**: added an explicit reconciliation clause
  in `DEMETRIUS_v7_9_6_HANDOFF.txt` — if the same match drives both
  deductions, apply the larger only; if genuinely different matches,
  both stand.

### 6. Rule 31 — first real enforcement of any kind
Existed in the prompt with zero code and zero compliance verification.
Built as real Python (`rule_31_correlation_check()`) since it's
inherently a cross-pick comparison — no single-evaluation audit could
ever check it. Runs batch-wide after scoring, flags correlated LESS
exposure on court-speed-sensitive props at the same tournament,
disclosure-only, never touches confidence.

### 7. New Mission Control capability — Calibration screen
Sidebar → Learn & Improve → Calibration (`openclaw_ops.py` +
`openclaw_mission_control.py`). Shows every provisional rule's
fired/settled count and real hit rate once it clears its minimum
sample.

### 8. New Mission Control capability — Confidence calibration report
Confidence Audit screen now includes a predicted-vs-real reliability
table: for every settled pick, does a 70-75% pick actually hit ~70-75%
of the time? No manual "run" step — same as every other report in the
app, it's a live query that shows up when you open the screen.

### 9. Slip screenshot review — real $ ROI groundwork
`#slips-pnl` now accepts a slip-confirmation screenshot. Read via
vision, staged as an editable card in Mission Control → Pick Intake →
Slip Review — nothing logs until you confirm it. Existing typed-entry
path is completely unchanged. (`openclaw_core.py`, `openclaw_intake.py`,
`discord_bot.py`, `openclaw_mission_control.py`)

### 10. Memory-node date field (`command_chat_writer.py`)
Memory Center graph nodes now carry their real date — was a genuine
gap, never selected into the query.

### 11. PrizePicks/Playwright pipeline — confirmed dead, not yet removed
Verified with real files this session: no LaunchAgent runs it, nothing
imports it live, Mission Control's intake shares zero code with it.
Still sitting there at your request — safe to delete whenever you want,
separate from this batch.

### 12. Access control — Mission Control had none (real gap, now fixed)
Found during this session's own audit: zero authentication anywhere,
bound to all network interfaces, now displaying real financial data.
Added HTTP Basic Auth via `MC_AUTH_USER`/`MC_AUTH_PASS` environment
variables — **the server refuses every request if these aren't set,
by design**, rather than silently falling back to no-auth. Tested with
5 real HTTP requests against an actual running server.

### 13. Discord post failures could be silently recorded as successful posts
`send_discord()` returned nothing — no caller could tell if a post
actually reached Discord. One of the three POSTED-marking call sites
was marking Dataset A as posted *before* even calling `send_discord()`.
Fixed: `send_discord()` now returns real success/failure, and all three
sites are gated on it — a failed post now correctly stays at
`SCORING_COMPLETE` with `posted=0` and logs loudly, instead of lying
about what happened.

### 14. Gate 14 now uses real per-player data — closes the oldest open item
`v8_get_home_away_split()` was imported at the very start of this
session and never called. Now wired into `research_agent()`, surfaced
directly in the evaluation prompt for both players, and Gate 14's own
instruction was extended with a real per-player calibration table
(real gap ≥15pp → -10%, 5-15pp → -8% as before, <5pp → -4%) instead of
always using the flat default. Compliance check 16 upgraded to verify
against these real numbers when available, falling back to the
original procedural-only check when the data is still too thin.

### 15. Real $ ROI — now computed, not just captured
New `slip_roi_report()` groups the auto-captured slip log by slip,
resolves clean WIN/LOSS slips into real profit/loss, and **honestly
excludes** anything ambiguous (pending, missing dollar data, PUSH/VOID,
correlation-rejected, or a mixed win/loss result this system has no
partial-payout data for) rather than guessing. Shown as a new panel on
the existing Bankroll screen, clearly labeled as separate from the
manual entries already there — nothing about the existing manual
tracker changed.

---

## DEPLOY STEPS

**Before anything else**: add to the Mission Control LaunchAgent
plist's `EnvironmentVariables` dict:
```xml
<key>MC_AUTH_USER</key><string>your-chosen-username</string>
<key>MC_AUTH_PASS</key><string>your-chosen-password</string>
```
Skip this and the dashboard will start but refuse every single request
— that's intentional, not a bug.

```bash
cd "/path/to/home/openclaw"

# Backup first
for f in openclaw_core.py openclaw_ops.py openclaw_mission_control.py \
         openclaw_intake.py discord_bot.py command_chat_writer.py \
         DEMETRIUS_v7.9.6_HANDOFF.txt; do
  cp "$f" "$f.bak.$(date +%F)" 2>/dev/null
done

launchctl unload ~/Library/LaunchAgents/com.apex.discordbot.plist
launchctl unload ~/Library/LaunchAgents/com.apex.openclawmissioncontrol.plist

# Copy the 7 updated files into place here. Note: on disk this file is
# named "DEMETRIUS_v7.9.6_HANDOFF.txt" (dots) — the loader checks both
# dot and underscore variants, but match whatever your real filename
# already is so you're editing the one actually being read.

find "/path/to/home/openclaw/" -name "*.pyc" -delete
find "/path/to/home/openclaw/" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# Verify hashes match the "After" column above
shasum -a 256 openclaw_core.py openclaw_ops.py openclaw_mission_control.py \
              openclaw_intake.py discord_bot.py command_chat_writer.py \
              DEMETRIUS_v7.9.6_HANDOFF.txt

launchctl load ~/Library/LaunchAgents/com.apex.discordbot.plist
launchctl load ~/Library/LaunchAgents/com.apex.openclawmissioncontrol.plist
launchctl list | grep com.apex
```

`tennis_warehouse_collector.py` and its LaunchAgent are untouched — no
restart needed there.

---

## POST-DEPLOY SMOKE TEST

1. **Mission Control loads clean** — no JS console errors on first
   paint (Calibration and Confidence Audit both fetch new data on load).
2. **Calibration screen** (Learn & Improve → Calibration) — expect all
   9 rules at or near 0 fired until real evaluations run. Correct, not
   broken.
3. **Confidence Audit** — new "🎯 Calibration" table at the top will be
   empty ("No settled picks yet") until real outcomes are recorded.
4. **Slip screenshot** — send a real slip confirmation to `#slips-pnl`,
   confirm the bot replies with a summary and doesn't auto-log, then
   confirm/edit it in Pick Intake → Slip Review, check
   `data/slips/slip_log.json` for real `stake`/`potential_payout`.
5. **Existing typed slip entry** — type one the old way, confirm it
   still logs exactly as before (the one real regression risk worth a
   direct check, since `parse_slip_entry`'s signature changed).
6. **Run one real prop evaluation** — check
   `data/calibration/rule_firings.json` for RBMD/Gate14/CFEF/Rule9
   entries starting to appear, and confirm `rule_activations` in
   `ate.db` shows real citations.
7. **Run one real moneyline evaluation** — same check, confirm
   `ML_Gate14_HomeCourtLean` starts firing from real moneyline data now
   instead of never firing at all.
8. **Dataset A spot check** — after a real evaluation, query
   `evaluations` for that `eval_id` and confirm `classification`,
   `req_count`, `dominance_level`, and `gate11b_dominance_key` are no
   longer null.
