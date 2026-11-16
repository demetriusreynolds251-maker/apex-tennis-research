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
FRAC_LABELS = [("A_0", 0.0), ("12.5pct", 0.125), ("25pct", 0.25), ("37.5pct", 0.375),
               ("50pct", 0.5), ("62.5pct", 0.625), ("75pct", 0.75), ("B_100", 1.0)]

# ROI ASSUMPTION DISCLOSURE: no real odds/payout field exists anywhere in
# settled_picks() or apex_engine_picks_log_v1.csv. Using standardized flat
# -110 American-odds convention (risk 1.1 units to win 1.0 unit per pick),
# the standard sportsbook player-prop juice. Push = 0 net. This is an
# ASSUMPTION, not observed sportsbook pricing, and is flagged in every
# output section below.
RISK_PER_PICK = 1.1
WIN_PAYOUT = 1.0

all_scored = []
for p in settled:
    if p["hit"] is None or p["prob"] is None:
        continue
    all_scored.append(p)

CAT_ORDER = ["aces", "dfs", "breaks", "fantasy_score", "games_won", "total_games", "total_sets", "tiebreaks"]

def score_picks(picks, frac):
    out = []
    for p in picks:
        s = _score(p["prob"], p["category"], p.get("bo5", False), rec, frac)
        out.append((s, p))
    return out

def wl_stats(scored_subset):
    wins = sum(1 for s, p in scored_subset if p["hit"] is True)
    losses = sum(1 for s, p in scored_subset if p["hit"] is False)
    total = wins + losses
    win_pct = round(wins / total, 4) if total else None
    net_units = round(wins * WIN_PAYOUT - losses * RISK_PER_PICK, 2)
    roi = round(net_units / (total * RISK_PER_PICK), 4) if total else None
    return {"wins": wins, "losses": losses, "pushes": 0, "n": total,
            "win_pct": win_pct, "net_units": net_units, "roi_pct": round(roi * 100, 2) if roi is not None else None}

all_pushes = [p for p in settled if p["hit"] is None and p["prob"] is not None]
PUSH_COUNT_GLOBAL = len(all_pushes)

def band_breakdown(scored_subset):
    buckets = {}
    for s, p in scored_subset:
        b = bucket_of(s)
        buckets.setdefault(b, {"n": 0, "w": 0, "l": 0})
        buckets[b]["n"] += 1
        if p["hit"] is True: buckets[b]["w"] += 1
        elif p["hit"] is False: buckets[b]["l"] += 1
    for b, d in buckets.items():
        decided = d["w"] + d["l"]
        d["win_rate"] = round(d["w"] / decided, 4) if decided else None
        if b in EXPECTED_MID:
            d["expected"] = EXPECTED_MID[b]
            d["gap"] = round(d["win_rate"] - EXPECTED_MID[b], 4) if d["win_rate"] is not None else None
    return buckets

def high_conf_subset(scored_subset, floor):
    sub = [(s, p) for s, p in scored_subset if s >= floor]
    stats = wl_stats(sub)
    return stats

def top_n_subset(scored_subset, n):
    ranked = sorted(scored_subset, key=lambda x: -x[0])[:n]
    return wl_stats(ranked)

def day_stability(scored_subset):
    by_day = {}
    for s, p in scored_subset:
        day = p.get("match_date") or "unknown"
        by_day.setdefault(day, 0)
        if s >= 70:
            by_day[day] += 1
    vals = list(by_day.values())
    n = len(vals)
    if n == 0:
        return {"days": 0, "mean": None, "cv": None}
    m = sum(vals) / n
    sd = (sum((v - m) ** 2 for v in vals) / n) ** 0.5
    cv = round(sd / m, 4) if m else None
    return {"days": n, "mean": round(m, 2), "cv": cv}

results = {}
for label, frac in FRAC_LABELS:
    scored = score_picks(all_scored, frac)
    overall = wl_stats(scored)
    overall["pushes"] = PUSH_COUNT_GLOBAL
    bands = band_breakdown(scored)
    hc = {
        "70plus": high_conf_subset(scored, 70),
        "80plus": high_conf_subset(scored, 80),
        "90plus": high_conf_subset(scored, 90),
    }
    by_prop = {}
    for cat in CAT_ORDER:
        cat_scored = [(s, p) for s, p in scored if p["category"] == cat]
        if not cat_scored:
            continue
        by_prop[cat] = wl_stats(cat_scored)
        by_prop[cat]["n_total_scored"] = len(cat_scored)
    top_plays = {
        "top10": top_n_subset(scored, 10),
        "top25": top_n_subset(scored, 25),
        "top50": top_n_subset(scored, 50),
        "top100": top_n_subset(scored, 100),
    }
    stab = day_stability(scored)
    results[label] = {
        "frac": frac,
        "overall": overall,
        "bands": bands,
        "high_confidence": hc,
        "by_prop_type": by_prop,
        "top_plays": top_plays,
        "stability": stab,
    }

with open('/tmp/winrate_roi_result.json', 'w') as f:
    json.dump(results, f, indent=1, default=str)

print("DONE")
print("total_decided_scored:", len(all_scored), "pushes:", PUSH_COUNT_GLOBAL)
for label, frac in FRAC_LABELS:
    o = results[label]["overall"]
    print(label, "winpct=", o["win_pct"], "n=", o["n"], "roi%=", o["roi_pct"], "net_units=", o["net_units"])
