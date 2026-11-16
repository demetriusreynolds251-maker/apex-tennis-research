# PRODUCTION CHANGE PROPOSAL — Candidate C (segmented aces dispersion)
Status: PROPOSAL ONLY. Nothing below has been applied. apex_prop_engine.py,
apex_prop_sim_v1.py, apex_prop_model_v1.py are all currently unmodified
(MD5 PASS as of the last check, tonight).

## ⚠ Gate flag (read before anything else)
This proposal was requested before DISPERSION-FWD has any settled forward
results — the shadow hook proposed earlier tonight was never installed (still
awaiting your go), so 0 matches have gone through live forward tracking.
Your own DISPERSION_FWD_DESIGN.md, approved earlier tonight, ties the
PROMOTE/MAINTAIN/RESTRICT decision to milestones at 25/50/100 *settled*
forward results, mirroring BO5-FWD-001. What exists right now is holdout
backtest evidence (apex_v2_dispersion_calib_holdout, apex_v2_dispersion_
promotion_analysis) plus one day's shadow comparison (16 picks, not yet
settled against real outcomes). That is meaningfully less evidence than the
gate you designed asks for. This document answers exactly what you asked —
files, lines, impact, rollback — so it's ready the moment you decide to act,
but I'd flag this gap before you actually apply it.

## 1. Exact file and lines that would change
ONE file, ONE seam. No other production file touches aces dispersion.

**File:** `apex_prop_engine.py`
**Function:** `evaluate_match()`
**Lines:** 122–126 (current, confirmed by direct read tonight)

Current (production):
```python
        dm = z["c"].get("disp_mult", 1.0)
        s = sim.simulate(hA, hB, z["c"]["tb_k"], bo, (mu["fav"][0][0], mu["fav"][1][0]), (mu["dog"][0][0], mu["dog"][1][0]),
                         (z["c"]["disp"]["fav"]["aces"] * dm, z["c"]["disp"]["fav"]["dfs"] * dm),
                         (z["c"]["disp"]["dog"]["aces"] * dm, z["c"]["disp"]["dog"]["dfs"] * dm),
                         sims, sigma=z["c"].get("gap_sigma", 0.0))
```

Proposed:
```python
        # CANDIDATE-C-2026-09-26: tour-specific aces dispersion, aces-only scope.
        # Frozen, evidence-fit constants (method-of-moments, fit_df year<=2021;
        # reproduced identically in apex_v2_dispersion_calib_tune.py,
        # apex_v2_dispersion_calib_holdout.py, apex_v2_dispersion_promotion_analysis.py).
        # DFs are intentionally left on production's own disp_mult path -- no DF
        # calibration evidence exists for these dm values (DISPERSION_FWD_DESIGN.md S2).
        _R_ATP = {"fav": 8.70148205269834, "dog": 5.885645957929439}; _DM_ATP = 0.6
        _R_WTA = {"fav": 3.9866756061964232, "dog": 2.7971092624925418}; _DM_WTA = 0.4
        _r, _dm = (_R_WTA, _DM_WTA) if wta else (_R_ATP, _DM_ATP)
        dfs_dm = z["c"].get("disp_mult", 1.0)
        s = sim.simulate(hA, hB, z["c"]["tb_k"], bo, (mu["fav"][0][0], mu["fav"][1][0]), (mu["dog"][0][0], mu["dog"][1][0]),
                         (_r["fav"] * _dm, z["c"]["disp"]["fav"]["dfs"] * dfs_dm),
                         (_r["dog"] * _dm, z["c"]["disp"]["dog"]["dfs"] * dfs_dm),
                         sims, sigma=z["c"].get("gap_sigma", 0.0))
```

