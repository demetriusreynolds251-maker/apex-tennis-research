# OPENCLAW OPERATIONS CENTER — TUI DESIGN (v1.2, DESIGN ONLY)
# Per instruction: design first, no implementation without approval.

## Philosophy
Every major bug this system has had lived in the gap between "the system
is doing something" and "the operator can see it." The Ops Center's one
job is closing that gap. Therefore: STRICTLY READ-ONLY against pipeline
state — it observes logs, archives, and launchctl; it never writes
weights, caches, or picks. The ONE exception is the Pending Approval
panel, which may invoke the same --approve/--reject CLI you already use
(explicit keypress + confirm, nothing automatic).

## Stack
Python Textual (single file `openclaw_ops.py`), run in a terminal:
`python3 openclaw_ops.py`. No daemon, no ports, no dependencies beyond
`textual` + the existing project. Refresh model: 2s tail of the log
file (the primary truth source — every agent already logs), 30s poll of
archives/launchctl/usage. Nothing hooks into the running bot process.

## Data sources (all already exist — zero bot changes required)
- data/logs/discord_bot.log + discord_bot_error.log (live tail)
- data/picks_archive/picks_*.json + reasoning_*.txt (ledger, grades)
- data/validation/run_history.json (GREEN trend, from the suite)
- data/proposals/pending_proposals.json (approvals)
- data/learning/signal_history.json + ml_signal_history.json (records)
- launchctl print gui/$UID/com.apex.discordbot (health/PID)
- The usage report values (parsed from log lines the bot already emits)

## Layout (80x24 minimum, panels grow with terminal)
┌─ HEALTH ──────────────┬─ ALERTS FEED (live) ───────────────────┐
│ PID 31416 ● RUNNING   │ 21:43 🛑 SYSTEM FAILURE — no pick ...  │
│ Uptime 2h11m          │ 21:40 ⚠️ Gate11 unverified ...          │
│ Last log line 3s ago  │ 21:38 ✅ WIN — Djokovic MORE 2.5 ...    │
│ Sched: 17:00/23:00 ok │ (color-coded 🛑/⚠️/✅, scrollback)      │
├─ PROP QUEUE ──────────┴─ ACTIVE EVALUATION ─────────────────────┤
│ tonight: 6 props      │ Kostyuk DF 2.5 — stage: COMPLIANCE (2) │
│ ✔ done 3  ⏳ active 1 │ Research→Eval→Compliance→Scoring→Post   │
│ ✖ failed 1  ⏸ queued 1│    ✔      ✔       ⏳         ·      ·  │
├─ CONFIDENCE LEDGER (selected pick) ─────────────────────────────┤
│ eval 72% → 72% GREEN | adjustments: (none) | REQs 4/4 | HARD    │
│ or: eval 65% → 59% (Compliance 2 Cat-A [Rule30, DirInt] x 3%)   │
├─ TODAY'S GREENS ──────┬─ COSTS ──────────┬─ APPROVALS ──────────┤
│ 🟢 2  🟡 4  🔴 1       │ calls 214        │ 🔔 1 PENDING          │
│ hit-rate (suite):     │ est $[amount] today  │ ml_serve 0.35→0.37   │
│ 71% last run ↑        │ retries 3/4 clr  │ [a]pprove [r]eject   │
└───────────────────────┴──────────────────┴──────────────────────┘

## The ten required panels → where each lives
1. Live Prop Queue → PROP QUEUE (parsed from batch log lines)
2. Active Evaluation Monitor → ACTIVE EVALUATION stage tracker (log
   phases: Research/Evaluation/Compliance attempt N/Scoring/Posted)
3. Confidence Ledger Viewer → LEDGER panel; arrow keys select any pick
   from today's archive, shows score_adjustments verbatim
4. Compliance Viewer → tab of LEDGER panel: flags, categories, status,
   attempt count, retraction/normalization log lines
5. Alerts Feed → ALERTS (mirrors #alerts-channel content from the log,
   so nothing depends on Discord delivery working)
