#!/usr/bin/env python3
"""APEX-TIERAUDIT-CMD-2026-09-28 -- exposes apex_edge_tracker.prop_type_overlap_report()
(added by apex_typedetail_filter_patch.py, APEX-TYPEDETAIL-FILTER-2026-09-28) as a
Discord command, /tieraudit, in #general. Lets the fix for the goblin/standard
duplicate-props bug be spot-checked on demand instead of only by eyeballing
three separate board messages.

Usage: python3 apex_tieraudit_command_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "discord_bot.py"
PIN = "4cb04764ba865c38fe73f47959029eb56f13c1a2d3c68444624f8806775b512a"
MARK = "APEX-TIERAUDIT-CMD-2026-09-28"

A1_OLD = '''def _bb_render(cmd):
    """Runs in a worker thread: board load + ranking, no event-loop blocking."""
    import apex_edge_tracker as _aet
    picks, note = _aet.load_current_board()
    if note:
        return note
    if cmd in _BB_TYPE_COMMANDS:                      # APEX-TYPECMD-BOT-2026-09-09
        ptype, lim = _BB_TYPE_COMMANDS[cmd]
        return _aet.best_bets_detail(picks, prop_type=ptype, limit=lim, slip_rules=True)
    cat, worst = _BB_COMMANDS[cmd]
    return _aet.best_bets_detail(picks, category=cat, worst=worst)
'''
A1_NEW = '''def _bb_render(cmd):
    """Runs in a worker thread: board load + ranking, no event-loop blocking."""
    import apex_edge_tracker as _aet
    picks, note = _aet.load_current_board()
    if note:
        return note
    if cmd == "/tieraudit":                            # APEX-TIERAUDIT-CMD-2026-09-28
        return _aet.prop_type_overlap_report(picks, limit=6)["text"]
    if cmd in _BB_TYPE_COMMANDS:                      # APEX-TYPECMD-BOT-2026-09-09
        ptype, lim = _BB_TYPE_COMMANDS[cmd]
        return _aet.best_bets_detail(picks, prop_type=ptype, limit=lim, slip_rules=True)
    cat, worst = _BB_COMMANDS[cmd]
    return _aet.best_bets_detail(picks, category=cat, worst=worst)
'''

A2_OLD = '''            elif _txt in _BB_COMMANDS or _txt in _BB_TYPE_COMMANDS:
'''
A2_NEW = '''            elif _txt in _BB_COMMANDS or _txt in _BB_TYPE_COMMANDS or _txt == "/tieraudit":
'''

ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW)]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read()
    s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"
    assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o)
        assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors 2/2 unique")
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pretieraudit"
    shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS:
        new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try:
        py_compile.compile(F, doraise=True)
    except Exception as e:
        shutil.copy2(bak, F)
        print("py_compile FAILED -> restored:", e)
        sys.exit(1)
    print("APPLIED. backup:", bak)
    print("new sha:", sha(F))


if __name__ == "__main__":
    main()
