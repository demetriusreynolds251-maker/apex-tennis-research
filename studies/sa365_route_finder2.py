#!/usr/bin/env python3
# SA365 route discovery round 2. READ-ONLY.
import json, time
from sa365_prematch_probe import get, rows

def peek(path):
    st, p = get(path); time.sleep(0.3)
    if p is None:
        print(f"  {str(st):5} {path}"); return None
    if isinstance(p, dict) and "error" in p:
        print(f"  {str(st):5} {path}\n        ERROR SAYS: {json.dumps(p)[:200]}"); return None
    txt = json.dumps(p)
    print(f"  {str(st):5} {path}\n        size={len(txt)}  start: {txt[:300]}")
    return p

_, pf = get("/atp/fixtures?filter=PlayerGroup:singles&include=round,tournament"); fx = rows(pf)
r = fx[0] if fx else {}
F, P1, P2, T = r.get("id"), r.get("player1Id"), r.get("player2Id"), r.get("tournamentId")
print("fixture:", F, "players:", P1, P2, "tournament:", T)
print("sample fixture row:", json.dumps(r)[:400])

print("\n-- what the error messages say")
for p in ["/atp/players", "/atp/h2h", "/atp/results", "/atp/rankings"]:
    peek(p)

print("\n-- routes with ids filled in")
for p in [f"/atp/players/{P1}", f"/atp/player/{P1}", f"/atp/players/{P1}/stats", f"/atp/players/{P1}/matches",
          f"/atp/player/{P1}/stats", f"/atp/h2h/{P1}/{P2}", f"/atp/h2h?player1Id={P1}&player2Id={P2}",
          f"/atp/tournaments/{T}", f"/atp/tournament/{T}", f"/atp/matches/{F}/stats", f"/atp/match-stats/{F}",
          f"/atp/fixtures/{F}/stats", f"/atp/stats/{F}", f"/atp/fixture/{F}"]:
    peek(p)

print("\n-- one match-list row with include=odds")
_, po = get("/atp/fixtures?filter=PlayerGroup:singles&include=odds"); fo = rows(po)
print(json.dumps(fo[0])[:800] if fo else "none")

print("\n-- timeline on a few live matches")
_, pl = get("/extend/api/events/live")
for e in rows(pl)[:4]:
    peek(f"/extend/api/event/timeline/{e.get('id')}")
