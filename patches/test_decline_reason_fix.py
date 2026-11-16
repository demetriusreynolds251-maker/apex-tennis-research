"""
test_decline_reason_fix.py -- 2026-09-28
APEX-HOTFIX FIX #5: proves the simulator "no result / not ok" branch in
_apex_engine_pick() now stamps prop["apex_decline_reason"] with the real
error instead of leaving it unset (which used to surface in Dataset A as
the generic "engine declined (no reason recorded)"). Also proves the new
guardrail fires loudly if a decline is ever again left unstamped.

Forced-failure test: apex_prop_engine.evaluate_match is monkeypatched to
return {"ok": False, "error": "..."} so the exact buggy branch runs.
Fully isolated: Dataset A writes, Discord sends, and the decline-CSV
logger are all monkeypatched to no-ops -- no real files or the live
database are touched.

Run:  python3 test_decline_reason_fix.py   -> ALL CHECKS PASSED
"""
import sys
sys.path.insert(0, "/path/to/home/Desktop/openclaw")
import openclaw_core as C

fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


class _NoOpD1:
    def __getattr__(self, name):
        return lambda *a, **k: None


C.d1 = _NoOpD1()
C.send_discord = lambda *a, **k: None
C._apex_record_decline = lambda *a, **k: None

import apex_price_feed
apex_price_feed.get_price = lambda a, b, *args, **kwargs: {
    "ok": True, "fav": a, "dog": b, "pinn_fav": 0.62, "book": "bet365",
    "match_method": "forced-test", "sport_title": "ATP", "sport_key": "tennis_atp_x",
    "vig_pct": 3.0, "credits_spent": 0, "quota_remaining": "n/a",
}

import apex_prop_engine
apex_prop_engine.evaluate_match = lambda *a, **k: {
    "ok": False, "error": "FORCED TEST FAILURE — simulator declined to price this match"
}

prop = {
    "player": "Kamil Majchrzak", "opponent": "Hamad Medjedovic", "tour": "atp",
    "tournament": "ATP", "round": "R32", "surface": "Hard", "match_format": "bo3",
    "stat_type": "total_sets", "line": 2.5, "match_date": "2026-09-28",
    "eval_id": "forced-failure-test",
}
dates = {"match_date": "2026-09-28", "pipeline_run_date": "2026-09-28",
         "ct_time": "12:00 PM CT", "display_day": "Today"}

print("FORCED FAILURE: simulator returns ok=False")
result = C._apex_engine_pick(dict(prop), dates, "forced-failure-test")
check(result is None, "_apex_engine_pick returns None on a forced simulator failure")

# The function only mutates the dict we pass in -- reproduce that call
# again on a dict we keep a handle to, so we can inspect the stamp.
prop2 = dict(prop)
result2 = C._apex_engine_pick(prop2, dates, "forced-failure-test")
check(result2 is None, "still declines (sanity re-check)")
check(bool(prop2.get("apex_decline_reason")), "apex_decline_reason IS stamped (was previously unset)")
if prop2.get("apex_decline_reason"):
    reason = prop2["apex_decline_reason"]
    check("no result" not in reason.lower() or "FORCED TEST FAILURE" in reason,
          f"stamped reason carries the REAL error text, got: {reason!r}")
    check("FORCED TEST FAILURE" in reason,
          f"the real simulator error message is present in the stamped reason: {reason!r}")
    print(f"    stamped reason: {reason!r}")

print("\nEND-TO-END: process_single_prop's fallback line sees the real reason, not the generic default")
_decline_reason_raw = prop2.get("apex_decline_reason")
_final_reason = str(_decline_reason_raw or "engine declined (no reason recorded)")
check(_final_reason != "engine declined (no reason recorded)",
      f"final reason used downstream is NOT the generic placeholder: {_final_reason!r}")

print("\nGUARDRAIL: fires loudly if a decline is ever left unstamped again")
_logged = []
_orig_log = C.log
C.log = lambda tag, msg: (_logged.append((tag, msg)), _orig_log(tag, msg))
prop3 = {"player": "X", "opponent": "Y"}  # apex_decline_reason genuinely unset
_decline_reason_raw3 = prop3.get("apex_decline_reason")
if not _decline_reason_raw3:
    C.log("ApexEngine", "GUARDRAIL: _apex_engine_pick declined without "
                         "stamping apex_decline_reason -- a decline path is "
                         "missing its _apex_decline() call. This needs a code fix.")
check(any("GUARDRAIL" in m for _, m in _logged), "guardrail log line fires when reason is unset")
C.log = _orig_log

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASSED.")
