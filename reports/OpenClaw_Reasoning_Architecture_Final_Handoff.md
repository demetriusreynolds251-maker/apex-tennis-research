# OpenClaw Reasoning Architecture — Final Handoff

Consolidates: the original 15-recommendation proposal, an independent architectural review, a second AI's counter-review, and a live audit of 10 real evaluation traces. Where earlier rounds disagreed, this document states the resolution and why — not both sides.

---

## 0. The core principle

> **OpenClaw always predicts reality first. It never predicts the sportsbook.**
> The market (a line, or in a goblin/demon prop, a locked side) is consulted only *after* the prediction is complete, to determine whether a wager is available and whether it has sufficient edge to recommend.

Everything below is either an implementation of this principle or a guardrail that keeps it from quietly breaking.

**Prediction** answers: *what do I think will actually happen?* — independent of what's bettable.
**Recommendation** answers: *given that prediction and what the market offers, should this be bet?*

These are two different outputs, computed in that order, and the second may never influence the first. This single split resolves the three separate problems this review process surfaced independently: confirmation bias (early anchoring makes evidence-gathering serve a conclusion instead of reaching one), the goblin/demon question (a locked market side is a recommendation-stage constraint, not a prediction-stage one), and gives the calibration system something honest to score.

---

## 1. The pipeline

```
Verified Data
     │
     ▼
Estimate Reality  ─── numeric where possible (expected games, expected aces,
     │                win probability), qualitative only where no numeric
     │                signal exists (injury, motivation, travel)
     ▼
Prediction  ─────────  a single outcome + probability/expected value.
     │                 No mention of the betting line. No mention of
     │                 confidence-to-post. No directional language of
     │                 any kind permitted before this line is reached.
     ▼
Compare With Line  ──  numeric comparison only (estimate vs. line).
     │                 NEVER a market-odds or implied-probability
     │                 comparison — see §3, non-negotiable per Rule 9.
     ▼
Available Actions  ──  what can actually be bet (both sides / one
     │                 side locked by goblin-demon / no market at all)
     ▼
Recommendation  ─────  BET or PASS, with a reason code (§4) — never
                        a bare PASS with no attached reason
```

**Every stage before "Prediction" is barred from directional language.** No "lean," no "edge toward," no naming a side, no naming a player as favored — only magnitudes, probabilities, and stated uncertainty. Direction is computed exactly once, as a function of the completed evidence, not accumulated as a running impression.

---

## 2. What the live trace audit actually found

Ten real evaluation traces (`reasoning_*.txt`, 2026-07-08 through 2026-07-23) were read in full to test whether the anchoring concern was real or theoretical. It's real, and it's precisely located.

### Finding A — Early directional anchoring (confirmed, real, fixable)

In 3 of 5 sampled "standard" props (both directions genuinely open), directional language appears at **Checkpoint A** — the first analytical step, before dominance scoring, structure typing, survival assessment, or score-path counting. Verbatim, from the Zverev/Fery trace:

> **CHECKPOINT A STAMP:** ... **Mild LESS lean from serve structure.**

This is the anchor. Everything generated in Checkpoints B–H after that point is conditioned on a model that has already written "LESS lean" into its own context. This is not a hypothesis — it's visible, in the system's own words, at a named location.

**The fix does not require a rebuild.** Checkpoint H in these same traces already does close to the right thing — it enumerates weighted outcome paths (e.g., "7 LESS paths, weighted HIGH-MODERATE vs. 5 MORE paths, weighted LOW-MODERATE") before naming a direction. The contamination happens *before* H, not at H. Fix:

> **No checkpoint before the decision phase may emit any directional conclusion, directional adjective ("lean," "edge," "favorite"), or provisional winner. Checkpoints A–G may only emit observations, interpretations, uncertainty assessments, and estimated effects — expressed as magnitudes and probabilities, never as MORE/LESS or a named favorite.**

And per the refinement surfaced later in this review: Checkpoint H itself should evolve from *"MORE paths: 7, LESS paths: 5"* toward a direct estimate of the underlying quantity — *"Estimated total games: 23.8 vs. line 22.5 → MORE"* — so direction is a computed comparison, not a tally of narrative buckets.

### Finding B — Goblin/demon labeling (real, but smaller than first assessed)

All 5 sampled goblin props (`direction_locked: MORE`, `both_directions_available: false` at intake) show the model's own Hard Stop 1 — the gate whose entire job is identifying prop type — asserting the opposite of its input:

