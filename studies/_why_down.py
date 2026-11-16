import sys
sys.path.insert(0, '.')
import apex_edge_tracker as aet

picks, note = aet.load_current_board()
rec = aet.records()
r = aet.best_bets_detail(picks, rec=rec, limit=len(picks), return_scored=True)
scored = r.get("scored") or []
print("n scored:", len(scored))
for d in sorted(scored, key=lambda x: -x["sc"]):
    p = d["p"]
    name = p["opponent"] if p.get("player")=="match" else p.get("player")
    print(f"- {name:<28} {p.get('category'):<13} sc={d['sc']:<4} conf={d.get('conf')} ev={d.get('ev')} "
          f"up={d.get('up')} down={d.get('down')}")
