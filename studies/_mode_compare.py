import sys, json
sys.path.insert(0, '.')
import openclaw_core as core
import apex_edge_tracker as aet
import discord_bot as db

core.send_discord = lambda *a, **k: None
aet.capture_board_membership = lambda *a, **k: None

result = db._fetch_publish_all_render_inner(core.get_system_dates(), lambda *a, **k: None)
picks, note = aet.load_current_board()
rec = aet.records()

BE = aet.BREAK_EVEN
LABEL = aet.LABEL
BUCKETS = aet.BUCKETS
group_of = aet.group_of
attention = aet.attention

_FIXED = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}

def _score(prob, cat, bo5, rec, mode):
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or {"n": 0, "cal_pts": None, "cal_wins": 0}
    n = cs.get("n", 0); w = min(n / 25.0, 1.0)
    up, down = [], []
    score = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BE) / (0.85 - BE)))
    if prob >= 0.65: up.append("stated %d%%" % round(prob * 100))
    if prob <= 0.55: down.append("thin stated probability %d%%" % round(prob * 100))
    if mode == "A":
        if n >= 5 and cs.get("cal_pts") is not None:
            cal_scale = cs["cal_pts"] / 0.10
            ev = (30.0 if cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, cal_scale))
            score += ev
        elif n < 5:
            pass
    else:
        if cat in _FIXED:
            score += _FIXED[cat]
    g = group_of(cat)
    prior = {"rate_model": 8.0, "sim_derived": 3.0, "total_games": -8.0}.get(g, 0.0)
    pr = prior * (1.0 - w) * (0.5 if n < 5 else 1.0)
    score += pr
    for name, blo, bhi in BUCKETS:
        if n < 5:
            break
        if blo <= prob < bhi:
            for bn, bw_, bl_, bstat in rec["buckets"]:
                if bn == name and (bw_ + bl_) >= 3 and bstat:
                    br = bw_ / (bw_ + bl_)
                    adj = 10.0 * min((bw_ + bl_) / 10.0, 1.0) * max(-1.0, min(1.0, (br - bstat) / 0.10))
                    score += adj
            break
    lvl, _w = attention(cat, prob, rec)
    if bo5: lvl = "LOW"
    score += {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0)
    score = max(0.0, min(100.0, score))
    return round(score)

def scored_list(fn, **kw):
    r = fn(picks, rec=rec, return_scored=True, **kw)
    if isinstance(r, str):
        return []
    return r.get("scored") or []

orig_apex_score = aet.apex_score

def run_mode(mode):
    aet.apex_score = (lambda prob, cat, bo5, rec2: (_score(prob, cat, bo5, rec2, mode), "", "", [], [])) if mode == "A" else orig_apex_score
    top3    = scored_list(aet.best_bets_detail, limit=3, exclude_fantasy_score=True)
    elite6  = scored_list(aet.elite6_detail, exclude_fantasy_score=True)
    top10   = scored_list(aet.best_bets_detail, limit=10, exclude_fantasy_score=True)
    goblin  = scored_list(aet.best_bets_detail, prop_type='goblin', limit=6, slip_rules=True, exclude_fantasy_score=True)
    demon   = scored_list(aet.best_bets_detail, prop_type='demon', limit=6, slip_rules=True, exclude_fantasy_score=True)
    standard= scored_list(aet.best_bets_detail, prop_type='standard', limit=6, slip_rules=True, exclude_fantasy_score=True)
    allp    = scored_list(aet.best_bets_detail, limit=max(len(picks), 1))
    scores = [d["sc"] for d in allp]
    def _ident(d):
        p = d["p"]
        nm = p["opponent"] if p.get("player") == "match" else p.get("player")
        return "%s | %s %s %s" % (nm, p.get("category"), p.get("line"), p.get("direction"))
    return {
        "Top3": len(top3), "Elite6": len(elite6), "Top10": len(top10),
        "Goblin": len(goblin), "Demon": len(demon), "Standard": len(standard),
        "70+": sum(1 for s in scores if s >= 70),
        "80+": sum(1 for s in scores if s >= 80),
        "90+": sum(1 for s in scores if s >= 90),
        "highest": max(scores) if scores else None,
        "avg": round(sum(scores) / len(scores), 1) if scores else None,
        "n": len(allp),
        "top3_set": set(_ident(d) for d in top3),
        "elite6_set": set(_ident(d) for d in elite6),
        "top10_set": set(_ident(d) for d in top10),
        "goblin_set": set(_ident(d) for d in goblin),
        "demon_set": set(_ident(d) for d in demon),
        "standard_set": set(_ident(d) for d in standard),
    }

modeA = run_mode("A")
modeB = run_mode("B")
aet.apex_score = orig_apex_score

# per-prop comparison across the full picks list (not just board-filtered)
rows = []
for p in picks:
    prob = float(p.get("prob") or 0.0)
    cat = p.get("category")
    bo5 = bool(p.get("bo5"))
    sa = _score(prob, cat, bo5, rec, "A")
    sb = _score(prob, cat, bo5, rec, "B")
    name = p["opponent"] if p.get("player") == "match" else p.get("player")
    rows.append({
        "player": name, "category": cat, "line": p.get("line"), "direction": p.get("direction"),
        "probability_pct": round(prob * 100, 1),
        "score_mode_a": sa, "score_mode_b": sb, "diff": sb - sa,
    })
rows.sort(key=lambda r: -r["score_mode_b"])

def _plain(m):
    return {k: v for k, v in m.items() if not k.endswith("_set")}

diffs = {}
for board in ("top3", "elite6", "top10", "goblin", "demon", "standard"):
    a_set = modeA[board + "_set"]
    b_set = modeB[board + "_set"]
    diffs[board] = {
        "entered_under_B_only": sorted(b_set - a_set),
        "removed_under_A_only": sorted(a_set - b_set),
    }

out = {
    "raw_total": result.get("raw_total"),
    "active_board_len": len(picks),
    "modeA_summary": _plain(modeA),
    "modeB_summary": _plain(modeB),
    "board_diffs": diffs,
    "top25": rows[:25],
}
with open('/tmp/mode_compare_result.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
print("DONE", len(rows))
