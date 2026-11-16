# OPENCLAW RULE ROADMAP (v1.0 — 2026-07-10)

The master map of every active rule: why it exists, where it lives, what
it costs or protects, what depends on it, and a classification. Trigger
frequency is marked MEASURE where only live data can answer it — the
GREEN Validation Suite's section 3 (rule/cap effectiveness) is the
instrument; run it after 2-3 weeks of benchmark accumulation and revisit
every REVIEW/AUDIT entry with real records.

Classifications: KEEP (earning its place) · REVIEW (sound idea, tuning or
evidence question open) · AUDIT (impact unproven — measure before trusting)
· REMOVE (none currently — dead prop-signal weights were already stripped).

═══════════════════════════════════════════════════════════════════
## GATES (existence/validity — stop rules, not confidence rules)
═══════════════════════════════════════════════════════════════════

**Gate 11 — match verification.** Purpose: never grade a prop on a match
that doesn't exist as described. Location: gate_11_check (code) + Step 1
in all docs. Impact: REJECT on failed check; 69% cap on V8-outage
unverifiable (OPEN DECISION: recommended reclassification to SKIP —
system failure ≠ confidence deduction — awaiting operator ruling).
Dependencies: V8 availability; feeds pipeline_flags. **KEEP** (resolve
the outage-treatment decision).

**Gate 11-B — format detection (bo3/bo5).** Purpose: stop bo3 baselines
from pricing bo5 matches; caps non-HARD bo5 LESS at 64%. Location:
gate_11b_format_detection + gate_11b_scoring_correction. Impact: 64% cap
+ format warnings. Dependencies: dominance_level (fixed tonight — was
reading a key props never wrote, so EVERY bo5 LESS was capped
dominance-blind all tournament). **KEEP** — and put bo5 HARD-LESS picks
in the benchmark to confirm the fix earns wins.

**Gate 14 — home crowd (direction-aware).** Purpose: home-crowd effect
priced with direction awareness (flat -8% wrongly hit MORE picks it
should support — already corrected). Impact: eval-side deduction, legal
under Conservation (outside path model). Frequency: MEASURE. **REVIEW**
— direction-aware version is young; verify with suite records.

═══════════════════════════════════════════════════════════════════
## NUMBERED RULES
═══════════════════════════════════════════════════════════════════

**Rule 9 — market/seed exclusion.** Purpose: odds/line movement never
justify dominance; on-court traits only. Location: DT Checkpoint D +
compliance awareness. Impact: prevents circular market reasoning; no
direct % effect. Note: was being miscited for the rest-day deduction —
now firewalled (that is Rule 30). **KEEP.**

**Rule 12 — Truth Lock.** Purpose: the eval may not call a value
unknown/uncertain when confirmed data exists. Location: compliance check
+ the CONFIRMED V8 GROUND TRUTH block (the auditor now sees the same
corrected packet the eval reasons from — the stale-packet fork is
closed). Impact: Category-A when genuinely violated. Dependencies:
research_data["v8_packet"] correctness. **KEEP** — highest-value
compliance check in the system.

**Rule 24 / Correction 24 — class-gap vs form-noise.** Purpose: form
generated against stronger opposition cannot flip direction against a
structural class gap. Location: LOCKED spec (HANDOFF) + injection
trigger in build_evaluation_content. Impact: reasoning constraint (a
prompt injection, not a %); tonight tightened from a drifted ≥50/
asymmetry trigger back to the locked ≥100 + opponent-status condition.
Frequency: MEASURE post-tightening. **REVIEW** — the collaborator's own
sample question stands: does it improve GREEN records? Suite section 3
answers it.

**Rule 30 — rest-day scaled deduction.** Purpose: fatigue priced by
actual turnaround, not flat penalty. Location: DT (authoritative) +
HANDOFF (aligned tonight) + compliance check 9 (aligned tonight).
Impact: -4% (24-48h), 0% (48h+), CFEF suppression (<24h); prop-type
scoped (TG/TGW both players; DF/Aces/BP evaluated player only).
Dependencies: confirmed match_date + last-match date from ground truth;
CFEF trigger definitions. **REVIEW** — the collaborator's early sample
(6-8 on Rule-30-touched GREENs) is exactly why this one goes in the
benchmark first.

**Rule 31 — common failure mode.** Purpose: flag correlated LESS
exposure ("if courts play slow, X picks bust together"). Impact:
disclosure only. **KEEP** (cheap, protective).

**Rule 32 — underdog statistical ceiling.** Purpose: caps underdog
confidence claims (renumbered from stale Rule 9 citations). Impact:
ceiling; compliance flags stale numbering. Frequency: MEASURE. **AUDIT**
— ceiling value has no recorded evidence trail; measure before trusting.

═══════════════════════════════════════════════════════════════════
## CONFIDENCE ARCHITECTURE
═══════════════════════════════════════════════════════════════════

**Conservation Rule (v7.9.8).** Purpose: every uncertainty charged
exactly once — anchor = weighted path probability (≤80%), caps = limits,
deductions only for outside-path uncertainty with a one-clause
justification; cap-covered facts (hold, thin data) are never also
deductions (Finding 4). Location: all three docs + enforced by the
scoring ledger. Dependencies: EVERYTHING downstream — this is the
constitution of the confidence system. **KEEP.**

**Confidence Conservation Ledger.** Purpose: every scoring move
itemized; unexplained movement = HIGH-SEVERITY alert. Location:
scoring_agent (_adj + note builder). Dependencies: none; everything
depends on it. **KEEP** — this is the instrument that caught half of
this week's bugs.

