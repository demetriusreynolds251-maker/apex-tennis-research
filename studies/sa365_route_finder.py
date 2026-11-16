#!/usr/bin/env python3
# SA365 route discovery: stats / results / players / h2h. READ-ONLY.
import json, time
from sa365_prematch_probe import get, rows, label

WORDS = ("ace", "double", "break", "serve", "statistic", "h2h", "winner", "set")

def peek(path):
    st, p = get(path); time.sleep(0.3)
    if p is None:
        print(f"  {str(st):5} {path}"); return None
    txt = json.dumps(p); low = txt.lower()
    keys = list(p.keys())[:8] if isinstance(p, dict) else f"list[{len(p)}]"
    hits = [w for w in WORDS if w in low]
    print(f"  {str(st):5} {path}\n        size={len(txt)} keys={keys} words={hits}")
    return p

_, pl = get("/extend/api/events/live"); live = rows(pl)
E = live[0].get("id") if live else "0"
print("live event:", E, label(live[0]) if live else "(none live)")
_, pf = get("/atp/fixtures?filter=PlayerGroup:singles&include=round,tournament"); fx = rows(pf)
F = fx[0].get("id") if fx else "0"
print("fixture id:", F, "| fixture row keys:", sorted(fx[0].keys()) if fx else None)

print("\n-- odds-side routes, live event id")
for p in [f"/extend/api/event/{E}", f"/extend/api/events/{E}", f"/extend/api/event/{E}/statistics",
          f"/extend/api/event/statistics/{E}", f"/extend/api/event/stats/{E}", f"/extend/api/event/details/{E}",
          f"/extend/api/event/timeline/{E}", f"/extend/api/event/score/{E}", f"/extend/api/event/h2h/{E}",
          f"/extend/api/h2h/{E}", "/extend/api/events/ended", "/extend/api/events/finished",
          "/extend/api/events/results", "/extend/api/events/ended/atp", "/extend/api/events/finished/atp"]:
    peek(p)

print("\n-- match-list side routes")
for p in [f"/atp/fixtures/{F}", f"/atp/fixtures/{F}?include=statistics", f"/atp/fixtures/{F}/statistics",
          f"/atp/matches/{F}", "/atp/players", "/atp/rankings", "/atp/h2h", "/atp/results", "/atp/tournaments"]:
    peek(p)

print("\n-- extra options on the match list")
for inc in ["statistics", "stats", "scores", "score", "players", "player", "odds", "sets", "h2h", "venue"]:
    peek(f"/atp/fixtures?filter=PlayerGroup:singles&include={inc}")
