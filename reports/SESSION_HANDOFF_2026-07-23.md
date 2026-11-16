# SESSION HANDOFF — 2026-07-21 through 2026-07-23
Project Apex Intelligence™ / OpenClaw — full session record.
Builds on SESSION_HANDOFF_2026-07-19.md. Read that one first for the
audit groundwork; this one covers everything since.

---

## 1. FINAL FILE STATE (hashes = the truth, always verify before/after copy)

| File | Final hash (first 8) | Deployed to Mac Mini? |
|---|---|---|
| `openclaw_core.py` | `dec090f5` | ✅ CONFIRMED (operator's own shasum, 2026-07-21) |
| `openclaw_ops.py` | `00341f5b` | ✅ CONFIRMED |
| `openclaw_mission_control.py` | `c8d9dccc` | ⚠️ Mini runs `a7939ddf` — functionally identical; `c8d9dccc` only fixes a misleading re-enable comment (see §2b.1). Deploy at leisure, no restart urgency. |
| `openclaw_intake.py` | `babeeae2` | ✅ CONFIRMED |
| `discord_bot.py` | `6f657147` | ✅ CONFIRMED |
| `command_chat_writer.py` | `8e23390c` | ✅ CONFIRMED |
| `DEMETRIUS_v7_9_6_HANDOFF.txt` | `58f23e13` (81,098 chars) | ❌ ALMOST CERTAINLY STALE ON THE MINI — see §1a below. A post-session review also found a THIRD variant (`a96c53e4`) circulating that is older still: missing the entire Confidence Conservation v7.9.8 section, still carrying the v7.9.5 raw-count-ceiling formula, the -5% 3-set deduction, and the v7.9.7 stacking cap. |
| `command_chat_tools.py` | `d58debca` | ❌ NOT DEPLOYED — but independently re-verified byte-for-byte by a second review, full test suite re-passed (25-tool schema↔dispatch sync, web_search routing proof, zero write statements). The copy is right; only the live-API leg on the Mini remains untested. |
| `command_chat_engine.py` | `7bed43c5` | ❌ NOT DEPLOYED — same, independently re-verified. |

### 1a. Prompt-file drift — the evidence, and the exact verification
This session's own Mini logs are the smoking gun: every startup on the
Mini (11:35 PM, 11:43 PM, 11:53 PM, 9:16 PM CT across both processes)
loaded `DEMETRIUS_v7.9.6_HANDOFF.txt` at **70,767 chars**. The delivered
`58f23e13` version is **81,098 chars**. The live file is not the
delivered file — no grep needed to predict the outcome, but the greps
below are the definitive check. Run on the Mini:

```bash
cd "/path/to/home/openclaw"
shasum -a 256 DEMETRIUS_v7.9.6_HANDOFF.txt      # want: 58f23e13...
wc -c DEMETRIUS_v7.9.6_HANDOFF.txt              # want: 81098
grep -c "PER-PLAYER CALIBRATION" DEMETRIUS_v7.9.6_HANDOFF.txt   # want: 1
grep -c "CONSERVATION" DEMETRIUS_v7.9.6_HANDOFF.txt             # want: 3
grep -c "CFEF TRIGGER 6, ADDED THIS SESSION" DEMETRIUS_v7.9.6_HANDOFF.txt  # want: 1
```

**If the hash isn't `58f23e13`, replace the WHOLE file with the
delivered version — do not patch individual sections.** The drift is
bigger than the two named edits: the stale variants are missing
Confidence Conservation v7.9.8 entirely, which was the fix for a
systemic double-charging bug. Then restart both LaunchAgents and
confirm the startup log shows the prompt loading at 81,098 chars.

**Second drift signal, same class:** the Mini's two processes loaded
DIFFERENT sizes of `DEMETRIUS_PROPS_DECISION_TREE.txt` — discord_bot
read 35,080 chars (11:35 PM and again 12:36 AM) while mission control
read 36,848 chars (11:43 PM onward). Either the discord bot hasn't
restarted since the newer decision tree landed, or two variants exist
on disk. After replacing the handoff file, restart BOTH agents and
confirm both logs show identical char counts for all three prompt
files.

Also delivered (documents, not code):
- `PROJECT_APEX_INTELLIGENCE_MASTER_USER_MANUAL.docx` — revised (Part V
  rewritten with dated changelog + 16 screenshots + new screen sections
  + Case Study 6; Rule 24 and BP Rule HONEST STATUS boxes corrected
  with real traced evidence).
- `MISSION_CONTROL_OPERATIONS_MANUAL.docx` — brand new, 21 chapters,
  72 panel-level cropped images interleaved per section.

---

## 2. WHAT HAPPENED THIS SESSION, IN ORDER

### 2a. Remaining audit items — all five closed
1. **Moneyline calibration hook** — wired into moneyline's compliance
   pass (reads `checks_passed`/flags; moneyline never calls the props
   citation extractor). `ML_Gate14_HomeCourtLean` now fed from its real
   source for the first time.
2. **Props Gate14 mislabel fixed** — props citations were firing the
   moneyline-named registry entry. Now correctly `Gate14_Props_Procedural`.
   One test's expected value updated to match (that's correct behavior,
   not a regression).
