"""
APEX-ACESBAND-2026-10-07 (owner, requested)

Tests whether Aces' category-wide calibration penalty is too coarse by
replacing it with a probability-band-specific calibration, Aces only, all
other categories completely unchanged -- then replays Top1/Top3/Top6/
Elite6/Best Bets under both versions.

READ-ONLY. Does not modify apex_edge_tracker.py or any production file.
The band-specific version lives entirely in this script's own
alt_apex_score() function; production's apex_score() is also called
unmodified for the "current production" side of every comparison.

Run from the same directory as apex_monitoring_pipeline.py:
    python3 apex_aces_band_calibration_study.py > /tmp/apex_aces_band_output.json
"""
import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

GATE = aet.CATEGORY_PROBABILITY_GATE
RISK, WIN = 1.1, 1.0
BREAK_EVEN = aet.BREAK_EVEN
_FIXED_CAL_MANUAL = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}
GLOBAL_BLEND_FRAC = 0.25
_GROUP_PRIOR = {"rate_model": 8.0, "sim_derived": 3.0, "total_games": -8.0}

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

# ===========================================================================
# STEP 1: Aces band analysis (ALL settled Aces picks, ungated)
# ===========================================================================
aces_all = [p for p in all_picks if p["category"] == "aces"]
BANDS = [(50, 60), (60, 70), (70, 80), (80, 101)]
aces_band_stats = {}
band_cal = {}  # label -> (n, avg_prob, actual_rate, cal_pts)
for lo, hi in BANDS:
    label = f"{lo}-{hi-1}%" if hi <= 100 else f"{lo}%+"
    sub = [p for p in aces_all if lo <= p["prob"] * 100 < hi]
    stats = wl(sub)
    decided = [p for p in sub if p["hit"] is not None]
    avg_prob = round(sum(p["prob"] for p in decided) / len(decided) * 100, 2) if decided else None
    actual_rate = stats["win_rate"]
    cal_gap = round(actual_rate - avg_prob, 2) if (actual_rate is not None and avg_prob is not None) else None
    stats["expected_win_rate_pct"] = avg_prob
    stats["actual_win_rate_pct"] = actual_rate
    stats["calibration_gap_pts"] = cal_gap
    aces_band_stats[label] = stats
    n_band = len(decided)
    cal_pts_band = round((actual_rate / 100.0) - (avg_prob / 100.0), 4) if (actual_rate is not None and avg_prob is not None) else None
    band_cal[label] = {"n": n_band, "avg_prob": (avg_prob / 100.0) if avg_prob is not None else None,
                        "actual_rate": (actual_rate / 100.0) if actual_rate is not None else None,
                        "cal_pts": cal_pts_band}

# ===========================================================================
# STEP 2: current category-wide penalty, shown applied identically to every band
# ===========================================================================
aces_cs = rec["cats"].get("aces") or {"n": 0, "cal_pts": None}
aces_n = aces_cs["n"]; aces_w = min(aces_n / 25.0, 1.0)
if aces_n >= 5 and aces_cs.get("cal_pts") is not None:
    _scale = aces_cs["cal_pts"] / 0.10
    aces_ev_calibrated_categorywide = (30.0 if _scale < 0 else 20.0) * aces_w * max(-1.5, min(1.0, _scale))
else:
    aces_ev_calibrated_categorywide = 0.0
aces_ev_categorywide = aces_ev_calibrated_categorywide + GLOBAL_BLEND_FRAC * (_FIXED_CAL_MANUAL["aces"] - aces_ev_calibrated_categorywide)

