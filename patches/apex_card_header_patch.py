#!/usr/bin/env python3
"""
APEX-CARD-HEADER-2026-08-27 -- pass this card's probability to the tracker header
so the ATTENTION line can combine the category standing with the pick itself.
One exact-match edit in openclaw_core.py (inside _apex_engine_card). Backup, compile check, auto-restore.
Run:  cd ~/openclaw && python3 apex_card_header_patch.py [--dry-run]
"""
import hashlib, os, shutil, sys
from datetime import datetime
MARKER = "APEX-CARD-HEADER-2026-08-27"; TARGET = "openclaw_core.py"
OLD = '''            _hdr = _aet.discord_header(t.get("category"))
'''
NEW = '''            # APEX-CARD-HEADER-2026-08-27: same decided probability the pick uses
            _po, _pu = float(t.get("p_over") or 0), float(t.get("p_under") or 0)
            _hdr = _aet.discord_header(t.get("category"), prob=((max(_po, _pu) / (_po + _pu)) if (_po + _pu) > 0 else None))
'''
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
src = open(TARGET, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already present -- refusing to re-apply")
n = src.count(OLD); print(f"{MARKER}  {TARGET}  sha256 {sha(TARGET)}\n  [{'ok' if n == 1 else 'FAIL'}] header call: {n} match(es)")
if n != 1: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok, nothing written"); sys.exit(0)
bak = f"{TARGET}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}_precardheader"; shutil.copy2(TARGET, bak)
open(TARGET, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
import py_compile
try: py_compile.compile(TARGET, doraise=True)
except Exception as e: shutil.copy2(bak, TARGET); sys.exit(f"ABORT -- compile failed ({e}); restored {bak}")
print(f"written {TARGET}  sha256 {sha(TARGET)}  (backup {bak}, py_compile OK)")
