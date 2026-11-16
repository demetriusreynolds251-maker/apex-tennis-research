# Prop Model V1 — Deployment Record
Project Apex Intelligence / OpenClaw (DEMETRIUS) — Mr. owner
Script: `apex_prop_model_v1.py` · marker `APEX-PROP-MODEL-V1-2026-08-22`
Build date: 2026-08-22 · replay 2005-01-03 → 2026-08-03, main tour only (no challengers)

## What this model is

**Prop Model V1 is primarily a player-rate model, not a fragility model.**

The core edge comes from:
- surface-specific ace rates
- surface-specific double-fault rates
- hold rates
- break rates
- market-derived service opportunities (expected service games from the Pinnacle price)

Fragility V3 and the related overlays (elo-gap, age gap, surface switch) provide
small but measurable adjustments. They refine; they do not drive.

The objective is not historical fit. It is to lock a clean model and find out whether
the player-rate approach keeps beating simple market-derived baselines on matches
nobody has seen yet.

## Data and splits
- Priced + finished + full serve stats: 53,987 matches
- Fit ≤2021: 34,891 · Tune 2022-23: 8,120 · Holdout 2024+: 10,976
- Price: Pinnacle de-vigged favorite probability (`pinn_a` from `apex_batch_a_rows.csv`)
- Fragility: frozen V3 betas (model json SHA `8bf6937adafed48c…` verified), percentile
  within price band against this script's own ≤2023 favorite reference

## Frozen feature list
Layer 1 (market): pinn_fav, logit(p), logit(p)², best_of=5, is_wta
Layer 2 (rates, per player, surface-specific, **window 40 matches, shrink k=15** toward
all-surface rate): ace_rate, df_rate, hold_rate, break_rate, spg (points per service game)
Layer 3 (overlays): fragility z (match-level), elo_gap z and age_gap z in the player's own
frame and residualised on fragility (elo: raw − 0.642·frag; age: raw − 0.799·frag),
own surface switch (0/1)

## Formulas
```
E[TG]       = 24.078 − 0.415·lp − 0.399·lp² + 15.451·bo5 − 1.483·wta − 1.220·bo5·lp
E[svg_fav]  = −0.009 + 0.4947·E[TG]        E[svg_dog] = 0.033 + 0.4887·E[TG]
base aces   = E[svg]·spg·ace_rate
base dfs    = E[svg]·spg·df_rate
base holds  = E[svg]·(hold_rate − (opp_break_rate − mean_break))
base breaks = E[svg_opp]·(break_rate + (1 − opp_hold_rate) − mean_fail_hold)
final       = c0 + c1·base + Σ overlay_coef·overlay_z, floored at 0
```
(c0/c1 per side and category are printed by `--spec`.)

## Overlay gate (pre-registered, mechanical, no manual override path in the code)
Keep only if fit ≤2021 |t| ≥ 3 **and** tune 2022-23 same sign with |t| ≥ 1.5.
Fail → coefficient set to exactly 0.

## Final overlay coefficients (units per 1 SD; 0 = failed gate)
| side | cat | fragility | elo_gap | switch_self | age_gap |
|---|---|---|---|---|---|
| fav | aces | −0.1336 | 0 | +0.2385 | −0.2350 |
| fav | dfs | +0.0589 | 0 | +0.3415 | 0 |
| fav | holds | 0 | −0.1479 | 0 | 0 |
| fav | breaks | −0.0925 | −0.2166 | 0 | −0.1028 |
| fav | svgms | +0.0769 | 0 | 0 | 0 |
| dog | aces | +0.1412 | 0 | 0 | −0.1978 |
| dog | dfs | 0 | 0 | +0.2500 | 0 |
| dog | holds | +0.1560 | −0.2641 | 0 | −0.1762 |
| dog | breaks | +0.0617 | −0.1406 | 0 | −0.1245 |
| dog | svgms | +0.0759 | 0 | 0 | 0 |

Watch item: fav switch → fav aces (+0.24) passed the gate with surface-specific rates in
place. This was the "provisional artifact" from the link study; it survived its retest,
but shrinkage (k=15) still mixes surfaces a little for thin samples. Treat as the
overlay most likely to fade in the forward test.

## Holdout 2024+ (never used for fitting or tuning) — MAE, price-only / rates / full
| cat | fav | dog |
|---|---|---|
| aces | 3.365 / 2.616 / 2.612 | 3.071 / 2.411 / 2.410 |
| dfs | 1.959 / 1.785 / 1.787 | 1.968 / 1.833 / 1.835 |
| holds | 2.316 / 2.149 / 2.148 | 2.804 / 2.614 / 2.608 |
| breaks | 1.614 / 1.387 / 1.379 | 1.703 / 1.501 / 1.497 |
| svgms | 2.475 / 2.475 / 2.475 | 2.527 / 2.527 / 2.527 |

Rates layer: aces ≈ −22%, breaks ≈ −14%, holds ≈ −7%, dfs ≈ −8% vs price-only.
Overlays: ≤ 0.01 MAE on top of rates. Service games: market-owned, no gain (expected).

## Calibration (full model, holdout, predicted-decile mean vs actual mean)
Aces, dfs, breaks: within ~0.3 across all deciles. Soft spots: lowest dog-ace decile
projects 0.9 vs 1.5 actual (zero floor); low hold deciles run ~0.3-0.4 under.

## Freeze and forward test
- `--freeze` stamps `apex_prop_model_v1.json` with a content SHA; `--project` refuses
  unfrozen or tampered models; freezing twice is refused.
- `--build` **refuses** when the model is frozen. After a Sackmann refresh use
  `--refresh-state` (rebuilds players only, never touches the model). A new model
  is a new file (V2).
- Forward log `apex_prop_forward_log_v1.csv`: one row per match / player / category,
  never rewritten. Schema: ts, match_id, match_date, player, opponent, is_fav, pinn_fav,
  surface, category, projection, fragility, book, line, odds_over, odds_under, edge,
  actual, settled_ts, model_sha.
- `--report` includes a **fragility drift check**: Prop V1 fragility vs `fragility_live`
  score on shared matches (mean diff, mean |diff|, max |diff|). Replay Elo differs from
  the cache by ~5 Elo on average (max 340 on name-mismatch outliers), so some drift is
  expected; the check quantifies it.
- Rules carried over from Fragility V3: no real-money decisions from this model alone,
  no hypothetical matches in the log, no refit/retune during the forward test.

## Live commands
```
python3 apex_prop_model_v1.py --project "Fav Name" "Dog Name" --pinn 0.64 --surface Hard [--bo5] [--wta]
python3 apex_prop_model_v1.py --line MATCH_ID "Player Name" aces 4.5 prizepicks
python3 apex_prop_model_v1.py --settle-sackmann
python3 apex_prop_model_v1.py --report
```
