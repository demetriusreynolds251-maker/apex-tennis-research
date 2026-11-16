import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet
from collections import defaultdict

_f = aet._f; _norm = aet._norm; _tier = aet._tier; _read = aet._read
_parse_best_of_hand = aet._parse_best_of_hand
SIM_LOG, PICK_LOG, HAND_LOG = aet.SIM_LOG, aet.PICK_LOG, aet.HAND_LOG

def settled_picks_prefix_bug(sim_log=SIM_LOG, pick_log=PICK_LOG, hand_log=HAND_LOG):
    out, keys, legacy_n = [], set(), 0
    picks = {(r.get("match_id"), _norm(r.get("player")), r.get("category")): r for r in _read(pick_log)}
    for r in _read(sim_log):
        if not r.get("actual") or not r.get("line"):
            continue
        line, actual = _f(r["line"]), _f(r["actual"])
        po, pu = _f(r.get("p_over")) or 0.0, _f(r.get("p_under")) or 0.0
        pk = picks.get((r.get("match_id"), _norm(r.get("player")), r.get("category")))
        if pk and pk.get("direction") in ("MORE", "LESS"):
            direction, prob, tier = pk["direction"], _f(pk.get("prob")), pk.get("tier")
        else:
            direction = "MORE" if po >= pu else "LESS"
            prob, tier = ((max(po, pu) / (po + pu)) if (po + pu) > 0 else None), None
        name = r.get("player") if r.get("player") != "match" else (r.get("opponent") or "").split(" v ")[0]
        d = {"source": "log", "match_date": r.get("match_date") or "", "settled_ts": r.get("settled_ts") or "",
             "name": name, "opponent": r.get("opponent"), "category": r["category"], "tier": _tier(r["category"], tier),
             "line": line, "direction": direction, "prob": prob, "actual": actual,
             "prop_type": ((pk or {}).get("prop_type") or "untyped").strip().lower()}
        d["bo5"] = str(r.get("best_of") or "").strip() in ("5", "5.0")
        d["hit"] = None if actual == line else ((actual > line) if direction == "MORE" else (actual < line))
        out.append(d)
        keys.add((r["category"], line, _norm(name)))
        for nm in (r.get("opponent") or "").split(" v "):
            keys.add((r["category"], line, _norm(nm)))
    for r in _read(hand_log):
        line, actual = _f(r.get("line")), _f(r.get("actual"))
        if line is None or actual is None:
            continue
        key = (r["category"], line, _norm(r.get("player")))
        if key in keys:
            continue
        d = {"source": r.get("source") or "hand", "match_date": r.get("match_date") or "", "settled_ts": "",
             "name": r.get("player"), "opponent": r.get("opponent"), "category": r["category"],
             "tier": _tier(r["category"], r.get("tier")), "line": line,
             "direction": (r.get("direction") or "MORE").upper(), "prob": _f(r.get("prob")), "actual": actual,
             "prop_type": (r.get("prop_type") or "untyped").strip().lower()}
        d["bo5"], _legacy = _parse_best_of_hand(r)
        legacy_n += 1 if _legacy else 0
        d["hit"] = None if actual == line else ((actual > line) if d["direction"] == "MORE" else (actual < line))
        out.append(d); keys.add(key)
    out.sort(key=lambda p: (p["match_date"], p["settled_ts"]))
    return out

BUCKETS = aet.BUCKETS
group_of = aet.group_of
attention = aet.attention
BE = aet.BREAK_EVEN
_FIXED_B = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}

def make_scorer(rec):
    def _ev_a(cat):
        cs = rec["cats"].get(cat) or {"n": 0, "cal_pts": None}
        n = cs.get("n", 0); w = min(n / 25.0, 1.0)
        if n >= 5 and cs.get("cal_pts") is not None:
            cal_scale = cs["cal_pts"] / 0.10
            return (30.0 if cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, cal_scale))
        return 0.0
    def _ev_b(cat):
        return _FIXED_B.get(cat, 0.0)
    def _score(prob, cat, bo5, frac):
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
    return _score

RISK, PAY = 1.1, 1.0

def wl_stats(subset):
    wins = sum(1 for s, p in subset if p["hit"] is True)
    losses = sum(1 for s, p in subset if p["hit"] is False)
    decided = wins + losses
    net_units = round(wins * PAY - losses * RISK, 2)
    roi = round(net_units / (decided * RISK) * 100, 2) if decided else None
    wr = round(wins / decided * 100, 2) if decided else None
    return {"n_picks": len(subset), "wins": wins, "losses": losses,
            "win_rate_pct": wr, "roi_pct": roi, "net_units": net_units}

def run_for(settled, label):
    rec = aet.records(settled)
    score_fn = make_scorer(rec)
    all_picks = [p for p in settled if p["prob"] is not None and p.get("match_date")]
    days = defaultdict(list)
    for p in all_picks:
        days[p["match_date"]].append(p)
    day_list = sorted(days.keys())
    modes = {"B": 1.0, "G25": 0.25}
    scored_by_mode = {}
    for mode, frac in modes.items():
        sbd = {}
        for day in day_list:
            scored = [(score_fn(p["prob"], p["category"], p.get("bo5", False), frac), p) for p in days[day]]
            scored.sort(key=lambda x: -x[0])
            sbd[day] = scored
        scored_by_mode[mode] = sbd

    def pool_for(mode, kind):
        sbd = scored_by_mode[mode]
        pool = []
        for day in day_list:
            scored = sbd[day]
            if kind == "top3": sel = scored[:3]
            elif kind == "elite6": sel = [sp for sp in scored if sp[0] >= 70][:6]
            elif kind == "bestbets70": sel = [sp for sp in scored if sp[0] >= 70]
            else: sel = scored
            pool.extend(sel)
        return pool

    out = {}
    for kind in ["top3", "elite6", "bestbets70"]:
        out[kind] = {}
        for mode in modes:
            out[kind][mode] = wl_stats(pool_for(mode, kind))
    print(f"=== {label} ===")
    for kind in ["top3", "elite6", "bestbets70"]:
        for mode in modes:
            r = out[kind][mode]
            print(f"  {kind:12s} {mode:4s} n={r['n_picks']:4d} wr={r['win_rate_pct']} roi={r['roi_pct']} units={r['net_units']}")
    return out

pre_settled = settled_picks_prefix_bug()
post_settled = aet.settled_picks()

pre_out = run_for(pre_settled, "PRE-FIX boards")
post_out = run_for(post_settled, "POST-FIX boards")

with open('/tmp/prepost_boards.json', 'w') as f:
    json.dump({"pre": pre_out, "post": post_out}, f, indent=1, default=str)
print("DONE")
