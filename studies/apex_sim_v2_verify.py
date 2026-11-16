"""Task 1 Step 3 verification: regression check (B) + spot checks (C).
Read-only against V1; writes nothing back to any source file.
"""
import numpy as np
import apex_prop_model_v1 as v1
import apex_prop_sim_v1 as sim
import apex_prop_sim_v2 as sim2

m = v1.load_model()
c = sim.load_sim()
W, K = m["window"], m["shrink"]

with open("/tmp/oppbr_state.pkl", "rb") as f:
    import pickle
    state = pickle.load(f)

from datetime import date
today = date.fromisoformat(state["latest_date"])
players = [n for n, p in state["players"].items()
           if p["n"] > 300 and p["last_date"] and (today - p["last_date"]).days < 90]
print("candidate live players:", len(players))

pairs = [(players[i], players[i + 7]) for i in range(0, 15, 1) if i + 7 < len(players)][:5]
print("=" * 78)
print("B) REGRESSION CHECK -- V1 vs V2, deterministic mu/P level (not RNG samples)")
print("=" * 78)
all_nonaces_identical = True
for fav, dog in pairs:
    pinn = 0.62
    df = sim.build_live_row(fav, dog, pinn, "Hard", False, False, today, m, state)
    P1, hf1, hd1, mu1 = sim.v1_inputs_from_rows(df, m)
    P2, hf2, hd2, mu2 = sim2.v2_inputs_from_rows(df, m)
    print(f"\n{fav} vs {dog}")
    for side in ("fav", "dog"):
        aces_diff = mu2[side][0][0] - mu1[side][0][0]
        dfs_diff = mu2[side][1][0] - mu1[side][1][0]
        print(f"  [{side}] aces mu  V1={mu1[side][0][0]:.5f}  V2={mu2[side][0][0]:.5f}  diff={aces_diff:+.5f}")
        print(f"  [{side}] dfs  mu  V1={mu1[side][1][0]:.5f}  V2={mu2[side][1][0]:.5f}  diff={dfs_diff:+.5f}  "
              f"{'OK identical' if dfs_diff == 0 else 'MISMATCH'}")
        for cat in ("dfs", "holds", "breaks", "svgms"):
            v1v = P1[side][cat] if not hasattr(P1[side][cat], "__len__") else P1[side][cat][0]
            v2v = P2[side][cat] if not hasattr(P2[side][cat], "__len__") else P2[side][cat][0]
            same = (v1v == v2v)
            all_nonaces_identical &= bool(same)
            if not same:
                print(f"  [{side}] {cat}: V1={v1v} V2={v2v} MISMATCH")
    hf_same = (hf1[0] == hf2[0]); hd_same = (hd1[0] == hd2[0])
    all_nonaces_identical &= hf_same and hd_same
print("\nALL non-aces (dfs, holds, breaks, svgms, total_games, hf, hd) identical V1 vs V2:", all_nonaces_identical)

print()
print("=" * 78)
print("C) SPOT CHECK -- V1 ace mean vs opponent_break_rate vs V2 adjusted mean")
print("=" * 78)
for fav, dog in pairs:
    pinn = 0.62
    df = sim.build_live_row(fav, dog, pinn, "Hard", False, False, today, m, state)
    P1, hf1, hd1, mu1 = sim.v1_inputs_from_rows(df, m)
    P2, hf2, hd2, mu2 = sim2.v2_inputs_from_rows(df, m)
    print(f"\n{fav} vs {dog}  (pinn_fav={pinn})")
    for side, nm in (("fav", fav), ("dog", dog)):
        opp = "dog" if side == "fav" else "fav"
        obr = df["%s_W%d_K%d_break_rate" % (opp, W, K)].values[0]
        mb = m["mean_break_rate"]
        v1_mean = mu1[side][0][0]
        v2_mean = mu2[side][0][0]
        expected_sign = "DOWN (opp above-average returner)" if obr > mb else "UP (opp below-average returner)" if obr < mb else "unchanged (opp exactly average)"
        actual_dir = "DOWN" if v2_mean < v1_mean else "UP" if v2_mean > v1_mean else "unchanged"
        print(f"  {nm}: V1 ace mu={v1_mean:.5f}  opponent_break_rate={obr:.5f} (pop mean={mb:.5f})  "
              f"-> V2 ace mu={v2_mean:.5f}  ({actual_dir}, expected {expected_sign})")

print()
print("=" * 78)
print("REGRESSION: SOURCE FILE INTEGRITY (V1 files must be byte-identical)")
print("=" * 78)
import hashlib
for fn in ("apex_prop_model_v1.py", "apex_prop_sim_v1.py"):
    print(" ", fn, hashlib.md5(open(fn, "rb").read()).hexdigest())
