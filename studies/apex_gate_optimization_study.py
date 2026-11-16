"""
APEX-GATESTUDY-2026-10-07 (owner, requested)

Gate sensitivity study: for DFS, Fantasy Score, and Total Games -- the three
gates the monitoring dashboard flagged HURTING -- recompute win rate / ROI /
units at the Current floor, Current-5pts, and Current-10pts, and show the
knock-on impact on Top 3, Elite 6, and Best Bets 15 board membership.

READ-ONLY. Does not touch apex_edge_tracker.py, CATEGORY_PROBABILITY_GATE,
or any production file. It imports the live module purely to reuse its
settled_picks() / records() / apex_score() and re-derive board membership
under alternate gate dicts kept entirely local to this script.

Run from the same directory as apex_monitoring_pipeline.py (i.e. wherever
apex_edge_tracker.py importable), same as the daily monitoring job:

    python3 apex_gate_optimization_study.py > /tmp/apex_gate_study_output.json

Mirrors apex_monitoring_pipeline.py's board reconstruction methodology
exactly (full-pool rank -> gate filter -> score-descending -> board cutoffs)
so numbers are apples-to-apples with the monitoring dashboard already built.
"""
import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

PROD_GATE = aet.CATEGORY_PROBABILITY_GATE
RISK, WIN = 1.1, 1.0

settled = aet.settled_picks()
rec = aet.records()
all_picks = [p for p in settled if p["prob"] is not None and p.get("match_date") and p.get("hit") is not None]

days = {}
for p in all_picks:
    days.setdefault(p["match_date"], []).append(p)
day_list = sorted(days.keys())

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

def wl_scored(subset_scored):
    return wl([d["p"] for d in subset_scored])

def board_pool(kind, gate_dict):
    """Exact mirror of apex_monitoring_pipeline.board_pool(), parameterized
    on the gate dict instead of always reading the live production one."""
    pool = []
    for day in day_list:
        scored = []
        for p in days[day]:
            cat = p["category"]
            prob = p.get("prob")
            floor = gate_dict.get(cat)
            gate_pass = not (floor is not None and (prob is None or float(prob) < floor))
            sc, ev, lvl, up, down = aet.apex_score(prob, cat, bool(p.get("bo5", False)), rec)
            scored.append({"score": sc, "p": p, "gate_pass": gate_pass})
        gated = [d for d in scored if d["gate_pass"]]
        gated.sort(key=lambda d: -d["score"])
        if kind == "top3":
            sel = [d for d in gated if d["score"] >= 70][:3]
        elif kind == "elite6":
            sel = [d for d in gated if d["score"] >= 70][:6]
        elif kind == "bestbets15":
            sel = gated[:15]
        else:
            raise ValueError(kind)
        pool.extend(sel)
    return pool

BOARDS = ["top3", "elite6", "bestbets15"]
BOARD_LABEL = {"top3": "Top 3", "elite6": "Elite 6", "bestbets15": "Best Bets 15"}

# ---------------------------------------------------------------------------
# Scenario definitions: current production floor, -5pts, -10pts, per category
# (expressed as probability fractions, matching CATEGORY_PROBABILITY_GATE's
# own units -- 0.60 == 60%).
# ---------------------------------------------------------------------------
SCENARIOS = {
    "dfs": {
        "current": PROD_GATE["dfs"],
        "floor_minus_5": PROD_GATE["dfs"] - 0.05,
        "floor_minus_10": PROD_GATE["dfs"] - 0.10,
    },
    "fantasy_score": {
        "current": PROD_GATE["fantasy_score"],
        "floor_minus_5": PROD_GATE["fantasy_score"] - 0.05,
        "floor_minus_10": PROD_GATE["fantasy_score"] - 0.10,
    },
    "total_games": {
        "current": PROD_GATE["total_games"],
        "floor_minus_10": PROD_GATE["total_games"] - 0.10,
        "floor_minus_5": PROD_GATE["total_games"] - 0.05,
    },
}

results = {}
for cat, variants in SCENARIOS.items():
    results[cat] = {}
    for variant_name, floor in variants.items():
        # category-level stats at this floor (picks that WOULD pass the gate)
        cat_subset = [p for p in all_picks if p["category"] == cat and p["prob"] is not None and p["prob"] >= floor]
        cat_stats = wl(cat_subset)

        # board impact: swap only this category's floor, leave the other
        # seven gates at their production values
        variant_gate = dict(PROD_GATE)
        variant_gate[cat] = floor

        board_stats = {}
        for kind in BOARDS:
            pool = board_pool(kind, variant_gate)
            board_stats[kind] = wl_scored(pool)

        results[cat][variant_name] = {
            "floor_pct": round(floor * 100, 1),
            "category": cat_stats,
            "boards": board_stats,
        }

# ---------------------------------------------------------------------------
# Recommendation pass: for each category, score each floor on the four
# target metrics (Elite 6 WR, Elite 6 ROI, Top 3 WR, Top 3 ROI), then check
# whether the unit swing vs current production is a net gain or a net loss
# across Top 3 + Elite 6 + Best Bets 15 combined.
# ---------------------------------------------------------------------------
recommendation = {}
for cat, variants in results.items():
    baseline = variants["current"]
    rows = []
    for variant_name, v in variants.items():
        e6, t3, bb = v["boards"]["elite6"], v["boards"]["top3"], v["boards"]["bestbets15"]
        units_combined = (e6["net_units"] or 0) + (t3["net_units"] or 0) + (bb["net_units"] or 0)
        base_units_combined = (
            (baseline["boards"]["elite6"]["net_units"] or 0)
            + (baseline["boards"]["top3"]["net_units"] or 0)
            + (baseline["boards"]["bestbets15"]["net_units"] or 0)
        )
        rows.append({
            "variant": variant_name,
            "floor_pct": v["floor_pct"],
            "elite6_wr": e6["win_rate"],
            "elite6_roi": e6["roi"],
            "top3_wr": t3["win_rate"],
            "top3_roi": t3["roi"],
            "units_combined_top3_elite6_bestbets15": round(units_combined, 2),
            "unit_delta_vs_current": round(units_combined - base_units_combined, 2),
        })
    recommendation[cat] = rows

output = {
    "note": (
        "READ-ONLY study. No production file touched. Board figures use the "
        "monitoring dashboard's own re-score methodology (full-pool rank -> "
        "gate -> score-descending -> board cutoffs) so these are directly "
        "comparable to the dashboard. Sample sizes shrink fast once a gate "
        "is loosened and flows into Top 3 / Elite 6 -- read win_rate/roi "
        "together with picks count, not alone."
    ),
    "scenarios": results,
    "recommendation_rows": recommendation,
}

with open("/tmp/apex_gate_study_output.json", "w") as f:
    json.dump(output, f, indent=1, default=str)

print(json.dumps(output, indent=1, default=str))
