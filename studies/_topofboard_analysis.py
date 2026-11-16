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

RISK_PER_PICK = 1.1
WIN_PAYOUT = 1.0

PROP_SPECIFIC_FRAC = {
    "aces": 0.75, "dfs": 0.0, "breaks": 0.0, "fantasy_score": 0.0,
    "games_won": 0.0, "total_games": 0.0, "total_sets": 0.0, "tiebreaks": 0.0,
}

def frac_for(mode, cat):
    if mode == "B":
        return 1.0
    if mode == "G25":
        return 0.25
    return PROP_SPECIFIC_FRAC.get(cat, 0.0)

all_picks_raw = [p for p in settled if p["prob"] is not None and p.get("match_date")]

def wl_stats(subset):
    wins = sum(1 for s, p in subset if p["hit"] is True)
    losses = sum(1 for s, p in subset if p["hit"] is False)
    pushes = sum(1 for s, p in subset if p["hit"] is None)
    decided = wins + losses
    win_pct = round(wins / decided, 4) if decided else None
    net_units = round(wins * WIN_PAYOUT - losses * RISK_PER_PICK, 2)
    roi = round(net_units / (decided * RISK_PER_PICK), 4) if decided else None
    avg_score = round(sum(s for s, p in subset) / len(subset), 2) if subset else None
    return {"n_picks": len(subset), "wins": wins, "losses": losses, "pushes": pushes,
            "win_rate_pct": round(win_pct * 100, 2) if win_pct is not None else None,
            "roi_pct": round(roi * 100, 2) if roi is not None else None,
            "net_units": net_units, "avg_score": avg_score}

def wl_stats2(subset):
    d = wl_stats(subset)
    d["avg_confidence_prob"] = round(sum(p["prob"] for s, p in subset) / len(subset), 4) if subset else None
    return d

from collections import defaultdict

def by_day(picks):
    d = defaultdict(list)
    for p in picks:
        d[p["match_date"]].append(p)
    return d

days = by_day(all_picks_raw)

configs = ["B", "G25", "PS"]
CONFIG_NAMES = {"B": "Current_B", "G25": "Global_25pct", "PS": "Prop_Specific"}

results = {}
for mode in configs:
    scored_by_day = {}
    for day, picks in days.items():
        scored = [(_score(p["prob"], p["category"], p.get("bo5", False), rec, frac_for(mode, p["category"])), p) for p in picks]
        scored.sort(key=lambda x: -x[0])
        scored_by_day[day] = scored

    top3_pool, top5_pool, top10_pool = [], [], []
    for day, scored in scored_by_day.items():
        top3_pool.extend(scored[:3])
        top5_pool.extend(scored[:5])
        top10_pool.extend(scored[:10])

    results[CONFIG_NAMES[mode]] = {
        "days": len(scored_by_day),
        "top3": wl_stats2(top3_pool),
        "top5": wl_stats2(top5_pool),
        "top10": wl_stats2(top10_pool),
    }

    # "elite" tier proxy (recorded field in settled_picks, closest analog to
    # a top-of-board / highest-confidence designation actually in the data;
    # true Goblin/Elite6/Standard/Demon slip-type membership is NOT stored
    # in settled history and cannot be reconstructed without fabrication)
    elite_all = [p for p in all_picks_raw if p.get("tier") == "elite"]
    elite_scored = [(_score(p["prob"], p["category"], p.get("bo5", False), rec, frac_for(mode, p["category"])), p) for p in elite_all]
    results[CONFIG_NAMES[mode]]["tier_elite"] = wl_stats2(elite_scored)

with open('/tmp/topofboard_result.json', 'w') as f:
    json.dump(results, f, indent=1, default=str)

print("DONE", "days analyzed:", len(days))
for name, r in results.items():
    print(name, "top3:", r["top3"]["win_rate_pct"], r["top3"]["roi_pct"], r["top3"]["net_units"],
          "| top5:", r["top5"]["win_rate_pct"], r["top5"]["roi_pct"],
          "| top10:", r["top10"]["win_rate_pct"], r["top10"]["roi_pct"],
          "| elite:", r["tier_elite"]["win_rate_pct"], r["tier_elite"]["roi_pct"], r["tier_elite"]["n_picks"])
