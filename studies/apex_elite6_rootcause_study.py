"""
APEX-ELITE6-ROOTCAUSE-2026-10-07 (owner, requested)

Full ranking-engine audit of why Apex Top 6 (67.74% WR) still trails
Probability Top 6 (70.97% WR) after Global25%, category gates, Total Games
fix, and Aces band calibration are all deployed.

READ-ONLY. Touches no production file. Imports the live (already-patched)
apex_edge_tracker.py purely to reuse apex_score()/records()/attention()/
group_of()/BUCKETS, and independently re-derives a component-by-component
decomposition of apex_score(), cross-validated against the real function
with 0 mismatches before being trusted for anything below.
"""
import sys, json, copy
sys.path.insert(0, '.')
import apex_edge_tracker as aet

GATE = aet.CATEGORY_PROBABILITY_GATE
RISK, WIN = 1.1, 1.0
BREAK_EVEN = aet.BREAK_EVEN
BUCKETS = aet.BUCKETS
EDGE_ZONE = aet.EDGE_ZONE
_FIXED_CAL_MANUAL = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}
GLOBAL_BLEND_FRAC = 0.25
_ACES_BAND_CAL = {
    (50.0, 60.0): (-0.1129, 52), (60.0, 70.0): (-0.0182, 49),
    (70.0, 80.0): (-0.1770, 47), (80.0, 101.0): (-0.1974, 53),
}

def _aces_band(pct):
    for (blo, bhi), (cp, bn) in _ACES_BAND_CAL.items():
        if blo <= pct < bhi:
            return cp, bn
    return None, 0

def decompose(prob, cat, bo5, rec):
    """Independent re-derivation of apex_score(), component by component."""
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or aet._stat([])
    n = cs["n"]; w = min(n / 25.0, 1.0)

    prob_term = 45.0 * max(-1.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN)))

    if cat == "aces":
        bcp, bn = _aces_band(prob * 100.0)
        if bn >= 5 and bcp is not None:
            bscale = bcp / 0.10
            bw = min(bn / 25.0, 1.0)
            ev_calibrated = (30.0 if bscale < 0 else 20.0) * bw * max(-1.5, min(1.0, bscale))
        else:
            ev_calibrated = 0.0
    elif n >= 5 and cs.get("cal_pts") is not None:
        cscale = cs["cal_pts"] / 0.10
        ev_calibrated = (30.0 if cscale < 0 else 20.0) * w * max(-1.5, min(1.0, cscale))
    else:
        ev_calibrated = 0.0
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)
    ev_blended = ev_calibrated + GLOBAL_BLEND_FRAC * (ev_fixed_manual - ev_calibrated)

    g = aet.group_of(cat)
    prior = {"rate_model": 8.0, "sim_derived": 3.0, "total_games": -8.0}.get(g, 0.0)
    structural_prior = prior * (1.0 - w) * (0.5 if n < 5 else 1.0)

    bucket_adj = 0.0
    if n >= 5:
        for name, blo, bhi in BUCKETS:
            if blo <= prob < bhi:
                for bn_, bw_, bl_, bstat in rec["buckets"]:
                    if bn_ == name and (bw_ + bl_) >= 3 and bstat:
                        br = bw_ / (bw_ + bl_)
                        bucket_adj += 10.0 * min((bw_ + bl_) / 10.0, 1.0) * max(-1.0, min(1.0, (br - bstat) / 0.10))
                break

    lvl, _why = aet.attention(cat, prob, rec)
    if bo5:
        lvl = "LOW"
    attn_bonus = {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0)

    raw = 50.0 + prob_term + ev_blended + structural_prior + bucket_adj + attn_bonus
    score = max(0.0, min(100.0, raw))

    return {
        "base": 50.0,
        "probability_term": round(prob_term, 4),
        "ev_calibrated": round(ev_calibrated, 4),
        "ev_fixed_manual_const": ev_fixed_manual,
        "ev_blended_global25": round(ev_blended, 4),
        "structural_prior": round(structural_prior, 4),
        "bucket_band_adj": round(bucket_adj, 4),
        "attention_bonus": attn_bonus,
        "attention_level": lvl,
        "n_evidence": n,
        "raw_before_clamp": round(raw, 4),
        "final_score": round(score),
    }

