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

r = aet.best_bets_detail(picks, rec=rec, limit=max(len(picks), 1), return_scored=True)
allp = [] if isinstance(r, str) else (r.get("scored") or [])

BE = aet.BREAK_EVEN
rows = []
for d in allp:
    p = d["p"]
    prob = float(p.get("prob") or 0.0)
    cat = p.get("category")
    cs = rec["cats"].get(cat) or {}
    n = cs.get("n", 0)
    w = min(n / 25.0, 1.0)
    base = 50.0 + 45.0 * max(-1.0, min(1.0, (prob - BE) / (0.85 - BE)))
    cal_adj = 0.0
    if n >= 5 and cs.get("cal_pts") is not None:
        cal_scale = cs["cal_pts"] / 0.10
        cal_adj = (30.0 if cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, cal_scale))
    name = p["opponent"] if p.get("player") == "match" else p.get("player")
    rows.append({
        "player": name,
        "category": cat,
        "line": p.get("line"),
        "direction": p.get("direction"),
        "probability_pct": round(prob * 100, 1),
        "base_score": round(base, 1),
        "cal_adjustment": round(cal_adj, 1),
        "final_score": d["sc"],
    })

rows.sort(key=lambda x: -x["probability_pct"])

with open("/tmp/top25_prob_full.json", "w") as f:
    json.dump({"count": len(rows), "rows": rows}, f, indent=1, default=str)
print("DONE", len(rows))
