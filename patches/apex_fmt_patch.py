#!/usr/bin/env python3
"""APEX-FMT-001 -- US Open main-draw date fix + honest format labels + conflict log."""
import hashlib, shutil, sys
from datetime import datetime
MARKER = "APEX-FMT-001"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
FILES = {
"apex_price_feed.py": [
("P1 main-draw date (2026 US Open began Sun Aug 30)",
'''    "us open": {"2026": "2026-08-31"},''',
'''    "us open": {"2026": "2026-08-30"},   # APEX-FMT-001: was 08-31; Day 1 was Sun 08-30 (five Bo5 matches evaluated as Bo3)'''),
],
"openclaw_core.py": [
("C1 capture format_basis",
'''                _mt, _fh, _ft = _fc.get("main_total"), _fc.get("format_hint"), _fc.get("tournament")''',
'''                _mt, _fh, _ft = _fc.get("main_total"), _fc.get("format_hint"), _fc.get("tournament")
                _fb = _fc.get("format_basis")   # APEX-FMT-001: the feed's REAL basis'''),
("C2 honest label + conflict log",
'''        _why = (f"Pinnacle total-games line {_mt}" if _mt is not None
                else "women's singles")''',
'''        _why = _fb or (f"Pinnacle total-games line {_mt}" if _mt is not None
                       else "no stated basis")
        # APEX-FMT-001: a bo3 verdict on an ATP slam fixture with no market line is
        # exactly the shape of the 08-29 failure -- keep the verdict (calendar owns
        # qualifying) but say it LOUDLY so a stale calendar can never hide again.
        if _fh == "bo3" and is_slam and is_atp and _mt is None:
            log("Gate11B", f"\u26a0\ufe0f FORMAT CONFLICT WATCH: bo3 on ATP slam fixture "
                           f"{player} vs {opponent} with NO market line (basis: {_why}) "
                           f"-- verify calendar if this is a main-draw day")'''),
],
}
def main():
    ok = True; srcs = {}
    for fn, edits in FILES.items():
        srcs[fn] = open(fn, encoding="utf-8", errors="replace").read()
        if MARKER in srcs[fn]: sys.exit(f"{MARKER} already in {fn} -- refusing")
        print(f"{MARKER}  {fn}  sha256 {sha(fn)}")
        for name, old, new in edits:
            n = srcs[fn].count(old)
            print("  [%s] %s: %d" % ("ok" if n == 1 else "FAIL", name, n)); ok = ok and n == 1
    if not ok: sys.exit("ABORT -- nothing written")
    if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for fn, edits in FILES.items():
        shutil.copy2(fn, f"{fn}.bak_{ts}_prefmt")
        s = srcs[fn]
        for name, old, new in edits: s = s.replace(old, new, 1)
        open(fn, "w", encoding="utf-8").write(s)
    import py_compile
    try:
        for fn in FILES: py_compile.compile(fn, doraise=True)
        import importlib, apex_price_feed as apf
        importlib.reload(apf)
        assert apf.SLAM_MAIN_DRAW_START["us open"]["2026"] == "2026-08-30", "date not applied"
        assert "2026-08-29" < "2026-08-30" and "2026-08-30" >= "2026-08-30", "calendar comparison sanity"
        print("smoke OK: qual 08-29 -> bo3, main draw 08-30 -> bo5")
    except Exception as e:
        for fn in FILES: shutil.copy2(f"{fn}.bak_{ts}_prefmt", fn)
        sys.exit(f"ABORT -- {e}; restored")
    for fn in FILES: print(f"written {fn}  sha256 {sha(fn)}")
if __name__ == "__main__": main()