6. Cost Dashboard → COSTS (usage-report log lines; the report that
   never reached Discord until tonight's channel-typo fix)
7. Bot Health Status → HEALTH (launchctl + log freshness heartbeat;
   log silent >120s while props queued = ⚠️ stall warning)
8. Daily GREEN Tracking → TODAY'S GREENS + suite trend arrow
9. System Failure Monitor → filter view of ALERTS (🛑 only) with count
   badge in HEALTH
10. Pending Approval Monitor → APPROVALS with keybound approve/reject
    (the one permitted write, via the existing CLI)

## Keybindings
q quit · TAB cycle panels · ↑/↓ select pick · ENTER open reasoning file
in pager · f filter alerts (all/🛑/⚠️) · a/r approve/reject (confirm) ·
g jump to GREENs · / search picks

## Failure honesty
Every panel renders its data age ("as of 3s ago"). If a source file is
missing/unreadable, the panel says exactly that — no blank optimism.
Same principle as the ledger: unexplained is worse than bad news.

## MISSION CONTROL PRINCIPLE (v1.1 addition — governs everything above)
The OpenClaw TUI is NOT a dashboard. It is a mission-control center.
The operator must be able to: (1) watch props move through agents,
(2) watch confidence change in real time, (3) watch rules activate,
(4) see failures immediately, (5) see GREEN candidates immediately,
(6) audit why a score changed, (7) operate remotely via Tailscale SSH.
Design around visibility and workflow, not statistics. The thing being
fought for months isn't better graphics — it's "show me what OpenClaw
is actually doing."

## v1.1 PANELS (added on collaborator review)

### A. Agent Workflow Visualization (highest priority)
Per-prop pipeline lane, not a stage label:
    Research      🟢
    Evaluation    🟢
    Compliance    🟡  (attempt 2)
    Scoring       ⚪
    Posting       ⚪
🟢 completed · 🟡 running · 🔴 failed · ⚪ waiting. One lane per active
prop; the operator literally watches the prop move through OpenClaw.
Source: log phase lines (already emitted per agent).

### B. Agent Reasoning Feed
Live "watching it think" stream for the selected prop:
    Research Agent
      ✓ Match verified   ✓ V8 packet loaded   ✓ Hold% loaded
    Evaluation Agent
      ✓ Dominance = HARD   ✓ REQs = 4/4   ✓ Anchor = 72%
Source: log lines + extracted fields from the archived evaluation as
each stage lands. (Full token-streaming would require bot changes —
Phase 3 option; log-granularity feed requires none.)

### C. Rule Monitor (selected prop)
    TRUTH LOCK      PASS      RULE 24        ACTIVE
    RULE 30         PASS      COMP CONTEXT   ACTIVE
    DOMINANCE       HARD      GREEN ELIGIBLE YES
Source: compliance checks_passed/failed + evaluated fields + injected-
correction markers. Saves manual audit reading.

### D. Confidence Flow Graph (the Djokovic-bug catcher)
Vertical waterfall of the conservation ledger:
    eval 72% → Serve-Stat Gate 72% → Rule30 72% → Compliance 69% → FINAL 69%
Every hop is a ledger entry; an unexplained hop renders in red. This
panel is the ledger made visual — it would have caught the stolen
GREEN instantly.

### E. Active GREEN Queue
    GREENS TODAY:  Djokovic 72% · Fritz 71% · Alcaraz 74%   (3)
GREENs are what gets played; they get their own always-visible panel,
above the YELLOW noise.

### F. Feature Echo Risk
    Djokovic — Rank Gap ├ Dominance ├ Match Control └ Comp Context
    Risk: HIGH
Source: green_validation_suite.py --echo-trace output for today's
reasoning files (the suite is the engine; this panel is its window).

### G. OpenClaw Health Score
    V8 API 🟢  Discord 🟢  Compliance 🟢  Scoring 🟢  Archives 🟢
    Health Score: 98%
Composite of: V8 reachability, log freshness, last Discord send OK,
zero unexplained-ledger alerts today, archives writable. One glance.

### H. Validation Suite Panel
    Last validation: GREEN hit 71% · Archived 24 · Preserved 21 ·
    Lost 3 · New 2 · trend ↑
Source: data/validation/run_history.json — the benchmark lives inside
the TUI.

## VISUAL REFERENCE EXAMPLES (what "TUI" means here)
Aim for the information density and liveness of these, not a log viewer:
- btop (system mission control): https://github.com/aristocratos/btop
- k9s (Kubernetes ops center — closest spiritual match: live workloads
  moving through states, drill-in on any object): https://k9scli.io
- lazygit (panel navigation + action keybinds):
  https://github.com/jesseduffield/lazygit
- htop (health-at-a-glance): https://htop.dev
- Textual gallery (the framework's own dashboards):
  https://www.textualize.io/projects/ and https://textual.textualize.io
The target feel: k9s's "watch objects move through states" + btop's
health density, applied to props moving through agents.

## Build estimate & sequencing (upon approval)
Phase 1 (one session): Agent Workflow lanes (A), Confidence Flow
Graph (D), ALERTS, HEALTH+Health Score (G), APPROVALS — the set that
would have caught this week's bugs on sight. Phase 2: Rule Monitor (C),
GREEN Queue (E), Reasoning Feed (B), Validation panel (H), costs.
Phase 3 (requires bot changes, optional): true token-level reasoning
stream, Feature Echo live panel (F) wired to per-batch echo runs.
Nothing in Phase 1-2 requires bot code changes.

═══════════════════════════════════════════════════════════════════
# PERFORMANCE EXPANSION (v1.2 — approved design task, pre-implementation)
═══════════════════════════════════════════════════════════════════
The top of the TUI becomes a mission-control scoreboard answering the
operator's first question — "Am I winning?" — before anything else
renders. Four always-visible trackers. 80x24-safe. Identical over
Tailscale SSH (pure terminal, no browser, no ports).

## 1. UPDATED SCREEN LAYOUT (scoreboard pinned above v1.1 panels)
┌─ OPENCLAW COMMAND CENTER ──────────────────────────────────────────┐
│ GREENS   72/100  ✅ 71.4% (50-20) ██████████████▍░░░░  strk W4 L7  │
│ SLIPS    34/100  ROI +118%  net $[amount]  ██████▊░░░░░░  6/6:9 5/6:6│
│ MONEYLN  41/100  🟡 68.3% (28-13) ████████▏░░░░░░░░░░  strk W2    │
│ BANKROLL $[amount] / $[amount]   0.84%  ▍░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
├─ (v1.1 panels below: workflow lanes, flow graph, alerts, health…) ─┤
Status glyphs: ✅ ≥ target · 🟡 within 5 pts · 🔴 below. Each tracker
row is one line; ENTER on a row opens its detail panel (streaks, avg
GREEN confidence, last validation run, per-slip ledger, ML breakdown).

## 2. STORAGE DESIGN — data/ops_center/ (TUI-owned, pipeline-untouched)
- ops_config.json      → all goals/targets/bankroll (see §4). No
                          hardcoded values anywhere.
- green_tracker.json   → cache of completed GREEN picks:
                          [{date, player, stat, line, direction, conf,
                            outcome}] — DERIVED, rebuildable.
- slip_ledger.json     → manual entries, append-only:
                          [{id, date, stake, legs:[...], result:
                            "6/6"|"5/6"|"LOSS", payout, profit}]
                          + running bankroll snapshots. Schema carries a
                          "v" field for future expansion.
- ml_tracker.json      → completed moneyline picks, same shape as
                          green_tracker, SEPARATE file, separate math.
- All JSON, human-editable, restart-safe by construction (files ARE the
  state). Corrupt/missing file → panel says so and offers rebuild.

## 3. DATA FLOW DESIGN
- GREEN tracker: AUTO-DERIVED. Nightly learning already determines
  HIT/BUST per pick; the TUI joins picks_*.json (grade GREEN) with
  outcome records and caches to green_tracker.json on each refresh.
  Zero manual work; zero bot changes.
- MONEYLINE tracker: AUTO-DERIVED the same way from ML archives +
  ml_signal_history outcomes. Never mixed with props — separate file,
  separate calculations, separate report.
- SLIP tracker: MANUAL by design (only the operator knows what was
  actually staked). Entry via TUI form (keybind `s`): date, stake,
  legs, result, payout → profit computed. Where the existing
  #slips-pnl parsing already produced structured slip results, the TUI
  offers one-time import — but manual entry is the primary path.
- BANKROLL: starting_bankroll (config) + Σ slip profit = current;
  progress bar vs target_bankroll. Recomputed from the ledger every
  refresh — no stored running total to drift.
- ROI = net profit / total staked. Slip win% counts 6/6 and 5/6
  separately (payout-relevant), win-rate uses paying slips.

## 4. CONFIGURATION DESIGN — data/ops_center/ops_config.json
{
  "green_goal": 100,            // 100/250/500/1000/custom
  "green_target_hit_rate": 0.70,
  "slip_goal": 100,
  "ml_goal": 100,
  "ml_target_hit_rate": 0.70,
  "starting_bankroll": 500.00,
  "target_bankroll": 500000.00,
  "near_target_band": 0.05      // 🟡 window below target
}
Edited by hand or via TUI settings screen (`c`). Read on every refresh
— changing a goal never requires a code edit or restart.

## IMPLEMENTATION PLAN (for approval — no code until approved)
- Phase A (one session): ops_config + scoreboard row rendering from
  existing archives (GREEN + ML trackers auto-derived read-only), slip
  ledger schema + manual entry form + bankroll math.
- Phase B: detail drill-downs (streaks, calibration pull from
  run_history.json, per-slip ledger view), one-time slips-pnl import.
- Phase C: integrate scoreboard atop the v1.1 mission-control panels as
  one openclaw_ops.py application.
- Testing: synthetic archives + a scripted slip ledger; verify identical
  rendering in a plain 80x24 ssh session (no mouse, no truecolor
  assumptions).

## Open questions for the operator before implementation
1. Terminal-only on the Mac Mini, or must it work over Tailscale from
   the MacBook Air? (Textual handles both; affects nothing structural.)
2. Should approve/reject be included at all, or keep the TUI 100%
   read-only and leave approvals in the plain CLI?
3. Phase 1 first, or full build in one pass?
