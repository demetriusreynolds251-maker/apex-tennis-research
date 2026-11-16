#!/usr/bin/env python3
"""
APEX-HEALTHCHECK-MC-WIRE-2026-08-23
Project Apex Intelligence / OpenClaw (DEMETRIUS)

Surfaces apex_healthcheck.py's daily report inside Mission Control.

WHAT IT ADDS
  1. A reader function `_apex_healthcheck_view()` that loads
     apex_healthcheck_report.json (written atomically by the healthcheck) and
     adds a staleness verdict of its own.
  2. `"apex_healthcheck": _apex_healthcheck_view()` into the dict returned by
     state(), so the existing /api/state consumers get it for free.
  3. A dedicated route: GET /api/apex_healthcheck

THE POINT OF THE STALENESS VERDICT
  The panel must fail LOUD when the healthcheck itself stops running. A missing
  or old report is reported as STALE / NEVER_RUN — never as "fine". Silence is
  never success; that is the whole reason this exists.

WHAT IT DOES NOT DO
  - Runs nothing. It reads a file the healthcheck already wrote.
  - Touches no frozen model, no state, no log.
  - Changes no existing route or view.

FAIL-OPEN: the reader never raises. On any problem it returns a dict whose
status is UNKNOWN with the reason, and Mission Control renders as before.

USAGE (from the project folder)
    python3 apex_healthcheck_mc_wire.py --check
    python3 apex_healthcheck_mc_wire.py --apply
    python3 apex_healthcheck_mc_wire.py --revert
"""
import argparse, hashlib, os, py_compile, re, shutil, tempfile
from datetime import datetime

MARKER = "APEX-HEALTHCHECK-MC-WIRE-2026-08-23"
TARGET = "openclaw_mission_control.py"

ANCHOR_FN = "def state():"
ANCHOR_STATE_KEY = '    return {"cfg": cfg, "green": g, "ml": m, "slips": s, "health": hs,'
ANCHOR_ROUTE = '        elif u.path == "/api/state": self._send(200, state())'

READER = '''# ---------------------------------------------------------------------------
# APEX-HEALTHCHECK-MC-WIRE-2026-08-23 -- surfaces the daily healthcheck report.
# Reads apex_healthcheck_report.json (written atomically by apex_healthcheck.py).
# Runs nothing, changes nothing. Fail-open: any problem returns UNKNOWN and
# Mission Control renders exactly as it did before.
#
# Staleness is deliberately loud. A healthcheck that stopped running must never
# look like a healthy system -- that failure mode is exactly why this exists
# (bot silently dead Jul 23 -> Aug 21, nothing alerted).
# ---------------------------------------------------------------------------
_APEX_HC_REPORT = "apex_healthcheck_report.json"
_APEX_HC_STALE_HOURS = 30      # daily job + 6h grace


def _apex_healthcheck_view():
    """APEX-HEALTHCHECK-MC-WIRE-2026-08-23: the daily report, or a loud reason."""
    try:
        import json as _json, os as _os, time as _time
        path = _APEX_HC_REPORT
        if not _os.path.isabs(path):
            path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), path)
        if not _os.path.exists(path):
            return {"status": "NEVER_RUN", "overall": "UNKNOWN", "checks": [],
                    "headline": "Healthcheck has never run — no report file",
                    "age_hours": None, "stale": True}
        age_h = (_time.time() - _os.path.getmtime(path)) / 3600.0
        with open(path) as f:
            rep = _json.load(f)
        stale = age_h > _APEX_HC_STALE_HOURS
        checks = rep.get("checks", [])
        fails = rep.get("failures", [])
        warns = rep.get("warnings", [])
        if stale:
            headline = ("Healthcheck has not run in %.0f hours — treat every panel "
                        "below as unverified" % age_h)
            status = "STALE"
        elif fails:
            headline = "%d check(s) failing: %s" % (len(fails), ", ".join(fails))
            status = "FAIL"
        elif warns:
            headline = "%d warning(s): %s" % (len(warns), ", ".join(warns))
            status = "WARN"
        else:
            headline = "All %d checks passing" % len(checks)
            status = "OK"
        return {"status": status,
                "overall": rep.get("overall", "UNKNOWN"),
                "generated_at": rep.get("generated_at"),
                "age_hours": round(age_h, 1),
                "stale": stale,
                "headline": headline,
                "failures": fails,
                "warnings": warns,
                "checks": checks,
                "text": rep.get("text", "")}
    except Exception as e:
        return {"status": "UNKNOWN", "overall": "UNKNOWN", "checks": [], "stale": True,
                "headline": "Healthcheck report unreadable: %s: %s" % (type(e).__name__, e),
                "age_hours": None}


'''

