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

CATS = ["aces","dfs","games_won","fantasy_score","breaks","total_games","total_sets","tiebreaks"]
THRESH = [0.50,0.55,0.60,0.65,0.70,0.75,0.80]

def wl(subset):
    wins = sum(1 for p in subset if p["hit"] is True)
    losses = sum(1 for p in subset if p["hit"] is False)
    n = wins+losses
    wr = round(wins/n*100,2) if n else None
    net = round(wins*1.0 - losses*1.1,2)
    roi = round(net/(n*1.1)*100,2) if n else None
    return {"n":n,"wr":wr,"roi":roi,"units":net}

out = {"thresholds": {}}
for cat in CATS:
    picks = [p for p in settled if p["category"]==cat and p["prob"] is not None and p["hit"] is not None]
    row = {}
    for t in THRESH:
        sub = [p for p in picks if p["prob"] >= t]
        row[str(int(t*100))] = wl(sub)
    out["thresholds"][cat] = {"total_decided": len(picks), "by_thresh": row}

with open('/tmp/postfix_thresholds.json','w') as f:
    json.dump(out, f, indent=1, default=str)

print("=== POST-FIX RAW PROBABILITY THRESHOLDS ===")
for cat in CATS:
    d = out["thresholds"][cat]
    print(f"--- {cat} (total decided: {d['total_decided']}) ---")
    for t in THRESH:
        r = d["by_thresh"][str(int(t*100))]
        print(f"  {int(t*100)}+: n={r['n']} wr={r['wr']} roi={r['roi']} units={r['units']}")
