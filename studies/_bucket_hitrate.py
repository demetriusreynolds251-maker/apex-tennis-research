import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

picks = aet.settled_picks()
rec = aet.records()

BE = aet.BREAK_EVEN
BUCKETS = aet.BUCKETS
group_of = aet.group_of
attention = aet.attention

_FIXED = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}

def _score(prob, cat, bo5, rec, mode):
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or {"n": 0, "cal_pts": None}
    n = cs.get("n", 0); w = min(n / 25.0, 1.0)
    score = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BE) / (0.85 - BE)))
    if mode == "A":
        if n >= 5 and cs.get("cal_pts") is not None:
            cal_scale = cs["cal_pts"] / 0.10
            ev = (30.0 if cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, cal_scale))
            score += ev
    else:
        if cat in _FIXED:
            score += _FIXED[cat]
    g = group_of(cat)
    prior = {"rate_model": 8.0, "sim_derived": 3.0, "total_games": -8.0}.get(g, 0.0)
    pr = prior * (1.0 - w) * (0.5 if n < 5 else 1.0)
    score += pr
    for name, blo, bhi in BUCKETS:
        if n < 5:
            break
        if blo <= prob < bhi:
            for bn, bw_, bl_, bstat in rec["buckets"]:
                if bn == name and (bw_ + bl_) >= 3 and bstat:
                    br = bw_ / (bw_ + bl_)
                    adj = 10.0 * min((bw_ + bl_) / 10.0, 1.0) * max(-1.0, min(1.0, (br - bstat) / 0.10))
                    score += adj
            break
    lvl, _w = attention(cat, prob, rec)
    if bo5: lvl = "LOW"
    score += {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0)
    return round(max(0.0, min(100.0, score)))

def bucket_of(s):
    if s < 50: return "under50"
    if s < 60: return "50-59"
    if s < 70: return "60-69"
    if s < 80: return "70-79"
    if s < 90: return "80-89"
    return "90+"

def run(mode):
    buckets = {}
    for p in picks:
        if p["hit"] is None or p["prob"] is None:
            continue
        s = _score(p["prob"], p["category"], p.get("bo5", False), rec, mode)
        b = bucket_of(s)
        buckets.setdefault(b, {"count": 0, "w": 0, "l": 0})
        buckets[b]["count"] += 1
        if p["hit"]:
            buckets[b]["w"] += 1
        else:
            buckets[b]["l"] += 1
    for b, d in buckets.items():
        d["hit_rate"] = round(d["w"] / d["count"], 4) if d["count"] else None
    return buckets

modeA = run("A")
modeB = run("B")

def combined(buckets, bands):
    w = sum(buckets.get(b, {}).get("w", 0) for b in bands)
    l = sum(buckets.get(b, {}).get("l", 0) for b in bands)
    n = w + l
    return {"count": n, "w": w, "l": l, "hit_rate": round(w / n, 4) if n else None}

out = {
    "total_settled_decided": sum(1 for p in picks if p["hit"] is not None and p["prob"] is not None),
    "modeA_buckets": modeA,
    "modeB_buckets": modeB,
    "modeA_70plus": combined(modeA, ["70-79", "80-89", "90+"]),
    "modeA_80plus": combined(modeA, ["80-89", "90+"]),
    "modeA_90plus": combined(modeA, ["90+"]),
    "modeB_70plus": combined(modeB, ["70-79", "80-89", "90+"]),
    "modeB_80plus": combined(modeB, ["80-89", "90+"]),
    "modeB_90plus": combined(modeB, ["90+"]),
}
with open('/tmp/bucket_hitrate_result.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
print("DONE")
print(json.dumps(out, indent=1, default=str))
