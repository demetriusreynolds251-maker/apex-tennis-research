# APEX HANDOFF — 2026-08-30 (end of session)
Working dir: ~/Desktop/openclaw  (NOTE: moved from ~/openclaw; all launchd plists repaired)

## SHAs (verified at close)
apex_edge_tracker.py     402c6d9c
openclaw_core.py         129db3ef
apex_learning_engine.py  d25eb5aa
discord_bot.py           ee1d50d1
apex_price_feed.py       20ae45cc

## STATE
hand_settled 72 rows · sim forward 101 · picks log 101 · pending settlements 56
snapshots 2 (08-29, 08-30, both v002g) · hypotheses 4 · lessons 12
Projection MAE 3.69 (n=28) · bias +1.00 · out-of-band 21% (expected 20%)
Root cause: 11 losses classified — VARIANCE 7 (64%), MODEL_ERROR 3 (27%)
Selection Quality: LIVE, n=2 joined, INSUFFICIENT EVIDENCE (gate: n>=100, top-band >=20)
Bo5 forward test: 3 settled, milestone review #1 at 25

## DEPLOYED THIS SESSION (in order)
BO5-FWD-001   Bo5 as separate evidence stream; best_of column; refusal gates; milestones 25/50/100
BB-001/001b   Best Bets embed; evidence-weighted APEX SCORE; rescale (50 = break-even)
BB-002a       /bestbets CLI + board loader (reads pick log, no re-evaluation)
BB-002b       Discord command family in #general (text-triggered, not native slash)
BB-002c/c3    limit 15 · one slot per player · artifact clamp (>=95%)
BB-002d       evidence > probability: untested caps, band-credit gating
BB-002e       two-tier dedup: match props compete against BOTH players (9/9 selftests)
BB-002g       TRUTH-FIRST: removed ALL score caps; warnings replace suppression
BB-002h       fix: multiple match-level props per match (ValueError on .remove)
FMT-001       US Open main-draw date 08-31 -> 08-30 (five Bo5 matches were priced as Bo3)
SLAM-001      Gate 11-B slam matching survives punctuation ("U.S. Open")
CARDFIX-001/2 reasoning cards: one file per PICK (was one per match, ~66% were overwritten)
SETTLELOG-001 skip hand rows with empty actual (VOID rows crashed settle_log)
CONF-001      CONFIDENCE dimension (0-100) — independent of APEX SCORE, soft tie-break within 8 pts

## NEW MODULES
apex_selection_snapshot.py   freeze board beliefs BEFORE outcomes (--snapshot / --slip / --show)
apex_selection_quality.py    Purpose 2: score bands, rank bands, separation, monotonicity
apex_projection_analysis.py  Purpose 1: projection error, MAE, in-band %, drift
apex_root_cause.py           6-way loss classification (MODEL_ERROR / VARIANCE / etc.)
apex_error_registry.py       patterns + lesson state machine (Hypothesis->Observed->Supported->Validated)
apex_validation_loop.py      version comparison, adoption tracking (n>=100/side to validate)
apex_reasoning_audit.py      L5-A: parses reasoning cards, finds missing expected inputs
apex_card_index.py           card lookup by (player, category, date) — replaced glob matching
apex_l5b_reasoner.py         L5-B: LLM hypothesis proposer, Proposed-state only
apex_settlement_daemon.py    auto-settlement with confidence gates + pending queue
apex_h2h_settle.py           h2h/recent lookup: aces, DFs, breaks, games, sets + RET/WO detection
apex_large_miss.py           projection-miss forensics (z-spread, band breaches, concentration)
apex_penalty_impact.py       historical impact of proposed score penalties before deployment
apex_alis_daily.sh           runs the whole ALIS chain in one command

