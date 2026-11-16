#!/usr/bin/env python3
"""APEX-TYPECMD-TRK-2026-09-09 -- best_bets_detail gains prop_type= so /goblin and /standard
can show the best N of one prop type. Ranking, scoring and slip layer unchanged.
Usage: python3 apex_typecmd_tracker_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "apex_edge_tracker.py"; PIN = "6b2f753cca096439cd0d68a6652f5f83222373ce4e1342f3af7ebf86f0c119a4"
MARK = "APEX-TYPECMD-TRK-2026-09-09"

A1_OLD = r'''def best_bets_detail(picks, category=None, worst=False, rec=None, limit=15):
'''
A1_NEW = r'''def best_bets_detail(picks, category=None, worst=False, rec=None, limit=15, prop_type=None):
'''
A2_OLD = r'''        rec = rec or records()
        scored = []
        for p in picks:
            cat = p.get("category") or ""
            if not cat:
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob_cal", p.get("prob")), cat, bool(p.get("bo5")), rec)
'''
A2_NEW = r'''        rec = rec or records()
        # APEX-TYPECMD-TRK-2026-09-09: one prop type only (goblin / standard / demon).
        # Rows evaluated before 09-08 carry no prop_type and are simply not in these views.
        if prop_type:
            picks = [p for p in picks if str(p.get("prop_type") or "").lower() == str(prop_type).lower()]
            if not picks:
                return ("No %s props on the current board yet. (Prop type has been logged since "
                        "2026-09-08 -- boards evaluated before then carry no type.)" % prop_type)
        scored = []
        for p in picks:
            cat = p.get("category") or ""
            if not cat:
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob_cal", p.get("prob")), cat, bool(p.get("bo5")), rec)
'''
A3_OLD = r'''        else:
            head = "\U0001F3C6 **APEX BEST BETS TODAY -- %s** (entire evaluated board, %d picks)" % (_d.today().isoformat(), len(scored))
'''
A3_NEW = r'''        elif prop_type:
            head = "\U0001F3C6 **BEST %s PROPS TODAY -- %s** (%d on the board)" % (
                str(prop_type).upper(), _d.today().isoformat(), len(scored))
        else:
            head = "\U0001F3C6 **APEX BEST BETS TODAY -- %s** (entire evaluated board, %d picks)" % (_d.today().isoformat(), len(scored))
'''
A4_OLD = r'''                    "direction": r.get("direction") or "", "prob": prob,
                    "prob_cal": _cal_of(r, prob),          # APEX-ACESCAL-TRK-2026-09-09
'''
A4_NEW = r'''                    "direction": r.get("direction") or "", "prob": prob,
                    "prob_cal": _cal_of(r, prob),          # APEX-ACESCAL-TRK-2026-09-09
                    "prop_type": r.get("prop_type") or "", # APEX-TYPECMD-TRK-2026-09-09
'''
ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW), ("A4", A4_OLD, A4_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors 4/4 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pretypecmd"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
