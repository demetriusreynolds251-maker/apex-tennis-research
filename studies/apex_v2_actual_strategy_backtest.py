"""
APEX-ACTUAL-STRATEGY-BACKTEST-2026-09-27
Read-only. Never touches apex_prop_sim_v1.py, apex_prop_model_v1.py, or
apex_prop_engine.py -- no re-simulation at all. Reuses old_prob from
apex_backtest_rows_cache.pkl (the true historical / live-at-the-time
probability for every category, every real settled pick, all 13 real
trading days) -- this alone satisfies "no hindsight" / "the board that
would have existed at that time" with zero re-simulation risk.

Board-construction/scoring (apex_score, apex_confidence, rank_score,
_bb_sortkey, _demote_bo5_from_top, slip_builder) imported and called exactly
as they run in production today -- not reimplemented.

slip_builder always builds a full 5-slot ranked slip in one pass (SLIP_SLOTS
is a fixed module constant, not parameterized) -- confirmed by direct source
inspection. Slots 1-3 of a single 5-slot run already have the tighter
category+direction cap applied (the code branches on rank position <=3 vs
>3 inside one pass), so Top-1..Top-5 are obtained by slicing slots 1..N from
ONE slip_builder call, not by five separate truncated calls -- these are the
real, valid slip configurations, not an approximation.

Dollar ROI/P&L is computed only for N=3 (Standard/Goblin 3-pick Flex payout
tables already validated this session). For N=1,2,4,5, PrizePicks' official
payout tables are not held here and are NOT fabricated -- board quality
across N is instead measured with un-monetized accuracy metrics (perfect-hit
rate, avg legs won) which need no payout assumption at all.
"""
import os, sys, json, math
import pandas as pd, numpy as np
from collections import defaultdict

HERE = "/path/to/home/openclaw"
sys.path.insert(0, HERE)
os.chdir(HERE)
import apex_edge_tracker as et

LOG_PATH = os.path.join(HERE, "apex_v2_actual_strategy_backtest.log")
OUT_JSON = os.path.join(HERE, "apex_v2_actual_strategy_backtest_results.json")

def log(msg):
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")
    print(msg)

open(LOG_PATH, "w").close()
log("=== APEX actual-strategy backtest start ===")

df = pd.read_pickle(os.path.join(HERE, "apex_backtest_rows_cache.pkl"))
df = df[df["actual"].notna()].copy()   # only real, settled, graded rows
log("graded rows available=%d" % len(df))

REC = et.records()
log("REC overall n=%d" % REC["overall"]["n"])

days = sorted(df["match_date"].unique())
log("trading days=%d : %s" % (len(days), days))
tagged_days = sorted(df[df["prop_type"].notna()]["match_date"].unique())
log("days with real prop_type tags=%d : %s" % (len(tagged_days), tagged_days))

def build_d(row):
    prob = row["old_prob"]
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

def build_day_board(day_rows):
    scored = [build_d(r) for _, r in day_rows.iterrows()]
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

PAYOUT3 = {"standard": {3: 3.0, 2: 1.0, 1: 0.0, 0: 0.0},
           "goblin":   {3: 2.5, 2: 0.5, 1: 0.0, 0: 0.0}}
STAKE = 100.0

def slip_legs_n(scored, kind, n):
    """Slice slots 1..n from ONE slip_builder pass (mixed = first n non-bo5
    picks in rank order, one per player -- board is already deduped)."""
    if kind == "mixed":
        return [d for d in scored if not d["bo5"]][:n]
    sm = et.slip_builder(scored, kind)
    slotted = sorted((v[0], d) for d in scored if (v := sm.get(id(d))) and v[0])
    return [d for slot, d in slotted if slot <= n]

def grade_legs(legs):
    graded = [grade_leg(d) for d in legs]
    if any(g is None for g in graded):
        return None
    return graded

def slip_result(legs, kind, n):
    """Accuracy-only result (no payout assumption) for any N; adds dollar
    P&L only when n==3, using the already-validated 3-pick Flex tables."""
    if len(legs) != n:
        return None
    graded = grade_legs(legs)
    if graded is None:
        return None
    hits = sum(1 for g in graded if g)
    out = {"n": n, "hits": hits, "perfect": hits == n, "hit_rate": hits / n}
    if n == 3:
        # "mixed" isn't its own PrizePicks slip type -- it allows both MORE/LESS
        # like Standard does (unlike Goblin, which is MORE-only), so it is graded
        # on the Standard payout table, matching the convention already used and
        # shown to the user in the prior dispersion-profitability report.
        payout_key = "standard" if kind == "mixed" else kind
        mult = PAYOUT3[payout_key][hits]
        out["mult"] = mult
        out["pnl"] = STAKE * (mult - 1.0)
    return out

KINDS = ("mixed", "standard", "goblin")
NS = (1, 2, 3, 4, 5)

per_day = {}
for day in days:
    day_rows = df[df["match_date"] == day]
    board = build_day_board(day_rows)
    entry = {"day": day, "n_rows": len(day_rows), "n_board": len(board)}
    for kind in KINDS:
        entry[kind] = {}
        for n in NS:
            legs = slip_legs_n(board, kind, n)
            res = slip_result(legs, kind, n)
            entry[kind][n] = {
                "legs": [d["p"]["player"] + "|" + d["cat"] + "|" + d["p"]["direction"] for d in legs],
                "result": res,
            }
    per_day[day] = entry
    log("day %s: board=%d mixed3=%s standard3=%s goblin3=%s" % (
        day, len(board), entry["mixed"][3]["legs"], entry["standard"][3]["legs"], entry["goblin"][3]["legs"]))

