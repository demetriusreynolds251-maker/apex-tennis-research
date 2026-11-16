import sys, json, csv, datetime
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

def settled_pass(frac):
    buckets = {}
    for p in settled:
        if p["hit"] is None or p["prob"] is None:
            continue
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
    total_n = sum(d["count"] for d in buckets.values())
    total_w = sum(d["w"] for d in buckets.values())
    return buckets, total_n, total_w

cutoff = (datetime.date(2026, 10, 6) - datetime.timedelta(days=29))
daily_rows = []
with open('apex_engine_picks_log_v1.csv', newline='') as f:
    for row in csv.DictReader(f):
        ts = row.get("ts") or ""
        day = ts[:10] if ts else None
        if not day:
            continue
        try:
            d = datetime.date.fromisoformat(day)
        except Exception:
            continue
        if d < cutoff or d > datetime.date(2026, 10, 6):
            continue
        prob = row.get("prob"); cat = row.get("category")
        if not prob or not cat:
            continue
        try:
            prob_f = float(prob)
        except Exception:
            continue
        bo5 = str(row.get("best_of") or "").strip() in ("5", "5.0")
        daily_rows.append((day, prob_f, cat, bo5))

def daily_pass(frac):
    by_day = {}
    for day, prob_f, cat, bo5 in daily_rows:
        s = _score(prob_f, cat, bo5, rec, frac)
        by_day.setdefault(day, {"total": 0, "70+": 0, "80+": 0, "90+": 0})
        by_day[day]["total"] += 1
        if s >= 70: by_day[day]["70+"] += 1
        if s >= 80: by_day[day]["80+"] += 1
        if s >= 90: by_day[day]["90+"] += 1
    days = sorted(by_day)
    def avg(key):
        vals = [by_day[d][key] for d in days]
        return round(sum(vals) / len(vals), 2) if vals else None
    def std(key):
        vals = [by_day[d][key] for d in days]
        if not vals: return None
        m = sum(vals) / len(vals)
        return round((sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5, 2)
    return {
        "avg_total_per_day": avg("total"),
        "avg_70plus_per_day": avg("70+"),
        "avg_80plus_per_day": avg("80+"),
        "avg_90plus_per_day": avg("90+"),
        "std_70plus_per_day": std("70+"),
        "days": len(days),
    }

results = {}
for label, frac in [("ModeA_0pct", 0.0), ("25pct_to_B", 0.25), ("50pct_to_B", 0.5), ("75pct_to_B", 0.75), ("ModeB_100pct", 1.0)]:
    buckets, total_n, total_w = settled_pass(frac)
    overall_acc = round(total_w / total_n, 4) if total_n else None
    avg_gap = None
    gaps = [buckets[b]["gap"] for b in EXPECTED_MID if b in buckets and buckets[b].get("gap") is not None]
    if gaps:
        avg_gap = round(sum(abs(g) for g in gaps) / len(gaps), 4)
    dp = daily_pass(frac)
    results[label] = {
        "frac_to_B": frac,
        "total_predictions": total_n,
        "overall_accuracy": overall_acc,
        "buckets": buckets,
        "avg_abs_calibration_gap": avg_gap,
        "daily": dp,
    }

with open('/tmp/balance_analysis.json', 'w') as f:
    json.dump(results, f, indent=1, default=str)
print("DONE")
