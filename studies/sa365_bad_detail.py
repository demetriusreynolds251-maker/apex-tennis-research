#!/usr/bin/env python3
# Raw numbers on the matches that failed the trust check. READ-ONLY.
import time, datetime, urllib.parse
from sa365_prematch_probe import get
DAY = "2026-09-22"
PAIRS = [("Max Sheldon", "Teodor Davidov"), ("Atakan Karahan", "Henry Lieberman"),
         ("Lucas Renard", "Alex Kobelt"), ("Kaua Lorenzo Santos Gava", "Pedro Sakamoto"),
         ("Mitchell Krueger", "Sebastian Gorzny"), ("Evan Zhu", "Henry Searle"),
         ("Genaro Alberto Olivieri", "Valerio Aboian")]

def g(path):
    st, p = get(path); time.sleep(0.3); return p

def find(a, b):
    for n in (0, -1, 1):
        d = (datetime.date.fromisoformat(DAY) + datetime.timedelta(days=n)).isoformat()
        for x, y in ((a, b), (b, a)):
            r = (g(f"/extend/api/event/get/{urllib.parse.quote(x)}/{urllib.parse.quote(y)}/{d}") or {}).get("result") or {}
            if r.get("id"):
                return r, f"{x} / {y} on {d}"
    return None, None

def pair(sec, grp, key):
    try:
        s = sec[grp][key]
        return f"{s['player1']['value']}-{s['player2']['value']}"
    except Exception:
        return "--"

for a, b in PAIRS:
    r, how = find(a, b)
    print(f"\n=== {a} vs {b}")
    if not r:
        print("   not found"); continue
    res = (g(f"/extend/api/event/get/statistics/{r['id']}") or {}).get("result") or {}
    S = res.get("statistics") or {}
    print(f"   found with       : {how}")
    print(f"   match record     : 1st={r.get('participant1')}  2nd={r.get('participant2')}  score={r.get('score')}")
    print(f"   stat sheet       : 1st={res.get('player1')}  2nd={res.get('player2')}")
    for k in ["ALL", "1ST", "2ND", "3RD"]:
        if k in S:
            print(f"   {k:4} gamesWon {pair(S[k], 'games', 'gamesWon'):7} breaks {pair(S[k], 'return', 'breakPointsScored'):7}"
                  f" aces {pair(S[k], 'service', 'aces'):7} dfs {pair(S[k], 'service', 'doubleFaults')}")
