import sys, json, csv, datetime
sys.path.insert(0, '.')
import apex_edge_tracker as aet

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

cutoff = (datetime.date(2026, 10, 6) - datetime.timedelta(days=29))  # last 30 days incl. today

by_day_A = {}
by_day_B = {}
rows_read = 0
rows_used = 0
with open('apex_engine_picks_log_v1.csv', newline='') as f:
    r = csv.DictReader(f)
    for row in r:
        rows_read += 1
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
        prob = row.get("prob")
        cat = row.get("category")
        if not prob or not cat:
            continue
        try:
            prob_f = float(prob)
        except Exception:
            continue
        bo5 = str(row.get("best_of") or "").strip() in ("5", "5.0")
        rows_used += 1
        sa = _score(prob_f, cat, bo5, rec, "A")
        sb = _score(prob_f, cat, bo5, rec, "B")
        by_day_A.setdefault(day, {"70+": 0, "80+": 0, "90+": 0})
        by_day_B.setdefault(day, {"70+": 0, "80+": 0, "90+": 0})
        if sa >= 70: by_day_A[day]["70+"] += 1
        if sa >= 80: by_day_A[day]["80+"] += 1
        if sa >= 90: by_day_A[day]["90+"] += 1
        if sb >= 70: by_day_B[day]["70+"] += 1
        if sb >= 80: by_day_B[day]["80+"] += 1
        if sb >= 90: by_day_B[day]["90+"] += 1

all_days = sorted(set(by_day_A) | set(by_day_B))

def avg(by_day, key):
    vals = [by_day.get(d, {}).get(key, 0) for d in all_days]
    return round(sum(vals) / len(vals), 2) if vals else None

out = {
    "rows_read": rows_read,
    "rows_used": rows_used,
    "days_covered": len(all_days),
    "day_range": [all_days[0], all_days[-1]] if all_days else None,
    "modeA_by_day": {d: by_day_A.get(d, {"70+": 0, "80+": 0, "90+": 0}) for d in all_days},
    "modeB_by_day": {d: by_day_B.get(d, {"70+": 0, "80+": 0, "90+": 0}) for d in all_days},
    "modeA_avg": {"70+": avg(by_day_A, "70+"), "80+": avg(by_day_A, "80+"), "90+": avg(by_day_A, "90+")},
    "modeB_avg": {"70+": avg(by_day_B, "70+"), "80+": avg(by_day_B, "80+"), "90+": avg(by_day_B, "90+")},
}
with open('/tmp/daily_slate_bands.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
print("DONE", rows_used, "rows,", len(all_days), "days")
