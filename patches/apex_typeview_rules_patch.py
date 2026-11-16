#!/usr/bin/env python3
"""APEX-TYPEVIEW-RULES-2026-09-18 -- /goblin and /standard return legs you can actually play
together: one pick per match and the category caps, the same rules the Slip Candidates block
uses. Without this the type views could hand back two players from one match.
Usage: python3 apex_typeview_rules_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "apex_edge_tracker.py"; PIN = "d6195a60b44287f1dcfb6dc22c4a1dd50fcd1d844f82d7c184e940c1b900ad99"
MARK = "APEX-TYPEVIEW-RULES-2026-09-18"

A1_OLD = r'''def best_bets_detail(picks, category=None, worst=False, rec=None, limit=15, prop_type=None):
'''
A1_NEW = r'''def best_bets_detail(picks, category=None, worst=False, rec=None, limit=15, prop_type=None,
                     slip_rules=False):
'''
A2_OLD = r'''        medals = {1: "\U0001F947", 2: "\U0001F948", 3: "\U0001F949"}
'''
A2_NEW = r'''        # APEX-TYPEVIEW-RULES-2026-09-18: a prop-type view is a SLIP, so it obeys the slip
        # rules -- one pick per match, max 2 per category. Dropped picks are listed below.
        _held = []
        if slip_rules and not worst:
            _keep, _seen_m, _catn = [], set(), {}
            for _d in scored:
                _p = _d["p"]; _c = _d.get("cat") or _p.get("category", "")
                _mid = _p.get("match_id", "")
                if _mid and _mid in _seen_m:
                    _held.append((_d, "same match as a pick already on this slip")); continue
                if _catn.get(_c, 0) >= 2:
                    _held.append((_d, "category cap: %s already x2 on this slip" % _c)); continue
                _seen_m.add(_mid); _catn[_c] = _catn.get(_c, 0) + 1; _keep.append(_d)
            scored = _keep
        medals = {1: "\U0001F947", 2: "\U0001F948", 3: "\U0001F949"}
'''
A3_OLD = r'''        L.append("_Deterministic read of the current evaluated board -- no re-evaluation._")
'''
A3_NEW = r'''        if _held:                                  # APEX-TYPEVIEW-RULES-2026-09-18
            L.append("\u2500" * 30)
            L.append("**Held back (slip rules):**")
            for _d, _why in _held[:6]:
                _p = _d["p"]; _c = _d.get("cat") or _p.get("category", "")
                _nm = _p["opponent"] if _p.get("player") == "match" else _p.get("player", "")
                L.append("\u00b7 %s %s %s %s -- %s" % (_nm, LABEL.get(_c, _c), _p.get("line", ""),
                                                        _p.get("direction", ""), _why))
        L.append("_Deterministic read of the current evaluated board -- no re-evaluation._")
'''
ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors 3/3 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pretypeview"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
