import re, json
LOG = "/tmp/apex_coverage_fix_run_20260928_221521.log"
lines = open(LOG, encoding="utf-8", errors="replace").readlines()

vpat = re.compile(r"VERIFIED — (.+?) vs (.+?) — SportsAPI365 lists it: (.+?) \| (\w+) \|")
tour_map = {}  # frozenset({p,o}) -> (tournament, tour)
for l in lines:
    m = vpat.search(l)
    if m:
        p, o, tourney, tour = m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
        key = frozenset([p.lower(), o.lower()])
        tour_map[key] = (tourney, tour)

print("VERIFIED_PAIRS_INDEXED:", len(tour_map))

rpat = re.compile(r"REJECTED — (.+?) vs (.+?) — not found in V8")
rejects = []
for l in lines:
    if "[Gate11] REJECTED" in l and "not found in V8" in l:
        m = rpat.search(l)
        if m:
            p, o = m.group(1).strip(), m.group(2).strip()
            o_clean = re.sub(r"\s+1st Set$", "", o, flags=re.IGNORECASE).strip()
            key = frozenset([p.lower(), o_clean.lower()])
            rejects.append({"player": p, "opponent_raw": o, "opponent_clean": o_clean, "key": key})

print("TOTAL_REJECTS:", len(rejects))

matched = 0
levels = {}
for r in rejects:
    info = tour_map.get(r["key"])
    if info:
        matched += 1
        r["tournament"] = info[0]
        r["tour"] = info[1]
    else:
        r["tournament"] = None
        r["tour"] = None

print("MATCHED_TO_A_KNOWN_TOURNAMENT_VIA_SIBLING_PROP:", matched, "of", len(rejects))

from collections import Counter
tcounter = Counter(r["tournament"] for r in rejects if r["tournament"])
print("TOP TOURNAMENTS AMONG REJECTED MATCHES:")
for t, c in tcounter.most_common(30):
    print(f"  {c:3d}  {t}")

tourcounter = Counter(r["tour"] for r in rejects if r["tour"])
print("TOUR BREAKDOWN (ATP/WTA) AMONG REJECTED MATCHES:", dict(tourcounter))

unmatched = [r for r in rejects if not r["tournament"]]
print("UNMATCHED (no sibling verified prop for same match):", len(unmatched))
for r in unmatched[:20]:
    print("  ", r["player"], "vs", r["opponent_clean"])

with open("/tmp/gate11_audit2_output.json", "w") as f:
    json.dump(rejects, f, indent=2, default=str)
print("DONE2")