step2 = {
    "category_wide_cal_pts_all_aces": round(aces_cs.get("cal_pts") or 0.0, 4),
    "category_wide_n": aces_n,
    "category_wide_ev_calibrated": round(aces_ev_calibrated_categorywide, 2),
    "category_wide_final_ev_applied_to_every_band": round(aces_ev_categorywide, 2),
    "note": "This single EV number is added to EVERY Aces pick's score today, regardless of band -- confirmed by construction (ev depends only on category, not probability).",
    "band_specific_calibration_if_used_instead": {},
}
for label, bc in band_cal.items():
    if bc["n"] >= 5 and bc["cal_pts"] is not None:
        scale = bc["cal_pts"] / 0.10
        ev_cal_band = (30.0 if scale < 0 else 20.0) * min(bc["n"] / 25.0, 1.0) * max(-1.5, min(1.0, scale))
    else:
        ev_cal_band = 0.0
    ev_band_final = ev_cal_band + GLOBAL_BLEND_FRAC * (_FIXED_CAL_MANUAL["aces"] - ev_cal_band)
    step2["band_specific_calibration_if_used_instead"][label] = {
        "n": bc["n"],
        "cal_pts": round(bc["cal_pts"], 4) if bc["cal_pts"] is not None else None,
        "ev_calibrated_band_specific": round(ev_cal_band, 2),
        "final_ev_band_specific": round(ev_band_final, 2),
        "diff_vs_category_wide_ev": round(ev_band_final - aces_ev_categorywide, 2),
    }

# ===========================================================================
# alt_apex_score: EXACT mirror of aet.apex_score(), except Aces' ev_calibrated
# is computed from the pick's OWN probability band instead of the whole
# category. Every other category's math is byte-identical to production.
# ===========================================================================
def band_label_for(prob_pct):
    for lo, hi in BANDS:
        if lo <= prob_pct < hi:
            return f"{lo}-{hi-1}%" if hi <= 100 else f"{lo}%+"
    return None

def alt_apex_score(prob, cat, bo5, rec):
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or {"n": 0, "cal_pts": None}
    n = cs["n"]; w = min(n / 25.0, 1.0)

    base = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN)))

    if cat == "aces":
        lbl = band_label_for(prob * 100)
        bc = band_cal.get(lbl) or {"n": 0, "cal_pts": None}
        if bc["n"] >= 5 and bc["cal_pts"] is not None:
            scale = bc["cal_pts"] / 0.10
            ev_calibrated = (30.0 if scale < 0 else 20.0) * min(bc["n"] / 25.0, 1.0) * max(-1.5, min(1.0, scale))
        else:
            ev_calibrated = 0.0
    else:
        if n >= 5 and cs.get("cal_pts") is not None:
            _cal_scale = cs["cal_pts"] / 0.10
            ev_calibrated = (30.0 if _cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, _cal_scale))
        else:
            ev_calibrated = 0.0
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)
    ev = ev_calibrated + GLOBAL_BLEND_FRAC * (ev_fixed_manual - ev_calibrated)
    score = base + ev

    g = aet.group_of(cat)
    prior_raw = _GROUP_PRIOR.get(g, 0.0)
    pr = prior_raw * (1.0 - w) * (0.5 if n < 5 else 1.0)
    score += pr

    if n >= 5:
        for name, blo, bhi in aet.BUCKETS:
            if blo <= prob < bhi:
                for bn, bw_, bl_, bstat in rec["buckets"]:
                    if bn == name and (bw_ + bl_) >= 3 and bstat:
                        br = bw_ / (bw_ + bl_)
                        score += 10.0 * min((bw_ + bl_) / 10.0, 1.0) * max(-1.0, min(1.0, (br - bstat) / 0.10))
                break

    lvl, _why = aet.attention(cat, prob, rec)
    if bo5:
        lvl = "LOW"
    score += {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0)

    return round(max(0.0, min(100.0, score)))

# sanity: for every non-aces category, alt_apex_score must exactly equal
# production apex_score (proves the mirror is faithful and isolates Aces
# as the only changed path).
sanity_mismatches = []
for p in all_picks[:300]:
    if p["category"] == "aces":
        continue
    prod_sc, *_ = aet.apex_score(p["prob"], p["category"], bool(p.get("bo5", False)), rec)
    alt_sc = alt_apex_score(p["prob"], p["category"], bool(p.get("bo5", False)), rec)
    if prod_sc != alt_sc:
        sanity_mismatches.append({"player": p["name"], "category": p["category"], "prod": prod_sc, "alt": alt_sc})

# ===========================================================================
# STEP 3: replay -- Method A (production apex_score) vs Method B (alt, band
# -specific Aces). Gate unchanged for both (current production floors).
# ===========================================================================
def qualify(score_fn):
    qualified = []
    for p in all_picks:
        cat = p["category"]
        prob = p.get("prob")
        floor = GATE.get(cat)
        gate_pass = not (floor is not None and (prob is None or float(prob) < floor))
        if not gate_pass:
            continue
        sc = score_fn(prob, cat, bool(p.get("bo5", False)), rec)
        qualified.append({"p": p, "prob": float(prob), "score": sc})
    return qualified

