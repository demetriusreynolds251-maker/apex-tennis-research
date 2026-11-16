"""
apex_dispersion_fwd_board_audit.py

Diagnostic only. Takes the most recent real aces board actually logged by
production (apex_engine_picks_log_v1.csv, match_date=2026-09-25, category=aces
-- the last live slate; 2026-09-26 has no aces rows logged yet), re-derives
fav/dog identity per match from the sim log's is_fav column, and for each of
the 20 logged per-player aces picks:
  1. re-runs PRODUCTION fresh (apex_prop_engine.evaluate_match) to confirm the
     logged probability reproduces exactly,
  2. runs the DISPERSION-FWD candidate (own fitted r, ATP dm=0.6/WTA dm=0.4,
     aces-only scope) on the SAME line and SAME direction,
using the identical "prob = raw/(p_over+p_under)" formula production itself
uses (openclaw_core.py APEX-ENGINE-ONLY-2026-08-24), so old vs new is a true
apples-to-apples comparison of the same stated pick's confidence.

Read-only against the two frozen V1 files and against apex_prop_engine.py.
Writes nothing back to any production log. MD5-checked before/after.
"""
import csv
import hashlib
import numpy as np

FROZEN = {
    "apex_prop_sim_v1.py": "7b03e521e804862b85804f8ac4db7346",
    "apex_prop_model_v1.py": "6bf50622a1761156a77ad0d35a2007f6",
}

def md5_check(tag):
    for fn, expected in FROZEN.items():
        got = hashlib.md5(open(fn, "rb").read()).hexdigest()
        status = "PASS" if got == expected else "FAIL"
        print("MD5 %s [%s]: %s" % (tag, fn, status))
        if status == "FAIL":
            raise SystemExit("MD5 MISMATCH -- aborting.")

md5_check("before")

import apex_dispersion_fwd as dfwd

TARGET_DATE = "2026-09-25"

with open("apex_engine_picks_log_v1.csv") as f:
    picks = [r for r in csv.DictReader(f) if r.get("match_date") == TARGET_DATE and r.get("category") == "aces"]
with open("apex_prop_sim_forward_log_v1.csv") as f:
    # scan ALL categories for this match_date, not just "aces" -- the counterpart
    # side's is_fav often only got logged under a different category (breaks,
    # games_won, fantasy_score, etc.) when its own aces line wasn't offered.
    sim_rows = [r for r in csv.DictReader(f) if r.get("match_date") == TARGET_DATE]

print("pick log rows:", len(picks), " sim log rows:", len(sim_rows))

# match_id -> {"fav":name, "dog":name}
fav_dog = {}
for r in sim_rows:
    mid = r["match_id"]
    fav_dog.setdefault(mid, {})
    if r["is_fav"] == "1":
        fav_dog[mid]["fav"] = r["player"]
    elif r["is_fav"] == "0":
        fav_dog[mid]["dog"] = r["player"]

print("distinct matches:", len(fav_dog))
for mid, fd in fav_dog.items():
    if "fav" not in fd or "dog" not in fd:
        print("  WARNING incomplete fav/dog for", mid, fd)


import apex_prop_engine as ape

results = []
cache_shadow = {}   # match_id -> (res, cand_fav_samp, cand_dog_samp)