**Correction 5 — 65% floor.** Purpose: a reasonably-supported direction
never posts below 65%. Impact: the ONLY upward mechanism in the system.
Eligibility: not thin-data, not unstable-LESS, no Cat-A penalty (in code
comments; should be one sentence in the HANDOFF too). Telemetry added so
the suite can answer: do floored 60-64% evals hit at 65% rates?
**REVIEW** — keep until the floored-pick bucket says otherwise.

**Dominance framework (LESS path).** HARD → GREEN-eligible; EDGE 69;
SOFT 66; UNSTABLE/UNKNOWN 62; normalization handles "Strong EDGE" etc.
Serve-stat props exempt (own gate). Matches docs exactly. **KEEP.**

**Proven-competitive REQs (MORE path).** 4/4 → GREEN-eligible; <4 → 69.
Also the exemption key for the serve-stat coin-flip gate (REQ3 IS the
buffer question). **KEEP.**

**Serve-stat gate (DF/Aces).** Strict <0.5 coin-flip band (inclusive
boundary removed — it was catching the standard X.5 line offset); MORE
with 4/4 REQs exempt (double-charge removed — the Djokovic stolen
GREEN); missing average → 65% cap. **KEEP** — post-fix; benchmark it.

**V8 tier caps.** Data-quality ceilings (Tier 3 = 72%, etc.). Purpose:
confidence can't exceed what the data tier supports. **KEEP.**

**Thin-data cap (68%) / hold gates (68%, 62% BP).** Purpose: no GREEN
without the load-bearing data. Now the SINGLE charge for those facts
(Finding 4). **KEEP.**

**BP Rule v7.3.** BP MORE below 2.5 = NO PLAY (hard block, alerted);
surface ceilings grass 72 / hard 75 / clay 78; opponent-hold suppression
(≥85% → 55% cap; 80-84 → -12%; 75-79 → -10%). **AUDIT** — the surface
ceilings and suppression tiers are the largest unmeasured numeric block
in the system; BP was historically locked out of early versions for a
reason. Benchmark before trusting BP GREENs.

**Goblin/Red Demon rules.** MORE-only locks; LESS conflict → 55%; Red
Demon partial justification -3%; never on a slip without explicit
approval. **KEEP** (operator-protective by design).

**Total Sets gates.** TS MORE <3 REQs → 67; Red Demon TS <4 REQs → 65;
TS evaluated only after TG (evaluation order lock); TS-vs-TG correlation
conflict alert. Origin: "Total Sets MORE as default" was a locked
formal-flaw correction. **KEEP.**

**Volatility cap.** UNSTABLE/UNKNOWN dominance + MORE + <3 REQs → 67.
Note: keys off dominance_level, NOT classification (v7.8 demoted
classification to context-only; the stale comment claiming otherwise was
fixed). **KEEP.**

**Form override (Cap 6).** Recent surface title → blowout-LESS capped
65%. **AUDIT** — narrow trigger, unmeasured; suite will show whether it
ever fires and whether it saves or costs.

**CFEF triggers.** Fatigue/context suppression (-2 to -5%, full
suppression for back-to-back per tonight's Rule 30 resolution); Week 1-2
symmetric-rust exemption; 2+ triggers on the "dominant" side →
reclassify UNSTABLE. Dependencies: Rule 30, dominance. **REVIEW** —
trigger definitions are spread across DT sections; worth consolidating
into one list next docs pass.

═══════════════════════════════════════════════════════════════════
## COMPLIANCE ARCHITECTURE
═══════════════════════════════════════════════════════════════════

**Category A/B/C.** A = data misuse or direction-contradicts-evidence
ONLY (-3%/flag, cap -15%); B = procedural, zero cost (Rule_
DirectionDrivers forced B-by-definition; confidence-math-structure
critiques are B; wrong-rule filing banned); C = malformed audit →
SYSTEM_FAILURE, no fabricated penalty, no pick. Retraction net kills
self-retracted flags. B-only flags = accept with note, NO Sonnet retry
(cost fix). **KEEP** — post this week's fixes, this is the strongest
part of the system.

**Direction Drivers / Direction Integrity.** Drivers section =
formatting (B); genuine contradiction = DirectionIntegrity /
DriverConfidenceSplit (A). **KEEP.**

═══════════════════════════════════════════════════════════════════
## DUPLICATION WATCHLIST (candidate echoes between rules)
═══════════════════════════════════════════════════════════════════
1. **Rank gap** feeds Correction 24, dominance classification, and
   Competition-Context Filter — three rules, one fact. The echo tracer
   (--echo-trace) is built to catch when all three add confidence in one
   evaluation. Highest-priority echo candidate.
2. **Fatigue** touches Rule 30, CFEF, and ML physical factors — scoping
   is documented (Rule 30 scaled vs CFEF back-to-back) but worth one
   suite cycle of verification.
3. **Competition-Context Filter vs Correction 24** — overlapping intent
   (who caused the struggles?); Correction 24 is gap-gated, CCF is
   always-active. If suite shows both firing on the same picks with no
   distinct contribution, merge candidates.

## PRIORITY ORDER FOR MEASUREMENT
1. Rule 30 (worst early sample), 2. BP Rule tiers (largest unmeasured
block), 3. Correction 24 post-tightening, 4. Form override / Rule 32
(may never meaningfully fire), 5. Floor (telemetry already wired).
