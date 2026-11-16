#!/usr/bin/env python3
"""APEX-BB-AUDIT-2026-09-06 -- read-only. Did the top-3 by RANK cash as a 3-leg each day?
Joins apex_bb_rank_log_v1.csv -> sim log actuals (+ picks for direction). Newest board per day."""
import csv, collections, itertools
def key(r): return (r["match_id"], r["player"].strip().lower(), r["category"], str(float(r["line"])) if r["line"] else "")
sim = {key(r): r for r in csv.DictReader(open("apex_prop_sim_forward_log_v1.csv")) if str(r.get("actual","")).strip()}
picks = {key(r): r for r in csv.DictReader(open("apex_engine_picks_log_v1.csv"))}
rl = list(csv.DictReader(open("apex_bb_rank_log_v1.csv")))
print("rank log rows", len(rl), "| columns:", ", ".join(rl[0].keys()))
def outcome(r):
    s, p = sim.get(key(r)), picks.get(key(r))
    if not s or not p: return None
    a, ln, d = float(s["actual"]), float(r["line"]), (r.get("direction") or p["direction"]).upper()
    if a == ln: return "PUSH"
    return "WIN" if (a > ln) == (d == "MORE") else "LOSS"
boards = collections.defaultdict(list)
for r in rl: boards[(r["ts"][:10], r["source"], r["board_id"])].append(r)
newest = {}
for (day, src, bid), rows in boards.items():
    if src != "detail": continue           # /bestbets view = the deduped playable board
    if day not in newest or rows[0]["ts"] > newest[day][0]["ts"]: newest[day] = rows
print(f"\n{'day':10s} {'top3 RANK':>10s} {'top3 APEX':>10s} {'legs settled':>13s}  top-3 picks (RANK order)")
tot = collections.Counter()
for day in sorted(newest):
    rows = sorted(newest[day], key=lambda r: int(r["rank_position"]))
    seen, top = set(), []
    for r in rows:                          # one slot per player, like the board
        if r["player"].lower() in seen: continue
        seen.add(r["player"].lower()); top.append(r)
        if len(top) == 3: break
    apx = sorted(newest[day], key=lambda r: int(r["legacy_apex_position"] or 999))[:3]
    o_r = [outcome(r) for r in top]; o_a = [outcome(r) for r in apx]
    def slip(o):
        if any(x is None for x in o): return "unsettled"
        if any(x == "LOSS" for x in o): return "LOSS"
        return "CASH" if all(x == "WIN" for x in o) else "PUSH"
    sr, sa = slip(o_r), slip(o_a); tot[("rank", sr)] += 1; tot[("apex", sa)] += 1
    legs = sum(1 for x in o_r if x == "WIN"), sum(1 for x in o_r if x is not None)
    print(f"{day:10s} {sr:>10s} {sa:>10s} {legs[0]:>6d}/{legs[1]:<6d}  " +
          " | ".join(f"{r['player'][:14]} {r['category'][:6]} {r['line']} {(r.get('direction') or picks.get(key(r),{}).get('direction',''))[:4]} p={float(r['probability']):.2f} {outcome(r) or '?'}" for r in top))
print("\nRANK top-3 days:", dict((k[1], v) for k, v in tot.items() if k[0] == "rank"))
print("APEX top-3 days:", dict((k[1], v) for k, v in tot.items() if k[0] == "apex"))
w = l = 0
for rows in newest.values():
    for r in rows:
        o = outcome(r)
        if o == "WIN": w += 1
        elif o == "LOSS": l += 1
print(f"all ranked picks settled: {w}-{l} ({100*w/max(1,w+l):.0f}%)  ->  3-leg cash rate at that per-leg rate: {(w/max(1,w+l))**3*100:.0f}%")
