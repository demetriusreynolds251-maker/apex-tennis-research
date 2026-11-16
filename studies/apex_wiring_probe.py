#!/usr/bin/env python3
"""
APEX-WIRING-PROBE-2026-08-27 -- end-to-end wiring proof
=======================================================

Proves, per category, that the REAL code path completes:

    prop dict (shaped exactly as the screenshot parser builds it)
      -> openclaw_core._apex_engine_pick        (real engine pick + card)
      -> apex_prop_sim_forward_log (probe copy)  (real forward-log writer)
      -> apex_prop_sim_v1.cmd_settle_sackmann    (real settlement, real score)
      -> apex_prop_sim_v1.cmd_report             (real report)

What it does NOT prove: the screenshot -> prop dict step (the vision model).
That needs a real screenshot through the bot; see the end of the output.

Isolation: the core and simulator log-file constants are pointed at probe
files (apex_probe_*.csv) before anything runs, so the LIVE forward logs are
never read or written. The test match is a match that has already finished
and is present in the Sackmann/TennisMyLife year files, so settlement uses a
real score, today. Price for a finished match cannot come from the feed, so
the prop carries typed odds -- the card will say price_source=typed. That is a
test input, not a wiring shortcut.

Run:  cd ~/openclaw && python3 apex_wiring_probe.py [--all] [--sackmann-dir DIR]
      --all  also exercises the five newly wired categories
"""
import argparse, glob, io, math, os, re, sys, contextlib
from datetime import datetime, timedelta

MARKER = "APEX-WIRING-PROBE-2026-08-27"

PRIORITY = [
    # (display name, PrizePicks label as shown, engine category, line, on_loser)
    ("Fantasy Score",  "Fantasy Score",   "fantasy_score", 17.5, False),
    ("Sets Won",       "Sets Won",        "sets_won",       1.5, False),
    ("Total Sets",     "Total Sets",      "total_sets",     2.5, False),
    ("Tiebreak Count", "Total Tie Breaks","tiebreaks",      0.5, False),
]
EXTRA = [
    ("First Set Games",  "First Set Games",  "first_set_games",    9.5, False),
    ("Any Tiebreak",     "Any Tiebreak",     "any_tiebreak",       0.5, False),
    ("First Set Winner", "First Set Winner", "first_set_fav_wins", 0.5, True),   # on the dog -> exercises the flip
    ("Goes 3 Sets",      "Goes 3 Sets",      "goes_3_sets",        0.5, False),
    ("Goes 5 Sets",      "Goes 5 Sets",      "goes_5_sets",        0.5, False),
]

OK, BAD = "\u2705", "\u274c"


def sackmann_default(sim_module):
    src = open(sim_module.__file__, encoding="utf-8").read()
    m = re.search(r"--sackmann-dir[^\n]*?default\s*=\s*(['\"])(.*?)\1", src)
    return m.group(2) if m else None


