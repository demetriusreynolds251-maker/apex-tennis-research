import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet
from collections import defaultdict

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
        if n < 5: break
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

all_picks_raw = [p for p in settled if p["prob"] is not None and p.get("match_date")]
days = defaultdict(list)
for p in all_picks_raw:
    days[p["match_date"]].append(p)
day_list = sorted(days.keys())

CONFIGS = {
    "B": {"default": 1.0, "aces": None},
    "G25": {"default": 0.25, "aces": None},
    "G25_Aces625": {"default": 0.25, "aces": 0.625},
    "G25_Aces75": {"default": 0.25, "aces": 0.75},
}

def frac_for(cfg, cat):
    c = CONFIGS[cfg]
    if cat == "aces" and c["aces"] is not None:
        return c["aces"]
    return c["default"]

def wl(subset):
    wins = sum(1 for s, p in subset if p["hit"] is True)
    losses = sum(1 for s, p in subset if p["hit"] is False)
    n = wins + losses
    wr = round(wins/n*100,2) if n else None
    net = round(wins*1.0 - losses*1.1, 2)
    roi = round(net/(n*1.1)*100,2) if n else None
    return {"n_picks": len(subset), "wins": wins, "losses": losses, "win_rate_pct": wr, "roi_pct": roi, "net_units": net}

scored_by_day = {}
for cfg in CONFIGS:
    sbd = {}
    for day in day_list:
        scored = [(_score(p["prob"], p["category"], p.get("bo5", False), rec, frac_for(cfg, p["category"])), p) for p in days[day]]
        scored.sort(key=lambda x: -x[0])
        sbd[day] = scored
    scored_by_day[cfg] = sbd

def board_pool(cfg, kind):
    sbd = scored_by_day[cfg]
    pool = []
    for day in day_list:
        scored = sbd[day]
        if kind == "top3": sel = scored[:3]
        elif kind == "top10": sel = scored[:10]
        elif kind == "elite6": sel = [sp for sp in scored if sp[0] >= 70][:6]
        elif kind == "bestbets70": sel = [sp for sp in scored if sp[0] >= 70]
        elif kind == "ge60": sel = [sp for sp in scored if sp[0] >= 60]
        elif kind == "ge70": sel = [sp for sp in scored if sp[0] >= 70]
        elif kind == "ge80": sel = [sp for sp in scored if sp[0] >= 80]
        else: sel = scored
        pool.extend(sel)
    return pool

BOARD_KINDS = ["top3", "elite6", "top10", "bestbets70", "ge60", "ge70", "ge80"]
results = {}
for cfg in CONFIGS:
    results[cfg] = {}
    for kind in BOARD_KINDS:
        pool = board_pool(cfg, kind)
        results[cfg][kind] = wl(pool)
        results[cfg][kind]["aces_subset"] = wl([sp for sp in pool if sp[1]["category"] == "aces"])

with open('/tmp/aces_hybrid_result.json', 'w') as f:
    json.dump(results, f, indent=1, default=str)

print("DONE")
for cfg in CONFIGS:
    print("===", cfg, "===")
    for kind in BOARD_KINDS:
        r = results[cfg][kind]
        a = r["aces_subset"]
        print(f"  {kind}: n={r['n_picks']} wr={r['win_rate_pct']} roi={r['roi_pct']} u={r['net_units']} | aces: n={a['n_picks']} wr={a['win_rate_pct']} roi={a['roi_pct']} u={a['net_units']}")