That's the entire change: 5 new lines, 2 lines modified (the `dm =` line removed,
the `s = sim.simulate(...)` args changed from `dm` to `_dm`/`dfs_dm`). Nothing
else in `apex_prop_engine.py` or any other file needs to change — `render_shadow_block()`
and every Discord/CLI path call `evaluate_match()`, so they inherit this
automatically. `apex_prop_sim_v1.py`, `apex_prop_model_v1.py`, and
`apex_prop_sim_v1.json` (the frozen coefs file) are **not touched** — the
tour-specific r/dm values live only in the adapter file, exactly as the
shadow module (`apex_dispersion_fwd.py`) already does it.

## 2. Expected impact

**Aces simulations (both `aces` per-player props and the derived `most_aces_fav`
/ `total_aces` match props):** dispersion increases materially, more so for
WTA than ATp. From tonight's holdout confirmation (apex_v2_dispersion_calib_holdout,
n=10,971 held-out matches, year>=2024):

| | Production (dm=1e6) | Candidate C |
|---|---|---|
| Pooled 80%+ bucket gap | +0.116 | +0.022 |
| ATP 80%+ bucket gap | +0.086 | +0.002 |
| WTA 80%+ bucket gap | +0.156 | +0.061 |
| Pooled most_aces_fav Brier | 0.2112 | 0.2021 |
| Pooled MAE (aces) | 2.5231 | 2.5216 (Δ -0.0015, noise) |
| Pooled MSE (aces) | 12.776 | 12.773 (Δ -0.003, noise) |

Live, on yesterday's real board (16 picks, apex_dispersion_fwd_board_audit.py):
stated confidence drops a mean of +6.1pp, median +4.66pp; every WTA pick
dropped 14.6–18.5pp, every ATP pick moved -3.1 to +6.8pp. This is a genuine,
visible change to what gets shown and priced — picks that currently read as
75-90% confident will mostly read several points lower, WTA picks
substantially so.

**Double-fault simulations: no change.** `dfs_dm` stays exactly
`z["c"].get("disp_mult", 1.0)` (currently 1,000,000, unchanged) — this is the
whole point of the aces-only scope decision. No DF prop's mean, variance, or
stated probability moves at all under this proposal.

**Everything else** (holds, breaks, games, sets, fantasy score, total_games,
etc.): unaffected — none of those categories read `coefs["disp"]`.

**Known open risk carried from backtest** (documented, not resolved): total-
aces O/U line calibration (`calib_brier`) was measured slightly *worse* under
this candidate in most backtested segments, even as favorite-win calibration
improved (Overall 0.2475→0.2492, Grass 0.2529→0.2617). If the total_aces
market is actively priced/played, this is the one place live results could
plausibly look worse before they look better.

## 3. Rollback procedure
Because this change is confined to 7 lines in one non-frozen file, rollback
is a straight revert, not a migration:

1. Restore lines 122–126 of `apex_prop_engine.py` to the "Current (production)"
   block in Section 1 above (a plain `git diff`/patch revert, or manual
   edit_block back to the original 5 lines).
2. MD5-check `apex_prop_sim_v1.py` / `apex_prop_model_v1.py` — unaffected by
   either direction of this change, so they should read PASS before and after
   with no action needed.
3. No data migration: any picks already made under Candidate C stay as
   historical fact in the forward logs (`apex_engine_picks_log_v1.csv`,
   `apex_prop_sim_forward_log_v1.csv`, `apex_dispersion_fwd_log_v1.csv`) —
   rollback does not need to (and should not) rewrite past rows.
4. No restart required beyond however `apex_prop_engine.py`'s in-process
   `_cache` normally refreshes (it caches `z["c"]` from `sim.load_sim()` once
   per process; a code change to the adapter file takes effect on the next
   process start, same as any other patch to this file today).
5. Verify: run `apex_dispersion_fwd_board_audit.py`-style spot check against
   a couple of live matches post-rollback and confirm probabilities match
   production's pre-change numbers again.

Total rollback time: the time to revert one file and confirm two MD5s —
minutes, not a deployment.

## What this document is NOT
It is not an application of the change. `apex_prop_engine.py` is unmodified
right now. Proceeding from here means explicitly deciding to bypass the
milestone-gated forward test your own approved design calls for — that's
your call to make, not mine to assume.
