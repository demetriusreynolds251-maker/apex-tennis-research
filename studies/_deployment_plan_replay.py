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
THRESHOLDS = [60, 70, 80, 90]
CAT_ORDER = ["aces", "dfs", "breaks", "fantasy_score", "games_won", "total_games", "total_sets", "tiebreaks"]

# PROP-SPECIFIC CANDIDATE: A (0%) for every category except aces, which
# uses 0.75 toward B -- the one category with a strong, well-sampled
# (n=201) documented preference for blending toward B from the prior
# PROP-TYPE SENSITIVITY ANALYSIS. Every other category's own evidence
# favored 0% (A) individually.
PROP_SPECIFIC_FRAC = {
    "aces": 0.75, "dfs": 0.0, "breaks": 0.0, "fantasy_score": 0.0,
    "games_won": 0.0, "total_games": 0.0, "total_sets": 0.0, "tiebreaks": 0.0,
}

all_picks_raw = [p for p in settled if p["prob"] is not None]

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

def score_config(picks, mode):
    # mode: "B" (frac=1 all cats), "G25" (frac=0.25 all cats), "PS" (prop-specific)
    out = []
    for p in picks:
        cat = p["category"]
        if mode == "B":
            frac = 1.0
        elif mode == "G25":
            frac = 0.25
        else:
            frac = PROP_SPECIFIC_FRAC.get(cat, 0.0)
        s = _score(p["prob"], cat, p.get("bo5", False), rec, frac)
        out.append((s, p))
    return out

configs = {"B_current_production": "B", "Global_25pct": "G25", "Prop_Specific": "PS"}

overall_results = {}
cat_results = {}
for label, mode in configs.items():
    scored = score_config(all_picks_raw, mode)
    thresh = {}
    for t in THRESHOLDS:
        subset = [(s, p) for s, p in scored if s >= t]
        thresh[str(t)] = wl_stats(subset)
    overall_results[label] = thresh
    by_cat = {}
    for cat in CAT_ORDER:
        cat_scored = [(s, p) for s, p in scored if p["category"] == cat]
        cat_thresh = {}
        for t in THRESHOLDS:
            subset = [(s, p) for s, p in cat_scored if s >= t]
            cat_thresh[str(t)] = wl_stats(subset)
        by_cat[cat] = cat_thresh
    cat_results[label] = by_cat

with open('/tmp/deployment_plan_result.json', 'w') as f:
    json.dump({"overall": overall_results, "by_category": cat_results}, f, indent=1, default=str)

print("DONE")
for label in configs:
    row = overall_results[label]
    for t in ["60","70","80","90"]:
        r = row[t]
        print(label, t, r["n_picks"], r["win_rate_pct"], r["roi_pct"], r["net_units"])
