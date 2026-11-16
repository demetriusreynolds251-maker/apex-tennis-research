#!/usr/bin/env python3
"""APEX-TYPECMD-BOT-2026-09-09 -- /goblin and /standard: best 6 props of that type.
Usage: python3 apex_typecmd_bot_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "discord_bot.py"; PIN = "ee1d50d13338946be7b0f82617b827b94b66d6ca53bd6dd7bd88eb106de20a97"
MARK = "APEX-TYPECMD-BOT-2026-09-09"

A1_OLD = r'''    "/besttotalgames": ("total_games", False),
}
'''
A1_NEW = r'''    "/besttotalgames": ("total_games", False),
}

# APEX-TYPECMD-BOT-2026-09-09: prop-type views -- best 6 of one book type.
_BB_TYPE_COMMANDS = {
    "/goblin":   ("goblin", 6),
    "/goblins":  ("goblin", 6),
    "/standard": ("standard", 6),
    "/standards": ("standard", 6),
    "/demon":    ("demon", 6),
    "/demons":   ("demon", 6),
}
'''
A2_OLD = r'''def _bb_render(cmd):
    """Runs in a worker thread: board load + ranking, no event-loop blocking."""
    import apex_edge_tracker as _aet
    cat, worst = _BB_COMMANDS[cmd]
    picks, note = _aet.load_current_board()
    if note:
        return note
    return _aet.best_bets_detail(picks, category=cat, worst=worst)
'''
A2_NEW = r'''def _bb_render(cmd):
    """Runs in a worker thread: board load + ranking, no event-loop blocking."""
    import apex_edge_tracker as _aet
    picks, note = _aet.load_current_board()
    if note:
        return note
    if cmd in _BB_TYPE_COMMANDS:                      # APEX-TYPECMD-BOT-2026-09-09
        ptype, lim = _BB_TYPE_COMMANDS[cmd]
        return _aet.best_bets_detail(picks, prop_type=ptype, limit=lim)
    cat, worst = _BB_COMMANDS[cmd]
    return _aet.best_bets_detail(picks, category=cat, worst=worst)
'''
A3_OLD = r'''            elif _txt in _BB_COMMANDS:
'''
A3_NEW = r'''            elif _txt in _BB_COMMANDS or _txt in _BB_TYPE_COMMANDS:
'''
ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors 3/3 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pretypecmd"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
