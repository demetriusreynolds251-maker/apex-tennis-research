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

def pid(p):
    return (p["name"], p["category"], p["match_date"], p["line"], p["direction"])

all_picks_raw = [p for p in settled if p["prob"] is not None and p.get("match_date")]
days = defaultdict(list)
for p in all_picks_raw:
    days[p["match_date"]].append(p)
day_list = sorted(days.keys())

modes = {"B": 1.0, "G25": 0.25}
scored_by_day = {}
for mode, frac in modes.items():
    sbd = {}
    for day in day_list:
        scored = [(_score(p["prob"], p["category"], p.get("bo5", False), rec, frac), p) for p in days[day]]
        scored.sort(key=lambda x: -x[0])
        sbd[day] = scored
    scored_by_day[mode] = sbd

def board_sel(mode, kind, day):
    scored = scored_by_day[mode][day]
    if kind == "top3": return scored[:3]
    if kind == "top10": return scored[:10]
    if kind == "elite6": return [sp for sp in scored if sp[0] >= 70][:6]
    if kind == "bestbets70": return [sp for sp in scored if sp[0] >= 70]
    return scored

def overlap_stats(kind):
    retained = removed = added = 0
    total_b = total_g = 0
    rank1_same = rank1_total = 0
    rank_match = {1:0,2:0,3:0}
    rank_total = {1:0,2:0,3:0}
    for day in day_list:
        b_sel = board_sel("B", kind, day)
        g_sel = board_sel("G25", kind, day)
        b_ids = [pid(p) for s,p in b_sel]
        g_ids = [pid(p) for s,p in g_sel]
        b_set, g_set = set(b_ids), set(g_ids)
        retained += len(b_set & g_set)
        removed += len(b_set - g_set)
        added += len(g_set - b_set)
        total_b += len(b_set)
        total_g += len(g_set)
        for r in [1,2,3]:
            if len(b_ids) >= r and len(g_ids) >= r:
                rank_total[r] += 1
                if b_ids[r-1] == g_ids[r-1]:
                    rank_match[r] += 1
    pct_retained = round(retained/total_b*100,1) if total_b else None
    pct_removed = round(removed/total_b*100,1) if total_b else None
    pct_added = round(added/total_g*100,1) if total_g else None
    rank_pct = {r: (round(rank_match[r]/rank_total[r]*100,1) if rank_total[r] else None) for r in [1,2,3]}
    return {"pct_retained_from_B": pct_retained, "pct_removed_from_B": pct_removed,
            "pct_new_in_G25": pct_added, "rank_match_pct": rank_pct,
            "total_b_picks": total_b, "total_g25_picks": total_g}

out = {}
for kind in ["top3","top10","elite6","bestbets70"]:
    out[kind] = overlap_stats(kind)

with open('/tmp/board_overlap_result.json','w') as f:
    json.dump(out, f, indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
