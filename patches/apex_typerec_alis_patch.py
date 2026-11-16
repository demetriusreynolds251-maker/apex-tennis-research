#!/usr/bin/env python3
"""APEX-TYPEREC-ALIS-2026-09-09 -- ALIS ledger carries prop_type; analyze() buckets by it;
the cycle report prints a Standard / Goblin / Demon split. Rows before 2026-09-08 have no
type and are reported as untyped rather than guessed.
Usage: python3 apex_typerec_alis_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "apex_learning_engine.py"; PIN = "a260421baac4bccaf642b1dfefe81890b5d2b7846814059832d08cea2b6f7fb9"
MARK = "APEX-TYPEREC-ALIS-2026-09-09"

A1_OLD = r'''                "tier": g("tier"), "result": res,
'''
A1_NEW = r'''                "tier": g("tier"), "result": res,
                "prop_type": (str(g("prop_type")).strip().lower() or "untyped"),   # APEX-TYPEREC-2026-09-09
'''
A2_OLD = r'''    A["by_group"] = {g: bucket([r for r in dec if r["group"] == g]) for g in ("rate", "sim", "tg")}
'''
A2_NEW = r'''    A["by_group"] = {g: bucket([r for r in dec if r["group"] == g]) for g in ("rate", "sim", "tg")}
    # APEX-TYPEREC-2026-09-09: book prop type (standard / goblin / demon / red_demon).
    # Logged since 2026-09-08; everything settled before that is "untyped".
    A["by_type"] = {t: bucket([r for r in dec if (r.get("prop_type") or "untyped") == t])
                    for t in sorted({(r.get("prop_type") or "untyped") for r in dec})}
'''
A3_OLD = r'''    L.append("\n## Groups")
'''
A3_NEW = r'''    L.append("\n## Prop type (standard / goblin / demon)")
    _typed = {t: b for t, b in (A.get("by_type") or {}).items() if t != "untyped"}
    if not _typed:
        L.append("- no settled picks carry a prop type yet (logging began 2026-09-08)")
    else:
        for _t in sorted(_typed):
            _b = _typed[_t]; _n = _b["w"] + _b["l"]
            _r3 = ((_b["w"] / _n) ** 3 * 100) if _n else 0
            L.append(f"- {_t}: {rec_str(_b['w'], _b['l'])}"
                     + (f" ({_b['w']/_n:.1%}) · a 3-leg of these cashes {_r3:.0f}% of the time" if _n else ""))
    _u = (A.get("by_type") or {}).get("untyped")
    if _u and (_u["w"] + _u["l"]):
        L.append(f"- untyped (settled before 09-08): {rec_str(_u['w'], _u['l'])}")
    L.append("\n## Groups")
'''
ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    assert src.index(A2_OLD) < src.index(A3_OLD), "analyze() must precede report_text()"
    print("CHECK OK: SHA pinned, anchors 3/3 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pretyperec"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