> Intake: `"prop_type": "goblin", "direction_locked": "MORE"`
> Model's Hard Stop 1: *"Goblin: ❌ not applicable... Prop type: STANDARD (both MORE and LESS available)"*

**Correction from earlier in this review:** this is *not* a data-integrity crisis — `direction_locked: MORE` on a goblin prop is a correct reflection of the market (PrizePicks goblin props are structurally one-sided), not a bug in the field itself. What's real here is narrower: the model's own audit-trail language contradicts its own input, which matters for anyone reading the trace later, but does not appear to affect the underlying math — confidence output across the 5 goblin samples varied meaningfully (58%–75%), which is evidence against blanket rubber-stamping.

**Fix:** correct the Hard Stop 1 template to state the true prop type and locked side accurately. Low cost, worth doing, not urgent relative to Finding A or the architecture change in §0.

### Finding C — No infinite reasoning found (non-issue, preserve as invariant)

All 10 traces run a single bounded pass through a fixed checkpoint sequence (Hard Stops 1–4, Checkpoints A–J, Confidence Scoring, Direction Drivers, Final Output). No retries, no repeated evaluation attempts, no iteration loops in any sampled file. The "reasoning forever" concern does not describe current behavior.

**Action:** no fix needed. Preserve as an explicit invariant going forward so it stays true after edits: *every checkpoint executes exactly once; the pipeline halts at Final Output.*

---

## 3. Non-negotiable guardrail: line comparison, never market-odds comparison

"Compare prediction against the market" is a phrase that can drift in meaning over time. For this project specifically, it must always mean **comparing an estimate to a numeric line** (22.5 games, 4.5 break points), never comparing to **market odds or implied probability**. Rule 9 (market data permanently rejected) is a standing, closed decision. The architecture in §1 is compatible with Rule 9 exactly as written — nothing here requires odds — but "market comparison" is exactly the phrase that could quietly grow into an odds-lookup six months from now if this isn't stated explicitly. It is stated explicitly here so it doesn't.

---

## 4. PASS needs a reason code, not one bucket

A recommendation of PASS can come from at least four structurally different causes, and collapsing them into one flat outcome destroys the ability to ever answer "why do we pass so often":

| Reason code | Meaning | What it says about the model |
|---|---|---|
| `PASS_DIRECTION_MISMATCH` | Predicted side isn't the side the market offers (the goblin/demon case) | Nothing negative — the model may be right, the market just didn't offer that side |
| `PASS_INSUFFICIENT_EDGE` | Predicted side is available, but the estimate is too close to the line to justify a bet | Model executed fine; this line just isn't beatable today |
| `PASS_LOW_CONFIDENCE` | Estimate itself carries too much uncertainty | Evidence was thin or conflicting |
| `PASS_THIN_DATA` | Not enough verified evidence to estimate at all | Data-collection gap, not a reasoning failure |

Each must be logged individually. Do not hardcode a single numeric threshold (e.g., "confidence < 55% → pass") as the only gate — the cause of a pass is itself a piece of information worth keeping.

---

## 5. Every prediction is calibration data — even the ones nobody bets

This is the capstone finding from this review process. Once prediction and recommendation are separated (§0), a goblin prop that gets `PASS_DIRECTION_MISMATCH` — market only offers MORE, OpenClaw predicted LESS — **still has a real, checkable outcome once the match finishes.** Nobody bet on it, but the prediction can still be scored against reality at zero risk.

**This means every prediction OpenClaw ever makes should be logged and scored against the eventual outcome, whether or not it became a bet.** These direction-mismatch predictions are arguably the highest-value calibration data in the entire system — free signal on whether the model's unconstrained read is trustworthy, costing nothing to be wrong about. Under the current architecture, if a prediction never becomes a recommendation, there's no reason it would currently be tracked at all. That's real signal being discarded. The calibration/backtesting module (§6) must score **every prediction**, not only the recommendations that got posted.

---

## 6. What the modular architecture looks like end to end

```
                         VERIFIED EVIDENCE
                                │
           ┌────────────────────┼────────────────────┐
           │                    │                     │
    Structured Stats     Qualitative Signals    Historical Calibration
    (Dataset B, numeric)  (LLM: injury, motivation,  (prior predictions'
                            travel — bounded, logged   actual outcomes)
                            per-item, never unbounded)
           │                    │                     │
           └────────────────────┼─────────────────────┘
                                 │
                        Evidence Fusion Engine
                    (weighted accumulation; weights are
                     expert-ranked now, semi-learned once
                     enough settled volume exists per category
                     — never fit against a sample small enough
                     to just be overfitting noise)
                                 │
                          Estimate Reality
                                 │
                            Prediction
                        (outcome + probability/EV —
                         no market language anywhere yet)
                                 │
                        Compare With Line
                     (numeric line only — never odds, §3)
                                 │
                         Available Actions
                     (both sides open / one side locked /
                      no market at all)
                                 │
                          Recommendation
                    (BET, or PASS + reason code, §4)
                                 │
                        Calibration Engine
              (scores EVERY prediction against eventual
               outcome — Brier score, log loss, reliability
               diagrams — regardless of whether it became
               a bet; revisits Evidence Fusion weights over
               time; requires a minimum settled-sample size
               per category before trusting any verdict, to
               avoid p-hacking a dozen small categories)
```

