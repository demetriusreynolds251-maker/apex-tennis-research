#!/usr/bin/env python3
# Do stat sheets disappear with age, or do some events (Slams) just not have them? READ-ONLY.
import time, urllib.parse, collections
import apex_settle_sa365 as S
DATES = ["2026-09-02", "2026-09-08", "2026-09-12", "2026-09-16", "2026-09-19", "2026-09-21"]
p, err = S.api("/extend/api/event/get/statistics/3896098")
print("US Open Shelton v Shapovalov (Sep 5, finished) stat sheet:",
      "YES" if ((p or {}).get("result") or {}).get("statistics") else "NO")
for day in DATES:
    fx, err = S.api(f"/atp/fixtures/{day}?filter=PlayerGroup:singles&pageSize=40")
    rows = (fx or {}).get("data") or []
    ended = sheet = 0; leagues = collections.Counter()
    for f in rows:
        a = (f.get("player1") or {}).get("name"); b = (f.get("player2") or {}).get("name")
        if not a or not b:
            continue
        ev = None
        for x, y in ((a, b), (b, a)):
            q, _ = S.api(f"/extend/api/event/get/{urllib.parse.quote(x)}/{urllib.parse.quote(y)}/{day}"); time.sleep(0.2)
            r = (q or {}).get("result") or {}
            if r.get("id"):
                ev = r; break
        if not ev or str(ev.get("status")).lower() != "ended":
            continue
        ended += 1
        st, _ = S.api(f"/extend/api/event/get/statistics/{ev['id']}"); time.sleep(0.2)
        has = bool(((st or {}).get("result") or {}).get("statistics"))
        sheet += has
        leagues[(str(ev.get("league"))[:30], "sheet" if has else "NO sheet")] += 1
        if ended >= 12:
            break
    print(f"\n{day}: finished matches checked {ended} | with stat sheet {sheet}")
    for (lg, s), n in leagues.most_common(6):
        print(f"    {n:2}  {lg:30}  {s}")
