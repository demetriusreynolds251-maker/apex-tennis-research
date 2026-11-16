#!/usr/bin/env python3
"""APEX-GOBLIN-FLOOR-FIX-2026-09-24 -- fixes a NameError in the goblin break-even
patch: GOBLIN_BREAKEVEN was defined only in the patch-writing script's own namespace,
never in the text actually inserted into openclaw_core.py, so scoring_agent crashed
at runtime the first time a goblin pick reached the new check. Adds the constant
inline where it's used.
Usage: python3 apex_goblin_floor_fix.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "openclaw_core.py"
PIN = "bca00bfe7c16f2eb4a0c39fe6bede55505f9ce22bdd841f6b500d8a1bc86a690"
MARK = "APEX-GOBLIN-FLOOR-FIX-2026-09-24"

A1_OLD = '''    # APEX-GOBLIN-FLOOR-2026-09-24: goblin is MORE-only and needs 72.1% to break
    # even at goblin payout odds. This runs LAST, after the Correction-5 floor and
    # Gate-11B format correction above (both can still move confidence), so it
    # checks the true final number rather than a value something downstream could
    # still push back above the line unnoticed.
    if (scored_result.get("prop_type_classified") == "goblin"'''
A1_NEW = '''    # APEX-GOBLIN-FLOOR-2026-09-24: goblin is MORE-only and needs 72.1% to break
    # even at goblin payout odds. This runs LAST, after the Correction-5 floor and
    # Gate-11B format correction above (both can still move confidence), so it
    # checks the true final number rather than a value something downstream could
    # still push back above the line unnoticed.
    GOBLIN_BREAKEVEN = 0.721   # APEX-GOBLIN-FLOOR-FIX-2026-09-24: defined inline, was undefined at runtime
    if (scored_result.get("prop_type_classified") == "goblin"'''

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    c = src.count(A1_OLD); assert c == 1, f"anchor matched {c}x"
    print("CHECK OK: SHA pinned, anchor 1/1 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_gobfloorfix"; shutil.copy2(F, bak)
    open(F, "w", encoding="utf-8").write(src.replace(A1_OLD, A1_NEW, 1))
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
