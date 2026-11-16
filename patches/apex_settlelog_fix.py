#!/usr/bin/env python3
"""APEX-SETTLELOG-001 -- skip hand rows with an empty actual (VOIDs) instead of crashing."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-SETTLELOG-001"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
OLD = '''        line = _f(h.get("line")); actual = _f(h.get("actual"))
        for r in rows:'''
NEW = '''        line = _f(h.get("line")); actual = _f(h.get("actual"))
        if actual is None:
            continue   # APEX-SETTLELOG-001: VOID/no-result rows carry no actual by design
        for r in rows:'''
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied")
n = src.count(OLD)
print(f"{MARKER}  {FN}  sha256 {sha(FN)}\n  [{'ok' if n==1 else 'FAIL'}] guard anchor: {n}")
if n != 1: sys.exit("ABORT -- nothing written")
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_presettlelog"; shutil.copy2(FN, bak)
open(FN, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
import py_compile
try: py_compile.compile(FN, doraise=True); print("compile OK")
except Exception as e: shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
