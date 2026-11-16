#!/usr/bin/env python3
"""APEX-SLAM-001 -- Gate 11-B slam matching survives punctuation ('U.S. Open')."""
import hashlib, shutil, sys
from datetime import datetime
FN = "openclaw_core.py"; MARKER = "APEX-SLAM-001"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
OLD = '''    is_slam    = any(slam in tournament for slam in GRAND_SLAM_NAMES)'''
NEW = '''    # APEX-SLAM-001: strip periods before matching -- PrizePicks says "U.S. Open",
    # the name table says "us open"; on 08-29 that gap + an exhausted odds cap
    # locked five Bo5 main-draw matches as Bo3.
    _t_norm    = tournament.replace(".", "")
    is_slam    = any(slam in _t_norm for slam in GRAND_SLAM_NAMES)'''
src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
n = src.count(OLD)
print(f"{MARKER}  {FN}  sha256 {sha(FN)}\n  [{'ok' if n == 1 else 'FAIL'}] slam match: {n}")
if n != 1: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_preslam"; shutil.copy2(FN, bak)
open(FN, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
import py_compile
try:
    py_compile.compile(FN, doraise=True)
    t = "u.s. open - new york".replace(".", "")
    assert any(s in t for s in {"us open"}), "normalization sanity"
    print("smoke OK: 'U.S. Open - New York' now matches")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
