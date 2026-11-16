import sys, csv, functools
from collections import defaultdict
sys.path.insert(0, '.')
import apex_edge_tracker as cur

BREAK_EVEN = cur.BREAK_EVEN
LABEL = cur.LABEL
GROUPS = cur.GROUPS
group_of = cur.group_of
attention = cur.attention

_FIXED_CAL_MANUAL = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}
GLOBAL_BLEND_FRAC = 0.25
EV_CONTRIBUTION_SCALE = 1.25
_ACES_BAND_CAL = {
    (50.0, 60.0): (-0.1129, 52), (60.0, 70.0): (-0.0182, 49),
    (70.0, 80.0): (-0.1770, 47), (80.0, 101.0): (-0.1974, 53),
}

def _aces_band_cal_pts(pct):
    for (blo, bhi), (cp, bn) in _ACES_BAND_CAL.items():
        if blo <= pct < bhi:
            return cp, bn
    return None, 0

def instrumented_score(prob, cat, bo5, rec, use_cal=True, use_fix=True, use_band=True, breakdown=None):
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or cur._stat([])
    n = cs["n"]; w = min(n / 25.0, 1.0)
    base = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN)))
    score = base

    if cat == "aces":
        _bcp, _bn = _aces_band_cal_pts(prob * 100.0)
        if _bn >= 5 and _bcp is not None:
            _bs = _bcp / 0.10
            _bw = min(_bn / 25.0, 1.0)
            ev_calibrated = (30.0 if _bs < 0 else 20.0) * _bw * max(-1.5, min(1.0, _bs))
        else:
            ev_calibrated = 0.0
    elif n >= 5 and cs.get("cal_pts") is not None:
        _cs = cs["cal_pts"] / 0.10
        ev_calibrated = (30.0 if _cs < 0 else 20.0) * w * max(-1.5, min(1.0, _cs))
    else:
        ev_calibrated = 0.0
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)

    cal_term = ev_calibrated if use_cal else 0.0
    fix_term = ev_fixed_manual if use_fix else 0.0
    ev = cal_term + GLOBAL_BLEND_FRAC * (fix_term - cal_term)
    ev *= EV_CONTRIBUTION_SCALE
    score += ev

    g = group_of(cat)
    prior = {"rate_model": 8.0, "sim_derived": 3.0, "total_games": -8.0}.get(g, 0.0)
    pr = prior * (1.0 - w) * (0.5 if n < 5 else 1.0)
    score += pr

    band_adj_total = 0.0
    if use_band:
        for name, blo, bhi in cur.BUCKETS:
            if n < 5:
                break
            if blo <= prob < bhi:
                for bn, bw_, bl_, bstat in rec["buckets"]:
                    if bn == name and (bw_ + bl_) >= 3 and bstat:
                        br = bw_ / (bw_ + bl_)
                        adj = 10.0 * min((bw_ + bl_) / 10.0, 1.0) * max(-1.0, min(1.0, (br - bstat) / 0.10))
                        score += adj
                        band_adj_total += adj
                break

    lvl, _w = attention(cat, prob, rec)
    if bo5: lvl = "LOW"
    attn_bonus = {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0)
    score += attn_bonus
    score = max(0.0, min(100.0, score))

    if breakdown is not None:
        cal_contrib = EV_CONTRIBUTION_SCALE * (1.0 - GLOBAL_BLEND_FRAC) * cal_term
        fix_contrib = EV_CONTRIBUTION_SCALE * GLOBAL_BLEND_FRAC * fix_term
        breakdown.append({"cat": cat, "prob": prob, "base": base,
                           "cal_contrib": cal_contrib, "fix_contrib": fix_contrib,
                           "ev_calibrated_raw": ev_calibrated, "ev_fixed_raw": ev_fixed_manual,
                           "ev_blended_scaled": ev, "prior": pr, "band": band_adj_total,
                           "attn": attn_bonus, "final": round(score), "n": n})
    ev_label = ("Very Low" if n < 5 else "Low" if n < 10 else "Moderate" if n < 25 else "Strong" if n < 100 else "Proven")
    return round(score), ev_label, lvl, [], []


def run_contribution_and_correlation():
    rec = cur.records()
    picks = rec["overall"]["picks"]  # all decided Bo3 picks, the real settled universe
    breakdown = []
    for p in picks:
        if p.get("prob") is None:
            continue
        instrumented_score(p["prob"], p["category"], False, rec, breakdown=breakdown)

    n = len(breakdown)
    avg = lambda k: sum(d[k] for d in breakdown) / n if n else 0.0
    print(f"===== STEP 6: AVERAGE SCORE CONTRIBUTION ACROSS {n} SCORED PROPS =====")
    print(f"Avg base (probability term):      {avg('base'):+.2f}")
    print(f"Avg Calibration contribution:     {avg('cal_contrib'):+.2f}")
    print(f"Avg EV(fixed-manual) contribution:{avg('fix_contrib'):+.2f}")
    print(f"Avg Prior (structural) contrib:   {avg('prior'):+.2f}")
    print(f"Avg Band contribution:            {avg('band'):+.2f}")
    print(f"Avg Attention bonus:              {avg('attn'):+.2f}")
    print(f"Avg Final score:                  {avg('final'):.2f}")

    def corr(ka, kb):
        xs = [d[ka] for d in breakdown]; ys = [d[kb] for d in breakdown]
        mx, my = sum(xs)/n, sum(ys)/n
        num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
        dx = sum((x-mx)**2 for x in xs) ** 0.5
        dy = sum((y-my)**2 for y in ys) ** 0.5
        return num / (dx*dy) if dx and dy else 0.0

    print(f"\n===== STEP 3: CORRELATION BETWEEN COMPONENTS (n={n}) =====")
    print(f"Calibration vs EV(fixed):   r = {corr('cal_contrib','fix_contrib'):+.3f}")
    print(f"Calibration vs Band:        r = {corr('cal_contrib','band'):+.3f}")
    print(f"EV(fixed) vs Band:          r = {corr('fix_contrib','band'):+.3f}")
    print(f"Calibration vs Prior:       r = {corr('cal_contrib','prior'):+.3f}")
    print(f"EV(fixed) vs Prior:         r = {corr('fix_contrib','prior'):+.3f}")

    # per-category averages, to show where double-direction stacking is worst
    print(f"\n===== PER-CATEGORY AVERAGE CONTRIBUTIONS =====")
    cats = sorted(set(d["cat"] for d in breakdown))
    print("category        | n    | cal_contrib | fix_contrib | prior  | band   | combined_ev+prior+band")
    for c in cats:
        rows = [d for d in breakdown if d["cat"] == c]
        m = len(rows)
        ca = sum(r["cal_contrib"] for r in rows)/m
        fi = sum(r["fix_contrib"] for r in rows)/m
        pr = sum(r["prior"] for r in rows)/m
        ba = sum(r["band"] for r in rows)/m
        print(f"{c:15s} | {m:4d} | {ca:+11.2f} | {fi:+11.2f} | {pr:+6.2f} | {ba:+6.2f} | {(ca+fi+pr+ba):+6.2f}")
    return breakdown

bd = run_contribution_and_correlation()
