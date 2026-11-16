#!/usr/bin/env python3
"""Bet365/DraftKings vs Pinnacle gap from RECENT FINISHED matches. READ-ONLY except its own CSV.
For each finished singles match in the last N days: odds summary -> each book's last Full Time
Result price posted BEFORE the start (in-play prices excluded by timestamp). Start = earliest
'kickoff' stamp any book has, else the scheduled time. Usage: python3 sa365_gap_backfill.py [days]"""
import sys, csv, time, re, statistics, urllib.parse, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import apex_settle_sa365 as S
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
OUT = "data/sa365_gap_backfill.csv"
BOOKS = ("Bet365", "DraftKings")
q = urllib.parse.quote

def devig(a, b):
    try:
        x, y = 1 / float(a), 1 / float(b); return x / (x + y)
    except Exception:
        return None

def iso_ts(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

def level(lg):
    lg = str(lg or "").lower()
    if "challenger" in lg: return "Challenger"
    if re.match(r"\s*[mw]\d", lg): return "ITF"
    return "Tour/other"

def fixtures(day, tour):
    out = []
    for page in range(1, 10):
        p, err = S.api(f"/{tour}/fixtures/{day}?filter=PlayerGroup:singles&pageSize=100&pageNo={page}")
        out += (p or {}).get("data") or []
        if not (p or {}).get("hasNextPage"):
            break
    return out

def points(book):
    ftr = (book or {}).get("Full Time Result") or {}
    out = {}
    for k in ("start", "kickoff", "end"):
        d = ftr.get(k) or {}
        if d.get("od1") and d.get("sourceAddTime") is not None:
            out[k] = (d["od1"], d["od2"], float(d["sourceAddTime"]))
    return out

def last_pre(pts, start):
    ok = [v for v in pts.values() if v[2] <= start + 60]
    return max(ok, key=lambda v: v[2]) if ok else None

def one(args):
    day, f = args
    a = (f.get("player1") or {}).get("name"); b = (f.get("player2") or {}).get("name")
    if not a or not b or "/" in a or "/" in b:
        return None
    nxt = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    ev = None
    for d in (day, nxt):
        for x, y in ((a, b), (b, a)):
            p, _ = S.api(f"/extend/api/event/get/{q(x)}/{q(y)}/{d}")
            r = (p or {}).get("result") or {}
            if r.get("id"):
                ev = r; break
        if ev: break
    if not ev or str(ev.get("status")).lower() != "ended":
        return None
    p, _ = S.api(f"/extend/api/odds/summary/{ev['id']}")
    res = (p or {}).get("result") or {}
    pin = points(res.get("Pinnacle"))
    if not pin:
        return None
    kicks = [v["kickoff"][2] for v in (points(bk) for bk in res.values()) if "kickoff" in v]
    start = min(kicks) if kicks else iso_ts(f.get("date"))
    if not start:
        return None
    pc = last_pre(pin, start)
    pp = devig(pc[0], pc[1]) if pc else None
    if pp is None:
        return None
    row = {"day": day, "event_id": ev["id"], "league": ev.get("league"), "match": ev.get("name"),
           "pin_fav_p": round(max(pp, 1 - pp), 4), "pin_age_min": round((start - pc[2]) / 60)}
    for bk in BOOKS:
        bc = last_pre(points(res.get(bk)), start)
        bp = devig(bc[0], bc[1]) if bc else None
        if bp is not None:
            b_fav = bp if pp >= 0.5 else 1 - bp
            row[f"{bk}_gap_pts"] = round((b_fav - max(pp, 1 - pp)) * 100, 2)
            row[f"{bk}_age_min"] = round((start - bc[2]) / 60)
    return row

today = dt.date.today()
jobs = []
for n in range(1, DAYS + 1):
    day = (today - dt.timedelta(days=n)).isoformat()
    for tour in ("atp", "wta"):
        fx = fixtures(day, tour)
        print(f"{day} {tour}: {len(fx)} matches listed", flush=True)
        jobs += [(day, f) for f in fx]
rows = []
with ThreadPoolExecutor(max_workers=4) as ex:
    for i, r in enumerate(ex.map(one, jobs), 1):
        if r: rows.append(r)
        if i % 100 == 0:
            print(f"  checked {i}/{len(jobs)} | usable so far {len(rows)}", flush=True)
flds = ["day", "event_id", "league", "match", "pin_fav_p", "pin_age_min"] + \
       [f"{b}_{k}" for b in BOOKS for k in ("gap_pts", "age_min")]
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=flds); w.writeheader(); w.writerows(rows)
print(f"\nmatches with a Pinnacle pre-start price: {len(rows)}  -> saved {OUT}")

def show(title, vals):
    if len(vals) < 8:
        print(f"  {title:30} n={len(vals):4}  (too few)"); return
    a = [abs(v) for v in vals]
    print(f"  {title:30} n={len(vals):4}  mean {statistics.mean(vals):+5.2f}  median {statistics.median(vals):+5.2f}"
          f"  spread {statistics.stdev(vals):4.2f}  within 1pt {sum(x <= 1 for x in a) / len(a):4.0%}"
          f"  within 2pt {sum(x <= 2 for x in a) / len(a):4.0%}")
for bk in BOOKS:
    k = f"{bk}_gap_pts"
    sub = [r for r in rows if k in r]
    print(f"\n=== {bk} minus Pinnacle (favourite win chance, percentage points), last prices before start")
    show("ALL", [r[k] for r in sub])
    show("both priced within 3h of start", [r[k] for r in sub if r["pin_age_min"] <= 180 and r[f"{bk}_age_min"] <= 180])
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)):
        show(f"Pinnacle fav {lo:.0%}-{min(hi, 1):.0%}", [r[k] for r in sub if lo <= r["pin_fav_p"] < hi])
    for lv in ("ITF", "Challenger", "Tour/other"):
        show(lv, [r[k] for r in sub if level(r["league"]) == lv])