STATE_KEY = ('    return {"apex_healthcheck": _apex_healthcheck_view(),   '
             '# APEX-HEALTHCHECK-MC-WIRE-2026-08-23\n'
             '            "cfg": cfg, "green": g, "ml": m, "slips": s, "health": hs,')

ROUTE = ('        elif u.path == "/api/state": self._send(200, state())\n'
         '        elif u.path == "/api/apex_healthcheck":'
         '  # APEX-HEALTHCHECK-MC-WIRE-2026-08-23\n'
         '            self._send(200, _apex_healthcheck_view())')


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def report(src, path):
    print(MARKER, "-- CHECK", path)
    print("file sha256", sha(path))
    print("lines", src.count("\n") + 1)
    print("marker present:", src.count(MARKER))
    ok = True
    for name, anchor in (("state() definition", ANCHOR_FN),
                         ("state() return dict", ANCHOR_STATE_KEY),
                         ("/api/state route", ANCHOR_ROUTE)):
        n = src.count(anchor)
        print("  %-24s %s" % (name, "OK" if n == 1 else "** %d matches — must be exactly 1" % n))
        if n != 1:
            ok = False
    if MARKER in src:
        print("\nALREADY PATCHED — --apply will refuse.")
        return False
    print("\n%s" % ("READY TO APPLY" if ok else "NOT READY — send this output back"))
    return ok


def apply_patch(path, src):
    out = src.replace(ANCHOR_FN, READER + ANCHOR_FN, 1)
    out = out.replace(ANCHOR_STATE_KEY, STATE_KEY, 1)
    out = out.replace(ANCHOR_ROUTE, ROUTE, 1)
    n = out.count(MARKER)
    if n < 4:
        raise SystemExit("only %d markers — refusing to write" % n)
    tmp = os.path.join(tempfile.mkdtemp(), TARGET)
    with open(tmp, "w") as f:
        f.write(out)
    py_compile.compile(tmp, doraise=True)
    print("compile check: OK (%d markers)" % n)
    backup = path + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, backup)
    with open(path, "w") as f:
        f.write(out)
    py_compile.compile(path, doraise=True)
    print("backup   ", backup)
    print("patched  ", path)
    print("new sha256", sha(path))
    print("\nMission Control must be restarted by hand for this to take effect.")
    print("This script starts and stops nothing.")


def revert(path):
    d = os.path.dirname(os.path.abspath(path)) or "."
    baks = [f for f in sorted(os.listdir(d)) if f.startswith(TARGET + ".bak_")]
    baks = [b for b in baks if MARKER not in open(os.path.join(d, b)).read()]
    if not baks:
        raise SystemExit("no pre-patch backup found")
    b = os.path.join(d, baks[-1])
    shutil.copy2(b, path)
    print("restored from", b, "\nsha256", sha(path))


def main():
    ap = argparse.ArgumentParser(description=MARKER)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--file", default=TARGET)
    a = ap.parse_args()
    if a.revert:
        revert(a.file); return
    if not os.path.exists(a.file):
        raise SystemExit("%s not found — run from the project folder" % a.file)
    src = open(a.file).read()
    if a.check or not a.apply:
        report(src, a.file); return
    if MARKER in src:
        raise SystemExit("already patched — refusing")
    if not report(src, a.file):
        raise SystemExit("checks failed — refusing to patch")
    print()
    apply_patch(a.file, src)


if __name__ == "__main__":
    main()
