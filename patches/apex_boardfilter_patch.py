"""APEX-BOARDFILTER-2026-08-31

load_current_board now also drops:
  - picks marked playable=0 (engine direction contradicts a MORE-only prop --
    honest evaluation kept in the log for ALIS, but not bettable, so not on
    the board or in any ranking)
  - picks whose slip_start_utc is in the past: a pick leaves the board the
    moment its match STARTS, not when it settles. Blank/unparseable start
    times fall back to the existing date + graded-pick filters. Fail open.
"""
import hashlib, os, shutil, sys, time, py_compile

TARGET = os.path.expanduser("~/openclaw/apex_edge_tracker.py")

OLD = '''    _dated = [r for r in best.values() if (r.get("match_date") or "") >= today]
    live = [r for r in _dated if not _is_dead(r)]'''

NEW = '''    # APEX-BOARDFILTER-2026-08-31: a pick leaves the board when its match
    # STARTS (slip_start_utc past), and an unplayable pick (playable=0:
    # MORE-only prop, engine says LESS) never appears at all. Blank values
    # fall back to the date + graded filters. Fail open on parse errors.
    from datetime import datetime as _bfdt, timezone as _bftz
    _bfnow = _bfdt.now(_bftz.utc)
    def _bf_started(r):
        s = (r.get("slip_start_utc") or "").strip()
        if not s:
            return False
        try:
            st = _bfdt.fromisoformat(s)
            if st.tzinfo is None:
                st = st.replace(tzinfo=_bftz.utc)
            return st <= _bfnow
        except Exception:
            return False
    _dated = [r for r in best.values() if (r.get("match_date") or "") >= today]
    _unplayable = sum(1 for r in _dated if str(r.get("playable") or "") == "0")
    _started    = sum(1 for r in _dated if _bf_started(r))
    _dated = [r for r in _dated
              if str(r.get("playable") or "") != "0" and not _bf_started(r)]
    if _unplayable or _started:
        try:
            print("[board] excluded %d unplayable, %d already-started pick(s)"
                  % (_unplayable, _started))
        except Exception:
            pass
    live = [r for r in _dated if not _is_dead(r)]'''


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    src = open(TARGET, encoding="utf-8").read()
    print("current sha : %s" % sha256(TARGET))
    bad = []
    if "APEX-BOARDFILTER" in src:
        bad.append("marker present -- refusing double-apply")
    n = src.count(OLD)
    print("anchor hits : %d (need 1)" % n)
    if n != 1:
        bad.append("anchor matched %d times" % n)
    if bad:
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_preboardfilter" % (TARGET, stamp)
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
