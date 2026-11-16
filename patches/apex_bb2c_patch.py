#!/usr/bin/env python3
"""APEX-BB-002c -- limit 15, one-entry-per-player, degenerate-prob clamp."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-BB-002c"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
E = [
("C1 default limit 15",
"def best_bets_detail(picks, category=None, worst=False, rec=None, limit=10):",
"def best_bets_detail(picks, category=None, worst=False, rec=None, limit=15):"),
("C2 degenerate-prob clamp in apex_score",
'''    if bo5:
        score = min(score, 49.0)
        down.append("Bo5 experimental -- LOW until 25 settled (BO5-FWD-001)")''',
'''    if prob >= 0.95:
        # APEX-BB-002c: near-certain model probabilities on tennis props are
        # almost always broken inputs (08-29: Bo3 math on Bo5 lines scored
        # 95-100 four separate times). Flag, never crown.
        score = min(score, 35.0)
        down.append("\u26a0\ufe0f stated %d%% -- likely artifact, verify the line before trusting" % round(prob * 100))
    if bo5:
        score = min(score, 49.0)
        down.append("Bo5 experimental -- LOW until 25 settled (BO5-FWD-001)")'''),
("C3 one entry per player",
'''        scored.sort(key=lambda d: (d["bo5"], -d["score"]))  # APEX-BB-001b: Bo5 always below Bo3''',
'''        scored.sort(key=lambda d: (d["bo5"], -d["score"]))  # APEX-BB-001b: Bo5 always below Bo3
        # APEX-BB-002c: one slot per player -- you can only play one prop per
        # player per slip-side. Best prop leads; the rest ride an "also:" line.
        _seen, _prim = {}, []
        for d in scored:
            _pk = (d["p"].get("player") or "") + "|" + (d["p"].get("opponent") or "")
            if _pk in _seen:
                _seen[_pk].setdefault("more", []).append(d)
            else:
                _seen[_pk] = d; _prim.append(d)
        scored = _prim'''),
("C4 render the also-line",
'''            L.append(("Why ranked low: %s" % why_dn) if worst else ("Why Apex likes it: %s" % why_up))''',
'''            L.append(("Why ranked low: %s" % why_dn) if worst else ("Why Apex likes it: %s" % why_up))
            if d.get("more"):
                L.append("also: " + " \u00b7 ".join("%s %s %s (%d)" % (LABEL.get(m["p"]["category"], m["p"]["category"]),
                         m["p"]["line"], m["p"]["direction"], m["sc"]) for m in d["more"][:4]))'''),
]
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
ok = True
print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
for name, old, new in E:
    n = src.count(old); print("  [%s] %s: %d" % ("ok" if n == 1 else "FAIL", name, n)); ok = ok and n == 1
if not ok: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2c"; shutil.copy2(FN, bak)
for name, old, new in E: src = src.replace(old, new, 1)
src += "\n# " + MARKER + " applied\n"
open(FN, "w", encoding="utf-8").write(src)
import py_compile
try:
    py_compile.compile(FN, doraise=True)
    print("smoke: compile OK")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