## DAILY ROUTINE
    cd ~/Desktop/openclaw
    /usr/bin/python3 apex_settlement_daemon.py --run       # dry run
    /usr/bin/python3 apex_settlement_daemon.py --commit    # write settlements + pending
    /usr/bin/python3 apex_edge_tracker.py --settle-log
    ./apex_alis_daily.sh                                   # all 5 ALIS phases
    /usr/bin/python3 apex_l5b_reasoner.py --run            # add --commit to write proposals

Discord: /bestbets /worstbets /bestdfs /bestaces /bestbreaks /bestfantasy /bestgameswon /besttotalgames
Bot restart: pkill -f discord_bot.py; nohup /usr/bin/python3 discord_bot.py >> data/logs/discord_bot.log 2>&1 &
(launchd label com.apex.discordbot exists; the manual nohup is what is running now)

## THE THREE LOSSES - FORENSIC CONCLUSIONS
Fucsovics dfs 5.5 LESS, proj 4.35, actual 11 -> classifier says MODEL_ERROR, but the
  large-miss investigation says VARIANCE: dfs has the LOWEST out-of-band rate (10%) and
  second-lowest MAE (2.11). ~1-in-200 event, not a defect. DFS penalty REJECTED on evidence
  (affected group 43% vs baseline 59%, but n=7 and only 1 pick crosses the 50-line).
Gaston aces 2.5 MORE, proj 4.2, actual 0 -> MODEL_ERROR. Card cites own ace rate + service
  games only; NO opponent-return term. Serving vs Medvedev (0.87 favorite). Ace opponent
  penalty NOT deployed - n=1 affected, would be fitting a rule to one observation.
Norrie GW 17.5 MORE, actual 14 -> NOT a model failure. Apex leaned LESS (GW 20.5 LESS
  score 46; TG 38.5 LESS score 39). Selection divergence. Norrie Rule approved, NOT built.

## OPEN HYPOTHESES (none promoted)
HYPOTHESIS_REGISTRY.json (4, from L5-A structural audit):
  missing_input:aces:opponent_return_strength       9 cards
  missing_input:games_won:match_length             15 cards
  missing_input:games_won:opponent_strength        15 cards
  missing_input:double_faults:dispersion_component 11 cards
LESSON_REGISTRY.json (manual, entered 08-29):
  bo5_scaling:player_level - Bo5 player-level projections may under-scale vs match-level
  dispersion:poisson_tails - sd ~= 1.06*sqrt(mean); tails may be too narrow
  KNOWN INCONSISTENCY: manual hypotheses sit in LESSON_REGISTRY while L5-A's sit in
  HYPOTHESIS_REGISTRY. Should be consolidated.
IMPORTANT: dispersion:poisson_tails is NOT supported at n=28. Out-of-band 21% vs expected
  20%; z-spread 1.12 vs 1.0. The bands are approximately honest. Do not act on it yet.

## OPEN ITEMS
1. Norrie Rule - approved, not implemented (exclude picks contradicting Apex's own direction)
2. Rotate Discord bot token + RapidAPI key (both exposed in the session transcript)
3. matches-played endpoint is provider-broken (HTTP 200, empty rows, accurate count).
   h2h/recent is the working substitute. Re-probe periodically.
4. fantasy_score has no auto-settlement path (derivable from the formula - not built)
5. hand CSV has no match_id column -> hand-only settlements invisible to Selection Quality
6. Snapshot idempotence guard compares date+version+count, not the tracker SHA
7. Sub-50 caution line renders a literal \u26a0 instead of the glyph
8. Tracker selftest baseline is stale (pins to the 08-27 tally) - 12 known failures, not regressions
9. Bo5 player-level scaling ratios (1.13-1.27) vs match-level (1.61) - unexplained, n=1

## PERMANENT PROTOCOLS
Frozen model + simulator: evaluate only, never modify. ALIS recommends only.
Append-only registries. VOID requires a reason. All records PROP-based.
Score = belief. Confidence = trust. Attention = earned trust. Warnings = risk. Never merged.
Nothing promoted past its evidence gate. 25 settled = early signal, 100 = emerging, nothing proven early.
