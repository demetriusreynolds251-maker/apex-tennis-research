#!/usr/bin/env python3
"""APEX-BB-002c2 -- put player dedup + also-line into best_bets_detail (C3/C4 landed in best_bets_block by anchor collision)."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-BB-002c2"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
E = [
("D1 dedup in best_bets_detail",
'''        scored.sort(key=lambda d: d["sc"] if worst else -d["sc"])
        if worst:''',
'''        scored.sort(key=lambda d: d["sc"] if worst else -d["sc"])
        # APEX-BB-002c2: one numbered slot per player-side (skip in worst mode --
        # every weak pick deserves its own warning line there).
        if not worst:
            _seen, _prim = {}, []
            for d in scored:
                _pk = (d["p"].get("player") or "") + "|" + (d["p"].get("opponent") or "")
                if _pk in _seen:
                    _seen[_pk].setdefault("more", []).append(d)
                else:
                    _seen[_pk] = d; _prim.append(d)
            scored = _prim
        if worst:'''),
("D2 also-line in the detail renderer",
'''            L.append(("Why ranked low: %s" % why_dn) if worst else ("Why Apex likes it: %s" % why_up))
            if not worst and d["sc"] < 50:''',
'''            L.append(("Why ranked low: %s" % why_dn) if worst else ("Why Apex likes it: %s" % why_up))
            if d.get("more"):
                L.append("also: " + " \u00b7 ".join("%s %s %s (%d)" % (LABEL.get(m["p"]["category"], m["p"]["category"]),
                         m["p"]["line"], m["p"]["direction"], m["sc"]) for m in d["more"][:4]))
            if not worst and d["sc"] < 50:'''),
]
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
ok = True
print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
for name, old, new in E:
    n = src.count(old); print("  [%s] %s: %d" % ("ok" if n == 1 else "FAIL", name, n)); ok = ok and n == 1
if not ok: sys.exit("ABORT -- nothing written (paste the FAIL name)")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2c2"; shutil.copy2(FN, bak)
for name, old, new in E: src = src.replace(old, new, 1)
open(FN, "w", encoding="utf-8").write(src)
import py_compile
try:
    py_compile.compile(FN, doraise=True); print("smoke: compile OK")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
