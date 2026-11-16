import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

settled = aet.settled_picks()
rec = aet.records()
BE = aet.BREAK_EVEN
BUCKETS = aet.BUCKETS
group_of = aet.group_of
attention = aet.attention

_FIXED_B = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}

def _ev_a(cat):
    cs = rec["cats"].get(cat) or {"n": 0, "cal_pts": None}
    n = cs.get("n", 0); w = min(n / 25.0, 1.0)
    if n >= 5 and cs.get("cal_pts") is not None:
        cal_scale = cs["cal_pts"] / 0.10
        return (30.0 if cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, cal_scale))
    return 0.0

def _ev_b(cat):
    return _FIXED_B.get(cat, 0.0)

def _score(prob, cat, bo5, rec, frac):
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or {"n": 0, "cal_pts": None}
    n = cs.get("n", 0); w = min(n / 25.0, 1.0)
    score = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BE) / (0.85 - BE)))
    ev = _ev_a(cat) + frac * (_ev_b(cat) - _ev_a(cat))
    score += ev
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

EXPECTED_MID = {"50-59": 0.55, "60-69": 0.65, "70-79": 0.75, "80-89": 0.85, "90+": 0.95}
FRACS = [("A_0", 0.0), ("12.5pct", 0.125), ("25pct", 0.25), ("37.5pct", 0.375),
         ("50pct", 0.5), ("62.5pct", 0.625), ("75pct", 0.75), ("B_100", 1.0)]

# categories present with decided (hit is not None) + prob available
by_cat = {}
for p in settled:
    if p["hit"] is None or p["prob"] is None:
        continue
    by_cat.setdefault(p["category"], []).append(p)

cat_counts = {c: len(v) for c, v in by_cat.items()}
# only categories with >= 15 decided picks get a full report
report_cats = [c for c, n in sorted(cat_counts.items(), key=lambda x: -x[1]) if n >= 15]

def settled_pass(picks, frac):
    buckets = {}
    for p in picks:
        s = _score(p["prob"], p["category"], p.get("bo5", False), rec, frac)
        b = bucket_of(s)
        buckets.setdefault(b, {"count": 0, "w": 0, "l": 0})
        buckets[b]["count"] += 1
        buckets[b]["w" if p["hit"] else "l"] += 1
    for b, d in buckets.items():
        d["accuracy"] = round(d["w"] / d["count"], 4) if d["count"] else None
        if b in EXPECTED_MID:
            d["expected"] = EXPECTED_MID[b]
            d["gap"] = round(d["accuracy"] - EXPECTED_MID[b], 4) if d["accuracy"] is not None else None
    gaps = [buckets[b]["gap"] for b in EXPECTED_MID if b in buckets and buckets[b].get("gap") is not None]
    avg_gap = round(sum(abs(g) for g in gaps) / len(gaps), 4) if gaps else None
    total_w = sum(d["w"] for d in buckets.values())
    total_n = sum(d["count"] for d in buckets.values())
    return buckets, avg_gap, total_w, total_n

def day_stability(picks, frac):
    by_day = {}
    for p in picks:
        day = p.get("match_date") or "unknown"
        s = _score(p["prob"], p["category"], p.get("bo5", False), rec, frac)
        by_day.setdefault(day, {"total": 0, "70+": 0})
        by_day[day]["total"] += 1
        if s >= 70:
            by_day[day]["70+"] += 1
    days = sorted(by_day)
    vals = [by_day[d]["70+"] for d in days]
    n = len(vals)
    if n == 0:
        return {"days": 0, "mean": None, "std": None, "cv": None}
    m = sum(vals) / n
    sd = (sum((v - m) ** 2 for v in vals) / n) ** 0.5
    cv = round(sd / m, 4) if m else None
    return {"days": n, "mean": round(m, 2), "std": round(sd, 2), "cv": cv}

out = {"category_counts": cat_counts, "report_categories": report_cats, "per_category": {}}

for cat in report_cats:
    picks = by_cat[cat]
    settings = {}
    for label, frac in FRACS:
        buckets, avg_gap, total_w, total_n = settled_pass(picks, frac)
        stab = day_stability(picks, frac)
        counts_70 = buckets.get("70-79", {}).get("count", 0) + buckets.get("80-89", {}).get("count", 0) + buckets.get("90+", {}).get("count", 0)
        settings[label] = {
            "frac": frac,
            "avg_abs_gap": avg_gap,
            "overall_accuracy": round(total_w / total_n, 4) if total_n else None,
            "buckets": buckets,
            "availability_70plus_n": counts_70,
            "stability": stab,
        }
    valid = [(lbl, s["avg_abs_gap"]) for lbl, s in settings.items() if s["avg_abs_gap"] is not None]
    valid.sort(key=lambda x: x[1])
    out["per_category"][cat] = {
        "sample_size": len(picks),
        "settings": settings,
        "ranked_by_gap": valid,
    }

with open('/tmp/prop_sensitivity_result.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
print("DONE", report_cats)
print(json.dumps(cat_counts, indent=1))
