"""
APEX ACES V2 -- Task 1, Step 4: suppression formula SELECTED + fitted
==========================================================================
Implements the approved opponent-suppression adjustment from
APEX_ACES_V2_DESIGN.md (Sections 2, 3, 7): scale mu[side][0] (the aces
component only) by an opponent-suppression factor derived from the
opponent's trailing break-rate, at the exact seam documented there --
between where sim.v1_inputs_from_rows() builds `mu` and where simulate()
consumes it.

KEY FINDING FROM BUILDING THIS FILE (worth recording): the opponent's own
break_rate column already exists in every DataFrame V1 itself consumes,
under the name "<opp_side>_W{W}_K{K}_break_rate" -- because V1's own
base_projection() (apex_prop_model_v1.py) ALREADY reads that exact column
for the HOLDS and BREAKS projections (V(otag + "_break_rate")). Aces is the
ONLY player-prop category that never reads it. So this file introduces no
new data path at all -- it reads a column V1 already produces and applies
it to one more category, exactly the structural gap the design doc names.

FUNCTIONAL FORM HISTORY (for audit trail):
- Step 3 built the mechanism with an un-fit linear placeholder (gamma=0.5)
  purely to prove the wiring worked and leave every other category
  untouched.
- Step 4's first attempt fit the LINEAR multiplicative form
  (aces2 = aces0*(1 - gamma*delta)) via closed-form OLS on year<=2021:
  gamma=35.240046. REJECTED by user: 32.24% of fit-window predictions went
  negative (physically impossible ace counts). A 5-method stability
  investigation (OLS/trimmed/Huber/bounded/median-of-ratios) then confirmed
  the *effect size* (gamma ~28-36 across every unconstrained method) is a
  real signal, not an outlier artifact -- the instability was in the
  UNCLAMPED LINEAR FORMULA, not the coefficient.
- A follow-up formula comparison (apex_v2_formula_comparison.py) tested 5
  candidate functional forms on the same year<=2021 window: linear
  (reference), clamped-linear (2 floor variants), exponential, logistic,
  and winsorized-delta linear. RESULT: the clamped/winsorized variants
  "won" on raw MSE only by pushing gamma far higher (~62) and flattening
  36-37% of the sample against a floor, which left a large leftover
  residual-vs-delta correlation (~0.25) -- i.e. a real remaining
  unexplained pattern the clamp was masking, not fixing. The EXPONENTIAL
  form (aces2 = aces0*exp(-gamma*delta)) was selected instead: 0% negative
  predictions BY CONSTRUCTION (exp() > 0 always, no arbitrary floor
  needed), a fit-window MSE improvement (19.98%) that slightly EXCEEDS the
  original unclamped linear reference (18.32%), and an essentially zero
  leftover residual-vs-delta correlation (-0.0007) -- the cleanest
  calibration diagnostic of all 5 candidates tested.
- USER DECISION (2026-09-26): Formula C (exponential) approved for V2,
  because (1) the underlying signal survives every fitting method tested,
  and (2) negative predictions disappear entirely under this form.
- GAMMA_FIT = 12.879686 (first attempt) was fit against
  pred_v1 = svgms * ace_rate, an INCORRECTLY SCALED proxy: rate_bundle()
  (apex_prop_model_v1.py line 205) defines ace_rate = aces / SERVE POINTS,
  not per service game, so this proxy averaged ~6.4x smaller than the real
  match-total aces it was meant to predict. Step 6 holdout (year>=2024)
  exposed this: MAE more than DOUBLED vs V1 (fav_aces 2.63->8.80, dog_aces
  2.41->5.51), 90% coverage collapsed (~87%->~50%). USER DECISION
  (2026-09-26): re-open Step 4, refit against the real production target.
  Opponent-suppression signal: still HIGH confidence (unaffected -- it was
  independently confirmed on raw historical data before this proxy ever
  existed). Exponential formula: still HIGH confidence (unaffected -- it's
  a functional-form choice, not a scale). Only the coefficient derivation
  was contaminated by the scale bug.
- REBUILT FIT (2026-09-26, apex_v2_step4_REBUILD.py): pred_v1 is now
  mu[side][0]*svgms_actual -- mu[side][0] is the REAL production per-GAME
  aces rate this file actually multiplies (V1's fully calibrated
  projection), scaled by service games played, exactly mirroring what the
  simulator does internally (lambda = mu*svgms). Verified this reproduces
  V1's real scale: baseline (gamma=0) fit-window agg_bias=+0.069 (vs the
  old proxy's -4.76), matching production holdout MAE (~2.3-2.6) almost
  exactly. GAMMA_FIT = 0.246189 (year<=2021, n=69,498 side-observations,
  nonlinear least squares / golden-section on MSE). Fit-window performance:
  MAE 2.2860->2.2844 (0.07% improvement), MSE 9.8783->9.8596 (0.19%
  improvement), 0.00% negative predictions. NOTE: the correctly-scaled
  effect size is far smaller than what the broken-proxy fit implied (which
  showed ~20% MSE improvement) -- once measured against V1's own
  already-well-calibrated baseline, the marginal benefit of adding
  opponent suppression is small. This is flagged, not hidden: whether a
  ~0.2% MSE improvement justifies the added model complexity is an open
  question for Step 5/6 to help answer, not resolved by this fit alone.

STRICT SCOPE (still in force): this value has been FIT on year<=2021 only,
against the real production target (mu[side][0]*svgms_actual).
- apex_prop_sim_v1.py and apex_prop_model_v1.py are imported read-only and
  are NEVER modified by this file.
- Do NOT tune on 2022-2023 beyond what Step 5 (rebuilt) authorizes. Do NOT
  holdout-test beyond what Step 6 (rebuilt) authorizes. Do NOT
  promote/freeze. Those remain separate, not-yet-authorized steps.
"""
import apex_prop_model_v1 as v1          # noqa: F401  (read-only)
import apex_prop_sim_v1 as sim           # read-only

