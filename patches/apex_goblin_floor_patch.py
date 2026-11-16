#!/usr/bin/env python3
"""APEX-GOBLIN-FLOOR-2026-09-24 -- goblin props are MORE-only and pay out at odds
that require a 72.1% win probability to break even. The existing PROP TYPE
ENFORCEMENT block (in scoring_agent) locks direction and requires GREEN, but never
checked the actual number against that break-even -- a goblin pick with a fully
legitimate MORE direction could still ship at, say, 60% confidence and lose money
by construction. This patch adds the missing floor as the true final check, after
every other cap/floor/correction in the function has already run (Correction-5
floor and Gate-11B format correction both execute after this point in the file and
can still move confidence, so checking any earlier risks the floor being silently
bypassed by a later adjustment). Blocked picks get a new terminal status,
GOBLIN_BELOW_BREAKEVEN, matching the existing BP_RULE_BLOCKED / NO_PLAY pattern
exactly: logged, alerted, terminated, heartbeat as success (blocking a bad pick
correctly is a correct outcome, same reasoning as BP_RULE_BLOCKED).
Usage: python3 apex_goblin_floor_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "openclaw_core.py"; PIN = "626bdca3267cd93076773b112773cc61d9f36fdda34e0896d8e8d08cb7f25140"
MARK = "APEX-GOBLIN-FLOOR-2026-09-24"
GOBLIN_BREAKEVEN = 0.721   # goblin payout structure requires this win prob to break even

A1_OLD = '''    d1.heartbeat("scoring", "IDLE", increment_success=True, _logger=log)

    return scored_result'''
A1_NEW = '''    # APEX-GOBLIN-FLOOR-2026-09-24: goblin is MORE-only and needs 72.1% to break
    # even at goblin payout odds. This runs LAST, after the Correction-5 floor and
    # Gate-11B format correction above (both can still move confidence), so it
    # checks the true final number rather than a value something downstream could
    # still push back above the line unnoticed.
    if (scored_result.get("prop_type_classified") == "goblin"
            and scored_result.get("confidence") is not None
            and scored_result.get("confidence") < GOBLIN_BREAKEVEN
            and scored_result.get("status") not in ("BP_RULE_BLOCKED", "AUDIT_MALFORMED", "NO_PLAY")):
        _gb_conf = scored_result["confidence"]
        log("Scoring", f"GOBLIN BREAK-EVEN BLOCK — {_gb_conf:.1%} is below the "
            f"{GOBLIN_BREAKEVEN:.1%} goblin needs to break even. No pick produced.")
        send_discord("alerts",
            f"\U0001f6d1 **GOBLIN BELOW BREAK-EVEN — NO PICK** — {evaluated.get('player')} "
            f"{evaluated.get('line')} {stat_type}\\n"
            f"Final confidence {_gb_conf:.1%} is below the {GOBLIN_BREAKEVEN:.1%} "
            f"goblin payout requires to break even. MORE direction and GREEN/YELLOW "
            f"grade do not override this -- blocked at scoring, not posted."
        )
        d1.terminate(eval_id, "GOBLIN_BELOW_BREAKEVEN",
                     f"goblin confidence {_gb_conf:.1%} below {GOBLIN_BREAKEVEN:.1%} break-even",
                     _logger=log)
        d1.heartbeat("scoring", "IDLE", detail="GOBLIN_BELOW_BREAKEVEN", increment_success=True, _logger=log)
        return {**scored_result, "status": "GOBLIN_BELOW_BREAKEVEN", "confidence": None,
                "color": "RED", "emoji": "\U0001f534",
                "note": f"goblin {_gb_conf:.1%} below {GOBLIN_BREAKEVEN:.1%} break-even -- no pick produced"}

    d1.heartbeat("scoring", "IDLE", increment_success=True, _logger=log)

    return scored_result'''
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    c = src.count(A1_OLD); assert c == 1, f"anchor matched {c}x"
    print("CHECK OK: SHA pinned, anchor 1/1 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pregoblinfloor"; shutil.copy2(F, bak)
    open(F, "w", encoding="utf-8").write(src.replace(A1_OLD, A1_NEW, 1))
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