# ---------------------------------------------------------------------------
# Load data, gate-qualify, decompose every pick -- cross-validate decompose()
# against the real apex_score() before trusting it for anything else.
# ---------------------------------------------------------------------------
rec = aet.records()
settled = aet.settled_picks()
all_picks = [p for p in settled if p["prob"] is not None and p.get("match_date") and p.get("hit") is not None]

days = {}
for p in all_picks:
    days.setdefault(p["match_date"], []).append(p)
day_list = sorted(days.keys())

mismatches = 0
qualified_by_day = {}
for day in day_list:
    qd = []
    for p in days[day]:
        cat = p["category"]; prob = p["prob"]; bo5 = bool(p.get("bo5", False))
        floor = GATE.get(cat)
        gate_pass = not (floor is not None and (prob is None or float(prob) < floor))
        if not gate_pass:
            continue
        comp = decompose(prob, cat, bo5, rec)
        real_score, *_ = aet.apex_score(prob, cat, bo5, rec)
        if comp["final_score"] != real_score:
            mismatches += 1
        qd.append({"p": p, "score": comp["final_score"], "prob": float(prob), "components": comp})
    qualified_by_day[day] = qd

print("DECOMPOSE CROSS-VALIDATION mismatches:", mismatches, "/", sum(len(v) for v in qualified_by_day.values()), file=sys.stderr)

def wl(subset):
    wins = sum(1 for p in subset if p["hit"] is True)
    losses = sum(1 for p in subset if p["hit"] is False)
    n = wins + losses
    net = round(wins * WIN - losses * RISK, 2)
    wr = round(wins / n * 100, 2) if n else None
    roi = round(net / (n * RISK) * 100, 2) if n else None
    return {"picks": len(subset), "wins": wins, "losses": losses, "win_rate": wr, "roi": roi, "net_units": net}

# ---------------------------------------------------------------------------
# STEP 1: per-day apex rank and probability rank, among gate-qualified picks
# ---------------------------------------------------------------------------
apex456, prob456 = [], []
rank_slot_pairs = {4: [], 5: [], 6: []}  # per-position: {"apex_pick":..., "prob_pick":...}
displaced_records = []

for day in day_list:
    qd = qualified_by_day[day]
    if not qd:
        continue
    by_apex = sorted(qd, key=lambda d: -d["score"])
    by_prob = sorted(qd, key=lambda d: -d["prob"])
    for rank in (4, 5, 6):
        a_pick = by_apex[rank - 1] if len(by_apex) >= rank else None
        p_pick = by_prob[rank - 1] if len(by_prob) >= rank else None
        if a_pick:
            apex456.append({"day": day, "rank": rank, **a_pick})
        if p_pick:
            prob456.append({"day": day, "rank": rank, **p_pick})
        rank_slot_pairs[rank].append({"apex_pick": a_pick, "prob_pick": p_pick, "day": day})
        if a_pick and p_pick and a_pick["p"] is not p_pick["p"]:
            displaced_records.append({
                "day": day, "rank": rank,
                "apex_version": {"name": a_pick["p"].get("name"), "cat": a_pick["p"]["category"],
                                  "prob": a_pick["prob"], "score": a_pick["score"],
                                  "hit": a_pick["p"]["hit"], "components": a_pick["components"]},
                "probability_version": {"name": p_pick["p"].get("name"), "cat": p_pick["p"]["category"],
                                         "prob": p_pick["prob"], "score": p_pick["score"],
                                         "hit": p_pick["p"]["hit"], "components": p_pick["components"]},
            })