3. **Fifth orphaned-key bug** — `classification` read a key that never
   existed (real key: `match_type`, only known post-evaluation). Fixed at
   EVALUATION_COMPLETE, same pattern as the other four.
4. **Rule 32 / Cap 6 research** — surface-specific upset rates (25%
   grass → 35% clay) support both qualitatively; exact magnitudes need
   Calibration Center data, same honest caveat as all weight research.
5. **ML S4 fatigue overlap** — checked, NOT a bug: S4 is independent
   deterministic Python; props/moneyline never share a confidence number.

### 2b. Operator's second audit round ("fix everything but #3")
1. **Mission Control auth** — HTTP Basic Auth built, tested with 5 real
   HTTP requests. **THEN DISABLED at operator's explicit request** after
   the plist deployment fight (see 2d). Final deployed state: 
   `_require_auth()` returns True unconditionally on line 1 of the body
   (`# AUTH DISABLED BY USER REQUEST`). The full mechanism
   (`MC_AUTH_ENABLED` flag, `_check_auth`, timing-safe compare, 401 page,
   startup `[Auth]` log line) is intact underneath. **Re-enable path:**
   delete the unconditional `return True` line AND set
   `MC_AUTH_ENABLED = True`, set `MC_AUTH_USER`/`MC_AUTH_PASS` in the
   LaunchAgent plist (already contains the dashboard login, removed here) —
   harmless while unused), restart. Also fixed en route: BrokenPipeError
   noise in `_require_auth` (client-disconnect try/except).
2. **Discord posting bug** — `send_discord()` now returns real
   True/False (unconfigured=True by design; any failed chunk=False).
   All three POSTED transition sites gated on it; the moneyline
   screenshot path had the worst version (marked POSTED *before* even
   calling send). Failed posts now stay SCORING_COMPLETE with posted=0
   and a loud log line.
3. **Gate 14 real data — oldest open item, closed.**
   `v8_get_home_away_split()` (imported since v7.9.6, never called) now
   invoked in `research_agent()` for both players; surfaced in the
   evaluation prompt with three honest states (CONFIRMED / THIN_SAMPLE /
   NO DATA); Gate 14's instruction got concrete per-player tiers
   (real gap ≥15pp → -10%, 5-15pp → -8%, <5pp → -4%, thin/no-data →
   flat -8%); compliance check 16 upgraded to verify against the tiers
   when CONFIRMED, procedural-only otherwise.
4. **Compliance cost measured** — checklist growth = ~1,168
   tokens/call on Haiku ≈ $[amount]/eval ≈ $[amount]-15/month at 50/day. Fine.
5. **Real $ ROI** — `slip_roi_report()` in openclaw_ops.py: groups
   slip log by slip_id; counts only clean all-WIN (profit =
   payout−stake) or any-LOSS (−stake) slips with real dollar data;
   honestly excludes pending / push-void / missing-dollar /
   correlation-rejected / mixed-result (no Power-Play-vs-Flex data —
   never guessed). Rendered as the "🎯 AUTO-CAPTURED ROI" panel on
   Bankroll, explicitly separate from the manual ledger.
6. **Stale "14 checks" reference** — "Audit all 14 checks" → 18. (The
   other apparent instance was correct historical prose; left alone.)

