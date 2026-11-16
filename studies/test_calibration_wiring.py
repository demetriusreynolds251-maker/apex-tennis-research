"""
Real functional test against the patched openclaw_core.py — not a
reimplementation. Monkeypatches only the two boundary points that would
otherwise require network (call_model) or a real calibration log file
(record_provisional_rule_fire), and calls the real, unmodified
evaluation_agent() / scoring_agent() functions directly.
"""
import sys
sys.path.insert(0, "/home/claude")
import openclaw_core as oc

fired = []

def fake_record(rule_name, eval_id, player=None, fired_at=None):
    fired.append((rule_name, eval_id, player))

oc.record_provisional_rule_fire = fake_record


def reset():
    fired.clear()


# ================================================================
# TEST 1 — RBMD cited (confirmed), Gate14 cited (challenged) —
# both should fire exactly once each, LPAB_PSAR should NOT fire
# even though it's also mentioned in text.
# ================================================================
def test_citation_hook():
    reset()
    fake_result = (
        "Some reasoning...\n"
        "✅ RULE: RBMD friction check passed\n"
        "⚡ RULE: Gate14 home lean applied, -2%\n"
        "The evaluation also discusses LPAB_PSAR conceptually here but "
        "never cites it with a RULE: marker.\n"
        "FINAL DIRECTION: MORE. Final confidence: 71%."
    )

    oc.call_model = lambda *a, **k: (fake_result, "end_turn", {"output_tokens": 50})
    oc.build_evaluation_content = lambda prop: "content"
    oc._ATE_AVAILABLE = False  # isolate this test from ATE entirely

    prop = {"player": "Test Player", "opponent": "Test Opp", "eval_id": "eval-1",
            "stat_type": "double_faults", "line": 2.5}
    evaluated = oc.evaluation_agent(prop)

    names = sorted(f[0] for f in fired)
    assert names == ["Gate14_Props_Procedural", "RBMD_v1_2"], f"FAIL: got {names}"
    assert all(f[1] == "eval-1" for f in fired), "FAIL: eval_id not threaded correctly"
    assert all(f[2] == "Test Player" for f in fired), "FAIL: player not threaded correctly"
    print("PASS — test_citation_hook: RBMD + Gate14 fired exactly once each, "
          "LPAB_PSAR correctly did NOT fire via citation")


# ================================================================
# TEST 2 — same rule cited twice (once confirmed, once challenged)
# must still fire only ONCE (dedup via set union).
# ================================================================
def test_dedup_same_evaluation():
    reset()
    fake_result = (
        "✅ RULE: RBMD first mention\n"
        "⚡ RULE: RBMD second mention, flagged\n"
        "FINAL DIRECTION: LESS. Final confidence: 68%."
    )
    oc.call_model = lambda *a, **k: (fake_result, "end_turn", {"output_tokens": 50})
    oc.build_evaluation_content = lambda prop: "content"
    oc._ATE_AVAILABLE = False

    prop = {"player": "Test Player 2", "opponent": "Opp 2", "eval_id": "eval-2",
            "stat_type": "aces", "line": 4.5}
    oc.evaluation_agent(prop)

    rbmd_fires = [f for f in fired if f[0] == "RBMD_v1_2"]
    assert len(rbmd_fires) == 1, f"FAIL: expected 1 fire, got {len(rbmd_fires)}"
    print("PASS — test_dedup_same_evaluation: RBMD cited twice in one eval, "
          "fired exactly once")


# ================================================================
# TEST 3 — no citations at all: nothing fires, no crash.
# ================================================================
def test_no_citations():
    reset()
    fake_result = "Plain reasoning, no rule citations at all. Final confidence: 65%."
    oc.call_model = lambda *a, **k: (fake_result, "end_turn", {"output_tokens": 30})
    oc.build_evaluation_content = lambda prop: "content"
    oc._ATE_AVAILABLE = False

    prop = {"player": "P3", "opponent": "O3", "eval_id": "eval-3",
            "stat_type": "total_games", "line": 21.5}
    oc.evaluation_agent(prop)
    assert fired == [], f"FAIL: expected no fires, got {fired}"
    print("PASS — test_no_citations: no rule text -> no fires, no crash")


# ================================================================
# TEST 4 — LPAB_PSAR mechanical gate: fires when gap < 0.5,
# does NOT fire when gap >= 0.5, does NOT fire when data missing.
# ================================================================
def test_lpab_psar_mechanical_gate():
    weights = {}  # scoring_agent reads defensively via .get() throughout

    base = {
        "player": "Gate Player", "stat_type": "double_faults", "line": 3.0,
        "direction": "LESS", "match_type": "COMPETITIVE",
        "dominance_level": "HARD", "competitive_reqs": 2,
        "eval_confidence": 0.75,
        "research_data": {
            "player": {"avg_double_faults": 3.2, "serve_hold_pct": 0.80,
                       "missing_fields": []},
            "opponent": {"serve_hold_pct": 0.78, "missing_fields": []},
            "match_context": {"stage": 2},
        },
    }

    # Case A: gap = |3.2 - 3.0| = 0.2 < 0.5 -> SHOULD fire
    reset()
    oc.scoring_agent(dict(base), weights, eval_id="eval-gap-small")
    assert any(f[0] == "LPAB_PSAR_v1_0" and f[1] == "eval-gap-small" for f in fired), \
        f"FAIL: expected LPAB_PSAR_v1_0 fire on small gap, got {fired}"
    print("PASS — LPAB_PSAR fires when gap (0.2) < 0.5")

    # Case B: gap = |3.2 - 2.0| = 1.2 >= 0.5 -> should NOT fire
    reset()
    wide = dict(base); wide["line"] = 2.0
    oc.scoring_agent(wide, weights, eval_id="eval-gap-wide")
    assert not any(f[0] == "LPAB_PSAR_v1_0" for f in fired), \
        f"FAIL: expected no fire on wide gap, got {fired}"
    print("PASS — LPAB_PSAR does NOT fire when gap (1.2) >= 0.5")

    # Case C: missing avg_double_faults -> hits the missing-data cap
    # branch instead, must NOT be counted as an LPAB_PSAR fire
    reset()
    missing = dict(base)
    missing["research_data"] = dict(base["research_data"])
    missing["research_data"]["player"] = {"avg_double_faults": None, "missing_fields": []}
    oc.scoring_agent(missing, weights, eval_id="eval-missing-data")
    assert not any(f[0] == "LPAB_PSAR_v1_0" for f in fired), \
        f"FAIL: missing-data branch must not count as LPAB_PSAR fire, got {fired}"
    print("PASS — missing serve-stat data correctly does NOT count as LPAB_PSAR fire")

    # Case D: exact boundary gap = 0.5 -> strict `<` means NOT flip-eligible,
    # must NOT fire (confirms the earlier inclusive-boundary fix still holds)
    reset()
    boundary = dict(base); boundary["line"] = 2.7  # |3.2-2.7| == 0.5 exactly
    oc.scoring_agent(boundary, weights, eval_id="eval-boundary")
    assert not any(f[0] == "LPAB_PSAR_v1_0" for f in fired), \
        f"FAIL: exact 0.5 boundary must not fire (strict <), got {fired}"
    print("PASS — exact 0.5 boundary correctly does NOT fire (strict <, not <=)")


if __name__ == "__main__":
    test_citation_hook()
    test_dedup_same_evaluation()
    test_no_citations()
    test_lpab_psar_mechanical_gate()
    print()
    print("ALL TESTS PASSED")
