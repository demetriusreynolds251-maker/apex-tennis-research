#!/usr/bin/env python3
"""
TRUTH LOCK BEHAVIORAL TEST — run this on the Mac Mini, not in a sandbox.

This makes REAL API calls to Haiku via your configured ANTHROPIC_API_KEY.
It does NOT touch Discord, V8, or any live pick — it only calls
compliance_agent() directly with synthetic, deliberately-broken evaluation
text, to prove Rule 12 (Truth Lock) actually catches what it's supposed to
catch, not just that the rule text exists.

Run from inside the openclaw folder:
    python3 test_truth_lock.py

Expected result: both test cases print "PASS — Rule12 fired" and exit 0.
If either prints "FAIL", Rule 12 is not actually enforcing anything and
needs more work before you trust it on real picks.
"""
import sys
sys.path.insert(0, ".")
from openclaw_core import compliance_agent  # noqa: E402

# ============================================================
# TEST CASE A — the exact Cobolli/Fery date-hedging violation
# ============================================================
# Ground truth clearly has match_date. The evaluation text below
# deliberately reproduces the EXACT hedging language from the real
# Cobolli/Fery file ("if play date is 7/7... if 7/8... if 7/9").
# Rule 12 should catch this and flag it.

test_a = {
    "player": "Test Player A",
    "opponent": "Test Opponent A",
    "stat_type": "double_faults",
    "line": 3.5,
    "direction": "MORE",
    "match_type": "COMPETITIVE",
    "is_favorite": True,
    "match_date": "2026-07-08",
    "_v8_packet_prefetched": {
        "player": {"recent_matches": [{"date": "2026-07-06"}]},
        "opponent": {"recent_matches": [{"date": "2026-07-06"}]},
    },
    "research_data": {
        "match_context": {"stage": 3},
        "player": {"avg_double_faults": 3.2, "df_match_count": 5,
                    "this_tournament_matches": 4, "this_tournament_3set_count": 2,
                    "serve_hold_pct": 0.797},
        "opponent": {"avg_double_faults": 2.2, "df_match_count": 5,
                      "this_tournament_matches": 4, "this_tournament_3set_count": 0,
                      "serve_hold_pct": 0.781},
    },
    "evaluation_output": """RULE 30 RESOLUTION (Rest-Day Awareness):
Player's most recent confirmed match: 2026-07-06. Today's evaluation date
context: Stage 3. If this match is being evaluated for play on 2026-07-07,
turnaround = ~24 hours or less -> -8% deduction applies. If play date is
2026-07-08, turnaround = ~48 hours -> -4% deduction applies. If play date
is 2026-07-09 or later, turnaround = 48+ hours -> 0% deduction. Round is
UNCONFIRMED per the prop card, so exact play date cannot be locked. I will
apply the conservative -4% deduction and flag this as the operative
assumption.
FINAL DIRECTION: MORE. Final confidence: 69%. Color: YELLOW.""",
}

# ============================================================
# TEST CASE B — the exact Cobolli/Fery "cannot compute" violation
# ============================================================
# Ground truth clearly has avg_double_faults + df_match_count=5. The
# evaluation text deliberately reproduces the EXACT "cannot compute"
# language from the real file, followed by a synthetic estimate instead.

test_b = dict(test_a)  # same ground truth, different evaluation text
test_b["evaluation_output"] = """CHECKPOINT — HOLD DATA:
The 3.2 average spans 5 matches. Without the individual match DF figures,
I cannot compute a Best-of-5-only average -- but the structural argument
(more sets = more service games = more DF opportunities) is sound.
29 second-serve points x 6% DF rate = ~1.7 DFs per set x 4 sets = ~6.8 DFs
in a 4-set match. This is a rough structural estimate, not a precise
calculation -- but it confirms the 3.5 line is beatable.
FINAL DIRECTION: MORE. Final confidence: 69%. Color: YELLOW."""


def run_test(name, evaluated):
    print(f"\n{'='*60}\n{name}\n{'='*60}")
    result = compliance_agent(evaluated, attempt=1)
    status = result.get("status")
    flags = result.get("flags", [])
    truth_lock_flags = [f for f in flags if "truthlock" in str(f.get("rule", "")).lower()
                         or "rule12" in str(f.get("rule", "")).lower()
                         or "rule_truthlock" in str(f.get("rule", "")).lower()]

    print(f"Compliance status: {status}")
    print(f"All flags: {flags}")

    if truth_lock_flags:
        print(f"\nPASS — Rule12 fired: {truth_lock_flags}")
        return True
    elif status == "FLAGGED_FOR_MANUAL_REVIEW":
        print("\nINCONCLUSIVE — compliance call itself failed (API/parse "
              "error), not a Rule12 miss. Check your API key / connection "
              "and re-run.")
        return None
    else:
        print("\nFAIL — Rule12 did NOT fire despite a clear, deliberate "
              "violation in the evaluation text. Truth Lock is not "
              "actually enforcing yet.")
        return False


if __name__ == "__main__":
    results = []
    results.append(run_test("TEST CASE A — date hedging despite match_date present", test_a))
    results.append(run_test("TEST CASE B — 'cannot compute' despite DF data present", test_b))

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)
    inconclusive = sum(1 for r in results if r is None)
    print(f"PASS: {passed} | FAIL: {failed} | INCONCLUSIVE: {inconclusive}")

    if failed > 0:
        sys.exit(1)
    elif inconclusive > 0:
        sys.exit(2)
    else:
        sys.exit(0)
