#!/usr/bin/env python3
"""APEX-GOBLIN-FLOOR-SELFTEST-2026-09-24 -- adds two checks to the existing --selftest
command, right after the hold-gate check, using the same 'fake' pattern already in the
file: (1) a goblin prop engineered to land well under 72.1% must return status
GOBLIN_BELOW_BREAKEVEN with confidence None; (2) a goblin prop engineered to land
comfortably above 72.1% must pass through unaffected by this patch.
Usage: python3 apex_goblin_floor_selftest.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "openclaw_core.py"
PIN = "0328973bda23ec5789e2d51e3e99a81d7d71903fb28d37fdcd64e5a321cf8e54"
MARK = "APEX-GOBLIN-FLOOR-SELFTEST-2026-09-24"

A1_OLD = '''            scored = scoring_agent(fake, load_weights())
            assert scored["confidence"] < 0.70, f"HOLD GATE FAILED — got {scored['confidence']:.0%}"
            print("PASS: hold gate caps missing-hold prop at", f"{scored['confidence']:.0%}")
            print("ALL SELFTESTS PASSED — walls are live.")'''
A1_NEW = '''            scored = scoring_agent(fake, load_weights())
            assert scored["confidence"] < 0.70, f"HOLD GATE FAILED — got {scored['confidence']:.0%}"
            print("PASS: hold gate caps missing-hold prop at", f"{scored['confidence']:.0%}")

            # APEX-GOBLIN-FLOOR-SELFTEST-2026-09-24: goblin below 72.1% must be blocked
            fake_gob_low = {"stat_type":"aces","direction":"MORE","line":7.5,
                    "match_type":"COMPETITIVE","dominance_level":"SOFT","competitive_reqs":2,
                    "eval_confidence": 0.60, "prop_type_classified":"goblin",
                    "research_data":{"player":{"serve_hold_pct":70,"missing_fields":[]},
                                     "opponent":{"serve_hold_pct":70,"missing_fields":[]},
                                     "match_context":{"stage":2}}}
            scored_gob_low = scoring_agent(fake_gob_low, load_weights())
            assert scored_gob_low["status"] == "GOBLIN_BELOW_BREAKEVEN", \\
                f"GOBLIN FLOOR FAILED TO BLOCK — status was {scored_gob_low.get('status')}, " \\
                f"confidence {scored_gob_low.get('confidence')}"
            assert scored_gob_low["confidence"] is None, "GOBLIN FLOOR should null confidence on block"
            print("PASS: goblin below break-even correctly blocked -> GOBLIN_BELOW_BREAKEVEN")

            # goblin comfortably above 72.1% must pass through untouched
            fake_gob_high = {"stat_type":"aces","direction":"MORE","line":4.5,
                    "match_type":"COMPETITIVE","dominance_level":"HARD","competitive_reqs":4,
                    "eval_confidence": 0.90, "prop_type_classified":"goblin",
                    "research_data":{"player":{"serve_hold_pct":85,"missing_fields":[]},
                                     "opponent":{"serve_hold_pct":60,"missing_fields":[]},
                                     "match_context":{"stage":2}}}
            scored_gob_high = scoring_agent(fake_gob_high, load_weights())
            assert scored_gob_high["status"] != "GOBLIN_BELOW_BREAKEVEN", \\
                f"GOBLIN FLOOR FALSE POSITIVE — blocked a pick at {scored_gob_high.get('confidence')}"
            print("PASS: goblin above break-even passes through at",
                  f"{scored_gob_high['confidence']:.0%}" if scored_gob_high.get("confidence") is not None else "N/A")

            print("ALL SELFTESTS PASSED — walls are live.")'''

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    c = src.count(A1_OLD); assert c == 1, f"anchor matched {c}x"
    print("CHECK OK: SHA pinned, anchor 1/1 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pregoblinfloortest"; shutil.copy2(F, bak)
    open(F, "w", encoding="utf-8").write(src.replace(A1_OLD, A1_NEW, 1))
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
