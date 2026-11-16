#!/usr/bin/env python3
# Stat-sheet trust check v2: +-1 day and name-order retries; breaks checked by serve arithmetic. READ-ONLY.
import re, sys, time, datetime, urllib.parse
from sa365_prematch_probe import get, rows
DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-09-22"
SETKEYS = ["1ST", "2ND", "3RD", "4TH", "5TH"]

def g(path):
    st, p = get(path); time.sleep(0.3); return st, p

def shift(day, n):
    return (datetime.date.fromisoformat(day) + datetime.timedelta(days=n)).isoformat()

def find(a, b):
    for d in (DAY, shift(DAY, -1), shift(DAY, 1)):
        for x, y in ((a, b), (b, a)):
            st, p = g(f"/extend/api/event/get/{urllib.parse.quote(x)}/{urllib.parse.quote(y)}/{d}")
            r = (p or {}).get("result") or {}
            if r.get("id"):
                return r, d
    return None, None

def v(sec, grp, key, who):
    try:
        return sec[grp][key][who]["value"]
    except Exception:
        return None

def parse_sets(score):
    out = []
    for s in str(score or "").split(","):
        m = re.match(r"\s*(\d+)-(\d+)", s)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out

def serve_ok(g1, g2, b1, b2, tb1, tb2):
    # games won = holds + breaks (+ tiebreak); each player's serve count must differ by at most 1
    h1, h2 = g1 - b1 - tb1, g2 - b2 - tb2
    if h1 < 0 or h2 < 0:
        return False
    return abs((h1 + b2) - (h2 + b1)) <= 1

st, p = g(f"/atp/fixtures/{DAY}?filter=PlayerGroup:singles&pageSize=40")
fx = rows(p); print(f"{DAY}: {len(fx)} matches listed\n")
t = dict(found=0, found_other_day=0, missing=0, not_ended=0, no_stats=0,
         games_ok=0, games_bad=0, breaks_ok=0, breaks_bad=0, breaks_unchecked=0)
for f in fx:
    a = (f.get("player1") or {}).get("name"); b = (f.get("player2") or {}).get("name")
    if not a or not b:
        continue
    r, d = find(a, b)
    if not r:
        t["missing"] += 1; print(f"  MISSING   {a} vs {b}"); continue
    t["found"] += 1
    if d != DAY:
        t["found_other_day"] += 1
    name, score = str(r.get("name"))[:44], str(r.get("score"))
    if str(r.get("status")) != "Ended":
        t["not_ended"] += 1; print(f"  NOT ENDED {name}  status={r.get('status')}  ({d})"); continue
    st, sp = g(f"/extend/api/event/get/statistics/{r['id']}")
    res = (sp or {}).get("result") or {}
    S = res.get("statistics") or {}
    ALL = S.get("ALL")
    if not ALL:
        t["no_stats"] += 1; print(f"  NO STATS  {name}  score={score}  ({d})"); continue
    flip = str(res.get("player1", "")).strip().lower() != str(r.get("participant1", "")).strip().lower()
    def pv(sec, grp, key):
        x, y = v(sec, grp, key, "player1"), v(sec, grp, key, "player2")
        return (y, x) if flip else (x, y)
    sets = parse_sets(score)
    s1, s2 = sum(x for x, _ in sets), sum(y for _, y in sets)
    w1, w2 = pv(ALL, "games", "gamesWon")
    gok = (w1, w2) == (s1, s2)
    t["games_ok" if gok else "games_bad"] += 1
    b1, b2 = pv(ALL, "return", "breakPointsScored")
    tb1 = sum(1 for x, y in sets if (x, y) == (7, 6)); tb2 = sum(1 for x, y in sets if (x, y) == (6, 7))
    checks = []
    if None not in (b1, b2):
        checks.append(serve_ok(s1, s2, b1, b2, tb1, tb2))
    for i, (x, y) in enumerate(sets[:5]):
        sec = S.get(SETKEYS[i])
        if sec:
            c1, c2 = pv(sec, "return", "breakPointsScored")
            if None not in (c1, c2):
                checks.append(serve_ok(x, y, c1, c2, int((x, y) == (7, 6)), int((x, y) == (6, 7))))
    if not checks:
        bres = "?? "; t["breaks_unchecked"] += 1
    elif all(checks):
        bres = "OK "; t["breaks_ok"] += 1
    else:
        bres = "BAD"; t["breaks_bad"] += 1
    a1, a2 = pv(ALL, "service", "aces"); d1, d2 = pv(ALL, "service", "doubleFaults")
    tag = "" if d == DAY else f"  (found on {d})"
    print(f"  {name:44} {score:16} games {'OK ' if gok else 'BAD'}  breaks {bres}({b1}/{b2})"
          f"  aces {a1}/{a2}  dfs {d1}/{d2}{tag}")
print("\nSUMMARY:", t)
