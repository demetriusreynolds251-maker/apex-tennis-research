"""
APEX-RANK456-ROOTCAUSE-2026-10-07 (owner, requested)

Root-cause the Top-6 crossover (Probability beats Apex Score at N=6) by
decomposing apex_score() into its exact components for every pick that
Apex Score ranked into positions #4-6 but Probability did not, paired
against the pick Probability ranked into #4-6 instead that same day.

READ-ONLY. Does not modify apex_edge_tracker.py. Re-derives apex_score()'s
own arithmetic component-by-component (base probability term, Global 25%
category blend, structural group prior, probability-band calibration
adjustment, attention bonus) using the SAME rec snapshot and SAME formula
as production, then cross-checks the sum against aet.apex_score()'s own
returned score for every pick -- if they don't match exactly, the script
says so rather than reporting unverified numbers.

Run from the same directory as apex_monitoring_pipeline.py:
    python3 apex_rank456_rootcause_study.py > /tmp/apex_rank456_rootcause_output.json
"""
import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

GATE = aet.CATEGORY_PROBABILITY_GATE
RISK, WIN = 1.1, 1.0
BREAK_EVEN = aet.BREAK_EVEN  # 0.542, verified against source

# Exact duplicate of the private _FIXED_CAL_MANUAL table inside apex_score()
# (read from apex_edge_tracker.py 2026-10-07; not importable, it's a local).
_FIXED_CAL_MANUAL = {
    "total_games":   8.1,
    "games_won":     2.1,
    "dfs":          -1.0,
    "fantasy_score": -1.6,
    "breaks":       -3.6,
    "aces":         -11.2,
}
GLOBAL_BLEND_FRAC = 0.25
_GROUP_PRIOR = {"rate_model": 8.0, "sim_derived": 3.0, "total_games": -8.0}

settled = aet.settled_picks()
rec = aet.records()
all_picks = [p for p in settled if p["prob"] is not None and p.get("match_date") and p.get("hit") is not None]

def decompose(prob, cat, bo5, rec):
    """Faithful re-derivation of apex_score()'s arithmetic, broken into
    named components. Returns (components_dict, recomputed_final_score)."""
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or {"n": 0, "cal_pts": None}
    n = cs["n"]
    w = min(n / 25.0, 1.0)

    base = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN)))

    if n >= 5 and cs.get("cal_pts") is not None:
        _cal_scale = cs["cal_pts"] / 0.10
        ev_calibrated = (30.0 if _cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, _cal_scale))
    else:
        ev_calibrated = 0.0
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)
    ev = ev_calibrated + GLOBAL_BLEND_FRAC * (ev_fixed_manual - ev_calibrated)

    g = aet.group_of(cat)
    prior_raw = _GROUP_PRIOR.get(g, 0.0)
    pr = prior_raw * (1.0 - w) * (0.5 if n < 5 else 1.0)

    band_adj = 0.0
    band_label = None
    if n >= 5:
        for name, blo, bhi in aet.BUCKETS:
            if blo <= prob < bhi:
                band_label = name
                for bn, bw_, bl_, bstat in rec["buckets"]:
                    if bn == name and (bw_ + bl_) >= 3 and bstat:
                        br = bw_ / (bw_ + bl_)
                        band_adj += 10.0 * min((bw_ + bl_) / 10.0, 1.0) * max(-1.0, min(1.0, (br - bstat) / 0.10))
                break

    lvl, why = aet.attention(cat, prob, rec)
    if bo5:
        lvl = "LOW"
    attn_bonus = {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0)

    raw_sum = base + ev + pr + band_adj + attn_bonus
    final = round(max(0.0, min(100.0, raw_sum)))

    components = {
        "n_evidence": n,
        "evidence_weight_w": round(w, 3),
        "base_probability_component": round(base, 2),
        "global25_category_blend_ev": round(ev, 2),
        "  of_which_calibrated_ev": round(ev_calibrated, 2),
        "  of_which_fixed_manual_const": ev_fixed_manual,
        "structural_group_prior": round(pr, 2),
        "  group": g,
        "  group_prior_raw_before_shrink": prior_raw,
        "probability_band_calibration_adj": round(band_adj, 2),
        "  band": band_label,
        "attention_bonus": attn_bonus,
        "  attention_level": lvl,
        "raw_sum_before_clip": round(raw_sum, 2),
        "recomputed_final_score": final,
    }
    return components, final

