import sys
sys.path.insert(0, "/home/claude")
import openclaw_core as oc

sent_messages = []
oc.send_discord = lambda channel, msg: sent_messages.append((channel, msg))


def reset():
    sent_messages.clear()


# ── Test 1: two LESS total_games picks, same tournament -> flagged, disclosed ──
def test_correlated_flagged():
    reset()
    props = [
        {"player": "A", "stat_type": "total_games", "direction": "LESS", "tournament": "Wimbledon", "confidence": 0.71},
        {"player": "B", "stat_type": "aces", "direction": "LESS", "tournament": "Wimbledon", "confidence": 0.68},
        {"player": "C", "stat_type": "double_faults", "direction": "MORE", "tournament": "Wimbledon", "confidence": 0.70},
    ]
    result = oc.rule_31_correlation_check(props)
    assert result[0]["rule31_flag"] is True, "FAIL: player A should be flagged"
    assert result[1]["rule31_flag"] is True, "FAIL: player B should be flagged"
    assert "rule31_flag" not in result[2], "FAIL: player C (MORE direction) should never be flagged"
    assert result[0]["confidence"] == 0.71, "FAIL: Rule 31 must never touch confidence (disclosure only)"
    assert len(sent_messages) == 1, f"FAIL: expected one disclosure message, got {len(sent_messages)}"
    assert "Wimbledon" in sent_messages[0][1]
    print("PASS — two correlated LESS picks (total_games + aces, same tournament) flagged, "
          "disclosed once, confidence untouched, MORE-direction pick correctly ignored")


# ── Test 2: only ONE LESS pick at a tournament -> no flag, no disclosure ──
def test_single_pick_not_flagged():
    reset()
    props = [
        {"player": "A", "stat_type": "total_games", "direction": "LESS", "tournament": "US Open", "confidence": 0.71},
        {"player": "B", "stat_type": "total_games", "direction": "LESS", "tournament": "Miami Open", "confidence": 0.68},
    ]
    result = oc.rule_31_correlation_check(props)
    assert "rule31_flag" not in result[0], "FAIL: lone pick at a tournament should not be flagged"
    assert "rule31_flag" not in result[1], "FAIL: lone pick at a different tournament should not be flagged"
    assert sent_messages == [], "FAIL: no disclosure should be sent when nothing is correlated"
    print("PASS — two LESS picks at two DIFFERENT tournaments (one each) correctly not flagged")


# ── Test 3: non-court-speed-sensitive stat types don't trigger it ──
def test_non_sensitive_stats_ignored():
    reset()
    props = [
        {"player": "A", "stat_type": "double_faults", "direction": "LESS", "tournament": "Wimbledon", "confidence": 0.71},
        {"player": "B", "stat_type": "break_points_won", "direction": "LESS", "tournament": "Wimbledon", "confidence": 0.68},
    ]
    result = oc.rule_31_correlation_check(props)
    assert "rule31_flag" not in result[0], "FAIL: double_faults is not court-speed-sensitive, should not flag"
    assert "rule31_flag" not in result[1], "FAIL: break_points_won is not court-speed-sensitive, should not flag"
    assert sent_messages == []
    print("PASS — non-court-speed-sensitive stat types (double_faults, break_points_won) "
          "correctly excluded from the correlation check")


# ── Test 4: rule31_correlated_with correctly names the other pick(s) ──
def test_correlated_with_names():
    reset()
    props = [
        {"player": "Learner Tien", "stat_type": "total_games", "direction": "LESS", "tournament": "Wimbledon", "confidence": 0.71},
        {"player": "Novak Djokovic", "stat_type": "aces", "direction": "LESS", "tournament": "Wimbledon", "confidence": 0.68},
    ]
    result = oc.rule_31_correlation_check(props)
    assert result[0]["rule31_correlated_with"] == ["Novak Djokovic aces LESS"]
    assert result[1]["rule31_correlated_with"] == ["Learner Tien total_games LESS"]
    print("PASS — rule31_correlated_with correctly names the other implicated pick(s)")


if __name__ == "__main__":
    test_correlated_flagged()
    test_single_pick_not_flagged()
    test_non_sensitive_stats_ignored()
    test_correlated_with_names()
    print("\nALL RULE 31 TESTS PASSED")
