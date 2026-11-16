#!/usr/bin/env python3
# SA365 id check + pre-match Pinnacle probe. READ-ONLY. Touches nothing in Apex.
import json, sys, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

BASE = "https://api.sportsapi365.com/v1/tennis"
KEY = Path.home().joinpath("openclaw/sportapi365_key.txt").read_text().strip()
CATEGORY = sys.argv[1] if len(sys.argv) > 1 else "atp"
BOOKS = ["Bet365","10Bet","YSB88","BWin","BetFair","Everygame","Interwetten","CashPoint",
         "Spreadex","VirginBet","DraftKings","Duelbits","FonBet","Polymarket","VBet",
         "CloudBet","DafaBet","MelBet","Pinnacle","Marathonbet"]
BUCKETS = [(0,30,"0-30 min"),(30,60,"30-60 min"),(60,180,"1-3 hrs"),
           (180,360,"3-6 hrs"),(360,720,"6-12 hrs"),(720,10**9,"12+ hrs")]
PER_BUCKET = 4

def get(path):
    req = urllib.request.Request(BASE + path, headers={
        "X-Gravitee-Api-Key": KEY, "Accept": "application/json", "User-Agent": "Mozilla/5.0 (ApexProbe)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return "ERR " + str(e)[:60], None

def rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("results", "result", "data"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []

def start_secs(ev):
    for k in ("startTimestamp", "start_timestamp", "startTime"):
        v = ev.get(k)
        if isinstance(v, (int, float)):
            return v / 1000 if v > 1e11 else v
    return None

def nm(x):
    return x.get("name", "?") if isinstance(x, dict) else str(x)

def label(ev):
    if ev.get("name"):
        return str(ev["name"])[:40]
    for hk, ak in (("homeTeam", "awayTeam"), ("home", "away")):
        if ev.get(hk) and ev.get(ak):
            return (nm(ev[hk]) + " v " + nm(ev[ak]))[:40]
    return "?"

def books_in(payload):
    text = json.dumps(payload).lower()
    return [b for b in BOOKS if b.lower() in text]

def odds_books(eid):
    q = "?market=" + urllib.parse.quote("Full Time Result")
    st, odds = get(f"/extend/api/event/odds/by-market/{eid}{q}")
    return st, (books_in(odds) if odds else [])

def show(tag, lead, ev, st, found):
    pin = "Pinnacle" in found
    shown = ",".join(found) if found else f"(none, HTTP {st})"
    print(f"  [{tag:9}] {lead:6.0f}m  {'YES' if pin else ' no'}  {label(ev):40}  {shown}")
    return pin

def main():
    now = time.time()
    st_l, p_l = get("/extend/api/events/live"); live = rows(p_l)
    st_u, p_u = get(f"/extend/api/events/upcoming/{CATEGORY}"); up = rows(p_u)
    print(f"events/live: HTTP {st_l}, {len(live)} rows")
    print(f"events/upcoming/{CATEGORY}: HTTP {st_u}, {len(up)} rows")
    if live: print("  live row keys:", sorted(live[0].keys()))
    if up: print("  upcoming row keys:", sorted(up[0].keys()))

    live_ids = {str(e.get("id")) for e in live}
    up_ids = {str(e.get("id")) for e in up}
    by_name = {label(e).lower(): e for e in live if label(e) != "?"}
    same = [e for e in up if label(e) != "?" and label(e).lower() in by_name]
    print(f"\nID CHECK: same id in both lists: {len(live_ids & up_ids)} | same match in both lists: {len(same)}")
    for e in same[:5]:
        print(f"  {label(e):40} upcoming id {e.get('id')}  live id {by_name[label(e).lower()].get('id')}")

    fut = lambda e: start_secs(e) and start_secs(e) > now
    live_future = [((start_secs(e) - now) / 60, e) for e in live if fut(e)]
    live_started = [e for e in live if not fut(e)]
    print(f"\nlive list: {len(live_future)} not started yet, {len(live_started)} already started")

    print("\nCONTROL (matches in progress, live ids -- should show Pinnacle):")
    for e in live_started[:3]:
        st, f = odds_books(e.get("id")); show("control", 0, e, st, f); time.sleep(0.5)

    if live_future:
        pool, tag = live_future, "live ids"
    else:
        pool, tag = [((start_secs(e) - now) / 60, e) for e in up if fut(e)], "UPCOMING ids"
        print("\nWARNING: live list has no not-started matches, so testing upcoming ids.")
        print("If these show Bet365 only, it may be the wrong-id trap, not a real 'no Pinnacle'.")
    pool.sort(key=lambda x: x[0])

    tally = {}
    print(f"\nPRE-MATCH TEST ({tag}):")
    for lo, hi, name in BUCKETS:
        n = y = 0
        for lead, e in [p for p in pool if lo <= p[0] < hi][:PER_BUCKET]:
            st, f = odds_books(e.get("id")); y += show(name, lead, e, st, f); n += 1; time.sleep(0.5)
        tally[name] = (n, y)
    print(f"\nSUMMARY ({tag}): Pinnacle present, by time before start")
    for _, _, name in BUCKETS:
        n, y = tally[name]
        print(f"  {name:10}  {y}/{n}" if n else f"  {name:10}  (no matches in this window)")

if __name__ == "__main__":
    main()