qualified = []
mismatches = []
for p in all_picks:
    cat = p["category"]
    prob = p.get("prob")
    floor = GATE.get(cat)
    gate_pass = not (floor is not None and (prob is None or float(prob) < floor))
    if not gate_pass:
        continue
    sc, ev_label, lvl, up, down = aet.apex_score(prob, cat, bool(p.get("bo5", False)), rec)
    comps, recomputed = decompose(prob, cat, bool(p.get("bo5", False)), rec)
    if recomputed != sc:
        mismatches.append({"player": p["name"], "category": cat, "prob": prob,
                            "production_score": sc, "recomputed_score": recomputed})
    qualified.append({"p": p, "prob": float(prob), "score": sc, "components": comps})

days = {}
for q in qualified:
    days.setdefault(q["p"]["match_date"], []).append(q)
day_list = sorted(days.keys())

# ---------------------------------------------------------------------------
# STEP 1 + 2: displaced pairs, per day
# ---------------------------------------------------------------------------
displaced_pairs = []
for day in day_list:
    day_qs = days[day]
    if len(day_qs) < 4:
        continue
    by_score = sorted(day_qs, key=lambda q: -q["score"])
    by_prob = sorted(day_qs, key=lambda q: -q["prob"])
    apex456 = by_score[3:6]
    prob456 = by_prob[3:6]
    apex456_ids = {id(q) for q in apex456}
    prob456_ids = {id(q) for q in prob456}
    apex_only = [q for q in apex456 if id(q) not in prob456_ids]
    prob_only = [q for q in prob456 if id(q) not in apex456_ids]
    # pair positionally: apex_only sorted by score desc, prob_only sorted by prob desc
    apex_only.sort(key=lambda q: -q["score"])
    prob_only.sort(key=lambda q: -q["prob"])
    for i in range(max(len(apex_only), len(prob_only))):
        a = apex_only[i] if i < len(apex_only) else None
        b = prob_only[i] if i < len(prob_only) else None
        displaced_pairs.append({"match_date": day, "apex_side": a, "prob_side": b})

def pick_summary(q):
    if q is None:
        return None
    p = q["p"]
    return {
        "match": "%s vs %s" % (p.get("name"), p.get("opponent")),
        "player": p.get("name"),
        "category": p.get("category"),
        "line": p.get("line"),
        "direction": p.get("direction"),
        "result": "WIN" if p.get("hit") is True else "LOSS" if p.get("hit") is False else "PUSH",
        "raw_probability_pct": round(q["prob"] * 100, 1),
        "final_apex_score": q["score"],
        "score_breakdown": q["components"],
    }

pairs_report = []
for pair in displaced_pairs:
    a, b = pair["apex_side"], pair["prob_side"]
    entry = {
        "match_date": pair["match_date"],
        "apex_ranked_this_into_4_6": pick_summary(a),
        "probability_ranked_this_into_4_6_instead": pick_summary(b),
    }
    if a is not None and b is not None:
        ac, bc = a["components"], b["components"]
        entry["why_apex_ranked_its_pick_higher"] = {
            "score_gap_apex_minus_prob_side": a["score"] - b["score"],
            "base_probability_component_diff": round(ac["base_probability_component"] - bc["base_probability_component"], 2),
            "global25_category_blend_diff": round(ac["global25_category_blend_ev"] - bc["global25_category_blend_ev"], 2),
            "structural_group_prior_diff": round(ac["structural_group_prior"] - bc["structural_group_prior"], 2),
            "probability_band_adj_diff": round(ac["probability_band_calibration_adj"] - bc["probability_band_calibration_adj"], 2),
            "attention_bonus_diff": round(ac["attention_bonus"] - bc["attention_bonus"], 2),
        }
    pairs_report.append(entry)

