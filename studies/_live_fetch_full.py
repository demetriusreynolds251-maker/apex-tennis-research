import sys, json
sys.path.insert(0, '.')
import openclaw_core as core
import apex_edge_tracker as aet
import discord_bot as db

# Suppress only the Discord post and the membership-log write (avoid
# duplicate-posting picks publicly / double-writing membership rows).
# Archiving to the picks log is allowed to run for real -- that's the
# normal, correct behavior of /fetch, and it's what makes load_current_board()
# reflect this fetch for the board-detail calls below.
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
allp    = scored_list(aet.best_bets_detail, limit=max(len(picks),1))

scores = [d["sc"] for d in allp]
out = {
    "raw_total": result.get("raw_total"),
    "deduped_total": result.get("deduped_total"),
    "data_source": result.get("data_source"),
    "engine_evaluated_raw": result.get("engine_evaluated_raw"),
    "declined_exact": result.get("declined_exact"),
    "demonlock_dropped": result.get("demonlock_dropped"),
    "active_board_len": len(picks),
    "Top3": len(top3), "Elite6": len(elite6), "Top10": len(top10),
    "Goblin": len(goblin), "Demon": len(demon), "Standard": len(standard),
    "AllPicks": len(allp),
    "highest_score": max(scores) if scores else None,
    "n_70plus": sum(1 for s in scores if s >= 70),
    "n_80plus": sum(1 for s in scores if s >= 80),
    "n_90plus": sum(1 for s in scores if s >= 90),
    "top25": [
        {"name": (d["p"]["opponent"] if d["p"].get("player")=="match" else d["p"].get("player")),
         "cat": d["p"].get("category"), "line": d["p"].get("line"),
         "dir": d["p"].get("direction"), "score": d["sc"], "conf": d.get("conf")}
        for d in sorted(allp, key=lambda x: -x["sc"])[:25]
    ],
}
with open('/tmp/live_fetch_full_result.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
print("DONE")
print(json.dumps({k:v for k,v in out.items() if k != "top25"}, indent=1, default=str))
