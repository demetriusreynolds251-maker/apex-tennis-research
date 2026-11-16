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
FRAC_LABELS = [("A_0", 0.0), ("12.5pct", 0.125), ("25pct", 0.25), ("37.5pct", 0.375),
               ("50pct", 0.5), ("62.5pct", 0.625), ("75pct", 0.75), ("B_100", 1.0)]
THRESHOLDS = [60, 70, 80, 90]
CAT_ORDER = ["aces", "dfs", "breaks", "fantasy_score", "games_won", "total_games", "total_sets", "tiebreaks"]

# all settled picks with a valid prob; keep hit True/False/None(push) all together
# so pushes are counted at whichever threshold their score lands in
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

results = {}
for label, frac in FRAC_LABELS:
    scored = [( _score(p["prob"], p["category"], p.get("bo5", False), rec, frac), p) for p in all_picks_raw]
    overall_thresh = {}
    for t in THRESHOLDS:
        subset = [(s, p) for s, p in scored if s >= t]
        overall_thresh[str(t)] = wl_stats(subset)
    by_cat = {}
    for cat in CAT_ORDER:
        cat_scored = [(s, p) for s, p in scored if p["category"] == cat]
        cat_thresh = {}
        for t in THRESHOLDS:
            subset = [(s, p) for s, p in cat_scored if s >= t]
            cat_thresh[str(t)] = wl_stats(subset)
        by_cat[cat] = cat_thresh
    results[label] = {"frac": frac, "overall": overall_thresh, "by_category": by_cat}

with open('/tmp/confidence_threshold_result.json', 'w') as f:
    json.dump(results, f, indent=1, default=str)

print("DONE")
for label, frac in FRAC_LABELS:
    row = results[label]["overall"]
    print(label, {t: (row[t]["win_rate_pct"], row[t]["n_picks"], row[t]["roi_pct"]) for t in ["60","70","80","90"]})
