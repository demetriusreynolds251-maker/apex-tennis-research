"""
APEX-SCOREVSPROB-2026-10-07 (owner, requested)

Historical replay: after a prop clears its category probability gate, is
Raw Probability or Apex Score the better ranking signal?

READ-ONLY. Does not touch apex_edge_tracker.py, CATEGORY_PROBABILITY_GATE,
or any production file or ranking path. Imports the live module purely to
reuse settled_picks() / records() / apex_score() and the production gate
dict, and re-derives "what Method A/B would have picked that day" entirely
in local lists.

Run from the same directory as apex_monitoring_pipeline.py:

    python3 apex_score_vs_probability_study.py > /tmp/apex_score_vs_prob_output.json
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

def topn_pools(n):
    pool_a, pool_b = [], []
    for day in day_list:
        day_qs = days[day]
        by_prob = sorted(day_qs, key=lambda q: -q["prob"])[:n]
        by_score = sorted(day_qs, key=lambda q: -q["score"])[:n]
        pool_a.extend(by_prob)
        pool_b.extend(by_score)
    return pool_a, pool_b

tests = {}
for n, label in [(1, "top1"), (3, "top3"), (6, "top6")]:
    pool_a, pool_b = topn_pools(n)
    tests[label] = {
        "method_a_probability": wl([q["p"] for q in pool_a]),
        "method_b_apex_score": wl([q["p"] for q in pool_b]),
    }

SCORE_BUCKETS = [(50, 60), (60, 70), (70, 80), (80, 90), (90, 10_000)]
score_buckets = {}
below_50 = [q for q in qualified if q["score"] < 50]
for lo, hi in SCORE_BUCKETS:
    label = f"{lo}-{hi-1}" if hi < 10_000 else f"{lo}+"
    sub = [q["p"] for q in qualified if lo <= q["score"] < hi]
    score_buckets[label] = wl(sub)
if below_50:
    score_buckets["below_50"] = wl([q["p"] for q in below_50])

PROB_BUCKETS = [(50, 60), (60, 70), (70, 80), (80, 101)]
prob_buckets = {}
for lo, hi in PROB_BUCKETS:
    label = f"{lo}-{hi-1}%" if hi <= 100 else f"{lo}%+"
    sub = [q["p"] for q in qualified if lo <= q["prob"] * 100 < hi]
    prob_buckets[label] = wl(sub)

def pearson_r(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return round(cov / (vx ** 0.5 * vy ** 0.5), 4)

decided = [q for q in qualified if q["p"]["hit"] is not None]
outcomes = [1.0 if q["p"]["hit"] else 0.0 for q in decided]
probs = [q["prob"] for q in decided]
scores = [q["score"] for q in decided]
corr = {
    "n": len(decided),
    "probability_vs_win_r": pearson_r(probs, outcomes),
    "apex_score_vs_win_r": pearson_r(scores, outcomes),
}

apex80 = [q["p"] for q in qualified if q["score"] >= 80]
prob80 = [q["p"] for q in qualified if q["prob"] >= 0.80]
head_to_head_80plus = {
    "apex_score_80_plus": wl(apex80),
    "probability_80pct_plus": wl(prob80),
}

def better_by_units(a_stats, b_stats, a_name, b_name):
    au = a_stats["net_units"] or 0
    bu = b_stats["net_units"] or 0
    if au == bu:
        return "TIE"
    return a_name if au > bu else b_name

answers = {
    "one_bet_per_day": better_by_units(
        tests["top1"]["method_a_probability"], tests["top1"]["method_b_apex_score"],
        "Highest Probability", "Highest Apex Score"
    ),
    "three_bets_per_day": better_by_units(
        tests["top3"]["method_a_probability"], tests["top3"]["method_b_apex_score"],
        "Top 3 Probability", "Top 3 Apex Score"
    ),
    "stronger_correlation_with_win": (
        "Probability" if (corr["probability_vs_win_r"] or 0) > (corr["apex_score_vs_win_r"] or 0)
        else "Apex Score" if (corr["apex_score_vs_win_r"] or 0) > (corr["probability_vs_win_r"] or 0)
        else "TIE"
    ),
    "apex80_outperforms_prob80": (
        (head_to_head_80plus["apex_score_80_plus"]["win_rate"] or 0)
        > (head_to_head_80plus["probability_80pct_plus"]["win_rate"] or 0)
    ),
}

output = {
    "note": (
        "READ-ONLY study. No production file or ranking path touched. "
        "'Gate-qualified' = passes current production CATEGORY_PROBABILITY_GATE "
        "floors, unchanged. Tests 1-3 pick per-day Top-N independently by each "
        "metric among that day's gate-qualified picks, then pool across all "
        "settled days. Units at RISK=1.1 / WIN=1.0, matching the monitoring "
        "dashboard and gate study."
    ),
    "test1_top1_per_day": tests["top1"],
    "test2_top3_per_day": tests["top3"],
    "test3_top6_per_day": tests["top6"],
    "test4_apex_score_buckets": score_buckets,
    "test5_probability_buckets": prob_buckets,
    "correlation_with_actual_win": corr,
    "test_apex80_vs_prob80": head_to_head_80plus,
    "answers": answers,
}

with open("/tmp/apex_score_vs_prob_output.json", "w") as f:
    json.dump(output, f, indent=1, default=str)

print(json.dumps(output, indent=1, default=str))