# ---------------------------------------------------------------------------
# STEP 4: aggregate displaced-pick category counts
# ---------------------------------------------------------------------------
CATS = ["aces", "dfs", "games_won", "fantasy_score", "breaks", "total_games", "total_sets", "tiebreaks"]
apex_side_cat_counts = {c: 0 for c in CATS}
prob_side_cat_counts = {c: 0 for c in CATS}
for pair in displaced_pairs:
    a, b = pair["apex_side"], pair["prob_side"]
    if a is not None:
        apex_side_cat_counts[a["p"]["category"]] = apex_side_cat_counts.get(a["p"]["category"], 0) + 1
    if b is not None:
        prob_side_cat_counts[b["p"]["category"]] = prob_side_cat_counts.get(b["p"]["category"], 0) + 1

# ---------------------------------------------------------------------------
# STEP 5: root-cause attribution -- average absolute contribution of each
# component to the score GAP across all complete pairs (both sides present).
# ---------------------------------------------------------------------------
complete_pairs = [p for p in pairs_report if p["apex_ranked_this_into_4_6"] and p["probability_ranked_this_into_4_6_instead"]]
component_keys = [
    ("base_probability_component_diff", "Base probability term"),
    ("global25_category_blend_diff", "Global 25% category blend (calibration + fixed manual)"),
    ("structural_group_prior_diff", "Structural group prior (rate-model/sim-derived/total-games)"),
    ("probability_band_adj_diff", "Probability-band calibration adjustment"),
    ("attention_bonus_diff", "Attention bonus"),
]
totals = {label: 0.0 for _, label in component_keys}
total_abs_gap = 0.0
for p in complete_pairs:
    w_ = p["why_apex_ranked_its_pick_higher"]
    for key, label in component_keys:
        totals[label] += abs(w_[key])
    total_abs_gap += sum(abs(w_[key]) for key, _ in component_keys)

attribution_pct = {}
if total_abs_gap > 0:
    for key, label in component_keys:
        attribution_pct[label] = round(totals[label] / total_abs_gap * 100, 1)

# aces-specific vs dfs-specific vs total_sets-specific share of the
# category-blend component specifically (the component the original
# hypothesis pointed at)
cat_blend_by_category_role = {"aces_suppression": 0.0, "dfs_inflation": 0.0, "total_sets_inflation": 0.0, "other": 0.0}
for p in complete_pairs:
    a = p["apex_ranked_this_into_4_6"]
    b = p["probability_ranked_this_into_4_6_instead"]
    diff = p["why_apex_ranked_its_pick_higher"]["global25_category_blend_diff"]
    # diff = apex_side blend - prob_side blend; attribute by which side is aces/dfs/total_sets
    if b["category"] == "aces":
        cat_blend_by_category_role["aces_suppression"] += abs(diff)
    elif a["category"] == "dfs":
        cat_blend_by_category_role["dfs_inflation"] += abs(diff)
    elif a["category"] == "total_sets":
        cat_blend_by_category_role["total_sets_inflation"] += abs(diff)
    else:
        cat_blend_by_category_role["other"] += abs(diff)
blend_total = sum(cat_blend_by_category_role.values())
cat_blend_pct = {k: (round(v / blend_total * 100, 1) if blend_total else None) for k, v in cat_blend_by_category_role.items()}

output = {
    "note": (
        "READ-ONLY root-cause study. Formula verification: every qualified "
        "pick's component sum was cross-checked against apex_edge_tracker's "
        "own apex_score() return value."
    ),
    "formula_verification": {
        "total_qualified_picks_checked": len(qualified),
        "mismatches_found": len(mismatches),
        "mismatch_detail": mismatches[:10],
    },
    "step1_2_displaced_pairs_count": len(displaced_pairs),
    "step1_2_displaced_pairs_detail": pairs_report,
    "step4_category_counts": {
        "apex_side_4_6_exclusive_picks_by_category": apex_side_cat_counts,
        "probability_side_4_6_exclusive_picks_by_category": prob_side_cat_counts,
    },
    "step5_root_cause_attribution_pct_of_total_abs_score_gap": attribution_pct,
    "step5_category_blend_component_breakdown_pct": cat_blend_pct,
}

with open("/tmp/apex_rank456_rootcause_output.json", "w") as f:
    json.dump(output, f, indent=1, default=str)
print(json.dumps(output, indent=1, default=str))
