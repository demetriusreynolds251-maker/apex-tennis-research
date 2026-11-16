"""
APEX-RANK456-2026-10-07 (owner, requested)

Why does Probability overtake Apex Score exactly at Top 6/day? Isolate
positions #4, #5, #6 specifically (the picks that are IN the Top 6 pool but
NOT in the Top 3 pool) under each ranking method, among that day's
gate-qualified picks, and compare category mix / win rate / ROI / units.

READ-ONLY. No production file touched.

Run from the same directory as apex_monitoring_pipeline.py:
    python3 apex_rank456_crossover_study.py > /tmp/apex_rank456_output.json
"""
import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

GATE = aet.CATEGORY_PROBABILITY_GATE
RISK, WIN = 1.1, 1.0

settled = aet.settled_picks()
rec = aet.records()
all_picks = [p for p in settled if p["prob"] is not None and p.get("match_date") and p.get("hit") is not None]

def wl(subset):
    wins = sum(1 for p in subset if p["hit"] is True)
    losses = sum(1 for p in subset if p["hit"] is False)
    pushes = sum(1 for p in subset if p["hit"] is None)
    n = wins + losses
    net = round(wins * WIN - losses * RISK, 2)
    wr = round(wins / n * 100, 2) if n else None
    roi = round(net / (n * RISK) * 100, 2) if n else None
    return {"picks": len(subset), "wins": wins, "losses": losses, "pushes": pushes,
            "win_rate": wr, "roi": roi, "net_units": net}

qualified = []
for p in all_picks:
    cat = p["category"]
    prob = p.get("prob")
    floor = GATE.get(cat)
    gate_pass = not (floor is not None and (prob is None or float(prob) < floor))
    if not gate_pass:
        continue
    sc, ev, lvl, up, down = aet.apex_score(prob, cat, bool(p.get("bo5", False)), rec)
    qualified.append({"p": p, "prob": float(prob), "score": sc})

days = {}
for q in qualified:
    days.setdefault(q["p"]["match_date"], []).append(q)
day_list = sorted(days.keys())

# positions 4,5,6 (1-indexed) = python slice [3:6]
pos456_by_score = []
pos456_by_prob = []
pos123_by_score = []  # for comparison context
pos123_by_prob = []
for day in day_list:
    day_qs = days[day]
    by_score = sorted(day_qs, key=lambda q: -q["score"])
    by_prob = sorted(day_qs, key=lambda q: -q["prob"])
    pos456_by_score.extend(by_score[3:6])
    pos456_by_prob.extend(by_prob[3:6])
    pos123_by_score.extend(by_score[0:3])
    pos123_by_prob.extend(by_prob[0:3])

def category_breakdown(pool):
    cats = {}
    for q in pool:
        cat = q["p"]["category"]
        cats.setdefault(cat, []).append(q["p"])
    return {cat: {**wl(picks), "avg_prob_pct": round(sum(qq["prob"] for qq in pool if qq["p"] in picks and qq["p"]["category"]==cat)/len(picks)*100,1) if picks else None} for cat, picks in cats.items()}

# simpler/robust category breakdown (avoid the picks-in-list identity issue above)
def category_breakdown2(pool):
    by_cat = {}
    for q in pool:
        cat = q["p"]["category"]
        by_cat.setdefault(cat, []).append(q)
    out = {}
    for cat, qs in by_cat.items():
        picks = [q["p"] for q in qs]
        stats = wl(picks)
        stats["avg_prob_pct"] = round(sum(q["prob"] for q in qs) / len(qs) * 100, 1)
        stats["avg_apex_score"] = round(sum(q["score"] for q in qs) / len(qs), 1)
        out[cat] = stats
    return out

result = {
    "note": (
        "READ-ONLY. Positions #4-6 = picks ranked 4th, 5th, 6th that day by "
        "the given metric, among gate-qualified picks -- i.e. exactly the "
        "picks that Top 6 adds beyond Top 3. Positions #1-3 included for "
        "context (same as the Top 3 test). Units RISK=1.1/WIN=1.0."
    ),
    "positions_4_6": {
        "by_apex_score": {
            "overall": wl([q["p"] for q in pos456_by_score]),
            "category_breakdown": category_breakdown2(pos456_by_score),
        },
        "by_probability": {
            "overall": wl([q["p"] for q in pos456_by_prob]),
            "category_breakdown": category_breakdown2(pos456_by_prob),
        },
    },
    "positions_1_3_for_context": {
        "by_apex_score": {
            "overall": wl([q["p"] for q in pos123_by_score]),
            "category_breakdown": category_breakdown2(pos123_by_score),
        },
        "by_probability": {
            "overall": wl([q["p"] for q in pos123_by_prob]),
            "category_breakdown": category_breakdown2(pos123_by_prob),
        },
    },
}

with open("/tmp/apex_rank456_output.json", "w") as f:
    json.dump(result, f, indent=1, default=str)
print(json.dumps(result, indent=1, default=str))
