#!/usr/bin/env python3
# SA365 id-field + Pinnacle-opening check. READ-ONLY.
import json, time, datetime
from sa365_prematch_probe import get, rows, odds_books, label, start_secs

def utc(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M UTC") if ts else "?"

_, pl = get("/extend/api/events/live"); live = rows(pl)
_, pu = get("/extend/api/events/upcoming/atp"); up = rows(pu)

print("ID FORMATS")
for tag, lst in (("live", live[:3]), ("upcoming", up[:3])):
    for e in lst:
        print(f"  {tag:8} id={e.get('id')}  matchId={e.get('matchId')}  status={e.get('status')}  {label(e)}")

pin_live = []
for e in live[:10]:
    st, f = odds_books(e.get("id")); time.sleep(0.5)
    if "Pinnacle" in f:
        pin_live.append(e)
    if len(pin_live) >= 2:
        break

print("\nODDS USING matchId INSTEAD OF id")
for tag, lst in (("live", pin_live), ("upcoming", up[:4])):
    for e in lst:
        st, f = odds_books(e.get("matchId")); time.sleep(0.5)
        print(f"  {tag:8} matchId {e.get('matchId')}: {','.join(f) or f'(none, HTTP {st})'}  {label(e)}")

print("\nPINNACLE OPENING PRICE ON LIVE MATCHES (odds summary)")
for e in pin_live:
    st, s = get(f"/extend/api/odds/summary/{e.get('id')}"); time.sleep(0.5)
    print(f"\n  {label(e)}  start {utc(start_secs(e))}  HTTP {st}")
    if not s:
        continue
    text = json.dumps(s)
    i = text.lower().find("pinnacle")
    print("  " + (text[max(0, i - 150): i + 700] if i >= 0 else "no Pinnacle in summary; first 600: " + text[:600]))