def agg_kind_n(kind, n):
    """Accuracy-only aggregate across all 13 real days for one (kind, n)."""
    rows = []
    for day in days:
        res = per_day[day][kind][n]["result"]
        if res:
            rows.append((day, res))
    if not rows:
        return {"n_slips": 0}
    hits_list = [r["hits"] for _, r in rows]
    perfects = sum(1 for _, r in rows if r["perfect"])
    out = {"n_slips": len(rows), "avg_legs_won": round(np.mean(hits_list), 3),
           "avg_leg_hit_rate": round(np.mean([r["hit_rate"] for _, r in rows]), 4),
           "perfect_slip_rate": round(perfects / len(rows), 4),
           "days": [d for d, _ in rows]}
    if n == 3:
        pnls = [r["pnl"] for _, r in rows]
        wins = sum(1 for p in pnls if p > 0)
        out["win_rate"] = round(wins / len(pnls), 4)
        out["loss_rate"] = round(1 - wins / len(pnls), 4)
        out["profit_loss"] = round(sum(pnls), 2)
        out["roi"] = round(sum(pnls) / (len(pnls) * STAKE), 4)
        streak = cur = 0
        for p in pnls:  # chronological already (days sorted)
            if p <= 0:
                cur += 1; streak = max(streak, cur)
            else:
                cur = 0
        out["longest_losing_streak"] = streak
    return out

board_quality = {kind: {n: agg_kind_n(kind, n) for n in NS} for kind in KINDS}
for kind in KINDS:
    for n in NS:
        log("%s top-%d: %s" % (kind, n, board_quality[kind][n]))

# ---- drawdown + weekly win-day bucketing, using mixed Top-3 (all 13 real
# days) as the primary proxy -- it is the only kind with full-sample
# coverage; true Standard/Goblin tags exist for only 2 of the 13 days. ----
def daily_pnl_series(kind):
    out = []
    for day in days:
        res = per_day[day][kind][3]["result"]
        out.append((day, res["pnl"] if res else None))
    return out

def drawdown_stats(series):
    vals = [p for _, p in series if p is not None]
    if not vals:
        return {"max_drawdown": None}
    cum, peak, maxdd = 0.0, 0.0, 0.0
    for p in vals:
        cum += p
        peak = max(peak, cum)
        maxdd = min(maxdd, cum - peak)
    return {"max_drawdown": round(maxdd, 2), "ending_cum_pnl": round(cum, 2)}

mixed3_series = daily_pnl_series("mixed")
mixed3_dd = drawdown_stats(mixed3_series)
log("mixed3 daily pnl series: %s" % mixed3_series)
log("mixed3 drawdown: %s" % mixed3_dd)

def iso_week(d):
    y, w, _ = pd.Timestamp(d).isocalendar()
    return "%d-W%02d" % (y, w)

weekly = defaultdict(lambda: {"trading_days": 0, "winning_days": 0, "days": []})
for day, pnl in mixed3_series:
    wk = iso_week(day)
    weekly[wk]["trading_days"] += 1
    weekly[wk]["days"].append(day)
    if pnl is not None and pnl > 0:
        weekly[wk]["winning_days"] += 1
weekly = dict(sorted(weekly.items()))
log("weekly mixed3 win-day buckets: %s" % json.dumps(weekly, indent=2))

winday_hist = defaultdict(int)
for wk, v in weekly.items():
    winday_hist[v["winning_days"]] += 1
log("distribution of winning-days-per-week (mixed3, %d weeks w/ >=1 trading day): %s" %
    (len(weekly), dict(sorted(winday_hist.items()))))

# ---- true 2-day Goblin+Standard combined bankroll illustration (thin sample) ----
combined_tagged = []
for day in tagged_days:
    s = per_day[day]["standard"][3]["result"]
    g = per_day[day]["goblin"][3]["result"]
    s_pnl = s["pnl"] if s else None
    g_pnl = g["pnl"] if g else None
    combined_tagged.append({"day": day, "standard_pnl": s_pnl, "goblin_pnl": g_pnl,
                             "day_total": (s_pnl or 0) + (g_pnl or 0) if (s_pnl is not None or g_pnl is not None) else None,
                             "day_win": ((s_pnl or 0) + (g_pnl or 0)) > 0 if (s_pnl is not None or g_pnl is not None) else None})
log("2-day tagged Goblin+Standard combined bankroll: %s" % combined_tagged)

results = {"generated": pd.Timestamp.now().isoformat(), "n_trading_days": len(days), "days": days,
           "tagged_days": tagged_days, "rec_overall_n": REC["overall"]["n"],
           "board_quality": board_quality, "per_day": per_day,
           "mixed3_daily_pnl": mixed3_series, "mixed3_drawdown": mixed3_dd,
           "weekly_mixed3": weekly, "winday_distribution_mixed3": dict(winday_hist),
           "combined_tagged_goblin_standard": combined_tagged}
with open(OUT_JSON, "w") as f:
    json.dump(results, f, indent=2, default=str)
log("wrote %s" % OUT_JSON)
log("=== done ===")
