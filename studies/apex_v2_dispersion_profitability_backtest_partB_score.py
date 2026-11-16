"""
APEX-DISPERSION-PROFITABILITY-BACKTEST-2026-09-27 -- Part B (score + slip + grade)
Read-only. Uses the Part-A cache (apex_backtest_rows_cache.pkl); does not
re-simulate. Reconstructs each real historical trading day's board TWICE
(OLD probability vs NEW probability for aces/dfs rows only) using the
UNMODIFIED, currently-live apex_edge_tracker.apex_score / apex_confidence /
rank_score / _bb_sortkey / _demote_bo5_from_top / slip_builder functions --
the exact board-ranking logic that exists today, applied identically to both
model variants so the only thing that differs is the probability input.
Grades every slip against the REAL settled outcome already in the logs.
"""
import os, sys, json, math
import pandas as pd, numpy as np

HERE = "/path/to/home/openclaw"
sys.path.insert(0, HERE)
os.chdir(HERE)
import apex_edge_tracker as et

LOG_PATH = os.path.join(HERE, "apex_v2_dispersion_profitability_backtest_partB.log")
OUT_JSON = os.path.join(HERE, "apex_v2_dispersion_profitability_backtest_results.json")

def log(msg):
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")
    print(msg)

open(LOG_PATH, "w").close()
log("=== Part B start ===")

df = pd.read_pickle(os.path.join(HERE, "apex_backtest_rows_cache.pkl"))
df = df[df["actual"].notna()].copy()   # only real, settled, graded rows
log("graded rows available=%d" % len(df))

REC = et.records()
log("REC overall n=%d" % REC["overall"]["n"])

def build_d(row, variant):
    prob = row["old_prob"] if variant == "old" else row["new_prob"]
    cat = row["category"]; bo5 = bool(row["bo5"])
    sc, ev, lvl, up, down = et.apex_score(prob, cat, bo5, REC)
    conf, _ctier, cwhy = et.apex_confidence(cat, bo5, REC, warnings=down, card_present=False)
    rank = et.rank_score(sc, conf)
    p = {"player": row["player"], "opponent": row["opponent"], "category": cat,
         "direction": row["direction"], "line": row["line"], "prob": prob,
         "edge": row["edge"], "match_id": row["match_id"],
         "prop_type": row["prop_type"] or "", "bo5": bo5,
         "best_of": 5 if bo5 else 3, "pinn_fav": row["pinn_fav"]}
    return {"p": p, "cat": cat, "score": sc, "ev": ev, "lvl": lvl, "conf": conf,
            "rank": rank, "up": up, "down": down, "bo5": bo5,
            "actual": row["actual"], "key": (row["match_id"], row["player"], cat, row["direction"])}

def dedupe_one_per_player(scored):
    seen, prim = {}, []
    for d in scored:
        pk = (d["p"].get("player") or "") + "|" + (d["p"].get("opponent") or "")
        if pk in seen:
            continue
        seen[pk] = d; prim.append(d)
    return prim

def build_day_board(day_rows, variant):
    scored = [build_d(r, variant) for _, r in day_rows.iterrows()]
    scored.sort(key=lambda d: et._bb_sortkey(d))
    scored = dedupe_one_per_player(scored)
    scored = et._demote_bo5_from_top(scored)
    return scored

def grade_leg(d):
    """True=won, False=lost, None=push/unknown."""
    actual = d["actual"]; line = d["p"]["line"]; direction = str(d["p"]["direction"]).upper()
    if actual is None or pd.isna(actual) or line is None or pd.isna(line):
        return None
    if direction == "MORE":
        return True if actual > line else (False if actual < line else None)
    return True if actual < line else (False if actual > line else None)

PAYOUT = {  # 3-pick Flex payout tables, PrizePicks
    "standard": {3: 3.0, 2: 1.0, 1: 0.0, 0: 0.0},
    "goblin":   {3: 2.5, 2: 0.5, 1: 0.0, 0: 0.0},
}
STAKE = 100.0

def grade_slip(legs, kind):
    graded = [grade_leg(d) for d in legs]
    if any(g is None for g in graded) or len(graded) < 3:
        return None
    hits = sum(1 for g in graded if g)
    mult = PAYOUT[kind][hits]
    pnl = STAKE * (mult - 1.0)
    return {"hits": hits, "mult": mult, "pnl": pnl, "legs": [
        {"player": d["p"]["player"], "category": d["cat"], "line": d["p"]["line"],
         "direction": d["p"]["direction"], "prob": round(d["p"]["prob"], 4),
         "score": d["score"], "conf": d["conf"], "rank": d["rank"], "actual": d["actual"],
         "won": g} for d, g in zip(legs, graded)]}

def top3_mixed(scored):
    return [d for d in scored if not d["bo5"]][:3]

def slip_legs(scored, kind):
    if kind == "mixed":
        return top3_mixed(scored)
    sm = et.slip_builder(scored, kind)
    slotted = sorted((v[0], d) for d in scored if (v := sm.get(id(d))) and v[0])
    return [d for _, d in slotted[:3]]

