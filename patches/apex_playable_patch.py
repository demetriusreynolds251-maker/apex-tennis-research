"""APEX-PLAYABLE-2026-08-31

The engine ignored the goblin lock: filter_props set direction_locked="MORE"
on Sonmez dfs 2.5 at 9:37pm and the engine picked LESS at 9:38 -- an
unplayable pick, ranked as bettable. The legacy enforcement branch at ~3817
is dead code (checks locked_direction, a field nothing sets) and its design
(force the direction) was explicitly PENDING_DECISION; resolved tonight the
other way: keep the honest evaluation, mark the pick unplayable.

Writer-only change: playable + slip_start_utc computed and logged in
_apex_forward_log_row. playable: "0" = engine direction contradicts a
MORE-only prop; "1" = classified, no conflict; "" = evaluated before
classification existed (unknown, never guessed).
"""
import hashlib, os, shutil, sys, time, py_compile

TARGET = os.path.expanduser("~/openclaw/openclaw_core.py")

OLD_FIELDS = '''_APEX_PICK_FIELDS = ["ts", "match_id", "match_date", "player", "opponent", "category", "stat_type", "line",
                     "direction", "prob", "tier", "label", "edge", "confidence", "surface", "best_of",
                     "tournament", "price_source", "main_total", "format_label", "pinn_fav", "sim_sha", "v1_sha"]'''

NEW_FIELDS = '''_APEX_PICK_FIELDS = ["ts", "match_id", "match_date", "player", "opponent", "category", "stat_type", "line",
                     "direction", "prob", "tier", "label", "edge", "confidence", "surface", "best_of",
                     "tournament", "price_source", "main_total", "format_label", "pinn_fav", "sim_sha", "v1_sha",
                     "playable", "slip_start_utc"]   # APEX-PLAYABLE-2026-08-31'''

OLD_ROW = '''    pick_row = {"ts": ts, "match_id": match_id, "match_date": match_date, "player": row_player, "opponent": row_opp,'''

NEW_ROW = '''    # APEX-PLAYABLE-2026-08-31: honest direction is kept; playability is a
    # separate fact about what the book offers. "" = prop was never classified
    # (pre-classification evaluation) -- unknown, never guessed.
    _ptype = str(prop.get("prop_type_classified") or "")
    _lock  = str(prop.get("direction_locked") or "")
    if _ptype and _lock:
        _playable = "1" if direction == _lock.upper() else "0"
    elif _ptype:
        _playable = "1"
    else:
        _playable = ""
    if _playable == "0":
        log("ApexEngine", f"UNPLAYABLE: {row_player} {cat} {f(line, '%.1f')} -- "
                          f"{_ptype} is {_lock}-only, engine says {direction}. "
                          f"Honest pick kept, excluded from bettable ranking.")
    pick_row = {"playable": _playable,
                "slip_start_utc": str(prop.get("slip_start_utc") or ""),
                "ts": ts, "match_id": match_id, "match_date": match_date, "player": row_player, "opponent": row_opp,'''


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    src = open(TARGET, encoding="utf-8").read()
    print("current sha : %s" % sha256(TARGET))
    bad = []
    if "APEX-PLAYABLE" in src:
        bad.append("marker present -- refusing double-apply")
    for nm, s in (("fields", OLD_FIELDS), ("pickrow", OLD_ROW)):
        c = src.count(s)
        print("  %-8s anchor %d (need 1)" % (nm, c))
        if c != 1:
            bad.append("%s matched %d times" % (nm, c))
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_preplayable" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % os.path.basename(backup))
    out = src.replace(OLD_FIELDS, NEW_FIELDS, 1).replace(OLD_ROW, NEW_ROW, 1)
    open(TARGET, "w", encoding="utf-8").write(out)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("COMPILE FAILED -- backup restored"); print(e); sys.exit(1)
    print("py_compile  : OK")
    print("new sha     : %s" % sha256(TARGET))
    print("APPLIED")


main()
