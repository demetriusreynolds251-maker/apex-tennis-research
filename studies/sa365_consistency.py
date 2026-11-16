#!/usr/bin/env python3
# Can we trust the stat sheet? Cross-check vs the final score. READ-ONLY.
import re, sys, time, urllib.parse
from sa365_prematch_probe import get, rows
DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-09-22"

def g(path):
    st, p = get(path); time.sleep(0.3); return st, p

def find(a, b):
    for x, y in ((a, b), (b, a)):
        st, p = g(f"/extend/api/event/get/{urllib.parse.quote(x)}/{urllib.parse.quote(y)}/{DAY}")
        r = (p or {}).get("result") or {}
        if r.get("id"):
            return r
    return None

def v(sec, grp, key, who):
    try:
        return sec[grp][key][who]["value"]
    except Exception:
        return None

def score_games(score):
    g1 = g2 = 0
    for s in str(score or "").split(","):
        m = re.match(r"\s*(\d+)-(\d+)", s)
        if m:
            g1 += int(m.group(1)); g2 += int(m.group(2))
    return g1, g2

st, p = g(f"/atp/fixtures/{DAY}?filter=PlayerGroup:singles&pageSize=40")
fx = rows(p); print(f"{DAY}: {len(fx)} matches listed\n")
t = dict(found=0, missing=0, no_stats=0, games_ok=0, games_bad=0, breaks_ok=0, breaks_bad=0)
for f in fx:
    a = (f.get("player1") or {}).get("name"); b = (f.get("player2") or {}).get("name")
    if not a or not b:
        continue
    r = find(a, b)
    if not r:
        t["missing"] += 1; print(f"  MISSING   {a} vs {b}"); continue
    t["found"] += 1
    st, sp = g(f"/extend/api/event/get/statistics/{r['id']}")
    res = (sp or {}).get("result") or {}
    ALL = (res.get("statistics") or {}).get("ALL")
    name, score = str(r.get("name"))[:44], str(r.get("score"))
    if not ALL:
        t["no_stats"] += 1; print(f"  NO STATS  {name}  status={r.get('status')} score={score}"); continue
    s1, s2 = score_games(score)
    w1, w2 = v(ALL, "games", "gamesWon", "player1"), v(ALL, "games", "gamesWon", "player2")
    if str(res.get("player1", "")).strip().lower() != str(r.get("participant1", "")).strip().lower():
        w1, w2 = w2, w1
    gok = (w1, w2) == (s1, s2)
    b1, b2 = v(ALL, "return", "breakPointsScored", "player1"), v(ALL, "return", "breakPointsScored", "player2")
    t1, t2 = v(ALL, "service", "serviceGamesTotal", "player1"), v(ALL, "service", "serviceGamesTotal", "player2")
    k1, k2 = v(ALL, "games", "serviceGamesWon", "player1"), v(ALL, "games", "serviceGamesWon", "player2")
    lost1 = t1 - k1 if None not in (t1, k1) else None
    lost2 = t2 - k2 if None not in (t2, k2) else None
    bok = (b1 == lost2 and b2 == lost1)
    t["games_ok" if gok else "games_bad"] += 1
    t["breaks_ok" if bok else "breaks_bad"] += 1
    a1, a2 = v(ALL, "service", "aces", "player1"), v(ALL, "service", "aces", "player2")
    d1, d2 = v(ALL, "service", "doubleFaults", "player1"), v(ALL, "service", "doubleFaults", "player2")
    print(f"  {name:44} {score:16} games {'OK ' if gok else 'BAD'}({w1}-{w2} vs {s1}-{s2})"
          f"  breaks {'OK ' if bok else 'BAD'}({b1}/{b2} vs {lost2}/{lost1})  aces {a1}/{a2}  dfs {d1}/{d2}")
print("\nSUMMARY:", t)
