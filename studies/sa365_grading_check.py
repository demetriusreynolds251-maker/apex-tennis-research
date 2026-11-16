#!/usr/bin/env python3
# Grading check: stat fields, final score, next-day availability, Bet365 pre-match markets. READ-ONLY.
import json, time, urllib.parse
from sa365_prematch_probe import get, rows, label, start_secs

def g(path):
    st, p = get(path); time.sleep(0.4); return st, p

def val(x):
    return json.dumps(x) if isinstance(x, dict) and len(x) > 1 else (x or {}).get("value") if isinstance(x, dict) else x

print("=== A. every whole-match stat field (Maloney vs Ribeiro, finished)")
st, p = g("/extend/api/event/get/statistics/4023097")
stats = ((p or {}).get("result") or {}).get("statistics") or {}
print("sections:", list(stats.keys()))
for grp, fields in (stats.get("ALL") or {}).items():
    for k, v in (fields or {}).items():
        print(f"  {grp:8} {k:26} p1={val(v.get('player1'))}  p2={val(v.get('player2'))}")

print("\n=== B. same match by names + date")
st, p = g("/extend/api/event/get/" + urllib.parse.quote("Patrick Maloney") + "/"
          + urllib.parse.quote("Igor Ribeiro Marcondes") + "/2026-09-23")
r = (p or {}).get("result") or {}
print(f"  HTTP {st} id={r.get('id')} status={r.get('status')} score={r.get('score')} "
      f"league={r.get('league')} stats={'yes' if r.get('stats') else 'none'} timeline={'yes' if r.get('timeline') else 'none'}")

print("\n=== C. yesterday's matches: still findable, stats still there?")
st, p = g("/atp/fixtures/2026-09-22?filter=PlayerGroup:singles&pageSize=15")
fx = rows(p); print(f"  fixtures by date: HTTP {st}, {len(fx)} rows")
found = 0
for f in fx:
    a = (f.get("player1") or {}).get("name"); b = (f.get("player2") or {}).get("name")
    if not a or not b:
        continue
    st2, p2 = g(f"/extend/api/event/get/{urllib.parse.quote(a)}/{urllib.parse.quote(b)}/2026-09-22")
    r = (p2 or {}).get("result") or {}
    if not r.get("id"):
        print(f"  not found: {a} vs {b}"); continue
    st3, p3 = g(f"/extend/api/event/get/statistics/{r['id']}")
    s = ((p3 or {}).get("result") or {}).get("statistics") or {}
    print(f"  {a} vs {b}: status={r.get('status')} score={r.get('score')} stat sections={list(s.keys())}")
    found += 1
    if found >= 5:
        break

print("\n=== D. markets Bet365 posts before start")
now = time.time()
_, pu = get("/extend/api/events/upcoming/atp")
up = sorted([e for e in rows(pu) if (start_secs(e) or 0) > now], key=start_secs)
for e in up[:3]:
    st, p = g(f"/extend/api/odds/pre-match/{e.get('id')}")
    res = (p or {}).get("result") or {}
    print(f"  {label(e):40} markets: {', '.join(res.keys()) if isinstance(res, dict) else '-'}")
