#!/usr/bin/env python3
"""APEX-BB-002g -- truth-first scoring: remove B1-B4 suppression, keep warnings,
strengthen negative-calibration reasoning. Score=belief, Attention=trust, Warnings=risk."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-BB-002g"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
E = [
("G1 remove untested caps, keep warnings (B4)",
'''    if n == 0:
        # APEX-BB-002d: zero settled evidence -> capped below every evidenced
        # pick's natural range. Evidence > probability.
        score = min(score, 45.0)
        down.append("\u26a0\ufe0f Untested Category -- no settled evidence (n=0)")
    elif n < 5:
        score = min(score, 55.0)
        down.append("\u26a0\ufe0f Untested Category -- minimal evidence (n=%d)" % n)''',
'''    if n == 0:
        # APEX-BB-002g: warning, not cap. Score = belief; risk lives in the flag.
        down.append("\u26a0\ufe0f Untested Category -- no settled evidence (n=0)")
    elif n < 5:
        down.append("\u26a0\ufe0f Thin Evidence -- small sample (n=%d)" % n)'''),
("G2 remove artifact cap, keep flag (B3)",
'''    if prob >= 0.95:
        # APEX-BB-002c: near-certain model probabilities on tennis props are
        # almost always broken inputs (08-29: Bo3 math on Bo5 lines scored
        # 95-100 four separate times). Flag, never crown.
        score = min(score, 35.0)
        down.append("\u26a0\ufe0f stated %d%% -- likely artifact, verify the line before trusting" % round(prob * 100))''',
'''    if prob >= 0.95:
        # APEX-BB-002g: true score shown; the flag carries the risk. Near-certain
        # probabilities on tennis props are almost always broken inputs (08-29).
        down.append("\u26a0\ufe0f LIKELY ARTIFACT -- stated %d%%; verify the line before trusting anything about this pick" % round(prob * 100))'''),
("G3 remove Bo5 cap, keep warning (B1)",
'''    if bo5:
        score = min(score, 49.0)
        down.append("Bo5 experimental -- LOW until 25 settled (BO5-FWD-001)")''',
'''    if bo5:
        # APEX-BB-002g: no cap. Attention=LOW carries the earned-trust verdict;
        # the tag carries the risk; the score states the belief.
        down.append("\u26a0\ufe0f Experimental Format -- 0 settled Bo5 results; LOW attention until 25 (BO5-FWD-001)")'''),
("G4 true-order sort in detail (B2)",
'''            _prim.sort(key=lambda d: (bool(d["p"].get("bo5")), -d["sc"]))''',
'''            _prim.sort(key=lambda d: -d["sc"])   # APEX-BB-002g: true score order; tags carry risk'''),
("G5 true-order initial sort in block (B2)",
'''        scored.sort(key=lambda d: (d["bo5"], -d["score"]))  # APEX-BB-001b: Bo5 always below Bo3''',
'''        scored.sort(key=lambda d: -d["score"])  # APEX-BB-002g: true score order'''),
("G6 strengthen negative calibration (reasoning replaces caps)",
'''    if n >= 5 and cs["cal_pts"] is not None:
        ev = 20.0 * w * max(-1.0, min(1.0, cs["cal_pts"] / 0.10))
        score += ev''',
'''    if n >= 5 and cs["cal_pts"] is not None:
        # APEX-BB-002g: negative calibration bites at double weight -- honest
        # reasoning doing what the removed caps faked. A 5-5/-0.57 category
        # now loses real points on its true score.
        _cal_scale = cs["cal_pts"] / 0.10
        ev = (30.0 if _cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, _cal_scale))
        score += ev''')
]
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
ok = True
print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
for name, old, new in E:
    c = src.count(old); print("  [%s] %s: %d" % ("ok" if c == 1 else "FAIL", name, c)); ok = ok and c == 1
if not ok: sys.exit("ABORT -- nothing written; paste the FAIL name")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2g"; shutil.copy2(FN, bak)
for name, old, new in E: src = src.replace(old, new, 1)
open(FN, "w", encoding="utf-8").write(src)
import py_compile, subprocess, os
TEST = r"""
import apex_edge_tracker as a
r = a.records(); F = []
b5 = a.apex_score(0.79, "aces", True, r)
if b5[0] <= 49: F.append("Bo5 still capped: %d" % b5[0])
if not any("Experimental" in d for d in b5[4]): F.append("Bo5 warning missing")
art = a.apex_score(0.99, "dfs", False, r)
if art[0] < 60: F.append("artifact still capped: %d" % art[0])
if not any("ARTIFACT" in d for d in art[4]): F.append("artifact flag missing")
ts = a.apex_score(0.79, "total_sets", False, r)
if ts[0] <= 45: F.append("untested still capped: %d" % ts[0])
if not any("Untested" in d for d in ts[4]): F.append("untested warning missing")
gw = a.apex_score(0.53, "games_won", False, r)
dfs = a.apex_score(0.53, "dfs", False, r)
if not gw[0] < dfs[0]: F.append("negative calibration not biting: gw=%d dfs=%d" % (gw[0], dfs[0]))
print("SELFTEST:", "PASS truth-first" if not F else "FAIL: " + "; ".join(F))
"""
try:
    py_compile.compile(FN, doraise=True)
    rr = subprocess.run(["/usr/bin/python3", "-c", TEST], capture_output=True, text=True, cwd=os.getcwd())
    print(rr.stdout.strip() or rr.stderr.strip()[-400:])
    if "PASS truth-first" not in rr.stdout: raise RuntimeError("selftest failed")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
