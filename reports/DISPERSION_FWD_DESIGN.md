# DISPERSION-FWD-001 — DESIGN DOCUMENT
Status: DESIGN COMPLETE (2026-09-26). No live hook installed yet. V1 untouched.

Approved candidate (2026-09-26):
  ATP: disp_mult = 0.6, own fitted r (fav=8.70148205269834, dog=5.885645957929439)
  WTA: disp_mult = 0.4, own fitted r (fav=3.9866756061964232, dog=2.7971092624925418)
r values fitted via method-of-moments on fit_df (year<=2021), reproduced identically
across apex_v2_dispersion_calib_tune.py, apex_v2_dispersion_calib_holdout.py, and
apex_v2_dispersion_promotion_analysis.py tonight. Not re-fit here — frozen constants.

## SECTION 1 — Reason (evidence, condensed)
Root-cause investigation this session: Aces V2 opponent suppression survived
holdout but effect size <1%, insufficient to explain observed overconfidence.
Dispersion audit found production's disp_mult=1,000,000 collapses fitted NB
overdispersion to near-Poisson. Holdout-confirmed (apex_v2_dispersion_calib_holdout,
apex_v2_dispersion_promotion_analysis): segmented candidate (ATP dm=0.6/WTA dm=0.4)
cuts the 80%+ confidence bucket gap from +0.116 to +0.022 (pooled), most_aces_fav
Brier improves 0.2112->0.2021 (pooled), MAE/MSE unchanged within noise everywhere
tested (ATP/WTA x Hard/Clay/Grass). Two open risks carried into this forward test
rather than resolved by more backtesting (see Section 4).

## SECTION 2 — Scope: ACES ONLY
`disp_mult` in production (`apex_prop_engine.py::evaluate_match()`) scales BOTH
aces and double-faults dispersion via one shared multiplier:
    (coefs["disp"]["fav"]["aces"] * dm, coefs["disp"]["fav"]["dfs"] * dm)
Tonight's entire evidence trail covers aces only — zero DF calibration evidence
exists for these dm values. DISPERSION-FWD is scoped to apply the candidate dm
to the ACES dispersion term only; the DFS term keeps production's own disp_mult
path untouched, in both the shadow computation and (if ever promoted) production.
This was an explicit decision (user deferred to recommended option), not an
assumption baked in silently.

## SECTION 3 — Architecture (shadow-only, confirmed against live code)
Live seam: `apex_prop_engine.py::evaluate_match()` lines ~102-112, the single
`sim.simulate(...)` call that produces every pick. NOT modified.

Live call site: `openclaw_core.py:4965-4966` —
    res = apex_prop_engine.evaluate_match(fav, dog, fav_p, surface=surf, bo5=bo5, wta=wta, lines={key: line})
followed by forward-log write at `_apex_forward_log_row(...)`, line 5040.

New module `apex_dispersion_fwd.py` (standalone, does not import into or get
imported by any frozen file):
  - `shadow_predict(res, wta)` — re-runs ONLY the final `simulate()` call using
    `res`'s own solved `fav`/`dog`/`surface`/`pinn_fav`/`best_of` (recomputing the
    same seam evaluate_match() runs, since evaluate_match() does not expose its
    solved hA/hB/mu), substituting the candidate's own fitted r * candidate dm for
    aces, keeping `coefs["disp"][side]["dfs"] * coefs["disp_mult"]` (production's
    own DF term) unchanged. Fail-open: returns None on any exception, never raises.
  - `log_shadow_row(res, wta)` — appends one row per match_id (dedup on match_id)
    to `apex_dispersion_fwd_log_v1.csv`, recording BOTH production's and the
    candidate's most_aces_fav probability, total_aces mean + O/U line probability,
    and each side's per-player aces mean. `actual_*` / `settled_ts` columns are
    left blank for a later settlement pass (mirrors `apex_prop_sim_forward_log_v1.csv`'s
    own actual/settled_ts convention). Fail-open: returns False on any exception,
    never raises, never blocks the caller.

Proposed hook (NOT yet installed — see Section 5): one guarded call in
`openclaw_core.py`, immediately after the existing `_apex_forward_log_row(...)`
call at line 5040, gated to aces-related categories only (`aces`, `most_aces_fav`,
`total_aces`) to avoid needless duplicate simulation cost on unrelated picks:
```python
if cat in ("aces", "most_aces_fav", "total_aces"):
    try:
        import apex_dispersion_fwd as _dfwd
        _dfwd.log_shadow_row(res, wta)
    except Exception:
        pass
```
This can never change `direction`, `prob`, the Discord card, or anything written
to the production forward log — it runs after all of that is already decided,
touches no shared state apex_prop_engine.py or openclaw_core.py otherwise use,
and is wrapped exactly like every other optional side-effect in this file
(`d1.transition(...)`, `d1.heartbeat(...)` above it use the identical try/except pass
pattern).

## SECTION 4 — Known open risks (carried into the forward test, not resolved by more backtesting)
1. Total-aces O/U line calibration (calib_brier) was *slightly worse* under the
   candidate in most backtested segments (Overall 0.2475->0.2492, Grass
   0.2529->0.2617) even as favorite-win calibration improved. Tracked live via
   item 7 below.
2. Grass is the smallest surface (n=1379 holdout, 539 in the 80%+ bucket) and
   showed an overshoot into underconfidence under the candidate. Tracked
   separately per the user's explicit item 6 below.
3. DFs are out of scope (Section 2) — if a future decision wants to extend this
   to double-faults, that requires its own holdout audit first, not inference
   from the aces result.

## SECTION 5 — Tracking (per approved decision)
Tracked in `apex_dispersion_fwd_log_v1.csv`, reviewed at milestones, mirroring
BO5-FWD-001's exact convention in `apex_learning_engine.py` (`_ms = (25, 50, 100)`,
`milestone_reached` / `next_milestone` fields, per-slice `bucket()` breakdown):
  1. most_aces_fav calibration (prod vs candidate, both logged, settled later)
  2. 75-80% confidence bucket
  3. 80%+ confidence bucket
  4. ATP, separately
  5. WTA, separately
  6. Grass, separately
  7. total-aces O/U calibration (the one metric that got worse in backtest)

Milestones: review at 25 / 50 / 100 settled. Decision gate at each milestone:
PROMOTE / MAINTAIN / RESTRICT — same three-way gate BO5-FWD-001 uses, decided
by the user from the tracked evidence, never auto-applied.

## SECTION 6 — What has NOT been done yet
- The hook in Section 3 is proposed, not installed. `openclaw_core.py` is
  unmodified.
- Settlement (filling `actual_*`/`settled_ts` from Sackmann results, the way
  `apex_prop_sim_forward_log_v1.csv` gets settled) is not yet built — needed
  before the first milestone review can score anything, but does not block
  starting to log shadow rows once the hook is approved.
- Milestone-review rendering in `apex_learning_engine.py`'s cycle report
  (the `## 🎾 BO5 MILESTONE REVIEW #k` equivalent) is not yet built.
