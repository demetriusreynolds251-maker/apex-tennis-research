#!/usr/bin/env python3
# Why were rows held? Full reasons for Sep 1+ rows. READ-ONLY.
import csv, re, time, collections, datetime as dt, urllib.parse
import apex_settle_sa365 as S
today = dt.date.today().isoformat()
rows = [r for r in csv.DictReader(open(S.LOG, newline=""))
        if "2026-09-01" <= r.get("match_date", "") < today]
print("rows:", len(rows))
reasons = collections.Counter(); bycat = collections.defaultdict(collections.Counter)
examples = collections.defaultdict(list); nosheet_dates = collections.Counter(); recheck = {}
for r in rows:
    got, msg = S.settle_one(r)
    if got is not None:
        reasons["GRADED OK"] += 1; bycat["GRADED OK"][r["category"]] += 1; continue
    key = re.sub(r"\s*score .*$", "", msg).strip()
    key = re.sub(r"games \d+-\d+ disagree", "games disagree", key)
    reasons[key] += 1; bycat[key][r["category"]] += 1
    if len(examples[key]) < 3:
        examples[key].append(f"{r['match_date']} {S._who(r)} {r['category']}")
    if "no stat sheet" in key:
        nosheet_dates[r["match_date"]] += 1
    if "NOT_FINISHED" in key or "NO MATCH" in key:
        p, o = S.target(r)
        if p:
            recheck[(p, o, r["match_date"])] = key
print("\n=== reasons (number of picks)")
for k, n in reasons.most_common():
    print(f"  {n:4}  {k}\n        by category: {dict(bycat[k])}")
    for e in examples[k]:
        print(f"        e.g. {e}")
print("\n=== 'no stat sheet' by match date:", dict(sorted(nosheet_dates.items())))
print(f"\n=== every SportsAPI365 record for up to 10 not-found / not-finished matches ({len(recheck)} total)")
for (p, o, d0), why in list(recheck.items())[:10]:
    print(f"\n  {p} vs {o} ({d0})  [{why}]")
    base = dt.date.fromisoformat(d0); hits = 0
    for n in (-2, -1, 0, 1, 2):
        d = (base + dt.timedelta(days=n)).isoformat()
        for x, y in ((p, o), (o, p)):
            pl, err = S.api(f"/extend/api/event/get/{urllib.parse.quote(x)}/{urllib.parse.quote(y)}/{d}")
            time.sleep(0.25)
            ev = (pl or {}).get("result") or {}
            if ev.get("id"):
                hits += 1
                print(f"     {d} [{x} / {y}] id={ev.get('id')} status={ev.get('status')} score={ev.get('score')} {ev.get('league')}")
    if not hits:
        print("     no records at all")
