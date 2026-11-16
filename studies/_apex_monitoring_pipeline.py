import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet
from collections import defaultdict, Counter
from datetime import date, timedelta

settled = aet.settled_picks()
rec = aet.records()
GATE = aet.CATEGORY_PROBABILITY_GATE
CAT_ORDER = ["aces", "dfs", "breaks", "fantasy_score", "games_won", "total_games", "total_sets", "tiebreaks"]
RISK, WIN = 1.1, 1.0

all_picks = [p for p in settled if p["prob"] is not None and p.get("match_date") and p.get("hit") is not None]
today = max(p["match_date"] for p in all_picks)
today_d = date.fromisoformat(today)

def in_window(d, days):
    if days is None:
        return True
    dd = date.fromisoformat(d)
    return (today_d - dd).days < days

WINDOWS = {"daily": 1, "7day": 7, "14day": 14, "30day": 30, "all_time": None}

def wl(subset):
    wins = sum(1 for p in subset if p["hit"] is True)
    losses = sum(1 for p in subset if p["hit"] is False)
    pushes = sum(1 for p in subset if p["hit"] is None)
    n = wins + losses
    net = round(wins * WIN - losses * RISK, 2)
    wr = round(wins / n * 100, 2) if n else None
    roi = round(net / (n * RISK) * 100, 2) if n else None
    avg_prob = round(sum((p["prob"] or 0) for p in subset) / len(subset) * 100, 1) if subset else None
    return {"picks": len(subset), "wins": wins, "losses": losses, "pushes": pushes,
            "win_rate": wr, "roi": roi, "net_units": net, "avg_probability": avg_prob}

# ============================================================ TASK 1: GLOBAL
global_perf = {}
for wname, wdays in WINDOWS.items():
    subset = [p for p in all_picks if in_window(p["match_date"], wdays)]
    global_perf[wname] = wl(subset)

# ======================================================= BOARD RECONSTRUCTION
# Re-simulate every settled day's board using the LIVE (patched, Global 25% +
# category-gate) apex_score(), exactly as production currently scores. This
# is the only faithful way to get board membership for historical dates,
# since the scoring formula changed today -- a literal historical snapshot
# would mix old and new scoring. Mixed Slip is excluded: its membership
# depends on same-day cross-board slip rules (category caps, same-match
# exclusion) that are not reconstructable from settlement history alone;
# it needs a live join against apex_bb_rank_log_v1.csv's slip_slot columns,
# flagged as a follow-up rather than approximated here.
days = defaultdict(list)
for p in all_picks:
    days[p["match_date"]].append(p)
day_list = sorted(days.keys())

scored_by_day = {}
rank_by_day = {}
for day in day_list:
    scored = []
    for p in days[day]:
        cat = p["category"]
        prob = p.get("prob")
        floor = GATE.get(cat)
        gate_pass = not (floor is not None and (prob is None or float(prob) < floor))
        sc, ev, lvl, up, down = aet.apex_score(prob, cat, bool(p.get("bo5", False)), rec)
        scored.append({"score": sc, "p": p, "gate_pass": gate_pass})
    # full-pool rank position (pre-gate), matches "Rank Performance" semantics:
    # where would this pick have landed by raw Apex Score among that day's picks
    full_rank = sorted(scored, key=lambda d: -d["score"])
    for i, d in enumerate(full_rank, 1):
        d["full_rank_pos"] = i
    gated = [d for d in scored if d["gate_pass"]]
    gated.sort(key=lambda d: -d["score"])
    scored_by_day[day] = {"all": scored, "gated": gated}

def board_pool(kind):
    pool = []
    per_day = []
    for day in day_list:
        g = scored_by_day[day]["gated"]
        if kind == "top3":
            sel = [d for d in g if d["score"] >= 70][:3]
        elif kind == "elite6":
            sel = [d for d in g if d["score"] >= 70][:6]
        elif kind == "top10":
            sel = g[:10]
        elif kind == "bestbets15":
            sel = g[:15]
        elif kind in ("goblin", "demon", "standard"):
            floor = {"goblin": 70, "demon": 60, "standard": 70}[kind]
            sel = [d for d in g if d["p"].get("prop_type") == kind and d["score"] >= floor][:6]
        else:
            raise ValueError(kind)
        pool.extend(sel)
        per_day.append(len(sel))
    return pool, per_day

BOARD_KINDS = ["top3", "elite6", "top10", "bestbets15", "goblin", "demon", "standard"]
BOARD_LABELS = {"top3": "Top 3", "elite6": "Elite 6", "top10": "Top 10", "bestbets15": "Best Bets",
                "goblin": "Goblin", "demon": "Demon", "standard": "Standard"}

def wl_scored(subset_scored):
    return wl([d["p"] for d in subset_scored])