def truth_from_row(c, sim, on_winner=True):
    """Ground truth computed directly from the Sackmann row (same formulas the
    settler uses, evaluated here independently so the two can be compared)."""
    ps = sim.parse_score(c["score"]); sets = ps["sets"]
    tg = sum(a + b for a, b, _ in sets)
    p, o = ("w_", "l_") if on_winner else ("l_", "w_")
    gw = sum((a if on_winner else b) for a, b, _ in sets); gl = tg - gw
    sw = sum(1 for a, b, _ in sets if (a > b) == on_winner); sl = len(sets) - sw
    fs = 10.0 + (gw - gl) + 3.0 * (sw - sl) + 0.5 * (float(c[p + "ace"]) - float(c[p + "df"]))
    return {"fantasy_score": fs, "sets_won": sw, "total_sets": len(sets),
            "tiebreaks": sum(s[2] for s in sets), "any_tiebreak": int(any(s[2] for s in sets)),
            "first_set_games": sets[0][0] + sets[0][1],
            "goes_3_sets": int(len(sets) == 3 if int(c["best_of"]) == 3 else len(sets) >= 3),
            "goes_5_sets": int(len(sets) == 5),
            "first_set_fav_wins": int(sets[0][0] > sets[0][1])}   # winner is the fav in this probe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sackmann-dir", default=None)
    ap.add_argument("--keep", action="store_true", help="keep the probe csv files afterwards")
    a = ap.parse_args()

    print(MARKER, datetime.now().isoformat(timespec="seconds"))
    try:
        import pandas as pd, numpy as np
        import apex_prop_model_v1 as v1
        import apex_prop_sim_v1 as sim
        import apex_prop_engine as eng
        import openclaw_core as core
    except Exception as e:
        sys.exit(f"import failed: {type(e).__name__}: {e}\n(run from ~/openclaw with the same python the bot uses)")

    # ---- isolation: probe logs only -----------------------------------------
    probe = {"sim": "apex_probe_sim_forward_log.csv", "pick": "apex_probe_engine_picks_log.csv",
             "decl": "apex_probe_engine_declines_log.csv"}
    for f in probe.values():
        if os.path.exists(f): os.remove(f)
    core._APEX_SIM_LOG = probe["sim"]; core._APEX_PICK_LOG = probe["pick"]; core._APEX_DECLINE_LOG = probe["decl"]
    sim.SIM_LOG = probe["sim"]
    live = ("apex_prop_sim_forward_log_v1.csv", "apex_engine_picks_log_v1.csv")
    live_sha = {f: (open(f, "rb").read() if os.path.exists(f) else b"") for f in live}
    print(f"isolation: core/sim logs -> {probe['sim']}, {probe['pick']} (live logs untouched)")

    # ---- patch presence -----------------------------------------------------
    core_src = open(core.__file__, encoding="utf-8").read()
    if "APEX-WIRING-2026-08-27" not in core_src:
        sys.exit("openclaw_core.py does not carry APEX-WIRING-2026-08-27 -- run apex_wiring_patch.py first")
    smap = core._APEX_STAT_MAP
    print("stat map:", ", ".join(f"{k}->{v}" for k, v in smap.items()
                                 if v in ("fantasy_score", "sets_won", "total_sets", "tiebreaks")))
    print("engine:", eng.status().replace("\n", " | "))

    # ---- sackmann + test match ----------------------------------------------
    sdir = a.sackmann_dir or sackmann_default(sim)
    if not sdir or not os.path.isdir(sdir):
        sys.exit(f"Sackmann dir not found ({sdir!r}); pass --sackmann-dir")
    df = v1.load_sackmann(sdir, year_from=datetime.now().year - 1, challengers=False)
    print(f"sackmann: {sdir}  rows {len(df)}  latest tourney_date {df['tourney_date'].max().date()}")
    need = ["w_ace", "l_ace", "w_df", "l_df", "w_SvGms", "l_SvGms", "w_bpFaced", "l_bpFaced", "w_bpSaved", "l_bpSaved"]
    cand = df.dropna(subset=need).sort_values("tourney_date", ascending=False)
    wta_col = next((c for c in ("is_wta", "wta", "tour") if c in df.columns), None)

    chosen = None
    for _, c in cand.head(200).iterrows():
        ps = sim.parse_score(c["score"])
        if not ps or ps["retired"] or int(c["best_of"]) not in (3, 5): continue
        # the settler needs exactly one meeting of this pair in the 21-day window
        w, l = v1.norm_name(c["winner_name"]), v1.norm_name(c["loser_name"])
        md = c["tourney_date"] + pd.Timedelta(days=3)
        win = df[(df["tourney_date"] >= md - pd.Timedelta(days=21)) & (df["tourney_date"] <= md)]
        win = win[win["winner_name"].map(v1.norm_name).isin([w, l]) & win["loser_name"].map(v1.norm_name).isin([w, l])]
        if len(win) != 1: continue
        wta = False
        if wta_col:
            v = c[wta_col]; wta = (str(v).lower() in ("1", "true", "wta"))
        r = eng.evaluate_match(c["winner_name"], c["loser_name"], 0.60, surface=str(c["surface"]),
                               bo5=int(c["best_of"]) == 5, wta=wta, sims=4000)
        if r and r.get("ok"):
            chosen = (c, wta, md); break
    if chosen is None:
        sys.exit("no finished match with full stats that the frozen engine can evaluate -- refresh the player state?")
    c, wta, md = chosen
    W, L = c["winner_name"], c["loser_name"]
    bo5 = int(c["best_of"]) == 5
    print(f"\nTEST MATCH  {c['tourney_name']}  {c['tourney_date'].date()}  {W} d. {L}  {c['score']}  "
          f"{c['surface']} Bo{c['best_of']}  (aces {int(c['w_ace'])}/{int(c['l_ace'])}, dfs {int(c['w_df'])}/{int(c['l_df'])})")
    truth_w = truth_from_row(c, sim, True); truth_l = truth_from_row(c, sim, False)

    dates = {"match_date": md.date().isoformat(), "pipeline_run_date": datetime.now().date().isoformat()}
    cats = PRIORITY + (EXTRA if a.all else [])
    results = {}

    # ---- 1. engine card + forward log, per category --------------------------
    for disp, label, cat, line, on_loser in cats:
        slug = core.normalize_stat_type(label)
        player, opp = (L, W) if on_loser else (W, L)
        prop = {  # shaped as the screenshot parser builds it
            "player": player, "opponent": opp, "stat_type": slug, "line": line, "direction": "MORE",
            "prop_type": "standard", "prop_type_classified": "standard",
            "tournament": str(c["tourney_name"]), "surface": str(c["surface"]).title(),
            "tour": "wta" if wta else "atp", "match_format": "bo5" if bo5 else "bo3",
            "is_grand_slam": False, "match_date": dates["match_date"],
            "slip_start_ct": f"{dates['match_date']}T12:00:00",
            # typed odds: a finished match has no live price. Winner priced as favorite.
            "apex_player_odds": "+125" if on_loser else "-150",
            "apex_opponent_odds": "-150" if on_loser else "+125",
        }
        print(f"\n== {disp}  (label '{label}' -> slug '{slug}' -> category '{smap.get(slug)}')  line {line}  player {player}")
        if smap.get(slug) != cat:
            print(f"  {BAD} slug '{slug}' does not map to '{cat}' (maps to {smap.get(slug)!r})")
            results[disp] = {"card": False, "log": False}; continue
        res = core._apex_engine_pick(prop, dates, f"PROBE-{cat}")
        if not res:
            print(f"  {BAD} Card Created -- engine declined: {prop.get('apex_decline_reason')}")
            results[disp] = {"card": False, "log": False}; continue
        card = res.get("_apex_engine_card") or ""
        card_ok = bool(card.strip()) and "EXPERIMENTAL" in card
        print(f"  {OK if card_ok else BAD} Card Created  -> {res['direction']} p={res['confidence']:.3f} tier={res['apex_tier']} "
              f"price_source={prop.get('apex_price_source')}")
        for ln in card.splitlines()[1:6]:
            print("      " + ln)
        # forward log row?
        rows = sim.read_log() if os.path.exists(probe["sim"]) else []
        mine = [r for r in rows if r["category"] == cat]
        log_ok = len(mine) == 1 and bool(mine[0]["line"])
        if log_ok:
            r = mine[0]
            print(f"  {OK} Forward Log Written -> match_id {r['match_id']} player {r['player']} {cat} line {r['line']} "
                  f"p_over {r['p_over']} p_under {r['p_under']} match_date {r['match_date']}")
        else:
            print(f"  {BAD} Forward Log Written -- {len(mine)} row(s) for {cat} in {probe['sim']}")
        results[disp] = {"card": card_ok, "log": log_ok, "res": res}

    # ---- 2. settlement (real code, real score) -------------------------------
    print("\n== SETTLEMENT  (apex_prop_sim_v1.cmd_settle_sackmann on the probe log)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sim.cmd_settle_sackmann(argparse.Namespace(sackmann_dir=sdir))
    print("  settler said:", buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else "(no output)")
    rows = sim.read_log()
    for disp, label, cat, line, on_loser in cats:
        if not results.get(disp, {}).get("log"):
            if disp in results: results[disp]["settle"] = False
            continue
        r = next((x for x in rows if x["category"] == cat), None)
        truth = (truth_l if (on_loser and cat not in core._APEX_MATCH_LEVEL) else truth_w).get(cat)
        settled = bool(r and r["actual"])
        agree = settled and abs(float(r["actual"]) - float(truth)) < 1e-6
        results[disp]["settle"] = settled and agree
        if settled:
            print(f"  {OK if agree else BAD} Settlement Completed  {disp}: actual {r['actual']}  (probe truth from score: {truth})"
                  + ("" if agree else "  MISMATCH"))
        else:
            print(f"  {BAD} Settlement Completed  {disp}: row still open (settler could not match the score row)")

    # ---- 3. report ----------------------------------------------------------
    print("\n== REPORT  (apex_prop_sim_v1.cmd_report on the probe log)")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sim.cmd_report(argparse.Namespace())
    rep = buf.getvalue()
    for disp, label, cat, line, on_loser in cats:
        if disp not in results: continue
        ln = next((x for x in rep.splitlines() if x.strip().startswith(cat + " ")), None)
        results[disp]["report"] = bool(ln)
        print(f"  {OK if ln else BAD} Report Entry Generated  {disp}" + (f":{ln}" if ln else ""))

    # ---- summary ------------------------------------------------------------
    print("\n== SUMMARY")
    allok = True
    for disp, label, cat, line, on_loser in cats:
        rr = results.get(disp, {})
        marks = [rr.get(k, False) for k in ("card", "log", "settle", "report")]
        allok &= all(marks) or disp not in dict((p[0], 1) for p in PRIORITY)
        print(f"  {disp:17s} " + "  ".join(f"{OK if m else BAD} {n}" for m, n in
              zip(marks, ("Card Created", "Forward Log Written", "Settlement Completed", "Report Entry Generated"))))
    # live logs untouched?
    for f in live:
        now = open(f, "rb").read() if os.path.exists(f) else b""
        print(f"  live log {f}: {'untouched' if now == live_sha[f] else 'CHANGED -- investigate'}")
    if not a.keep:
        for f in probe.values():
            if os.path.exists(f): os.remove(f)
    print("\nNOT proven here: screenshot -> prop dict (vision). Send one real PrizePicks screenshot each for "
          "Fantasy Score, Sets Won, Total Tie Breaks through the bot and check the log for "
          "'ENGINE_PICK <player> fantasy_score|sets_won|total_tie_breaks'.")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
