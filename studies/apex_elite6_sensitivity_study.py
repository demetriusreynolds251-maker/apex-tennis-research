"""
APEX-ELITE6-SENSITIVITY-2026-10-07 (owner, requested)
STEP 5 of the Elite-6 root-cause mission: scale each scoring component
+-10% independently (holding all others at production value, Aces band
calibration always enabled) and replay Top3 / Top6 / Elite6.

READ-ONLY. No production file touched.
"""
import sys, json
sys.path.insert(0, '.')
import apex_edge_tracker as aet

GATE = aet.CATEGORY_PROBABILITY_GATE
RISK, WIN = 1.1, 1.0
BREAK_EVEN = aet.BREAK_EVEN
BUCKETS = aet.BUCKETS
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

def scored_score(prob, cat, bo5, rec, k_prob=1.0, k_cal=1.0, k_ev=1.0, k_attn=1.0):
    """Mirrors apex_score() exactly, but with 4 independent scaling knobs:
    k_prob scales the raw probability term; k_cal scales ev_calibrated
    BEFORE the Global25 blend; k_ev scales the already-blended ev AFTER
    the blend (== 'EV contribution' as it actually hits score); k_attn
    scales the attention bonus. Aces band calibration always enabled."""
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or aet._stat([])
    n = cs["n"]; w = min(n / 25.0, 1.0)

    prob_term = 45.0 * max(-1.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN))) * k_prob

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
    ev_calibrated *= k_cal
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)
    ev_blended = (ev_calibrated + GLOBAL_BLEND_FRAC * (ev_fixed_manual - ev_calibrated)) * k_ev

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
    attn_bonus = {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0) * k_attn

    raw = 50.0 + prob_term + ev_blended + structural_prior + bucket_adj + attn_bonus
    return round(max(0.0, min(100.0, raw)))

rec = aet.records()
settled = aet.settled_picks()
all_picks = [p for p in settled if p["prob"] is not None and p.get("match_date") and p.get("hit") is not None]
days = {}
for p in all_picks:
    days.setdefault(p["match_date"], []).append(p)
day_list = sorted(days.keys())

def wl(subset):
    wins = sum(1 for p in subset if p["hit"] is True)
    losses = sum(1 for p in subset if p["hit"] is False)
    n = wins + losses
    net = round(wins * WIN - losses * RISK, 2)
    wr = round(wins / n * 100, 2) if n else None
    roi = round(net / (n * RISK) * 100, 2) if n else None
    return {"picks": len(subset), "wins": wins, "losses": losses, "win_rate": wr, "roi": roi, "net_units": net}

def build_scored(**kwargs):
    scored = []
    for p in all_picks:
        cat = p["category"]; prob = p["prob"]; bo5 = bool(p.get("bo5", False))
        floor = GATE.get(cat)
        gate_pass = not (floor is not None and (prob is None or float(prob) < floor))
        sc = scored_score(prob, cat, bo5, rec, **kwargs)
        scored.append({"p": p, "score": sc, "day": p["match_date"], "gate_pass": gate_pass})
    return scored

def replay(scored):
    byday = {}
    for d in scored:
        if not d["gate_pass"]:
            continue
        byday.setdefault(d["day"], []).append(d)
    top3, top6, elite6 = [], [], []
    for day in day_list:
        lst = sorted(byday.get(day, []), key=lambda d: -d["score"])
        top3.extend(lst[:3])
        top6.extend(lst[:6])
        elite6.extend([d for d in lst if d["score"] >= 70][:6])
    return {
        "top3": wl([d["p"] for d in top3]),
        "top6": wl([d["p"] for d in top6]),
        "elite6": wl([d["p"] for d in elite6]),
    }

baseline = replay(build_scored())

scenarios = {}
for comp, key in [("probability_term", "k_prob"), ("calibration_term_pre_blend", "k_cal"),
                   ("ev_contribution_post_blend", "k_ev"), ("attention_bonus", "k_attn")]:
    for pct, factor in [("-10pct", 0.9), ("+10pct", 1.1)]:
        kwargs = {"k_prob": 1.0, "k_cal": 1.0, "k_ev": 1.0, "k_attn": 1.0}
        kwargs[key] = factor
        scenarios[f"{comp}_{pct}"] = replay(build_scored(**kwargs))

# Combined best single-lever test: what if calibration penalty clamp itself
# is softened (less aggressive) -- i.e. k_cal at 0.5 and 0.75, since +-10%
# barely moves a term that's already clamped at its ceiling for the worst
# bands. This directly tests the saturation-clamp hypothesis from Step 4.
for factor in [0.5, 0.75, 1.25]:
    scenarios[f"calibration_term_pre_blend_{factor}x"] = replay(build_scored(k_cal=factor))

out = {"baseline_production": baseline, "scenarios": scenarios}
with open("/tmp/apex_elite6_sensitivity_output.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