def prod_score_fn(prob, cat, bo5, rec):
    sc, *_ = aet.apex_score(prob, cat, bo5, rec)
    return sc

qual_A = qualify(prod_score_fn)
qual_B = qualify(alt_apex_score)

def days_of(qualified):
    d = {}
    for q in qualified:
        d.setdefault(q["p"]["match_date"], []).append(q)
    return d

days_A, days_B = days_of(qual_A), days_of(qual_B)
day_list = sorted(set(days_A) | set(days_B))

def topn_pool(days_map, day_list, n):
    pool = []
    for day in day_list:
        qs = days_map.get(day, [])
        pool.extend(sorted(qs, key=lambda q: -q["score"])[:n])
    return pool

def elite_style_pool(days_map, day_list, cutoff, cap):
    pool = []
    for day in day_list:
        qs = days_map.get(day, [])
        g = sorted(qs, key=lambda q: -q["score"])
        pool.extend([q for q in g if q["score"] >= cutoff][:cap])
    return pool

def bestbets_pool(days_map, day_list, cap):
    pool = []
    for day in day_list:
        qs = days_map.get(day, [])
        pool.extend(sorted(qs, key=lambda q: -q["score"])[:cap])
    return pool

boards = {}
for label, n in [("top1", 1), ("top3", 3), ("top6", 6)]:
    boards[label] = {
        "method_a_current_production": wl([q["p"] for q in topn_pool(days_A, day_list, n)]),
        "method_b_band_specific_aces": wl([q["p"] for q in topn_pool(days_B, day_list, n)]),
    }
boards["elite6"] = {
    "method_a_current_production": wl([q["p"] for q in elite_style_pool(days_A, day_list, 70, 6)]),
    "method_b_band_specific_aces": wl([q["p"] for q in elite_style_pool(days_B, day_list, 70, 6)]),
}
boards["bestbets15"] = {
    "method_a_current_production": wl([q["p"] for q in bestbets_pool(days_A, day_list, 15)]),
    "method_b_band_specific_aces": wl([q["p"] for q in bestbets_pool(days_B, day_list, 15)]),
}

# ===========================================================================
# how many Aces picks are reintroduced into ranks #4-6 under Method B?
# ===========================================================================
reintroduced = 0
reintroduced_detail = []
for day in day_list:
    qs_b = days_B.get(day, [])
    qs_a = days_A.get(day, [])
    if len(qs_b) < 4:
        continue
    pos456_b = sorted(qs_b, key=lambda q: -q["score"])[3:6]
    pos456_a_players = {q["p"]["name"] + q["p"]["match_date"] for q in sorted(qs_a, key=lambda q: -q["score"])[3:6]}
    for q in pos456_b:
        if q["p"]["category"] == "aces" and (q["p"]["name"] + q["p"]["match_date"]) not in pos456_a_players:
            reintroduced += 1
            reintroduced_detail.append({"match_date": day, "player": q["p"]["name"],
                                         "prob_pct": round(q["prob"] * 100, 1), "score": q["score"]})

output = {
    "note": (
        "READ-ONLY. Method B changes ONLY how Aces' calibrated-EV term is "
        "computed (per probability band instead of per category); the fixed "
        "manual constant (-11.2), the 25/75 blend weighting, gates, and every "
        "other category's math are byte-identical to production."
    ),
    "sanity_check_non_aces_categories_unchanged": {
        "checked": len([p for p in all_picks[:300] if p['category'] != 'aces']),
        "mismatches": len(sanity_mismatches),
        "detail": sanity_mismatches[:5],
    },
    "step1_aces_band_analysis": aces_band_stats,
    "step2_score_impact_analysis": step2,
    "step3_replay_boards": boards,
    "aces_reintroduced_into_ranks_4_6_under_band_specific": {
        "count": reintroduced,
        "detail": reintroduced_detail,
    },
}

with open("/tmp/apex_aces_band_output.json", "w") as f:
    json.dump(output, f, indent=1, default=str)
print(json.dumps(output, indent=1, default=str))
