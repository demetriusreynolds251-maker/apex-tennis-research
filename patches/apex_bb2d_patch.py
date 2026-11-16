#!/usr/bin/env python3
"""APEX-BB-002d -- evidence > probability: no-history caps + band-credit gating."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-BB-002d"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
E = [
("E1 band credit requires category evidence (n>=5)",
'''    for name, blo, bhi in BUCKETS:
        if blo <= prob < bhi:''',
'''    for name, blo, bhi in BUCKETS:
        if n < 5:
            # APEX-BB-002d: band records are earned by settled picks in OTHER
            # categories; an untested category inherits none of that credit.
            break
        if blo <= prob < bhi:'''),
("E2 no-history caps, above the artifact clamp",
'''    if prob >= 0.95:''',
'''    if n == 0:
        # APEX-BB-002d: zero settled evidence -> capped below every evidenced
        # pick's natural range. Evidence > probability.
        score = min(score, 45.0)
        down.append("\u26a0\ufe0f Untested Category -- no settled evidence (n=0)")
    elif n < 5:
        score = min(score, 55.0)
        down.append("\u26a0\ufe0f Untested Category -- minimal evidence (n=%d)" % n)
    if prob >= 0.95:'''),
]
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
ok = True
print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
for name, old, new in E:
    c = src.count(old); print("  [%s] %s: %d" % ("ok" if c == 1 else "FAIL", name, c)); ok = ok and c == 1
if not ok: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2d"; shutil.copy2(FN, bak)
for name, old, new in E: src = src.replace(old, new, 1)
open(FN, "w", encoding="utf-8").write(src)
import py_compile
try:
    py_compile.compile(FN, doraise=True); print("smoke: compile OK")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
