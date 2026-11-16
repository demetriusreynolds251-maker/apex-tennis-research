#!/usr/bin/env python3
# Test the three routes from the SA365 docs. READ-ONLY.
import json, time, datetime, urllib.parse
from sa365_prematch_probe import get, rows, label, start_secs, books_in

def show(tag, path, n=500):
    st, p = get(path); time.sleep(0.4)
    txt = json.dumps(p) if p is not None else ""
    low = txt.lower()
    words = [w for w in ("pinnacle", "ace", "double", "break", "first serve") if w in low]
    print(f"  [{tag}] HTTP {st} size={len(txt)} words={words}\n        {path}")
    if txt:
        print("        start:", txt[:n])
    return p

now = time.time()
_, pu = get("/extend/api/events/upcoming/atp")
up = sorted([e for e in rows(pu) if (start_secs(e) or 0) > now], key=start_secs)
_, pl = get("/extend/api/events/live"); live = rows(pl)

print("=== 1. PRE-MATCH ODDS on not-yet-started matches")
n = len(up)
for e in (up[:2] + up[n//2:n//2+2] + up[-2:]):
    lead = (start_secs(e) - now) / 60
    st, p = get(f"/extend/api/odds/pre-match/{e.get('id')}"); time.sleep(0.4)
    b = books_in(p) if p else []
    print(f"  {lead:6.0f}m  {'PINNACLE' if 'Pinnacle' in b else '   -    '}  HTTP {st}  {label(e):40} books: {','.join(b) or '-'}")
if up:
    show("sample reply", f"/extend/api/odds/pre-match/{up[0].get('id')}", 700)

print("\n=== 2. MATCH STATISTICS (live now, and two matches from this morning)")
for e in live[:2]:
    show(label(e)[:30], f"/extend/api/event/get/statistics/{e.get('id')}", 800)
for eid, nm in (("4026607", "Burcescu vs Andreea (morning)"), ("4023097", "Maloney vs Ribeiro (earlier)")):
    show(nm, f"/extend/api/event/get/statistics/{eid}", 800)

print("\n=== 3. EVENT BY PLAYERS AND DATE (a live match, today's date)")
if live:
    e = live[0]
    parts = str(e.get("name", "")).split(" vs ")
    if len(parts) == 2:
        a, b = (urllib.parse.quote(x.strip()) for x in parts)
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        show(label(e)[:30], f"/extend/api/event/get/{a}/{b}/{today}", 1200)