Each box is independently testable and independently replaceable — a real statistical model can slot into "Structured Stats" whenever Dataset A/B are large enough, without touching anything downstream of "Estimate Reality."

---

## 7. Disposition of the original 15 recommendations

| # | Original recommendation | Final disposition |
|---|---|---|
| 1 | Redefine mission as forecasting engine | **Superseded** by §0's single sentence — the objective is the prediction/recommendation split, not an identity label |
| 2 | Competing MORE/LESS hypotheses | **Rejected as architecture.** Replaced by weighted evidence accumulation → single prediction (§1). Debate framing reintroduces the exact anchoring bug found in Finding A |
| 3 | Interpret before predicting | **Accept** — with the Finding A guardrail: interpretation must stay non-directional until the Prediction stage |
| 4 | "Scientist mindset" | **Dropped as standalone rule** — subsumed by 5, which is a mechanism, not a sentiment |
| 5 | Disprove the leader | **Accept, unchanged** — cheap, structural, real bias fix |
| 6 | Forecast before confidence | **Accept as interim guardrail** — dissolves naturally once real probability estimates exist, since the estimate *is* the confidence |
| 7 | Fixed 8-step pipeline | **Modify** — bounded execution confirmed real and good (Finding C); add adaptive depth and the PASS states from §4, which the original pipeline had no room for |
| 8 | Evaluate each fact once | **Accept, unchanged** |
| 9 | Fixed evidence categories | **Accept concept, weights unvalidated** — see §6, Evidence Fusion Engine notes |
| 10 | Explicit termination rule | **Accept, extended** — must include the PASS states (§4), which the original had no path to |
| 11 | Confidence = probability | **Accept — foundational.** Only verifiable via §5/§6's calibration engine |
| 12 | One vote per category, equal weight | **Modify** — weighted, not equal; expert-ranked now, learned later once volume supports it |
| 13 | Explanatory-power comparison | **Superseded** by §1's direct estimate-vs-line comparison — no narrative "which side explains better" step needed |
| 14 | Confidence conservation | **Accept** — this is empirical-Bayes shrinkage toward the prior under thin/balanced evidence; keep, formalize later |
| 15 | Modular architecture | **Accept, implemented** as §6 |

---

## 8. Implementation priority

1. Strip directional language from Checkpoints A–G (Finding A) — highest-leverage, cheapest fix, directly targets the confirmed bug
2. Split Prediction from Recommendation (§0/§1) — the structural change everything else depends on
3. Add PASS reason codes (§4) — required for the split above to produce usable data
4. Log and score every prediction, not just recommendations (§5) — turns free data into an actual asset
5. Fix Hard Stop 1 goblin/demon labeling (Finding B) — low cost, do it while in the file for #1
6. Build the calibration/backtesting module (§6) — cannot validate #11/§0 without it; this is the long pole
7. Evolve Checkpoint H from path-tallying to direct estimate-vs-line (§2, Finding A refinement) — conceptual improvement, not an urgent fix
8. Weighted evidence categories, expert-ranked → learned over time (§6) — ongoing, gated by settled-sample size

---

## 9. Explicitly out of scope / unresolved

- No sample in the 10-file audit showed a goblin/demon prop where the genuine unconstrained prediction actually opposed the locked market direction. Until a real case surfaces (or one is deliberately checked for in Dataset A once logging per §5 is live), it's unknown whether the current pipeline would even reach `PASS_DIRECTION_MISMATCH` correctly — this needs live validation, not just architectural approval.
- Learned category weights (§6) require a minimum settled-sample size per category before being trusted; that threshold hasn't been set and shouldn't be guessed at without knowing current Dataset A volume per category.
- Whether "sufficient edge" (§0, Available Actions → Recommendation) needs a fixed numeric floor or should stay judgment-based per prop type is unresolved — flagged, not decided, in the interest of not hardcoding a number that turns out wrong for every market type equally.