### 2c. Health page failure — root cause was macOS, not code
Symptoms: many pages not loading; "Log file stale or missing";
"Dataset A warehouse is not readable." Diagnosis chain proved: all
hashes correct, sqlite3 opened Dataset A fine, but Mission Control's
Python got `PermissionError: [Errno 1] Operation not permitted` reading
`data/logs/discord_bot.log` → **macOS Full Disk Access for
/usr/bin/python3 existed but was toggled OFF.** Toggled on + full
bootout/bootstrap → `/api/state` returned real JSON, all green.
Residual notes: all 8 agents show OFFLINE/"no heartbeat" until the
first real evaluation runs (expected, not broken); Validation check is
🟡 (pre-existing, unrelated); discord_bot.log showed ~5 rapid restarts
at 11:35 PM CT before settling — watch for recurrence.

### 2d. The auth/plist deployment fight (context for why auth is off)
The updated plist repeatedly failed to land (`plutil -p` showed no
EnvironmentVariables), curl proved the env vars never reached the
process, and the corrected .py files weren't making it onto the Mini
either (no `[Auth]` startup line ever appeared). After several rounds
the operator said plainly they didn't want the login at all → auth
disabled as described in 2b.1. Lesson recorded: file-transfer to the
Mini is the fragile step; in-place `python3 -c` edits or heredoc writes
directly on the Mini are more reliable than download-and-copy.

### 2e. Command Chat — full system-wide expansion (NOT yet deployed)
Operator's ask: ask anything about the whole system ("did the warehouse
store today's API run?", "matches count?"), recommendations + web
research allowed, but NEVER able to change anything.
Built:
- **15 new read-only tools** in `command_chat_tools.py`, all thin
  wrappers over existing proven functions: get_system_health,
  get_agent_status, get_live_pipeline_flow, get_rule_command_summary,
  get_calibration_status, get_ml_readiness, get_confidence_calibration,
  get_roi_summary, get_warehouse_collection_status,
  get_warehouse_run_history, get_match_coverage, get_player_coverage,
  get_warehouse_health, get_collection_trends, get_data_source_quality.
- **web_search** server-side tool appended to TOOL_SCHEMA (with the
  cache_control breakpoint on the last entry — preserved).
- **System prompt rewritten**: hard read-only rule (no action tool
  exists at all); recommendations explicitly encouraged and distinct
  from actions; research discipline (internal data vs web findings kept
  visibly separate, never cross-presented).
- **sources_cited** now also logs server_tool_use web searches (query
  captured) for operator transparency.
- Tests: 7 assertions incl. schema↔dispatch exact sync (25 tools) and
  proof web_search never routes through client dispatch.
- **Deploy + smoke test on the Mini still required** (sandbox has no
  Anthropic API network path — the real-API leg is the one untested
  part, as always for Command Chat).

