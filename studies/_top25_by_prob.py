import sys, json
sys.path.insert(0, '/path/to/home/openclaw')
import apex_edge_tracker as aet

picks = aet.load_current_board()
rec = aet.records()

scored = aet.best_bets_detail(picks, rec=rec, limit=len(picks), return_scored=True)

rows = []
for d in scored:
    p = d.get("p", {})
    prob = p.get("prob")
    sc = d.get("sc")
    conf = d.get("conf")
    ev = d.get("ev")
    base = None
    try:
        base = round(sc - (ev if ev is not None else 0), 2)
    except Exception:
        base = None
    rows.append({
        "player": p.get("player") or p.get("match_id") or p.get("name"),
        "opponent": p.get("opponent"),
        "category": p.get("category") or p.get("stat_type"),
        "line": p.get("line"),
        "direction": p.get("direction"),
        "prob": prob,
        "base_score": base,
        "cal_adjustment": ev,
        "final_score": sc,
        "conf": conf,
        "up": d.get("up"),
        "down": d.get("down"),
    })

rows.sort(key=lambda r: (r["prob"] if r["prob"] is not None else -1), reverse=True)

with open("/tmp/top25_by_prob.json", "w") as f:
    json.dump(rows, f, indent=2, default=str)

print("COUNT:", len(rows))
for r in rows:
    print(json.dumps(r, default=str))
