#!/usr/bin/env python3
"""APEX-TYPEREC-TRK-2026-09-09 -- settled picks carry prop_type; the tracker's Discord post
shows a Standard / Goblin / Demon split beside the group records.
Usage: python3 apex_typerec_trk_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "apex_edge_tracker.py"; PIN = "88e6ffc853da613ce8a50a86eb9ab9236b661171d5c15822797bed988a6d6bbc"
MARK = "APEX-TYPEREC-TRK-2026-09-09"

A1_OLD = r'''             "line": line, "direction": direction, "prob": prob, "actual": actual}
        d["bo5"] = str(r.get("best_of") or "").strip() in ("5", "5.0")
'''
A1_NEW = r'''             "line": line, "direction": direction, "prob": prob, "actual": actual,
             "prop_type": ((pk or {}).get("prop_type") or "untyped").strip().lower()}   # APEX-TYPEREC-TRK
        d["bo5"] = str(r.get("best_of") or "").strip() in ("5", "5.0")
'''
A2_OLD = r'''             "direction": (r.get("direction") or "MORE").upper(), "prob": _f(r.get("prob")), "actual": actual}
'''
A2_NEW = r'''             "direction": (r.get("direction") or "MORE").upper(), "prob": _f(r.get("prob")), "actual": actual,
             "prop_type": (r.get("prop_type") or "untyped").strip().lower()}   # APEX-TYPEREC-TRK
'''
A3_OLD = r'''    L.append("🔥 POTENTIAL EDGE TRACKER")
'''
A3_NEW = r'''    L.extend(_type_lines(rec))          # APEX-TYPEREC-TRK-2026-09-09
    L.append("🔥 POTENTIAL EDGE TRACKER")
'''
A4_OLD = r'''def _rs(r):
'''
A4_NEW = r'''def _type_lines(rec):
    """APEX-TYPEREC-TRK-2026-09-09: record by book prop type. Logged since 2026-09-08;
    anything settled before that is untyped and reported as such, never guessed."""
    try:
        picks = [p for p in rec["overall"]["picks"] if p.get("hit") is not None]
        b = {}
        for p in picks:
            t = p.get("prop_type") or "untyped"
            s = b.setdefault(t, [0, 0]); s[0 if p["hit"] else 1] += 1
        typed = {k: v for k, v in b.items() if k != "untyped"}
        if not typed:
            return ["", "🎲 PROP TYPE — no settled picks carry a type yet (logging began 09-08)"]
        out = ["", "🎲 PROP TYPE"]
        for k in sorted(typed):
            w, l = typed[k]; n = w + l
            out.append("  %-12s %d–%d (%s) · 3-leg of these cashes %d%%" % (
                k, w, l, _pct(w / n), round((w / n) ** 3 * 100)))
        if b.get("untyped"):
            out.append("  %-12s %d–%d (pre-09-08, type not logged)" % ("untyped", *b["untyped"]))
        return out
    except Exception:
        return []


def _rs(r):
'''
ANCHORS = [("A4", A4_OLD, A4_NEW), ("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors 4/4 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pretyperectrk"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