# ============================================================ TASK 2: BOARDS
board_perf = {}
for kind in BOARD_KINDS:
    board_perf[kind] = {}
    for wname, wdays in WINDOWS.items():
        pool, per_day_all = board_pool(kind)
        pool_w = [d for d in pool if in_window(d["p"]["match_date"], wdays)]
        stats = wl_scored(pool_w)
        stats["avg_apex_score"] = round(sum(d["score"] for d in pool_w) / len(pool_w), 1) if pool_w else None
        days_w = [dd for dd in day_list if in_window(dd, wdays)]
        stats["avg_picks_per_day"] = round(len(pool_w) / len(days_w), 2) if days_w else None
        board_perf[kind][wname] = stats

# ================================================== TASK 3: BOARD COMPOSITION
board_composition = {}
for kind in BOARD_KINDS:
    pool, _ = board_pool(kind)
    comp = {}
    for cat in CAT_ORDER:
        sub = [d for d in pool if d["p"]["category"] == cat]
        if sub:
            comp[cat] = wl_scored(sub)
    board_composition[kind] = comp
    if comp:
        by_wr = {c: v["win_rate"] for c, v in comp.items() if v["win_rate"] is not None}
        by_roi = {c: v["roi"] for c, v in comp.items() if v["roi"] is not None}
        board_composition[kind + "_summary"] = {
            "strongest_category": max(by_wr, key=by_wr.get) if by_wr else None,
            "weakest_category": min(by_wr, key=by_wr.get) if by_wr else None,
            "most_profitable_category": max(by_roi, key=by_roi.get) if by_roi else None,
            "least_profitable_category": min(by_roi, key=by_roi.get) if by_roi else None,
        }

# ============================================== TASK 4: CONFIDENCE BUCKETS
BUCKETS = [(50, 55), (55, 60), (60, 65), (65, 70), (70, 75), (75, 80), (80, 85), (85, 101)]
confidence_buckets = {}
for lo, hi in BUCKETS:
    label = f"{lo}-{hi if hi <= 100 else 100}%" if hi <= 100 else f"{lo}%+"
    sub = [p for p in all_picks if p["prob"] is not None and lo <= p["prob"] * 100 < hi]
    stats = wl(sub)
    decided = stats["wins"] + stats["losses"]
    actual_wr = (stats["wins"] / decided) if decided else None
    midpoint = (lo + min(hi, 100)) / 2 / 100
    stats["calibration_gap_pts"] = round((actual_wr - midpoint) * 100, 1) if actual_wr is not None else None
    confidence_buckets[label] = stats

# ================================================== TASK 5: CATEGORY REPORT
category_report = {}
for cat in CAT_ORDER:
    category_report[cat] = {}
    for wname, wdays in WINDOWS.items():
        if wname == "daily":
            continue  # not meaningful per-category; skip to keep output compact
        sub = [p for p in all_picks if p["category"] == cat and in_window(p["match_date"], wdays)]
        stats = wl(sub)
        # avg apex score needs rescoring (not stored on settled_picks)
        if sub:
            scs = [aet.apex_score(p["prob"], cat, bool(p.get("bo5", False)), rec)[0] for p in sub]
            stats["avg_apex_score"] = round(sum(scs) / len(scs), 1)
        else:
            stats["avg_apex_score"] = None
        category_report[cat][wname] = stats

# =================================================== TASK 6: RANK PERFORMANCE
rank_perf = {}
for r in range(1, 11):
    picks_at_rank = []
    for day in day_list:
        full = scored_by_day[day]["all"]
        for d in full:
            if d["full_rank_pos"] == r:
                picks_at_rank.append(d["p"])
    rank_perf[str(r)] = wl(picks_at_rank)
# monotonicity check: win rate should not systematically improve as rank worsens
wrs = [rank_perf[str(r)]["win_rate"] for r in range(1, 11) if rank_perf[str(r)]["win_rate"] is not None]
rank_health_breaks = sum(1 for i in range(1, len(wrs)) if wrs[i] > wrs[i - 1] + 5)  # tolerant threshold
ranking_healthy = rank_health_breaks <= 2

# =================================================== TASK 7: GATE AUDIT
gate_audit = {}
for cat, floor in GATE.items():
    evaluated = [p for p in all_picks if p["category"] == cat and p["prob"] is not None]
    rejected = [p for p in evaluated if p["prob"] < floor]
    accepted_n = len(evaluated) - len(rejected)
    rej_stats = wl(rejected)
    gate_audit[cat] = {
        "floor_pct": round(floor * 100, 1),
        "picks_evaluated": len(evaluated),
        "picks_rejected": len(rejected),
        "picks_accepted": accepted_n,
        "rejection_rate_pct": round(len(rejected) / len(evaluated) * 100, 1) if evaluated else None,
        "win_rate_of_rejected": rej_stats["win_rate"],
        "roi_of_rejected": rej_stats["roi"],
        "verdict": (
            "HELPING -- rejected picks performed worse than break-even" if (rej_stats["roi"] is not None and rej_stats["roi"] < 0)
            else "HURTING -- rejected picks were actually profitable" if (rej_stats["roi"] is not None and rej_stats["roi"] > 0)
            else "INSUFFICIENT DATA"
        ),
    }

