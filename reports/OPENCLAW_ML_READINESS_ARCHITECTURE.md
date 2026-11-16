# OPENCLAW ML READINESS + LIGHTGBM ARCHITECTURE (v1.0, DESIGN ONLY)
# NO CODE. NO MODEL INFLUENCE. OpenClaw remains the sole decision engine.
# Built entirely with Python + Tennis API + SQLite. ZERO LLM tokens for
# data collection — this is a data-engineering problem, not an LLM one.

## GOVERNING CONSTRAINT (repeated because it governs every section)
LightGBM is DORMANT. It does not adjust confidence, override confidence,
change grades, compliance, posting, bankroll, Rule 24/30, Truth Lock,
Dominance, or REQs — until explicit future approval. Build the whole
infrastructure now; activate nothing. The risk we are eliminating is
NOT training risk — it is arriving at training-time with missing,
unstructured, or unrecoverable data. So OpenClaw starts collecting
everything now, cleanly.

═══════════════════════════════════════════════════════════════════════
## 1. ML READINESS ARCHITECTURE (the five layers)
═══════════════════════════════════════════════════════════════════════
L1 Tennis API → Python Collection Service (no AI)
L2 SQLite Data Warehouse (no AI) — long-term company asset
L3 Mission Control ML Readiness screen (no AI) — readiness, health, growth
L4 LightGBM (dormant; activates only at challenger threshold)
L5 LightGBM Challenger (compares to OpenClaw; never decides)
Data flows L1→L2→L3; L4 reads L2 when thresholds met; L5 surfaces in L3.

═══════════════════════════════════════════════════════════════════════
## 2. PYTHON DATA COLLECTION ARCHITECTURE (no LLM)
═══════════════════════════════════════════════════════════════════════
A standalone `openclaw_collector.py` (own LaunchAgent, daily) that:
- pulls ATP + WTA matches (completed + upcoming) from the Tennis API,
- normalizes every field deterministically (see §4),
- upserts into the warehouse by natural key (no duplicates),
- writes a collection-run row (rows added, errors, API calls, duration).
It NEVER calls an LLM. It shares the API-key discovery already used by
openclaw_core (no new secrets). Two independent collectors:
- DATASET A (Performance): hooks the pipeline's existing archive writes —
  every evaluated pick (GREEN/YELLOW/RED/REJECTED/moneyline), not just
  posted GREENs (training only on GREENs = severe selection bias).
- DATASET B (Tennis): pulls raw match/player/stat data daily regardless
  of whether OpenClaw evaluated anything — learns tennis itself.

═══════════════════════════════════════════════════════════════════════
## 3. SQLITE WAREHOUSE DESIGN — data/warehouse/openclaw.db
═══════════════════════════════════════════════════════════════════════
Tables (3NF, natural + surrogate keys, all timestamped, source-tracked):
- players(player_id PK, name, canonical_name, tour, current_rank, updated_at)
- matches(match_id PK, date, player_a, player_b, surface, tournament,
          round, tour, result, score, source, collected_at)
- match_stats(match_id FK, player_id FK, hold_pct, break_pct,
          surface_hold_pct, surface_break_pct, aces, df, source, PRIMARY
          KEY(match_id, player_id))
- rankings(player_id FK, date, rank, points, PRIMARY KEY(player_id, date))
- h2h(player_a, player_b, surface, a_wins, b_wins, updated_at)
- evaluations(eval_id PK, date, player, opponent, market, stat_type,
          direction, line, surface, tournament, round, eval_confidence,
          final_confidence, final_grade, dominance, req_count, gate11,
          gate11b, rule24, rule30, truth_lock, feature_echo_flags,
          compliance_category, compliance_cost, score_adjustments_json,
          reasoning_ref, outcome, source, created_at)
- moneylines(ml_id PK, date, player, opponent, surface, tournament,
          confidence, grade, signals_json, outcome, created_at)
- outcomes(subject_type, subject_id, outcome, resolved_at, source,
          PRIMARY KEY(subject_type, subject_id))
- model_readiness(market PK, sample_count, tier, last_trained,
          model_status, updated_at)
- collection_runs(run_id PK, dataset, started_at, finished_at,
          rows_added, api_calls, errors)