MARKER = "APEX-PROP-SIM-V2-2026-09-26"

# REBUILT fit (2026-09-26) on the real production quantity mu[side][0]*svgms.
# See apex_v2_step4_REBUILD_results.json / apex_v2_step4_REBUILD.py for the
# full derivation, and the docstring above for why the original 12.879686
# was invalid (fit against a ~6.4x scale-broken proxy).
GAMMA_FIT = 0.246189


def v2_inputs_from_rows(df, m, gamma=GAMMA_FIT):
    """Exact mirror of sim.v1_inputs_from_rows(), except mu's ACES component
    is scaled by a centered, exponential opponent-suppression term. P, hf,
    hd are returned completely UNCHANGED (same values V1 computes) -- only
    mu[side][0] (aces) differs from V1's mu. mu[side][1] (dfs) is untouched.

    Suppression form (Formula C, approved 2026-09-26):
        aces2 = aces0 * exp(-gamma * (opp_break_rate - mean_break_rate))
    Always strictly positive by construction -- no floor/clamp required.
    """
    import numpy as np
    P, hf, hd, mu = sim.v1_inputs_from_rows(df, m)
    W, K = m["window"], m["shrink"]
    mean_break_rate = m["mean_break_rate"]  # V1's own frozen reference constant
    mu2 = {}
    for side in ("fav", "dog"):
        opp = "dog" if side == "fav" else "fav"
        opp_break_rate = df["%s_W%d_K%d_break_rate" % (opp, W, K)].values
        aces0, dfs0 = mu[side]
        suppression = np.exp(-gamma * (opp_break_rate - mean_break_rate))
        aces2 = aces0 * suppression
        mu2[side] = (aces2, dfs0)  # dfs UNCHANGED -- only aces adjusted
    return P, hf, hd, mu2


# simulate() is generic -- it only consumes whatever mu it's handed, so it
# needs no V2 version. Re-exported so callers need only import this module.
simulate = sim.simulate
build_live_row = sim.build_live_row
level_from = sim.level_from
price_level_pred = sim.price_level_pred
