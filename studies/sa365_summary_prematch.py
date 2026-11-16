#!/usr/bin/env python3
# Does odds/summary show Pinnacle on NOT-YET-STARTED matches? READ-ONLY.
import sys, time
from sa365_prematch_probe import get, rows, label, start_secs
CAT = sys.argv[1] if len(sys.argv) > 1 else "atp"
now = time.time()
_, pu = get(f"/extend/api/events/upcoming/{CAT}")
up = sorted([e for e in rows(pu) if (start_secs(e) or 0) > now], key=start_secs)
n = len(up); picks, seen = [], set()
for e in up[:3] + up[n//3:n//3+3] + up[2*n//3:2*n//3+3] + up[-3:]:
    if e.get("id") not in seen:
        seen.add(e.get("id")); picks.append(e)
print(f"upcoming/{CAT}: {n} not started, testing {len(picks)}\n")
hits = 0
for e in picks:
    st, s = get(f"/extend/api/odds/summary/{e.get('id')}"); time.sleep(0.5)
    lead = (start_secs(e) - now) / 60
    res = (s or {}).get("result") if isinstance(s, dict) else None
    res = res if isinstance(res, dict) else {}
    pin = res.get("Pinnacle")
    info = ""
    if isinstance(pin, dict):
        hits += 1
        m = pin.get("Full Time Result") or next(iter(pin.values()), {}) or {}
        a = (m.get("start") or {}).get("sourceAddTime"); b = m.get("end") or {}
        if a:
            info += f"  opened {(start_secs(e) - a) / 3600:.1f}h before start"
        if b.get("sourceAddTime"):
            info += f", last move {(now - b['sourceAddTime']) / 60:.0f}m ago, price {b.get('od1')}/{b.get('od2')}"
    print(f"  {lead:6.0f}m  {'YES' if pin else ' no'}  {label(e):40} HTTP {st}  books: {','.join(sorted(res)) or '-'}")
    if info:
        print("         " + info)
print(f"\nSUMMARY: Pinnacle on {hits}/{len(picks)} not-yet-started matches (summary route)")
