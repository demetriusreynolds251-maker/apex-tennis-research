#!/usr/bin/env python3
"""APEX-BB-002h -- fix ValueError when a match has several match-level props.
Second and later match props no longer .remove() slots already claimed."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-BB-002h"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
OLD = '''                elif all(md["sc"] > h["sc"] for h in _hits):
                    for h in _hits:                        # match prop wins the slot
                        _prim.remove(h)
                        md.setdefault("more", []).append(h)
                        md["more"].extend(h.pop("more", []))
                    _prim.append(md)'''
NEW = '''                elif all(md["sc"] > h["sc"] for h in _hits):
                    for h in _hits:                        # match prop wins the slot
                        if h in _prim:                     # APEX-BB-002h: a prior match
                            _prim.remove(h)                # prop may already have claimed it
                            md.setdefault("more", []).append(h)
                            md["more"].extend(h.pop("more", []))
                        else:
                            for w in _prim:                # attach to whoever holds it now
                                if h in w.get("more", []):
                                    w.setdefault("more", []).append(md); break
                            else:
                                md.setdefault("more", []).append(h)
                    if md not in _prim and not any(md in w.get("more", []) for w in _prim):
                        _prim.append(md)'''
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
n = src.count(OLD)
print(f"{MARKER}  {FN}  sha256 {sha(FN)}\n  [{'ok' if n == 1 else 'FAIL'}] match-prop block: {n}")
if n != 1: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2h"; shutil.copy2(FN, bak)
open(FN, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
import py_compile, subprocess, os
try:
    py_compile.compile(FN, doraise=True)
    r = subprocess.run(["/usr/bin/python3", "-c",
        "import apex_edge_tracker as a;"
        "b,_=a.load_current_board();"
        "t=a.best_bets_detail(b);"
        "assert 'unavailable' not in t, 'still failing';"
        "print('SMOKE OK -- board renders,', len(b), 'picks')"], capture_output=True, text=True, cwd=os.getcwd())
    print(r.stdout.strip() or r.stderr.strip()[-400:])
    if "SMOKE OK" not in r.stdout: raise RuntimeError("smoke failed")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
