#!/usr/bin/env python3
"""APEX-BB-002b -- Discord commands /bestbets etc. in #general (discord_bot.py). v2: insert above the decorator."""
import hashlib, shutil, sys
from datetime import datetime
FN = "discord_bot.py"; MARKER = "APEX-BB-002b"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

OLD = '''            if message.content and message.content.strip().lower() == "!cancel":
                await handle_cancel_command(message)
            else:
                await handle_general_message(message)'''

NEW = '''            _txt = (message.content or "").strip().lower()
            if _txt == "!cancel":
                await handle_cancel_command(message)
            elif _txt in _BB_COMMANDS:
                # APEX-BB-002b: on-demand Best Bets. Reads the latest evaluated
                # board from the pick log -- never re-evaluates, never blocks
                # the event loop (runs in a thread).
                await _handle_bestbets_command(message, _txt)
            else:
                await handle_general_message(message)'''

ANCHOR2 = '''@client.event
async def on_message(message):'''

FUNCS = '''# ──────────────────────────────────────────────────────────────
# APEX-BB-002b: /bestbets command family (#general)
# ──────────────────────────────────────────────────────────────
_BB_COMMANDS = {
    "/bestbets":       (None, False),
    "/worstbets":      (None, True),
    "/bestdfs":        ("dfs", False),
    "/bestfantasy":    ("fantasy_score", False),
    "/bestaces":       ("aces", False),
    "/bestbreaks":     ("breaks", False),
    "/bestgameswon":   ("games_won", False),
    "/besttotalgames": ("total_games", False),
}

def _bb_render(cmd):
    """Runs in a worker thread: board load + ranking, no event-loop blocking."""
    import apex_edge_tracker as _aet
    cat, worst = _BB_COMMANDS[cmd]
    picks, note = _aet.load_current_board()
    if note:
        return note
    return _aet.best_bets_detail(picks, category=cat, worst=worst)

async def _handle_bestbets_command(message, cmd):
    import asyncio
    try:
        txt = await asyncio.to_thread(_bb_render, cmd)
    except Exception as e:
        txt = f"best bets unavailable ({type(e).__name__}: {e})"
    for i in range(0, len(txt), 1900):
        await message.channel.send(txt[i:i+1900])


'''

src = open(FN, encoding="utf-8", errors="replace").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
ok1, ok2 = src.count(OLD), src.count(ANCHOR2)
print(f"{MARKER}  {FN}  sha256 {sha(FN)}")
print(f"  [{'ok' if ok1 == 1 else 'FAIL'}] general dispatch: {ok1}")
print(f"  [{'ok' if ok2 == 1 else 'FAIL'}] decorator+def anchor: {ok2}")
if ok1 != 1 or ok2 != 1: sys.exit("ABORT -- nothing written (if the decorator anchor failed, paste the two lines above on_message)")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2b"; shutil.copy2(FN, bak)
src = src.replace(OLD, NEW, 1).replace(ANCHOR2, FUNCS + ANCHOR2, 1)
open(FN, "w", encoding="utf-8").write(src)
import py_compile
try:
    py_compile.compile(FN, doraise=True)
    print("smoke OK: compiled with commands wired")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
