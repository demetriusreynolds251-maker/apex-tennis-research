import sys
sys.path.insert(0, '.')
import apex_edge_tracker as aet

CUTOFF_TS = "2026-10-05T21:27:38"
CUTOFF_DATE = "2026-10-05"

CATS = ["total_games", "aces", "breaks", "fantasy_score", "dfs", "games_won", "total_sets", "tiebreaks"]

all_picks = aet.settled_picks()

def in_restored_window(p):
    ts = p.get("settled_ts") or ""
    if ts:
        return ts <= CUTOFF_TS
    # hand-entries carry no settled_ts -- fall back to match_date
    return (p.get("match_date") or "") <= CUTOFF_DATE

restored_picks = [p for p in all_picks if in_restored_window(p)]

print(f"{'category':<15} {'CURRENT cal_pts':>16} {'  (n)':>6}   {'RESTORED cal_pts':>17} {'  (n)':>6}")
for cat in CATS:
    cur = aet._stat([p for p in all_picks if p["category"] == cat])
    res = aet._stat([p for p in restored_picks if p["category"] == cat])
    cur_cp = cur["cal_pts"]
    res_cp = res["cal_pts"]
    cur_s = f"{cur_cp*100:+.2f}pt" if cur_cp is not None else "n/a"
    res_s = f"{res_cp*100:+.2f}pt" if res_cp is not None else "n/a"
    print(f"{cat:<15} {cur_s:>16} {cur['n']:>6}   {res_s:>17} {res['n']:>6}")

print()
print("total settled picks (current):", len(all_picks))
print("total settled picks (restored/as-of-10-05-2127):", len(restored_picks))