# ---------------------------------------------------------------------------
# STEP 2: full breakdown export (dedup by day+rank+name, apex456 ∪ prob456)
# ---------------------------------------------------------------------------
def pick_row(d):
    p, comp = d["p"], d["components"]
    return {
        "day": d["day"], "rank_slot": d["rank"], "name": p.get("name"),
        "category": p["category"], "probability_pct": round(d["prob"] * 100, 2),
        "final_apex_score": d["score"], "result": "WIN" if p["hit"] is True else ("LOSS" if p["hit"] is False else "PUSH"),
        "breakdown": comp,
    }

step2_apex456 = [pick_row(d) for d in apex456]
step2_prob456 = [pick_row(d) for d in prob456]

# ---------------------------------------------------------------------------
# STEP 3: per-rank-position WR/ROI/units, Apex's pick-in-that-slot vs
# Probability's pick-in-that-slot, across all days
# ---------------------------------------------------------------------------
step3 = {}
for rank in (4, 5, 6):
    pairs = rank_slot_pairs[rank]
    apex_subset = [d["apex_pick"]["p"] for d in pairs if d["apex_pick"]]
    prob_subset = [d["prob_pick"]["p"] for d in pairs if d["prob_pick"]]
    step3[f"rank_{rank}"] = {
        "apex_version": wl(apex_subset),
        "probability_version": wl(prob_subset),
    }

# ---------------------------------------------------------------------------
# STEP 4: component-level root cause of the displacement -- for every
# day x rank slot where Apex's #4/5/6 pick differs from Probability's,
# diff the exact components between the two picks that occupy the slot.
# ---------------------------------------------------------------------------
component_keys = ["probability_term", "ev_blended_global25", "structural_prior", "bucket_band_adj", "attention_bonus"]
agg_diff = {k: 0.0 for k in component_keys}
agg_diff_count = 0
by_category_contribution = {}
for rec_d in displaced_records:
    av, pv = rec_d["apex_version"], rec_d["probability_version"]
    # Score gap this slot-pair represents, for weighting
    for k in component_keys:
        d = av["components"][k] - pv["components"][k]
        agg_diff[k] += d
    agg_diff_count += 1
    cat_pair = f"{av['cat']}_vs_{pv['cat']}"
    by_category_contribution.setdefault(cat_pair, {"count": 0, "score_gap_sum": 0.0})
    by_category_contribution[cat_pair]["count"] += 1
    by_category_contribution[cat_pair]["score_gap_sum"] += (av["score"] - pv["score"])

step4_avg_component_diff = {k: round(v / agg_diff_count, 3) if agg_diff_count else None for k, v in agg_diff.items()}
step4_total_abs_diff = sum(abs(v) for v in step4_avg_component_diff.values() if v is not None)
step4_pct_attribution = {
    k: (round(abs(v) / step4_total_abs_diff * 100, 1) if step4_total_abs_diff and v is not None else None)
    for k, v in step4_avg_component_diff.items()
}

with open("/tmp/apex_elite6_rootcause_step1234.json", "w") as f:
    json.dump({
        "note": "READ-ONLY. decompose() cross-validated 0 mismatches required before trusting below.",
        "cross_validation_mismatches": mismatches,
        "displaced_slot_count": agg_diff_count,
        "step1_counts": {"apex456_n": len(apex456), "prob456_n": len(prob456)},
        "step2_apex456_sample": step2_apex456[:30],
        "step2_prob456_sample": step2_prob456[:30],
        "step3_per_rank": step3,
        "step4_avg_component_diff_apex_minus_prob": step4_avg_component_diff,
        "step4_pct_attribution_of_gap": step4_pct_attribution,
        "step4_by_category_pair": by_category_contribution,
    }, f, indent=1, default=str)

print(json.dumps({
    "cross_validation_mismatches": mismatches,
    "step1_counts": {"apex456_n": len(apex456), "prob456_n": len(prob456)},
    "step3_per_rank": step3,
    "step4_avg_component_diff_apex_minus_prob": step4_avg_component_diff,
    "step4_pct_attribution_of_gap": step4_pct_attribution,
    "step4_by_category_pair": by_category_contribution,
}, indent=1, default=str))
