#!/usr/bin/env python3
"""APEX-CARDFIX-001 -- one reasoning file per pick, not per match.
Adds an optional pick_tag to save_evaluation_reasoning; callers that omit it
behave exactly as before."""
import hashlib, shutil, sys
from datetime import datetime
FN = "openclaw_core.py"; MARKER = "APEX-CARDFIX-001"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
E = [
("F1 signature gains pick_tag",
'''def save_evaluation_reasoning(player: str, opponent: str,
                               eval_type: str, full_text: str, dates: dict,
                               target_dir: Path = None):''',
'''def save_evaluation_reasoning(player: str, opponent: str,
                               eval_type: str, full_text: str, dates: dict,
                               target_dir: Path = None, pick_tag: str = ""):'''),
("F2 filename includes the pick tag",
'''    filename = (target_dir /
                f"reasoning_{dates['archive_date']}_{eval_type}_{safe_p1}_vs_{safe_p2}.txt")''',
'''    # APEX-CARDFIX-001: without a per-pick tag every pick in a match wrote to
    # the same path and truncated the previous card (open mode "w").
    safe_tag = re.sub(r"[^a-zA-Z0-9.]", "_", str(pick_tag))[:24]
    filename = (target_dir /
                (f"reasoning_{dates['archive_date']}_{eval_type}_{safe_p1}_vs_{safe_p2}"
                 + (f"_{safe_tag}" if safe_tag else "") + ".txt"))'''),
]
src = open(FN, encoding="utf-8", errors="replace").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
ok = True
print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
for n, old, new in E:
    c = src.count(old); print("  [%s] %s: %d" % ("ok" if c == 1 else "FAIL", n, c)); ok = ok and c == 1
if not ok: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_precardfix"; shutil.copy2(FN, bak)
for n, old, new in E: src = src.replace(old, new, 1)
open(FN, "w", encoding="utf-8").write(src)
import py_compile
try: py_compile.compile(FN, doraise=True); print("compile OK")
except Exception as e: shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