for p in picks:
    mid = p["match_id"]
    fd = fav_dog.get(mid)
    if not fd or "fav" not in fd or "dog" not in fd:
        print("skip (no fav/dog):", mid, p["player"], p["opponent"])
        continue
    fav, dog = fd["fav"], fd["dog"]
    wta = "women" in p["format_label"].lower()
    surface = p["surface"]
    bo5 = (p["best_of"] == "5")
    pinn = float(p["pinn_fav"])
    line = float(p["line"])
    direction = p["direction"]
    old_prob = float(p["prob"])

    if mid not in cache_shadow:
        res = ape.evaluate_match(fav, dog, pinn, surface=surface, bo5=bo5, wta=wta)
        if not res or not res.get("ok"):
            print("evaluate_match FAILED for", mid, fav, dog, res)
            cache_shadow[mid] = None
            continue
        cand = dfwd.shadow_predict(res, wta)
        # need FULL sample arrays for per-player line probabilities -- shadow_predict
        # only returns means, so re-derive the arrays the same way it does internally.
        z = ape._load()
        v1, sim = z["v1"], z["sim"]
        from datetime import date as _date
        today = _date.fromisoformat(res["date"])
        df = sim.build_live_row(res["fav"], res["dog"], pinn, surface, bo5, wta, today, z["m"], z["state"])
        _, hf, hd, mu = sim.v1_inputs_from_rows(df, z["m"])
        lv = sim.level_from(hf[0], hd[0], z["c"], sim.price_level_pred(df, z["c"])[0])
        t, _f = sim.solve_tilt(lv, pinn, z["c"]["tb_k"], res["best_of"], sigma=z["c"].get("gap_sigma", 0.0))
        hA = min(max(lv + t, 0.2), 0.995); hB = min(max(lv - t, 0.2), 0.995)
        r, dm = (dfwd.R_WTA, dfwd.DM_WTA) if wta else (dfwd.R_ATP, dfwd.DM_ATP)
        dfs_dm = z["c"].get("disp_mult", 1.0)
        s_cand = sim.simulate(hA, hB, z["c"]["tb_k"], res["best_of"],
                               (mu["fav"][0][0], mu["fav"][1][0]), (mu["dog"][0][0], mu["dog"][1][0]),
                               (r["fav"] * dm, z["c"]["disp"]["fav"]["dfs"] * dfs_dm),
                               (r["dog"] * dm, z["c"]["disp"]["dog"]["dfs"] * dfs_dm),
                               int(res.get("sims") or ape.DEFAULT_SIMS), sigma=z["c"].get("gap_sigma", 0.0))
        cache_shadow[mid] = (res, s_cand)

    entry = cache_shadow.get(mid)
    if entry is None:
        continue
    res, s_cand = entry
    is_fav_player = (p["player"] == fav)
    cand_samp = s_cand["fav"]["aces"] if is_fav_player else s_cand["dog"]["aces"]
    po = float(np.mean(cand_samp > line)); pu = float(np.mean(cand_samp < line))
    raw = po if direction == "MORE" else pu
    new_prob = (raw / (po + pu)) if (po + pu) > 0 else raw

    results.append({
        "match_id": mid, "player": p["player"], "opponent": p["opponent"], "line": line,
        "direction": direction, "old_prob": old_prob, "new_prob": new_prob,
        "drop_pp": (old_prob - new_prob) * 100.0, "wta": wta, "surface": surface,
    })


print("\n" + "=" * 100)
print("BOARD AUDIT -- %s -- %d aces picks, production vs DISPERSION-FWD candidate" % (TARGET_DATE, len(results)))
print("=" * 100)
results.sort(key=lambda r: -r["drop_pp"])
for r in results:
    print("%-18s vs %-18s | line %5.1f %-5s | old=%.4f new=%.4f | drop=%+6.2fpp | %s %s"
          % (r["player"], r["opponent"], r["line"], r["direction"], r["old_prob"], r["new_prob"],
             r["drop_pp"], "WTA" if r["wta"] else "ATP", r["surface"]))

drops = [r["drop_pp"] for r in results]
buckets = {"0-2%": 0, "2-5%": 0, "5-10%": 0, "10%+": 0, "negative (confidence rose)": 0}
for d in drops:
    if d < 0:
        buckets["negative (confidence rose)"] += 1
    elif d < 2:
        buckets["0-2%"] += 1
    elif d < 5:
        buckets["2-5%"] += 1
    elif d < 10:
        buckets["5-10%"] += 1
    else:
        buckets["10%+"] += 1

print("\n" + "=" * 100)
print("DISTRIBUTION OF CONFIDENCE DROPS (n=%d)" % len(drops))
print("=" * 100)
for k, v in buckets.items():
    print("  %-28s %d  (%.0f%%)" % (k, v, 100.0 * v / len(drops) if drops else 0))
print("\n  mean drop:   %+.2fpp" % (np.mean(drops) if drops else float("nan")))
print("  median drop: %+.2fpp" % (np.median(drops) if drops else float("nan")))
print("  min drop:    %+.2fpp" % (np.min(drops) if drops else float("nan")))
print("  max drop:    %+.2fpp" % (np.max(drops) if drops else float("nan")))

sinner_drop = 12.98
n_below_sinner = sum(1 for d in drops if d < sinner_drop)
print("\n  Sinner/Michelsen selftest drop was +%.2fpp (most_aces_fav, not a board pick)." % sinner_drop)
print("  %d of %d board picks (%.0f%%) show a SMALLER drop than Sinner's; %d (%.0f%%) show a LARGER drop."
      % (n_below_sinner, len(drops), 100.0 * n_below_sinner / len(drops) if drops else 0,
         len(drops) - n_below_sinner, 100.0 * (len(drops) - n_below_sinner) / len(drops) if drops else 0))

md5_check("after")
print("\nDONE.")