### 2f. Master Manual revisions
- Part V: dated "What's New" changelog (8 entries, 2026-06-09 →
  2026-07-21), 16 screenshots embedded with honest demo-data captions
  (screenshots show multi-sport placeholder data; system is
  tennis-only — stated plainly rather than hidden), new sections for
  every previously-undocumented screen, Calibration described from real
  code with an honest no-screenshot-exists note, Case Study 6 ("The
  Orphaned Key Bug, Five Times Over") in the exact
  Detection→Lesson format.
- Operator challenged two HONEST STATUS boxes → both re-traced against
  live code and **resolved with citations**:
  - **Rule 24**: "early cheap shortcut before expensive research" was
    factually wrong — research runs unconditionally first (lines
    7809 → 7823-29 → 7853). Rewritten: the gap is a GATE for one narrow
    form-noise correction, never evidence. And the "open question" vs
    RANKING IS NOT DOMINANCE: resolved — `_extract_dominance()` reads
    only the model's conclusion text, never the gap; two separate code
    paths. Box now ✓ CONFIRMED.
  - **BP Rule**: the three-tier suppression IS standalone Python in
    scoring_agent() (≥85% hard cap / 80-84% −12% / 75-79% −10%), not
    reasoning-embedded. Box now ✓ CONFIRMED with the real thresholds.
- Remaining HONEST STATUS boxes deliberately NOT touched yet (Gate 11
  pass-recording gap, Truth Lock naming, REQ framework depth, MORE/LESS
  path field) — each needs the same real trace before claiming answers.

### 2g. Mission Control Operations Manual — new standalone document
Built on the master manual's own styles/theme. v1: 40 pages, one
screenshot per chapter. Operator wanted visual alignment per section →
v2 (final): **72 panel-level crops** generated from the 19 screenshots
(PIL, fractional-height bands per the recorded layout descriptions),
each placed directly under the sub-heading it depicts. 21 chapters,
all 19 screens, every KPI/panel/button explained with data provenance,
HONEST STATUS callouts throughout (incl. Calibration's no-screenshot
note and the Bankroll exclusions box). Known limitation, stated to the
operator: crop boundaries derive from layout descriptions, not
pixel-verified — individual crops may need nudging if one clips a
panel; the generator (`/home/claude/mc_manual/` scripts + crops dir)
makes per-crop fixes cheap.

---

## 3. OPEN ITEMS FOR NEXT SESSION (priority order)

1. **Deploy Command Chat expansion** — copy `command_chat_tools.py`
   (`d58debca`) + `command_chat_engine.py` (`7bed43c5`) to the Mini,
   restart Mission Control, then real-API smoke test: ask "did the
   warehouse update today?" and "why is my health score 77?" and
   confirm real tool-cited answers + a web-search question.
2. **Verify the prompt files on the Mini per §1a** — the live handoff
   file is near-certainly stale (70,767 chars vs the delivered 81,098),
   and the decision tree shows a second drift signal between the two
   processes. Whole-file replace, never section patches; restart both
   agents; confirm both logs load identical char counts.
3. **Post-deploy smoke tests still outstanding** from the deploy
   package: run one real prop eval → check
   `data/calibration/rule_firings.json` fills; one real moneyline eval
   → `ML_Gate14_HomeCourtLean` fires from its real source;
   `rule_activations` count in ate.db non-zero; Dataset A spot-check
   that `classification`/`req_count`/`dominance_level`/
   `gate11b_dominance_key` are no longer null; typed slip entry
   regression; slip screenshot → Slip Review → confirm → real
   stake/payout in slip_log.json.
4. **Watch discord bot restart behavior** (the 11:35 PM CT rapid-restart
   burst) and the Validation 🟡.
5. **Trace the remaining manual HONEST STATUS boxes** (Gate 11 pass
   recording, Truth Lock naming, REQ framework, path field) with real
   code evidence — same standard as Rule 24/BP.
6. **Rule 32 / Cap 6** — still only qualitatively grounded; revisit
   once Calibration Center has settled volume.
7. **Phase 2 Apex Success metrics** — cost/win-rate joins across ATE +
   Dataset A; both old blockers cleared, join code still unbuilt.
8. **PrizePicks/Playwright dead code** — confirmed dead; operator said
   skip; delete whenever convenient.
9. **Auth** — parked, not dead. Full re-enable path in §2b.1. Password
   currently in chat history + plist; rotate if/when re-enabling.

## 4. STANDING FACTS WORTH RE-STATING
- Mac Mini path has a REQUIRED trailing space:
  `/path/to/home/openclaw`
- LaunchAgents: com.apex.discordbot, com.apex.openclawmissioncontrol
  (port 8788), com.apex.tenniswarehouse (daily 06:00).
- Prompt file on the Mini uses DOTS: `DEMETRIUS_v7.9.6_HANDOFF.txt`
  (loader checks both variants; match the real filename).
- Deploy ritual: backup → bootout both agents → copy files → delete
  *.pyc + __pycache__ → shasum verify → bootstrap both → check the
  `[Auth]`/startup lines in mission_control.log.
- Market comparison / odds capture: REJECTED by operator ("market data
  is a scam") — do not rebuild or suggest; Rule 9 stays absolute,
  moneyline screenshot odds remain display-only and unstored.
- Operator's standing standard: structured truth over assumptions —
  every claim traced to real code/lines; every "fix" tested with real
  assertions before delivery; honest gaps labeled, never papered over.

## 5. QUESTIONS FILE
The file attached with the handoff request arrived EMPTY (0 bytes of
content, nothing on disk). Questions unanswered because they never
arrived — operator needs to re-send or paste them.
