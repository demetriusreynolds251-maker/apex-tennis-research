"""
test_fantasy_score_dashboard_fix.py -- 2026-09-28
APEX-HOTFIX FIX #4: proves ml_readiness_center() and market_coverage_full()
in openclaw_ops.py no longer hardcode Fantasy Score as count=0/BLOCKED BY
DESIGN, and instead report real numbers pulled from Dataset A -- same
shape as every other market. Read-only: both functions only ever open
the warehouse with mode=ro.

Run:  python3 test_fantasy_score_dashboard_fix.py   -> ALL CHECKS PASSED
"""
import sys
import openclaw_ops as ops

fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


print("REGISTRATION: fantasy_score is in REAL_PROP_MARKETS")
check("fantasy_score" in ops.REAL_PROP_MARKETS,
      "'fantasy_score' key present in REAL_PROP_MARKETS")
check(ops.REAL_PROP_MARKETS.get("fantasy_score") == "Fantasy Score",
      "label is 'Fantasy Score'")

print("\nml_readiness_center(): Fantasy Score is unblocked and real")
r1 = ops.ml_readiness_center()
fs1 = next((m for m in r1["markets"] if m["market"] == "Fantasy Score"), None)
check(fs1 is not None, "Fantasy Score row present in ml_readiness_center()")
if fs1:
    check(fs1["blocked"] is False, f"blocked=False, got {fs1['blocked']}")
    check(fs1["tier"] != "BLOCKED BY DESIGN", f"tier is not BLOCKED BY DESIGN, got {fs1['tier']}")
    check("blocked_reason" not in fs1, "no leftover blocked_reason field")
    check(fs1["count"] > 0, f"count > 0 (real Dataset A data), got {fs1['count']}")
    check(fs1["model_status"] == "NOT STARTED",
          "model_status still reported the same way as every other market")

print("\nmarket_coverage_full(): Fantasy Score reports full real detail")
r2 = ops.market_coverage_full()
fs2 = next((m for m in r2 if m["market"] == "Fantasy Score"), None)
check(fs2 is not None, "Fantasy Score row present in market_coverage_full()")
if fs2:
    check(fs2["blocked"] is False, f"blocked=False, got {fs2['blocked']}")
    check(fs2["count"] == fs1["count"], "count matches ml_readiness_center()'s count exactly")
    check(fs2["first_date"] is not None, "first_date is populated (real data, not a stub)")
    check(fs2["players_covered"] > 0, f"players_covered > 0, got {fs2['players_covered']}")

print("\nSAFETY: other markets are unaffected by the fix")
other_markets_1 = {m["market"]: m["count"] for m in r1["markets"] if m["market"] != "Fantasy Score"}
other_markets_2 = {m["market"]: m["count"] for m in r2 if m["market"] != "Fantasy Score"}
check(other_markets_1.get("Total Sets", 0) > 0, "Total Sets still reports real data in ml_readiness_center()")
check(other_markets_2.get("Total Sets", 0) > 0, "Total Sets still reports real data in market_coverage_full()")
check(other_markets_1.get("Moneyline", -1) >= 0, "Moneyline row still present and computed")

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASSED.")
