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
print("TOTAL SETTLED PICKS (post-fix, live production data):", len(all_picks_raw))

def by_day(picks):
    d = defaultdict(list)
    for p in picks:
        d[p["match_date"]].append(p)
    return d

days = by_day(all_picks_raw)
day_list = sorted(days.keys())
print("DAYS:", len(day_list), day_list[0], "to", day_list[-1])

# ---- the 4 configurations under test ----
PROP_SPECIFIC_FRAC = {
    "aces": 0.75, "dfs": 0.0, "breaks": 0.0, "fantasy_score": 0.0,
    "games_won": 0.0, "total_games": 0.0, "total_sets": 0.0, "tiebreaks": 0.0,
}

def frac_for(cfg, cat):
    if cfg == "B":
        return 1.0
    if cfg == "G25":
        return 0.25
    if cfg == "G25_Aces625":
        return 0.625 if cat == "aces" else 0.25
    if cfg == "PropSpecific":
        return PROP_SPECIFIC_FRAC.get(cat, 0.0)
    raise ValueError(cfg)

CONFIGS = ["B", "G25", "G25_Aces625", "PropSpecific"]
CONFIG_LABELS = {
    "B": "Current Production (B)",
    "G25": "Global 25%",
    "G25_Aces625": "Global 25% + Aces 62.5%",
    "PropSpecific": "Prop-Specific",
}

def wl_stats(subset):
    wins = sum(1 for s, p in subset if p["hit"] is True)
    losses = sum(1 for s, p in subset if p["hit"] is False)
    pushes = sum(1 for s, p in subset if p["hit"] is None)
    decided = wins + losses
    win_pct = round(wins / decided, 4) if decided else None
    net_units = round(wins * WIN_PAYOUT - losses * RISK_PER_PICK, 2)
    roi = round(net_units / (decided * RISK_PER_PICK), 4) if decided else None
    return {"n_picks": len(subset), "wins": wins, "losses": losses, "pushes": pushes,
            "win_rate_pct": round(win_pct * 100, 2) if win_pct is not None else None,
            "roi_pct": round(roi * 100, 2) if roi is not None else None,
            "net_units": net_units}

# score every pick under every config, per day
scored_by_day_by_cfg = {}
for cfg in CONFIGS:
    sbd = {}
    for day in day_list:
        scored = [(_score(p["prob"], p["category"], p.get("bo5", False), rec, frac_for(cfg, p["category"])), p)
                   for p in days[day]]
        scored.sort(key=lambda x: -x[0])
        sbd[day] = scored
    scored_by_day_by_cfg[cfg] = sbd

def board_pool(cfg, kind):
    sbd = scored_by_day_by_cfg[cfg]
    pool = []
    per_day_counts = []
    for day in day_list:
        scored = sbd[day]
        if kind == "top3":
            sel = scored[:3]
        elif kind == "elite6":
            sel = [sp for sp in scored if sp[0] >= 70][:6]
        elif kind == "bestbets":
            sel = [sp for sp in scored if sp[0] >= 70]
        else:
            raise ValueError(kind)
        pool.extend(sel)
        per_day_counts.append(len(sel))
    return pool, per_day_counts

BOARD_KINDS = ["top3", "elite6", "bestbets"]
BOARD_LABELS = {"top3": "Top 3", "elite6": "Elite 6", "bestbets": "Best Bets (score>=70)"}

results = {}
for cfg in CONFIGS:
    results[cfg] = {}
    for kind in BOARD_KINDS:
        pool, per_day = board_pool(cfg, kind)
        stats = wl_stats(pool)
        stats["avg_picks_per_day"] = round(sum(per_day) / len(per_day), 3) if per_day else 0
        cat_counts = Counter(p["category"] for s, p in pool)
        total_n = len(pool)
        stats["category_composition_pct"] = {
            c: round(cat_counts.get(c, 0) / total_n * 100, 1) for c in CAT_ORDER if cat_counts.get(c, 0) > 0
        } if total_n else {}
        for focus_cat in ("aces", "total_games", "fantasy_score"):
            sub = [(s, p) for s, p in pool if p["category"] == focus_cat]
            stats[f"{focus_cat}_contribution"] = {
                "n": len(sub),
                "pct_of_board": round(len(sub) / total_n * 100, 1) if total_n else 0.0,
                **wl_stats(sub),
            } if sub else {"n": 0, "pct_of_board": 0.0}
        results[cfg][kind] = stats

with open('/tmp/final_championship_result.json', 'w') as f:
    json.dump(results, f, indent=1, default=str)

print("\n===== FINAL POST-FIX CHAMPIONSHIP REPLAY =====\n")
for cfg in CONFIGS:
    print(f"########## {CONFIG_LABELS[cfg]} ##########")
    for kind in BOARD_KINDS:
        r = results[cfg][kind]
        print(f"  [{BOARD_LABELS[kind]}] n={r['n_picks']} wr={r['win_rate_pct']}% roi={r['roi_pct']}% "
              f"units={r['net_units']} avg/day={r['avg_picks_per_day']}")
        print(f"      composition: {r['category_composition_pct']}")
        for fc in ("aces", "total_games", "fantasy_score"):
            c = r[f'{fc}_contribution']
            print(f"      {fc}: n={c.get('n')} pct={c.get('pct_of_board')} "
                  f"wr={c.get('win_rate_pct')} roi={c.get('roi_pct')} units={c.get('net_units')}")
    print()

print("DONE")
