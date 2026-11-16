#!/usr/bin/env python3
"""APEX-BB-002c3 -- dedup only; the also-line renderer already exists in best_bets_detail."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-BB-002c3"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
OLD = '''        scored.sort(key=lambda d: d["sc"] if worst else -d["sc"])
        if worst:'''
NEW = '''        scored.sort(key=lambda d: d["sc"] if worst else -d["sc"])
        # APEX-BB-002c3: one numbered slot per player-side; extras ride the
        # existing "also:" line. Skipped in worst mode -- every weak pick
        # deserves its own warning there.
        if not worst:
            _seen, _prim = {}, []
            for d in scored:
                _pk = (d["p"].get("player") or "") + "|" + (d["p"].get("opponent") or "")
                if _pk in _seen:
                    _seen[_pk].setdefault("more", []).append(d)
                else:
                    _seen[_pk] = d; _prim.append(d)
            scored = _prim
        if worst:'''
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
n = src.count(OLD)
print(f"{MARKER}  {FN}  sha256 {sha(FN)}\n  [{'ok' if n == 1 else 'FAIL'}] dedup anchor: {n}")
if n != 1: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2c3"; shutil.copy2(FN, bak)
open(FN, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
import py_compile
try:
    py_compile.compile(FN, doraise=True); print("smoke: compile OK")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
