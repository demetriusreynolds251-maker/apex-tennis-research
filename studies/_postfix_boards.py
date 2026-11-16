import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet
from collections import defaultdict, Counter

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
CAT_ORDER = ["aces", "dfs", "breaks", "fantasy_score", "games_won", "total_games", "total_sets", "tiebreaks"]

all_picks_raw = [p for p in settled if p["prob"] is not None and p.get("match_date")]
print("TOTAL SETTLED PICKS (post-fix):", len(all_picks_raw))

def by_day(picks):
    d = defaultdict(list)
    for p in picks:
        d[p["match_date"]].append(p)
    return d

days = by_day(all_picks_raw)
day_list = sorted(days.keys())
print("DAYS:", len(day_list), day_list[0], "to", day_list[-1])

def wl_stats(subset):
    wins = sum(1 for s, p in subset if p["hit"] is True)
    losses = sum(1 for s, p in subset if p["hit"] is False)
    pushes = sum(1 for s, p in subset if p["hit"] is None)
    decided = wins + losses
    win_pct = round(wins / decided, 4) if decided else None
    net_units = round(wins * WIN_PAYOUT - losses * RISK_PER_PICK, 2)
    roi = round(net_units / (decided * RISK_PER_PICK), 4) if decided else None
    avg_score = round(sum(s for s, p in subset) / len(subset), 2) if subset else None
    avg_conf = round(sum(p["prob"] for s, p in subset) / len(subset) * 100, 2) if subset else None
    return {"n_picks": len(subset), "wins": wins, "losses": losses, "pushes": pushes,
            "win_rate_pct": round(win_pct * 100, 2) if win_pct is not None else None,
            "roi_pct": round(roi * 100, 2) if roi is not None else None,
            "net_units": net_units, "avg_score": avg_score, "avg_confidence_pct": avg_conf}

modes = {"B": 1.0, "G25": 0.25}
scored_by_day_by_mode = {}
for mode, frac_default in modes.items():
    scored_by_day = {}
    for day in day_list:
        picks = days[day]
        scored = [(_score(p["prob"], p["category"], p.get("bo5", False), rec, frac_default), p) for p in picks]
        scored.sort(key=lambda x: -x[0])
        scored_by_day[day] = scored
    scored_by_day_by_mode[mode] = scored_by_day

def board_pool(mode, kind):
    scored_by_day = scored_by_day_by_mode[mode]
    pool = []
    per_day_counts = []
    for day in day_list:
        scored = scored_by_day[day]
        if kind == "top3":
            sel = scored[:3]
        elif kind == "top5":
            sel = scored[:5]
        elif kind == "top10":
            sel = scored[:10]
        elif kind == "elite6":
            sel = [sp for sp in scored if sp[0] >= 70][:6]
        elif kind == "bestbets70":
            sel = [sp for sp in scored if sp[0] >= 70]
        elif kind == "demon_proxy":
            sel = [sp for sp in scored if 60 <= sp[0] < 70]
        else:
            sel = scored
        pool.extend(sel)
        per_day_counts.append(len(sel))
    return pool, per_day_counts

BOARD_KINDS = ["top3", "top5", "top10", "elite6", "bestbets70", "demon_proxy"]
BOARD_NAMES = {"top3": "Top 3", "top5": "Top 5", "top10": "Top 10", "elite6": "Elite 6 (score>=70, cap 6)",
               "bestbets70": "Daily Best Bets / Qualifying Board (score>=70, uncapped)",
               "demon_proxy": "Demon-tier proxy (score 60-69, uncapped)"}

def pick_key(p):
    return (p.get("name") or p.get("player"), p["category"], p["match_date"], p.get("line"), p.get("direction"))

results = {}
for kind in BOARD_KINDS:
    results[kind] = {}
    for mode in modes:
        pool, per_day = board_pool(mode, kind)
        stats = wl_stats(pool)
        stats["avg_picks_per_day"] = round(sum(per_day) / len(per_day), 2) if per_day else 0
        cat_counts = Counter(p["category"] for s, p in pool)
        stats["category_counts"] = dict(cat_counts)
        # per-category win/roi breakdown within this board
        cat_breakdown = {}
        for cat in CAT_ORDER:
            sub = [(s, p) for s, p in pool if p["category"] == cat]
            if sub:
                cat_breakdown[cat] = wl_stats(sub)
        stats["category_breakdown"] = cat_breakdown
        stats["pick_keys"] = set(pick_key(p) for s, p in pool)
        results[kind][mode] = stats

# overlap / retention between B and G25 per board
overlap = {}
for kind in BOARD_KINDS:
    bkeys = results[kind]["B"]["pick_keys"]
    gkeys = results[kind]["G25"]["pick_keys"]
    retained = bkeys & gkeys
    removed = bkeys - gkeys
    added = gkeys - bkeys
    overlap[kind] = {
        "retained": len(retained), "removed": len(removed), "added": len(added),
        "pct_retained": round(len(retained) / len(bkeys) * 100, 1) if bkeys else None,
    }
    del results[kind]["B"]["pick_keys"]
    del results[kind]["G25"]["pick_keys"]

with open('/tmp/postfix_boards_result.json', 'w') as f:
    json.dump({"results": results, "overlap": overlap}, f, indent=1, default=str)

print("DONE")
for kind in BOARD_KINDS:
    for mode in modes:
        r = results[kind][mode]
        print(BOARD_NAMES[kind], mode, "avg/day=", r["avg_picks_per_day"], "n=", r["n_picks"],
              "wr=", r["win_rate_pct"], "roi=", r["roi_pct"], "units=", r["net_units"],
              "avgscore=", r["avg_score"], "avgconf=", r["avg_confidence_pct"])
    print("  overlap:", overlap[kind])
    print()

print("=== ACES WITHIN ELITE6 / BESTBETS70 ===")
for kind in ["elite6", "bestbets70"]:
    for mode in modes:
        cb = results[kind][mode]["category_breakdown"].get("aces")
        print(kind, mode, "aces:", cb)
