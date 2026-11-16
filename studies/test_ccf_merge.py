import sys
sys.path.insert(0, "/home/claude")
import openclaw_core as oc

def make_prop(player_rank, opp_rank):
    return {
        "player": "Test Player", "opponent": "Test Opponent",
        "stat_type": "total_games", "line": 21.5, "surface": "hard",
        "prop_type_classified": "standard",
        "research_data": {
            "player": {"ranking": str(player_rank), "avg_double_faults": 3.0,
                       "serve_hold_pct": 0.8, "recent_matches": []},
            "opponent": {"ranking": str(opp_rank), "avg_double_faults": 2.5,
                        "serve_hold_pct": 0.78, "recent_matches": []},
            "match_context": {"stage": 2},
        },
        "compliance_flags": [], "format_contamination": False,
    }

# ── Test 1: large gap (>=100) — merged block fires, no duplicate heading ──
content = oc.build_evaluation_content(make_prop(5, 250))
assert content.count("COMPETITION-CONTEXT FILTER") == 1, \
    f"FAIL: CCF should appear exactly once, found {content.count('COMPETITION-CONTEXT FILTER')}"
assert "CORRECTION 24" not in content, \
    "FAIL: the old duplicate 'CORRECTION 24' heading should no longer exist at all"
assert "CLASS-GAP CONCLUSION" in content, \
    "FAIL: the class-gap conclusion should be present when gap >= 100"
assert content.count("Who specifically caused the struggles") == 1, \
    "FAIL: the 'who caused the struggles' question should appear exactly once, not twice"
assert "VOLATILITY CAP RULE" in content
print("PASS — gap >= 100: Competition-Context Filter appears exactly ONCE, "
      "class-gap conclusion is appended to it (not a separate duplicate block), "
      "old 'CORRECTION 24' heading is gone entirely")

# ── Test 2: small gap (<100) — CCF still fires (always-active), class-gap conclusion does NOT ──
content2 = oc.build_evaluation_content(make_prop(40, 65))  # gap = 25
assert content2.count("COMPETITION-CONTEXT FILTER") == 1, "FAIL: CCF should still be always-active"
assert "CLASS-GAP CONCLUSION" not in content2, \
    "FAIL: class-gap conclusion should NOT appear when gap < 100"
assert "VOLATILITY CAP RULE" in content2
print("PASS — gap < 100: Competition-Context Filter still fires (always-active), "
      "class-gap conclusion correctly absent")

# ── Test 3: exact boundary (gap == 100) — should trigger the class-gap conclusion ──
content3 = oc.build_evaluation_content(make_prop(10, 110))  # gap = 100 exactly
assert "CLASS-GAP CONCLUSION" in content3, "FAIL: gap==100 should trigger (>=100), boundary inclusive"
print("PASS — exact gap==100 boundary correctly triggers the class-gap conclusion (>= is inclusive)")

print("\nALL DUPLICATION-FIX TESTS PASSED")
