#!/usr/bin/env python3
"""Follow-up sensitivity check, approved 2026-09-23: same test as apex_sensitivity_test.py,
restricted to picks from the last N days (minimal player-stats drift), with tour (ATP/WTA)
resolved via SportsAPI365's /h2h/playerType/{name} route instead of a guess."""
import csv, sys, time, random, statistics, collections, pickle, urllib.parse
from datetime import date, timedelta
import numpy as np
import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim
from sa365_prematch_probe import get

random.seed(7)
N_DRAWS = 25
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
_tour_cache = {}

def player_is_wta(name):
    if name not in _tour_cache:
        st, p = get(f"/h2h/playerType/{urllib.parse.quote(name)}")
        time.sleep(0.2)
        _tour_cache[name] = (str((p or {}).get("type", "")).lower() == "wta")
    return _tour_cache[name]

def load_misses():
    rows = list(csv.DictReader(open("data/sa365_gap_backfill.csv")))
    vals = [float(r["Bet365_gap_pts"]) for r in rows if r.get("Bet365_gap_pts")]
    lean = statistics.mean(vals) / 100.0
    return [v / 100.0 - lean for v in vals], lean

def run(fav, dog, pinn, surface, bo5, wta, today, m, c, state):
    df = sim.build_live_row(fav, dog, pinn, surface, bo5, wta, today, m, state)
    P, hf, hd, mu = sim.v1_inputs_from_rows(df, m)
    lv = sim.level_from(hf[0], hd[0], c, sim.price_level_pred(df, c)[0])
    bo = 5 if bo5 else 3
    t, flag = sim.solve_tilt(lv, pinn, c["tb_k"], bo, sigma=c.get("gap_sigma", 0.0))
    hA = min(max(lv + t, 0.2), 0.995); hB = min(max(lv - t, 0.2), 0.995)
    dm = c.get("disp_mult", 1.0)
    s = sim.simulate(hA, hB, c["tb_k"], bo, (mu["fav"][0][0], mu["fav"][1][0]), (mu["dog"][0][0], mu["dog"][1][0]),
                     (c["disp"]["fav"]["aces"] * dm, c["disp"]["fav"]["dfs"] * dm),
                     (c["disp"]["dog"]["aces"] * dm, c["disp"]["dog"]["dfs"] * dm), 4000, sigma=c.get("gap_sigma", 0.0))
    return hA, hB, s

def side_x(s, cat, player_is_fav):
    return s[cat] if cat in sim.MATCH_PROPS else s["fav" if player_is_fav else "dog"][cat]

