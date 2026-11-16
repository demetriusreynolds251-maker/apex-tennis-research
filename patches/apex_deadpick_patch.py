"""APEX-DEADPICK-2026-08-31 (Option A)

load_current_board() filtered on match_date >= today only. match_date is a
date, so a pick stayed on the board all day after its match finished --
carrying already-decided picks into the rank log and contaminating the
Best Bets 3.0 selection-quality measurement at its source.

Excludes any pick that already carries a grade in the hand-settled CSV.
Key is (match_date, player, opponent, category, line): `opponent` holds the
pair for match-level rows ("A v B"), so match props cannot collide with each
other the way a player/category/line key allows.

Partial by design -- catches graded picks only, not matches merely underway.
The durable fix is start-time filtering (Option B), which needs slip_start_utc
written into the log first. No log file is read for writing or modified here.
"""
import hashlib, os, shutil, sys, time, py_compile

TARGET = os.path.expanduser("~/openclaw/apex_edge_tracker.py")

OLD = '''    live = [r for r in best.values() if (r.get("match_date") or "") >= today]'''

NEW = '''    # APEX-DEADPICK-2026-08-31: drop picks that already carry a grade.
    # match_date is a DATE, so a finished match stayed "today" all day and
    # its picks kept entering the rank log after the outcome was known.
    # Key includes opponent so match-level rows (player="match", the pair in
    # opponent) cannot collide on a shared line.
    _graded = set()
    try:
        for _g in _read(HAND_LOG):
            if (_g.get("actual") or "").strip():
                _graded.add(((_g.get("match_date") or "").strip(),
                             (_g.get("player") or "").strip().lower(),
                             (_g.get("opponent") or "").strip().lower(),
                             (_g.get("category") or "").strip(),
                             (_g.get("line") or "").strip()))
    except Exception:
        _graded = set()          # fail open: no grades read, board unchanged

    def _is_dead(r):
        return ((r.get("match_date") or "").strip(),
                (r.get("player") or "").strip().lower(),
                (r.get("opponent") or "").strip().lower(),
                (r.get("category") or "").strip(),
                (r.get("line") or "").strip()) in _graded

    _dated = [r for r in best.values() if (r.get("match_date") or "") >= today]
    live = [r for r in _dated if not _is_dead(r)]
    _dropped = len(_dated) - len(live)
    if _dropped:
        try:
            print("[board] excluded %d already-graded pick(s)" % _dropped)
        except Exception:
            pass'''


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    if not os.path.exists(TARGET):
        print("BLOCKED: target not found"); sys.exit(1)
    src = open(TARGET, encoding="utf-8").read()
    print("current sha : %s" % sha256(TARGET))
    bad = []
    if "APEX-DEADPICK" in src:
        bad.append("marker present -- refusing double-apply")
    n = src.count(OLD)
    print("live-filter anchor hits: %d (need 1)" % n)
    if n != 1:
        bad.append("anchor matched %d times" % n)
    for name in ("HAND_LOG", "def _read"):
        print("  %-12s present: %s" % (name, name in src))
        if name not in src:
            bad.append("%s not found -- patch depends on it" % name)
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_predeadpick" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % os.path.basename(backup))
    open(TARGET, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("COMPILE FAILED -- backup restored"); print(e); sys.exit(1)
    print("py_compile  : OK")
    print("new sha     : %s" % sha256(TARGET))
    print("APPLIED")


main()
