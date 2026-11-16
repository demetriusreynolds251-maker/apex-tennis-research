import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

_f = aet._f
_norm = aet._norm
_tier = aet._tier
_read = aet._read
_parse_best_of_hand = aet._parse_best_of_hand
SIM_LOG, PICK_LOG, HAND_LOG = aet.SIM_LOG, aet.PICK_LOG, aet.HAND_LOG
BO5_CUTOFF = aet.BO5_CUTOFF

def settled_picks_prefix_bug(sim_log=SIM_LOG, pick_log=PICK_LOG, hand_log=HAND_LOG):
    """Reconstruction of settled_picks() using the OLD (pre-2026-10-07) join key,
    i.e. WITHOUT `line` in the key -- deliberately reproduces the bug for comparison.
    Does not touch the live production file."""
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

settled_pre = settled_picks_prefix_bug()
settled_post = aet.settled_picks()
print("PRE-FIX reconstructed n =", len(settled_pre))
print("POST-FIX live n =", len(settled_post))

CATS = ["aces", "dfs", "games_won", "fantasy_score", "breaks", "total_games", "total_sets", "tiebreaks"]
THRESH = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
RISK, PAY = 1.1, 1.0

def sweep(settled, label):
    print(f"=== {label} ===")
    results = {}
    for cat in CATS:
        cat_picks = [p for p in settled if p["category"] == cat and p["prob"] is not None and p["hit"] is not None]
        results[cat] = {}
        for t in THRESH:
            sub = [p for p in cat_picks if p["prob"] >= t]
            wins = sum(1 for p in sub if p["hit"] is True)
            losses = sum(1 for p in sub if p["hit"] is False)
            n = wins + losses
            wr = round(wins / n * 100, 2) if n else None
            units = round(wins * PAY - losses * RISK, 2)
            roi = round(units / (n * RISK) * 100, 2) if n else None
            results[cat][t] = {"n": n, "wr": wr, "roi": roi, "units": units}
        print(f"--- {cat} ---")
        for t in THRESH:
            r = results[cat][t]
            print(f"  {int(t*100)}+: n={r['n']} wr={r['wr']} roi={r['roi']} units={r['units']}")
    return results

pre_results = sweep(settled_pre, "PRE-FIX (reconstructed)")
post_results = sweep(settled_post, "POST-FIX (live)")

with open('/tmp/prepost_compare.json', 'w') as f:
    json.dump({"pre": pre_results, "post": post_results}, f, indent=1, default=str)
print("DONE")