Relationships explicit via FKs; evaluations.reasoning_ref points to the
existing reasoning archive file (no blob duplication). Every table has
source + timestamp for audit. Versioning where records mutate (rankings,
readiness) via dated rows, not overwrites.

The queries the prompt requires all become one-liners:
  "DF GREEN picks"     → evaluations WHERE stat_type='double_faults' AND final_grade='GREEN'
  "Rule30 picks"       → evaluations WHERE rule30=1
  "HARD dominance"     → evaluations WHERE dominance='HARD'
  "Moneylines on clay" → moneylines JOIN matches USING surface='clay'
  "losing GREEN picks" → evaluations WHERE final_grade='GREEN' AND outcome='BUST'
  "every pick for X"   → evaluations WHERE player='X'
No code rewrites needed six months out — that's the point of 3NF here.

═══════════════════════════════════════════════════════════════════════
## 4. DATA QUALITY STANDARDS
═══════════════════════════════════════════════════════════════════════
- Canonical player names (one resolver, reused from openclaw_core's V8
  name resolution — the Arseneault/Pegula fix lives there; don't fork it).
- One unit per field (hold% always 0-1 float, never mixed with 0-100).
- Enumerated surfaces/tours/grades/markets (CHECK constraints).
- Natural-key upserts → no duplicate matches or evaluations.
- No nested JSON except explicitly-typed *_json columns (score_
  adjustments, signals) that are append-only records, never queried-into
  for filters (the filterable facts are promoted to real columns).
- Every row: source + collected_at/created_at. Nullable fields explicit.
- A nightly `warehouse_audit` run: null-rate per column, duplicate scan,
  orphan-FK scan, surface/enum violations → surfaced in Mission Control.

═══════════════════════════════════════════════════════════════════════
## 5. ARCHIVE STRUCTURE
═══════════════════════════════════════════════════════════════════════
data/warehouse/
  openclaw.db                 (live)
  archive/2026/atp/…          (yearly, by-tour parquet/csv exports)
  archive/2026/wta/…
  archive/2026/evaluations/…  (by-model, by-season)
  snapshots/openclaw_YYYY-MM-DD.db   (nightly full DB copy, last 30 kept)
Partitioned by year → tour → dataset type. Permanent, searchable
(SQLite ATTACH across yearly files), recoverable (snapshots), auditable
(collection_runs + warehouse_audit history).

═══════════════════════════════════════════════════════════════════════
## 6/7. MARKET READINESS TRACKING + TIERS
═══════════════════════════════════════════════════════════════════════
PER-MARKET readiness (never one global model — each market is its own ML
problem): double_faults, aces, games_won, break_points_won,
total_games, total_sets, fantasy_score, moneyline.
PROP TIERS:  0-99 COLLECTING(grey) · 100-249 EXPLORATION(blue) ·
250-499 PROTOTYPE(orange) · 500-999 CHALLENGER-READY(green) ·
1000-2499 ADVANCED(purple) · 2500+ MATURE(gold).
MONEYLINE TIERS: 0-999 · 1000-4999 · 5000-9999 · 10000-24999 ·
25000-49999 · 50000+ ELITE.
sample_count = rows in evaluations/moneylines for that market WITH a
resolved outcome (unresolved don't count toward training readiness).

═══════════════════════════════════════════════════════════════════════
## 8. MISSION CONTROL — ML READINESS SCREEN (mockup)
═══════════════════════════════════════════════════════════════════════
Sidebar gains: ▢ ML Readiness (after Bankroll).
┌ ML READINESS ─────────────────────────────────────────────────────┐
│ WAREHOUSE  ATP 12,340 · WTA 9,880 · evals 1,204 · ML 611  ↑ +240/wk │
│ HEALTH  nulls 0.4% · dupes 0 · orphans 0 · last collect 06:02 ✅    │
├────────────────────────────────────────────────────────────────────┤
│ DOUBLE FAULTS  324/500  ██████████████░░░░  PROTOTYPE (orange)      │
│ ACES           118/500  ████░░░░░░░░░░░░░░  EXPLORATION (blue)      │
│ MONEYLINE     4321/5000 ████████████████░░  PROTOTYPE               │
│ GAMES WON       47/500  ██░░░░░░░░░░░░░░░░  COLLECTING (grey)       │
├─ MODELS ───────────────────────────────────────────────────────────┤
│ (none active — all DORMANT until challenger threshold)             │
└────────────────────────────────────────────────────────────────────┘
Reads ONLY model_readiness + warehouse counts + collection_runs +
warehouse_audit. No AI. When a model activates (§13) it renders a card:
name · market · dataset size · train date · accuracy · agreement% ·
top features · status(DORMANT/TRAINING/CHALLENGER/ACTIVE).

═══════════════════════════════════════════════════════════════════════
## 9/10/11/12. COLLECTION PLAN · STORAGE · API · GROWTH
═══════════════════════════════════════════════════════════════════════
DAILY PLAN: 06:00 collector run — upcoming slate + yesterday's results +
ranking deltas; hooks pick-archive writes in real time for Dataset A.
STORAGE: SQLite scales to millions of rows; ~50k matches + 5k evals ≈
low hundreds of MB; snapshots ×30 ≈ a few GB. Trivial for the Mac Mini.
API USAGE (estimate, verify against your plan): ~1 slate call + ~30-60
match-detail calls/day ≈ 1,000-2,000 calls/month for Dataset B; Dataset
A is free (reuses evaluation data already produced). ZERO LLM tokens.
GROWTH: ATP+WTA ≈ 150-250 completed matches/week in season → ~10k
matches/year; evaluations grow with your slate volume. Per-market
challenger-readiness (prop 500) is realistically months away — which is
exactly why collection must start now.

═══════════════════════════════════════════════════════════════════════
## 13. AUTOMATIC ACTIVATION LOGIC
═══════════════════════════════════════════════════════════════════════
Nightly, per market: if sample_count ≥ challenger threshold AND
model_status='DORMANT' → (1) mark CHALLENGER-READY, (2) train first
LightGBM on that market's resolved-outcome rows, (3) set status=
CHALLENGER, (4) begin logging challenger metrics. Training is a Python
job on the warehouse; it touches NOTHING in the live pipeline. An
operator kill-switch in ops_config (ml_challenger_enabled=false by
default) gates even this — nothing trains until you flip it.

═══════════════════════════════════════════════════════════════════════
## 14. CHALLENGER MODE ARCHITECTURE
═══════════════════════════════════════════════════════════════════════
When ACTIVE-as-challenger, for each new pick the challenger predicts a
probability and Mission Control shows, READ-ONLY, alongside OpenClaw's:
  OpenClaw 72% | LightGBM 69% | Agreement HIGH
  OpenClaw 74% | LightGBM 51% | Agreement LOW → "MODEL DISAGREEMENT" flag
The flag is INFORMATION for you, never an action. LightGBM cannot move
the number, the grade, the slip, or anything. It measures, validates,
and challenges OpenClaw — it does not replace it. Disagreements become a
research signal ("why do the reasoning engine and the statistical model
see this pick differently?"), which is the whole long-term value.

═══════════════════════════════════════════════════════════════════════
## 15. DATABASE MAINTENANCE STRATEGY
═══════════════════════════════════════════════════════════════════════
Nightly: warehouse_audit (nulls/dupes/orphans/enum violations) → health
panel; VACUUM weekly; snapshot nightly (retain 30); yearly export to
archive/ then prune live rows older than N years if ever needed (SQLite
stays small regardless). All maintenance is Python cron via LaunchAgent,
logged to collection_runs, visible in Mission Control. The warehouse is
treated as a permanent asset: recoverable from snapshots, auditable from
run history, portable as plain SQLite + parquet.

## BUILD SEQUENCING (when you approve implementation — none built yet)
Phase 1: warehouse schema + Dataset A hook (capture every evaluated pick
now — this is the irreplaceable one; every day unbuilt is data lost).
Phase 2: Dataset B daily collector + warehouse_audit + ML Readiness
screen. Phase 3: activation logic + first challenger training (gated
off by default). Phase 4: challenger metrics in Mission Control.
Nothing here influences a single OpenClaw decision at any phase.