# =================================================== TASK 8: HEALTH ALERTS
alerts = []
for kind in BOARD_KINDS:
    wr30 = board_perf[kind]["30day"]["win_rate"]
    roi30 = board_perf[kind]["30day"]["roi"]
    if wr30 is not None and wr30 < 55:
        alerts.append(f"BOARD ALERT: {BOARD_LABELS[kind]} win rate {wr30}% (<55%) over 30 days")
    if roi30 is not None and roi30 < 0:
        alerts.append(f"BOARD ALERT: {BOARD_LABELS[kind]} ROI {roi30}% negative over 30 days")
for cat in CAT_ORDER:
    wr30 = category_report[cat]["30day"]["win_rate"]
    roi30 = category_report[cat]["30day"]["roi"]
    if wr30 is not None and wr30 < 55:
        alerts.append(f"CATEGORY ALERT: {cat} win rate {wr30}% (<55%) over 30 days")
    if roi30 is not None and roi30 < 0:
        alerts.append(f"CATEGORY ALERT: {cat} ROI {roi30}% negative over 30 days")
if not ranking_healthy:
    alerts.append(f"RANKING ALERT: rank-order breakdown detected ({rank_health_breaks} inversions >5pt)")
for label, b in confidence_buckets.items():
    gap = b.get("calibration_gap_pts")
    if gap is not None and abs(gap) > 5:
        alerts.append(f"CALIBRATION ALERT: {label} bucket off by {gap:+.1f}pts")

# ================================================ TASK 9: MONTHLY EXECUTIVE
all_board_wr = {k: board_perf[k]["30day"]["win_rate"] for k in BOARD_KINDS if board_perf[k]["30day"]["win_rate"] is not None}
all_board_roi = {k: board_perf[k]["30day"]["roi"] for k in BOARD_KINDS if board_perf[k]["30day"]["roi"] is not None}
all_cat_wr = {c: category_report[c]["30day"]["win_rate"] for c in CAT_ORDER if category_report[c]["30day"]["win_rate"] is not None}
all_cat_roi = {c: category_report[c]["30day"]["roi"] for c in CAT_ORDER if category_report[c]["30day"]["roi"] is not None}
bucket_wr = {k: v["win_rate"] for k, v in confidence_buckets.items() if v["win_rate"] is not None and v["picks"] >= 5}

deployment_score = 50
if global_perf["30day"]["win_rate"] and global_perf["30day"]["win_rate"] >= 60: deployment_score += 15
if global_perf["30day"]["roi"] and global_perf["30day"]["roi"] > 0: deployment_score += 15
if ranking_healthy: deployment_score += 10
if len(alerts) == 0: deployment_score += 10
deployment_score = max(0, min(100, deployment_score))

executive_summary = {
    "system_win_rate_30day": global_perf["30day"]["win_rate"],
    "system_roi_30day": global_perf["30day"]["roi"],
    "total_units_30day": global_perf["30day"]["net_units"],
    "total_units_all_time": global_perf["all_time"]["net_units"],
    "best_board": max(all_board_roi, key=all_board_roi.get) if all_board_roi else None,
    "worst_board": min(all_board_roi, key=all_board_roi.get) if all_board_roi else None,
    "best_category": max(all_cat_roi, key=all_cat_roi.get) if all_cat_roi else None,
    "worst_category": min(all_cat_roi, key=all_cat_roi.get) if all_cat_roi else None,
    "strongest_confidence_bucket": max(bucket_wr, key=bucket_wr.get) if bucket_wr else None,
    "weakest_confidence_bucket": min(bucket_wr, key=bucket_wr.get) if bucket_wr else None,
    "ranking_health": "HEALTHY" if ranking_healthy else "DEGRADED",
    "calibration_health": "HEALTHY" if not any("CALIBRATION" in a for a in alerts) else "NEEDS ATTENTION",
    "deployment_success_score": deployment_score,
}

output = {
    "generated_at": today,
    "today": today,
    "methodology_note": ("Board/category/rank figures are RE-SCORED against the live, patched "
                          "Global-25%-blend + category-gate apex_score() so historical and current "
                          "scoring are apples-to-apples. Mixed Slip is not included -- its membership "
                          "needs a live join against apex_bb_rank_log_v1.csv slip_slot columns, not "
                          "yet built."),
    "global_performance": global_perf,
    "board_performance": board_perf,
    "board_composition": board_composition,
    "confidence_buckets": confidence_buckets,
    "category_report": category_report,
    "rank_performance": rank_perf,
    "rank_health_breaks": rank_health_breaks,
    "gate_audit": gate_audit,
    "alerts": alerts,
    "executive_summary": executive_summary,
}

with open("/tmp/apex_monitoring_output.json", "w") as f:
    json.dump(output, f, indent=1, default=str)

print("DONE. picks:", len(all_picks), "days:", len(day_list), "today:", today)
print("alerts:", len(alerts))
for a in alerts:
    print(" -", a)
