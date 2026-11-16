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
FRACS = [("ModeA_0", 0.0), ("12.5pct", 0.125), ("25pct", 0.25), ("37.5pct", 0.375),
         ("50pct", 0.5), ("62.5pct", 0.625), ("75pct", 0.75), ("ModeB_100", 1.0)]

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
    return buckets

# ---- load picks-log rows (last 30 days, for volume/stability + board comp) ----
cutoff30 = (datetime.date(2026, 10, 6) - datetime.timedelta(days=29))
rows_by_day = {}
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
        if d < cutoff30 or d > datetime.date(2026, 10, 6):
            continue
        prob = row.get("prob"); cat = row.get("category")
        if not prob or not cat:
            continue
        try:
            prob_f = float(prob)
        except Exception:
            continue
        bo5 = str(row.get("best_of") or "").strip() in ("5", "5.0")
        ptype = (row.get("prop_type") or "untyped").strip().lower()
        rows_by_day.setdefault(day, []).append((prob_f, cat, bo5, ptype))

all_days_sorted = sorted(rows_by_day)
last14_days = all_days_sorted[-14:] if len(all_days_sorted) >= 14 else all_days_sorted

def daily_pass(frac):
    by_day = {}
    for day, items in rows_by_day.items():
        by_day.setdefault(day, {"total": 0, "70+": 0, "80+": 0, "90+": 0})
        for prob_f, cat, bo5, ptype in items:
            s = _score(prob_f, cat, bo5, rec, frac)
            by_day[day]["total"] += 1
            if s >= 70: by_day[day]["70+"] += 1
            if s >= 80: by_day[day]["80+"] += 1
            if s >= 90: by_day[day]["90+"] += 1
    days = sorted(by_day)
    def stats(key):
        vals = [by_day[d][key] for d in days]
        if not vals: return {"mean": None, "std": None, "cv": None}
        m = sum(vals) / len(vals)
        sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
        cv = round(sd / m, 4) if m else None
        return {"mean": round(m, 2), "std": round(sd, 2), "cv": cv}
    return {
        "avg_total_per_day": stats("total")["mean"],
        "70plus": stats("70+"),
        "80plus": stats("80+"),
        "90plus": stats("90+"),
        "days": len(days),
    }

def board_comp_pass(frac):
    # APPROXIMATION NOTICE: reconstructs board membership from logged
    # prob/category/prop_type only. Cannot replicate the live pipeline's
    # correlation gate, demonlock filter, or slip-length rules for past
    # days (those require the live fetch context, which no longer exists
    # for a historical day). Top3/Top10 = top-N by score, no floor.
    # Elite6/Goblin/Standard = score>=70 within prop_type, capped at 6/10.
    # Demon = score>=60 (its production floor) within prop_type=demon.
    per_day = {}
    for day in last14_days:
        items = rows_by_day.get(day, [])
        scored = []
        for prob_f, cat, bo5, ptype in items:
            s = _score(prob_f, cat, bo5, rec, frac)
            scored.append((s, ptype))
        scored.sort(key=lambda x: -x[0])
        scores_only = [s for s, _ in scored]
        top3 = len(scored[:3])
        top10 = len(scored[:10])
        elite6 = len([s for s, _ in scored if s >= 70][:6])
        goblin = len([s for s, p in scored if p == "goblin" and s >= 70][:6])
        demon  = len([s for s, p in scored if p == "demon" and s >= 60][:6])
        standard = len([s for s, p in scored if p == "standard" and s >= 70][:6])
        per_day[day] = {
            "Top3": top3, "Elite6": elite6, "Top10": top10,
            "Goblin": goblin, "Demon": demon, "Standard": standard,
            "avg_score": round(sum(scores_only) / len(scores_only), 2) if scores_only else None,
            "highest_score": max(scores_only) if scores_only else None,
        }
    # averages across the 14 days
    def avgkey(k):
        vals = [per_day[d][k] for d in last14_days if per_day[d][k] is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    return {
        "per_day": per_day,
        "avg": {k: avgkey(k) for k in ("Top3", "Elite6", "Top10", "Goblin", "Demon", "Standard", "avg_score", "highest_score")},
    }

results = {}
for label, frac in FRACS:
    buckets = settled_pass(frac)
    gaps = [buckets[b]["gap"] for b in EXPECTED_MID if b in buckets and buckets[b].get("gap") is not None]
    avg_gap = round(sum(abs(g) for g in gaps) / len(gaps), 4) if gaps else None
    dp = daily_pass(frac)
    bc = board_comp_pass(frac)
    results[label] = {
        "frac_to_B": frac,
        "buckets": buckets,
        "avg_abs_calibration_gap": avg_gap,
        "daily": dp,
        "board_composition": bc,
    }

with open('/tmp/middle_ground_result.json', 'w') as f:
    json.dump({"last14_days": last14_days, "results": results}, f, indent=1, default=str)
print("DONE", len(last14_days), "days in board-comp window")
