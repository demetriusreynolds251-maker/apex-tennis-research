#!/usr/bin/env python3
"""Retire dead scripts that used the old data services.
--check lists what would go. --apply packs them into a verified backup zip, then deletes.
Any file still referenced by live code or a scheduled job is KEPT and reported."""
import sys, zipfile, datetime
from pathlib import Path
HERE = Path.home() / "openclaw"
CANDIDATES = [
    "apex_engine_only_patch.py", "apex_fmt002_patch.py", "apex_lag_totalfix_patch.py",
    "apex_lag_totalfix_verify.py", "apex_op_cooldown_patch.py", "apex_feed_window_patch.py",
    "check_raw_books.py", "oddspapi_backtest.py", "oddspapi_paths.py", "oddspapi_probe.py",
    "oddspapi_probe2.py", "oddspapi_prop_probe.py", "open_close_study.py", "open_vs_close.py",
    "openclaw_core_backup.py", "openclaw_v8_scaffold.py", "prop_lag_collector.py",
    "rapidapi_prop_probe.py", "rapidapi_prop_probe2.py", "rapidapi_prop_probe3.py",
    "rebet_vs_pinnacle.py", "test_v8_historical_depth.py", "memory_center_backfill.py",
    "memory_center_backfill_2.py", "historical_match_importer.py",
]
ME = Path(__file__).name
SEARCH = (list(HERE.glob("*.py")) + list(HERE.glob("*.sh"))
          + list((Path.home() / "openclaw_jobs").glob("*"))
          + list((Path.home() / "Library/LaunchAgents").glob("*.plist")))

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    cset = set(CANDIDATES); go, keep, missing = [], [], []
    for name in CANDIDATES:
        f = HERE / name
        if not f.exists():
            missing.append(name); continue
        users = []
        for s in SEARCH:
            if s.name in cset or s.name == ME or not s.is_file():
                continue
            try:
                if f.stem in s.read_text(errors="ignore"):
                    users.append(s.name)
            except Exception:
                pass
        (keep if users else go).append((name, users))
    print(f"WILL RETIRE ({len(go)}):"); [print("  ", n) for n, _ in go]
    print(f"KEPT - still used ({len(keep)}):"); [print("  ", n, "<- used by", ", ".join(u)) for n, u in keep]
    print(f"already gone ({len(missing)}):", ", ".join(missing) or "none")
    if mode != "--apply" or not go:
        return
    out = Path.home() / "openclaw_retired"; out.mkdir(exist_ok=True)
    z = out / ("retired_scripts_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, _ in go:
            zf.write(HERE / n, n)
    with zipfile.ZipFile(z) as zf:
        assert zf.testzip() is None and len(zf.namelist()) == len(go), "zip check FAILED - nothing deleted"
    for n, _ in go:
        (HERE / n).unlink()
    print(f"\nDELETED {len(go)} files. Backup zip: {z}")

if __name__ == "__main__":
    main()
