#!/usr/bin/env python3
"""APEX-BB-001b -- score rescale + Bo5 sort-last + Best-3 floor caution.
Three edits in apex_edge_tracker.py, one selftest addition. House protocol."""
import hashlib, shutil, sys, subprocess, os
from datetime import datetime
MARKER = "APEX-BB-001b"; FN = "apex_edge_tracker.py"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
E = [
("B1 rescale base (50 = break-even)",
'''    score = 55.0 * max(0.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN)))''',
'''    # APEX-BB-001b: 50 = break-even; decent picks land 50s-60s, strong 70+
    score = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN)))'''),
("B2 Bo5 sorts below all Bo3",
'''        scored.sort(key=lambda d: -d["score"])''',
'''        scored.sort(key=lambda d: (d["bo5"], -d["score"]))  # APEX-BB-001b: Bo5 always below Bo3'''),
("B3 Best-3 floor caution",
'''                why = "; ".join(d["up"][:2]) or "highest evidence-weighted score on the board"''',
'''                why = "; ".join(d["up"][:2]) or "highest evidence-weighted score on the board"
                if d["score"] < 50:
                    why += " -- \\u26a0\\ufe0f below the 50 bar: best available today, not a strong bet"'''),
("B4 selftest ordering check",
'''    if "ATTENTION: LOW" not in discord_header("aces", rec=r_bb, prob=0.75, bo5=True):
        fails.append("BB: header must force LOW on Bo5")''',
'''    if "ATTENTION: LOW" not in discord_header("aces", rec=r_bb, prob=0.75, bo5=True):
        fails.append("BB: header must force LOW on Bo5")
    if "ZZBO5" in _blk.splitlines()[1]:
        fails.append("BB-001b: Bo5 pick must never top the ranked board")
    if apex_score(0.63, "dfs", False, r_bb)[0] < 50:
        fails.append("BB-001b: a 63%% pick in an evidenced category should score >= 50")'''),
]
def main():
    src = open(FN, encoding="utf-8").read()
    if MARKER in src: sys.exit(f"{MARKER} already present -- refusing to re-apply")
    print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
    ok = True
    for name, old, new in E:
        n = src.count(old)
        print("  [%s] %s: %d match(es)" % ("ok" if n == 1 else "FAIL", name, n)); ok = ok and n == 1
    if not ok: sys.exit("ABORT -- nothing written")
    if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
    bak = f"{FN}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}_prebb001b"; shutil.copy2(FN, bak)
    for name, old, new in E: src = src.replace(old, new.replace("\\\\u", "\\u"), 1)
    src += "\n# " + MARKER + " applied\n"
    open(FN, "w", encoding="utf-8").write(src)
    import py_compile
    try:
        py_compile.compile(FN, doraise=True)
        r = subprocess.run(["/usr/bin/python3", "-c",
            "import apex_edge_tracker as a;"
            "s=a.apex_score(0.63,'dfs',False,a.records());"
            "print('rescaled dfs 63%% ->', s[0]); assert s[0] >= 45, 'rescale failed';"
            "print('smoke OK')"], capture_output=True, text=True, cwd=os.getcwd())
        print(r.stdout.strip() or r.stderr.strip())
        if "smoke OK" not in r.stdout: raise RuntimeError(r.stderr[-300:])
    except Exception as e:
        shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored {bak}")
    print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
if __name__ == "__main__": main()