days = sorted(df["match_date"].unique())
log("trading days=%d : %s" % (len(days), days))

per_day = {}
for day in days:
    day_rows = df[df["match_date"] == day]
    old_board = build_day_board(day_rows, "old")
    new_board = build_day_board(day_rows, "new")
    entry = {"day": day, "n_rows": len(day_rows)}
    for kind in ("mixed", "standard", "goblin"):
        ob_legs = slip_legs(old_board, kind)
        nb_legs = slip_legs(new_board, kind)
        entry[kind] = {
            "old_legs": [d["p"]["player"] + "|" + d["cat"] + "|" + d["p"]["direction"] for d in ob_legs],
            "new_legs": [d["p"]["player"] + "|" + d["cat"] + "|" + d["p"]["direction"] for d in nb_legs],
            "old_slip": grade_slip(ob_legs, "goblin" if kind == "goblin" else "standard") if len(ob_legs) == 3 else None,
            "new_slip": grade_slip(nb_legs, "goblin" if kind == "goblin" else "standard") if len(nb_legs) == 3 else None,
        }
    per_day[day] = entry
    log("day %s: rows=%d mixed_old=%s mixed_new=%s" % (day, len(day_rows), entry["mixed"]["old_legs"], entry["mixed"]["new_legs"]))

def agg(kind, variant):
    slips, legs_all = [], []
    for day, entry in per_day.items():
        s = entry[kind]["%s_slip" % variant]
        if s:
            slips.append((day, s))
            legs_all.extend(s["legs"])
    n = len(slips)
    if n == 0:
        return {"n_slips": 0}
    wins = sum(1 for _, s in slips if s["pnl"] > 0)
    losses = n - wins
    total_pnl = sum(s["pnl"] for _, s in slips)
    total_staked = n * STAKE
    return {"n_slips": n, "win_rate": round(wins / n, 4), "loss_rate": round(losses / n, 4),
            "roi": round(total_pnl / total_staked, 4), "profit_loss": round(total_pnl, 2),
            "avg_confidence": round(np.mean([l["conf"] for l in legs_all]), 2),
            "avg_edge": round(np.mean([abs(l["prob"] - 0.542) for l in legs_all]), 4),
            "avg_slip_hit_rate": round(np.mean([s["hits"] / 3.0 for _, s in slips]), 4),
            "days": [d for d, _ in slips]}

summary = {}
for kind in ("mixed", "standard", "goblin"):
    summary[kind] = {"old": agg(kind, "old"), "new": agg(kind, "new")}
    log("%s OLD: %s" % (kind, summary[kind]["old"]))
    log("%s NEW: %s" % (kind, summary[kind]["new"]))

# ---- board-membership change: did picks actually change, day by day, kind by kind ----
membership = {}
for kind in ("mixed", "standard", "goblin"):
    changes = []
    for day, entry in per_day.items():
        old_set, new_set = set(entry[kind]["old_legs"]), set(entry[kind]["new_legs"])
        if old_set != new_set:
            changes.append({"day": day, "removed": sorted(old_set - new_set),
                             "added": sorted(new_set - old_set),
                             "old": entry[kind]["old_legs"], "new": entry[kind]["new_legs"]})
    membership[kind] = changes
    log("%s membership changes on %d/%d days" % (kind, len(changes), len(per_day)))

# ---- per-category leg-level calibration: every settled aces/dfs pick, old vs new prob ----
cat_stats = {}
for cat in ("aces", "dfs"):
    sub = df[df["category"] == cat].copy()
    def _win(row):
        a, l, d = row["actual"], row["line"], str(row["direction"]).upper()
        if pd.isna(a) or pd.isna(l):
            return None
        if d == "MORE":
            return True if a > l else (False if a < l else None)
        return True if a < l else (False if a > l else None)
    sub["won"] = sub.apply(_win, axis=1)
    sub = sub[sub["won"].notna()]
    cat_stats[cat] = {
        "n": len(sub),
        "actual_hit_rate": round(sub["won"].mean(), 4),
        "old_avg_stated_prob": round(sub["old_prob"].mean(), 4),
        "new_avg_stated_prob": round(sub["new_prob"].mean(), 4),
        "old_brier": round(float(np.mean((sub["old_prob"] - sub["won"].astype(float)) ** 2)), 4),
        "new_brier": round(float(np.mean((sub["new_prob"] - sub["won"].astype(float)) ** 2)), 4),
    }
    log("cat %s: %s" % (cat, cat_stats[cat]))

results = {"generated": pd.Timestamp.now().isoformat(), "n_trading_days": len(days), "days": days,
           "rec_overall_n": REC["overall"]["n"], "summary": summary, "membership_changes": membership,
           "category_leg_stats": cat_stats, "per_day": per_day}
with open(OUT_JSON, "w") as f:
    json.dump(results, f, indent=2, default=str)
log("wrote %s" % OUT_JSON)
log("=== Part B done ===")
