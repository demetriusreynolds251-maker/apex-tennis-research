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

def scored_list(fn, **kw):
    r = fn(picks, rec=rec, return_scored=True, **kw)
    if isinstance(r, str):
        return []
    return r.get("scored") or []

top3    = scored_list(aet.best_bets_detail, limit=3, exclude_fantasy_score=True)
elite6  = scored_list(aet.elite6_detail, exclude_fantasy_score=True)
top10   = scored_list(aet.best_bets_detail, limit=10, exclude_fantasy_score=True)
goblin  = scored_list(aet.best_bets_detail, prop_type='goblin', limit=6, slip_rules=True, exclude_fantasy_score=True)
demon   = scored_list(aet.best_bets_detail, prop_type='demon', limit=6, slip_rules=True, exclude_fantasy_score=True)
standard= scored_list(aet.best_bets_detail, prop_type='standard', limit=6, slip_rules=True, exclude_fantasy_score=True)
allp    = scored_list(aet.best_bets_detail, limit=max(len(picks), 1))

scores = [d["sc"] for d in allp]

_FIXED = {
    "total_games": 8.1, "games_won": 2.1, "dfs": -1.0,
    "fantasy_score": -1.6, "breaks": -3.6, "aces": -11.2,
}
BE = aet.BREAK_EVEN
top10_rows = []
for d in sorted(allp, key=lambda x: -x["sc"])[:10]:
    p = d["p"]
    prob = float(p.get("prob") or 0.0)
    cat = p.get("category")
    name = p["opponent"] if p.get("player") == "match" else p.get("player")
    top10_rows.append({
        "player": name, "category": cat, "line": p.get("line"), "direction": p.get("direction"),
        "probability_pct": round(prob * 100, 1),
        "cal_adjustment": _FIXED.get(cat),
        "final_score": d["sc"],
    })

out = {
    "raw_total": result.get("raw_total"),
    "deduped_total": result.get("deduped_total"),
    "active_board_len": len(picks),
    "Top3": len(top3), "Elite6": len(elite6), "Top10": len(top10),
    "Goblin": len(goblin), "Demon": len(demon), "Standard": len(standard),
    "AllPicks": len(allp),
    "highest_score": max(scores) if scores else None,
    "n_70plus": sum(1 for s in scores if s >= 70),
    "n_80plus": sum(1 for s in scores if s >= 80),
    "n_90plus": sum(1 for s in scores if s >= 90),
    "top10": top10_rows,
}
with open('/tmp/fixed_cal_fetch_result.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
print("DONE")
