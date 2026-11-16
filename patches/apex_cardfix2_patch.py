#!/usr/bin/env python3
"""APEX-CARDFIX-002 -- props call sites pass a per-pick tag so each pick keeps its own card."""
import hashlib, shutil, sys
from datetime import datetime
FN = "openclaw_core.py"; MARKER = "APEX-CARDFIX-002"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
E = [
("G1 batch finalize call site",
'''    save_evaluation_reasoning(p_name, opp, "props", reasoning, dates)
    log("Batch",''',
'''    save_evaluation_reasoning(p_name, opp, "props", reasoning, dates,
                              pick_tag="%s_%s" % (prop.get("stat_type") or "", prop.get("line") or ""))
    log("Batch",'''),
("G2 supervisor call site",
'''            save_evaluation_reasoning(p_name, opp, "props", reasoning, dates)
    else:''',
'''            save_evaluation_reasoning(p_name, opp, "props", reasoning, dates,
                                      pick_tag="%s_%s" % (r.get("stat_type") or "", r.get("line") or ""))
    else:'''),
]
src = open(FN, encoding="utf-8", errors="replace").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
ok = True
print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
for n, old, new in E:
    c = src.count(old); print("  [%s] %s: %d" % ("ok" if c == 1 else "FAIL", n, c)); ok = ok and c == 1
if not ok: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_precardfix2"; shutil.copy2(FN, bak)
for n, old, new in E: src = src.replace(old, new, 1)
open(FN, "w", encoding="utf-8").write(src)
import py_compile
try: py_compile.compile(FN, doraise=True); print("compile OK")
except Exception as e: shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
