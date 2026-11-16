"""
APEX-DISPERSION-PROFITABILITY-BACKTEST-2026-09-27
Read-only, retroactive counterfactual backtest. Never touches apex_prop_sim_v1.py,
apex_prop_model_v1.py, or apex_prop_engine.py.

Part A: re-simulate every real, settled aces/dfs pick logged in
apex_engine_picks_log_v1.csv (all of it necessarily evaluated under OLD
dispersion -- Candidate C did not go live until 2026-09-26/27) under the
current, already-patched (NEW) apex_prop_engine.evaluate_match(), same match,
same requested line. Non-aces/dfs categories are mathematically unchanged
between OLD and NEW (dispersion fix is aces/dfs-only), so their historical
logged values serve as both OLD and NEW without re-simulation.
"""
import os, sys, json, math
import pandas as pd, numpy as np

HERE = "/path/to/home/openclaw"
sys.path.insert(0, HERE)
os.chdir(HERE)

import apex_prop_engine as ape
import apex_edge_tracker as et

LOG_PATH = os.path.join(HERE, "apex_v2_dispersion_profitability_backtest.log")

def log(msg):
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")
    print(msg)

open(LOG_PATH, "w").close()
log("=== APEX dispersion profitability backtest -- Part A (resim) start ===")

picks = pd.read_csv(os.path.join(HERE, "apex_engine_picks_log_v1.csv"), low_memory=False)
picks = picks[picks["category"].notna() & (picks["category"] != "category")].copy()
picks["line"] = pd.to_numeric(picks["line"], errors="coerce")
picks = picks.sort_values("ts").drop_duplicates(subset=["match_id", "player", "category", "direction", "line"], keep="last")

sim = pd.read_csv(os.path.join(HERE, "apex_prop_sim_forward_log_v1.csv"), low_memory=False)

m = picks.merge(sim[["match_id", "player", "category", "is_fav", "pinn_fav", "surface", "best_of", "actual", "p_over", "p_under"]],
                 on=["match_id", "player", "category"], how="left", suffixes=("", "_sim"))
log("total picks rows=%d, matched to settled sim=%d" % (len(m), m["actual"].notna().sum()))

REC = et.records()   # current, real, cumulative settled category track record
log("category record snapshot n_settled overall=%d" % REC["overall"]["n"])

def wta_flag(row):
    s = (str(row.get("format_label", "")) + " " + str(row.get("tournament", ""))).lower()
    return ("women" in s) or ("wta" in s)

def new_prob_for(row):
    """Re-run the exact historical match through the LIVE (Candidate-C) engine
    for the same requested line; return the NEW-model probability of the same
    direction that was actually picked at the time. (None, err) on failure --
    caller drops the row from the counterfactual set rather than guess."""
    try:
        if pd.isna(row["is_fav"]) or pd.isna(row["pinn_fav"]) or pd.isna(row["best_of"]):
            return None, "missing is_fav/pinn_fav/best_of"
        fav = row["player"] if int(row["is_fav"]) == 1 else row["opponent"]
        dog = row["opponent"] if int(row["is_fav"]) == 1 else row["player"]
        res = ape.evaluate_match(fav, dog, float(row["pinn_fav"]), surface=str(row["surface"]),
                                  bo5=(int(row["best_of"]) == 5), wta=wta_flag(row),
                                  date=str(row["match_date"]), sims=20000,
                                  lines={row["player"] + "|" + row["category"]: float(row["line"])})
        if not res.get("ok"):
            return None, res.get("error")
        for p in res["props"]:
            if p["player"] == row["player"] and p["category"] == row["category"]:
                if p["p_over"] is None:
                    return None, "no line resolved"
                return (p["p_over"] if str(row["direction"]).upper() == "MORE" else p["p_under"]), None
        return None, "no matching prop"
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)

def cal_ratio(row):
    """ACESCAL overlay (aces-LESS calibration) is independent of dispersion and
    unchanged by this deployment. Carry its observed multiplicative effect
    through to the NEW probability so OLD-vs-NEW isolates dispersion only."""
    try:
        pc = float(row.get("prob_cal")) if pd.notna(row.get("prob_cal")) else None
        p = float(row["prob"])
        if pc is not None and p > 0:
            return pc / p
    except Exception:
        pass
    return 1.0

rows = []
n_aces_dfs = 0
n_resim_ok = 0
n_resim_fail = 0
for i, row in m.iterrows():
    cat = row["category"]
    is_dispersion_cat = cat in ("aces", "dfs")
    old_prob = float(row["prob_cal"]) if pd.notna(row.get("prob_cal")) else float(row["prob"])
    new_prob = old_prob
    resim_err = None
    if is_dispersion_cat:
        n_aces_dfs += 1
        np_, err = new_prob_for(row)
        if np_ is not None:
            new_prob = max(0.0, min(1.0, np_ * cal_ratio(row)))
            n_resim_ok += 1
        else:
            resim_err = err
            n_resim_fail += 1
    bo5 = bool(int(row["best_of"]) == 5) if pd.notna(row.get("best_of")) else False
    rows.append({"idx": int(i), "match_date": row["match_date"], "match_id": row["match_id"],
                 "player": row["player"], "opponent": row["opponent"], "category": cat,
                 "line": row["line"], "direction": row["direction"], "bo5": bo5,
                 "prop_type": (str(row["prop_type"]).lower() if pd.notna(row.get("prop_type")) else None),
                 "pinn_fav": row.get("pinn_fav"), "edge": row.get("edge"),
                 "actual": row.get("actual"), "old_prob": old_prob, "new_prob": new_prob,
                 "resim_err": resim_err, "is_dispersion_cat": is_dispersion_cat})
    if is_dispersion_cat and n_aces_dfs % 25 == 0:
        log("...resimulated %d aces/dfs rows (ok=%d fail=%d)" % (n_aces_dfs, n_resim_ok, n_resim_fail))

log("DONE aces/dfs rows=%d resim_ok=%d resim_fail=%d" % (n_aces_dfs, n_resim_ok, n_resim_fail))
rowdf = pd.DataFrame(rows)
rowdf.to_pickle(os.path.join(HERE, "apex_backtest_rows_cache.pkl"))
log("cached per-row old/new probabilities to apex_backtest_rows_cache.pkl, shape=%s" % (rowdf.shape,))
