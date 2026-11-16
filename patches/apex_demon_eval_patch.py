#!/usr/bin/env python3
"""APEX-DEMON-EVAL-2026-09-04
filter_props: stop skipping ptype=="demon". Treat like red_demon: MORE-only lock,
engine evaluates honestly, writer stamps playable=0 if engine direction contradicts.
Usage: python3 apex_demon_eval_patch.py --check | --apply"""
import hashlib, os, shutil, sys, py_compile, datetime
F    = "openclaw_core.py"
PIN  = "f749a6b96eccaead21715a96ff0753d32e469d5f93cae6e0dbbf2d75cdee86ff"
MARK = "APEX-DEMON-EVAL-2026-09-04"

A_OLD = r'''        # Legacy demon (🔴 red icon without 😈) = SKIP entirely
        if ptype == "demon":
            skipped += 1
            log("Filter", f"Demon skipped: {prop.get('player')} {prop.get('line')}")
            send_discord("system",
                f"🔴 Demon prop skipped: {prop.get('player')} "
                f"{prop.get('line')} {prop.get('stat_type')}"
            )
            continue
'''
A_NEW = r'''        # APEX-DEMON-EVAL-2026-09-04: demons are NO LONGER skipped (82 dropped in
        # manual4 log). Same handling as red_demon: MORE-only lock, engine prices
        # it honestly, _apex_forward_log_row stamps playable=0 on a LESS verdict.
        if ptype == "demon":
            prop["direction_locked"] = "MORE"
            prop["both_directions_available"] = False
            log("Filter", f"Demon 🔴 flagged: {prop.get('player')} "
                f"{prop.get('line')} — MORE only, engine evaluates")
'''

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F).read()
    s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"
    assert MARK not in src, "already applied"
    n = src.count(A_OLD)
    assert n == 1, f"anchor matched {n}x (need exactly 1)"
    i = src.index(A_OLD)
    assert "def filter_props" in src[max(0, i - 3000):i], "anchor not inside filter_props"
    print("CHECK OK: SHA pinned, anchor 1/1 unique, inside filter_props")
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_predemoneval"
    shutil.copy2(F, bak)
    with open(F, "w") as fh:
        fh.write(src.replace(A_OLD, A_NEW, 1))
    try:
        py_compile.compile(F, doraise=True)
    except Exception as e:
        shutil.copy2(bak, F)
        print("py_compile FAILED -> restored from backup:", e)
        sys.exit(1)
    print("APPLIED. backup:", bak)
    print("new sha:", sha(F))

if __name__ == "__main__":
    main()