def main():
    misses, lean = load_misses()
    import csv as _csv
    _latest = max(r["match_date"] for r in _csv.DictReader(open("apex_prop_sim_forward_log_v1.csv"))
                  if r.get("actual") and r.get("line") and r.get("pinn_fav"))
    cutoff = (date.fromisoformat(_latest) - timedelta(days=DAYS - 1)).isoformat()
    print(f"anchoring to latest graded date {_latest} (grading was down 09-09..09-23 during the RapidAPI->SportsAPI365 migration)")
    print(f"Bet365 misses loaded: {len(misses)}  (avg lean removed: {lean * 100:+.2f} pts)")
    print(f"restricting to match_date >= {cutoff}")
    c = sim.load_sim(); m = v1.load_model()
    with open(v1.STATE_OUT, "rb") as f:
        state = pickle.load(f)
    all_rows = [r for r in csv.DictReader(open("apex_prop_sim_forward_log_v1.csv"))
                if r.get("actual") and r.get("line") and r.get("pinn_fav")]
    rows = [r for r in all_rows if r["match_date"] >= cutoff]
    print(f"graded, priced picks in window: {len(rows)}  (of {len(all_rows)} total)")
    out, mismatched, errors = [], 0, 0
    for i, r in enumerate(rows):
        cat = r["category"]; is_match = (r["player"] == "match")
        if is_match:
            names = r["opponent"].split(" v ")
            if len(names) != 2:
                continue
            fav_name, dog_name = names[0].strip(), names[1].strip()
        else:
            fav_name = r["player"] if r["is_fav"] == "1" else r["opponent"]
            dog_name = r["opponent"] if r["is_fav"] == "1" else r["player"]
        try:
            fav = v1.resolve_name(fav_name, state); dog = v1.resolve_name(dog_name, state)
        except Exception:
            errors += 1; continue
        wta = player_is_wta(fav_name)  # real lookup, not a guess
        pinn = float(r["pinn_fav"]); bo5 = (r["best_of"] == "5")
        today = date.fromisoformat(r["match_date"])
        try:
            hA0, hB0, s0 = run(fav, dog, pinn, r["surface"], bo5, wta, today, m, c, state)
        except Exception:
            errors += 1; continue
        drift = max(abs(hA0 - float(r["hold_fav"])), abs(hB0 - float(r["hold_dog"])))
        if drift > 0.01:
            mismatched += 1
        line = float(r["line"]); actual = float(r["actual"])
        is_fav_player = (r["is_fav"] == "1") if not is_match else True
        x0 = side_x(s0, cat, is_fav_player)
        p0 = float(np.mean(x0 > line))
        pick_dir0 = "MORE" if p0 >= 0.5 else "LESS"
        real_result0 = "WIN" if ((pick_dir0 == "MORE") == (actual > line)) else "LOSS"
        shifted_ps, flips = [], 0
        for _ in range(N_DRAWS):
            shift = random.choice(misses)
            p2 = min(max(pinn + shift, 0.501), 0.995)
            try:
                _, _, s2 = run(fav, dog, p2, r["surface"], bo5, wta, today, m, c, state)
            except Exception:
                continue
            x2 = side_x(s2, cat, is_fav_player)
            p2p = float(np.mean(x2 > line))
            shifted_ps.append(p2p)
            if (p2p >= 0.5) != (p0 >= 0.5):
                flips += 1
        if not shifted_ps:
            continue
        avg_p2 = statistics.mean(shifted_ps)
        would_win_rate = statistics.mean(
            (("MORE" if p >= 0.5 else "LESS") == "MORE") == (actual > line) for p in shifted_ps)
        out.append({"category": cat, "drift": drift, "p_pinnacle": p0, "p_bet365_avg": avg_p2,
                    "abs_move": abs(avg_p2 - p0), "flip_rate": flips / len(shifted_ps),
                    "real_result_pinnacle": real_result0, "would_win_rate_bet365": would_win_rate})
        if i and i % 50 == 0:
            print(f"  ...{i}/{len(rows)}", flush=True)
    ok = len(out) - mismatched
    print(f"\nharness check: {ok}/{len(out)} rows reproduced logged hold rates within 0.01 "
          f"({mismatched} drifted, {errors} errors/skipped)")
    if not out:
        print("no rows in window -- widen the day count"); return
    with open("data/sensitivity_results_recent.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    by_cat = collections.defaultdict(list)
    for o in out:
        by_cat[o["category"]].append(o)
    print(f"\n{'category':14} {'n':>4} {'typical move':>13} {'flip rate':>10} "
          f"{'win as-graded':>14} {'win if Bet365':>14}")
    for cat, v in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        if len(v) < 5:
            print(f"{cat:14} {len(v):4}  (too few in this window)"); continue
        moves = [o["abs_move"] for o in v]
        wr_real = statistics.mean(o["real_result_pinnacle"] == "WIN" for o in v)
        wr_b365 = statistics.mean(o["would_win_rate_bet365"] for o in v)
        print(f"{cat:14} {len(v):4} {statistics.mean(moves):12.1%} "
              f"{statistics.mean(o['flip_rate'] for o in v):9.1%} {wr_real:13.1%} {wr_b365:13.1%}")

if __name__ == "__main__":
    main()
