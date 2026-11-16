#!/usr/bin/env python3
"""
apex_batch_c_audit.py -- 2026-08-17   Batch C (tactical style) AUDIT ONLY. No features are joined to a model,
no residual test is run. Answers, with exact numbers:

  1  charted match counts by year (ATP / WTA)
  2  ATP / WTA coverage of the main-tour rows (share of rows where each side has ANY chart on file before the match)
  3  profile coverage at min 3 / 5 / 10 prior charts (players and rows)
  4  BOTH-player profile coverage by year, tour, tournament level
  5  fit sample = priced rows <= 2023 with both profiles      6  score sample = priced rows 2024+
  7  distributions of every proposed style variable (per chart, per player): mean / median / p10 / p90 / missing %
  8  detectability: on the actual score sample, the standard error of a paired logloss difference for a
     null feature -> minimum realistically detectable gain (~2 SE). Reported next to the +0.002 bar.

DATA: Match Charting Project (Jeff Sackmann, GitHub). --fetch downloads the needed CSVs into ./mcp/.
Priced rows: apex_batch_a_rows.csv if present (already joined to Pinnacle), else apex_rows_cache.pkl + ./odds/.

USAGE
  python3 apex_batch_c_audit.py --fetch                # download MCP files (~150 MB), then audit
  python3 apex_batch_c_audit.py                        # audit using ./mcp/
  python3 apex_batch_c_audit.py --selftest             # sanity run on the MCP match list alone (no Apex rows needed)
"""
import argparse, os, sys, urllib.request, warnings, bisect
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_combined_model as acm

MARKER = "APEX-BATCH-C-AUDIT-2026-08-17"
BASE = "https://raw.githubusercontent.com/JeffSackmann/tennis_MatchChartingProject/master/"
STATS = ["Overview", "ServeBasics", "ServeDirection", "ReturnDepth", "ReturnOutcomes", "Rally", "NetPoints", "ShotTypes", "ShotDirection", "KeyPointsServe", "SnV"]


def fetch(mcp_dir):
    os.makedirs(mcp_dir, exist_ok=True)
    files = ["charting-m-matches.csv", "charting-w-matches.csv"] + [f"charting-{g}-stats-{s}.csv" for g in ("m", "w") for s in STATS]
    for f in files:
        dst = os.path.join(mcp_dir, f)
        if os.path.exists(dst) and os.path.getsize(dst) > 1000:
            continue
        print(f"  fetching {f} ...", end="", flush=True)
        try:
            urllib.request.urlretrieve(BASE + f, dst)
            print(f" {os.path.getsize(dst)/1e6:.1f} MB")
        except Exception as e:
            print(f" FAILED ({e})")


def rd(path, rows=None, rowcol="row"):
    """Read a stats file; keep only the row-categories needed (memory)."""
    d = pd.read_csv(path, low_memory=False, encoding_errors="replace", dtype=str)
    if rows is not None and rowcol in d.columns:
        d = d[d[rowcol].astype(str).isin(rows)]
    keys = [c for c in ("match_id", "player", "server", rowcol, "set") if c in d.columns]
    d = d.drop_duplicates(keys)
    return d.reset_index(drop=True)


def _dbg(tag):
    if os.environ.get("APEX_DEBUG"):
        import resource; print(f"    [{tag}] maxrss {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB", flush=True)


def sdiv(a, b):
    a = pd.to_numeric(a, errors="coerce"); b = pd.to_numeric(b, errors="coerce")
    return np.where((b > 0), a / b, np.nan)


# ----------------------------------------------------------------------------- style variables per chart
def build_chart_vars(mcp_dir, g):
    """One row per (match_id, player) with the proposed style variables. g = 'm' or 'w'."""
    p = lambda s: os.path.join(mcp_dir, f"charting-{g}-stats-{s}.csv")
    M = rd(os.path.join(mcp_dir, f"charting-{g}-matches.csv"))
    M["date"] = pd.to_numeric(M["match_id"].astype(str).str[:8], errors="coerce")
    M = M[M["date"].notna()]
    ov = rd(p("Overview"), ["Total"], "set")
    for c in ["serve_pts", "aces", "dfs", "first_in", "first_won", "second_in", "second_won", "bk_pts", "bp_saved", "return_pts", "return_pts_won",
              "winners", "winners_fh", "winners_bh", "unforced", "unforced_fh", "unforced_bh"]:
        ov[c] = pd.to_numeric(ov[c], errors="coerce")
    V = ov[["match_id", "player"]].copy()
    tot_pts = ov["serve_pts"] + ov["return_pts"]
    V["ace_rate"] = sdiv(ov["aces"], ov["serve_pts"])
    V["df_rate"] = sdiv(ov["dfs"], ov["serve_pts"])
    V["first_in_pct"] = sdiv(ov["first_in"], ov["serve_pts"])
    V["first_won_pct"] = sdiv(ov["first_won"], ov["first_in"])
    V["second_won_pct"] = sdiv(ov["second_won"], ov["second_in"])
    V["ret_pts_won_pct"] = sdiv(ov["return_pts_won"], ov["return_pts"])
    V["winner_per_pt"] = sdiv(ov["winners"], tot_pts)
    V["ue_per_pt"] = sdiv(ov["unforced"], tot_pts)
    V["fh_winner_share"] = sdiv(ov["winners_fh"], ov["winners_fh"] + ov["winners_bh"])
    V["bh_ue_share"] = sdiv(ov["unforced_bh"], ov["unforced_fh"] + ov["unforced_bh"])
    V["aggression"] = V["winner_per_pt"] - V["ue_per_pt"]

    sb = rd(p("ServeBasics"), ["Total", "1"])
    t = sb[sb["row"].astype(str) == "Total"]
    v = t[["match_id", "player"]].copy()
    v["unret_rate"] = sdiv(t["unret"], t["pts"]); v["first_strike"] = sdiv(t["pts_won_lte_3_shots"], t["pts"])
    f1 = sb[sb["row"].astype(str) == "1"]
    w = f1[["match_id", "player"]].copy()
    tot = pd.to_numeric(f1["wide"], errors="coerce") + pd.to_numeric(f1["body"], errors="coerce") + pd.to_numeric(f1["t"], errors="coerce")
    w["srv1_wide_share"] = sdiv(f1["wide"], tot); w["srv1_t_share"] = sdiv(f1["t"], tot); w["srv1_body_share"] = sdiv(f1["body"], tot)
    V = V.merge(v, on=["match_id", "player"], how="left").merge(w, on=["match_id", "player"], how="left")
    _dbg("serve")
    ro = rd(p("ReturnOutcomes"), ["Total", "fh", "bh", "v1st", "v2nd"])
    t = ro[ro["row"].astype(str) == "Total"]; v = t[["match_id", "player"]].copy()
    v["ret_in_play"] = sdiv(t["in_play"], t["pts"]); v["ret_inplay_won"] = sdiv(t["in_play_won"], t["in_play"]); v["ret_winner_rate"] = sdiv(t["winners"], t["pts"])
    V = V.merge(v, on=["match_id", "player"], how="left")
    for side in ("fh", "bh", "v1st", "v2nd"):
        t = ro[ro["row"].astype(str) == side]; v = t[["match_id", "player"]].copy()
        v[f"ret_{side}_won"] = sdiv(t["pts_won"], t["pts"])
        V = V.merge(v, on=["match_id", "player"], how="left")

    _dbg("returnoutcomes")
    rdp = rd(p("ReturnDepth"), ["Total"])
    t = rdp[rdp["row"].astype(str) == "Total"]; v = t[["match_id", "player"]].copy()
    sh = pd.to_numeric(t["shallow"], errors="coerce"); dp = pd.to_numeric(t["deep"], errors="coerce"); vd = pd.to_numeric(t["very_deep"], errors="coerce")
    v["ret_deep_share"] = sdiv(dp, sh + dp)              # deep (incl. very deep) as share of returns in play
    v["ret_very_deep_share"] = sdiv(vd, sh + dp)
    V = V.merge(v, on=["match_id", "player"], how="left")

    _dbg("returndepth")
    ra = rd(p("Rally"), ["Total", "1-3", "4-6", "7-9", "10"])
    ra["pts"] = pd.to_numeric(ra["pts"], errors="coerce"); ra["pl1_won"] = pd.to_numeric(ra["pl1_won"], errors="coerce"); ra["pl2_won"] = pd.to_numeric(ra["pl2_won"], errors="coerce")
    tot = ra[ra["row"].astype(str) == "Total"][["match_id", "pts"]].rename(columns={"pts": "pts_total"})
    parts = []
    for row, tag in (("1-3", "short"), ("4-6", "mid"), ("7-9", "long"), ("10", "vlong")):
        r = ra[ra["row"].astype(str) == row].merge(tot, on="match_id", how="left")
        r[f"rally_{tag}_share"] = sdiv(r["pts"], r["pts_total"])
        for who, col in (("server", "pl1_won"), ("returner", "pl2_won")):
            q = r[["match_id", who, f"rally_{tag}_share", "pts", col]].rename(columns={who: "player"})
            q[f"rally_{tag}_won"] = sdiv(q[col], q["pts"])
            parts.append(q[["match_id", "player", f"rally_{tag}_share", f"rally_{tag}_won"]])
    R = pd.concat(parts, ignore_index=True).groupby(["match_id", "player"], as_index=False).first()
    V = V.merge(R, on=["match_id", "player"], how="left")

    _dbg("rally")
    st = rd(p("ShotTypes"), ["Total", "Sl", "Net", "Dr", "Fgs", "Gs"])
    st["shots"] = pd.to_numeric(st["shots"], errors="coerce")
    def share(rowname, out):
        a = st[st["row"].astype(str) == rowname][["match_id", "player", "shots"]].rename(columns={"shots": "n"})
        b = st[st["row"].astype(str) == "Total"][["match_id", "player", "shots"]].rename(columns={"shots": "d"})
        m = a.merge(b, on=["match_id", "player"], how="inner"); m[out] = sdiv(m["n"], m["d"]); return m[["match_id", "player", out]]
    for rowname, out in (("Sl", "slice_rate"), ("Net", "net_shot_rate"), ("Dr", "dropshot_rate"), ("Fgs", "fh_gs_shots"), ("Gs", "gs_shots")):
        V = V.merge(share(rowname, out), on=["match_id", "player"], how="left")
    V["fh_share"] = sdiv(V["fh_gs_shots"], V["gs_shots"]); V = V.drop(columns=["fh_gs_shots", "gs_shots"])

    _dbg("shottypes")
    sdn = rd(p("ShotDirection"), ["Total"])
    t = sdn[sdn["row"].astype(str) == "Total"]; v = t[["match_id", "player"]].copy()
    tot = sum(pd.to_numeric(t[c], errors="coerce") for c in ["crosscourt", "down_middle", "down_the_line", "inside_out", "inside_in"])
    v["dtl_share"] = sdiv(t["down_the_line"], tot); v["inside_out_share"] = sdiv(t["inside_out"], tot); v["crosscourt_share"] = sdiv(t["crosscourt"], tot)
    V = V.merge(v, on=["match_id", "player"], how="left")

    _dbg("shotdir")
    npn = rd(p("NetPoints"), ["NetPoints"])
    t = npn[npn["row"].astype(str) == "NetPoints"]; v = t[["match_id", "player", "net_pts", "pts_won"]].copy(); v["net_pts"] = pd.to_numeric(v["net_pts"], errors="coerce")
    v["net_win_pct"] = sdiv(v["pts_won"], v["net_pts"]); v = v.rename(columns={"net_pts": "net_pts_n"}).drop(columns=["pts_won"])
    V = V.merge(v, on=["match_id", "player"], how="left")
    tp = ov[["match_id", "player", "serve_pts", "return_pts"]].copy(); tp["tot_pts"] = tp["serve_pts"] + tp["return_pts"]
    V = V.merge(tp[["match_id", "player", "tot_pts"]], on=["match_id", "player"], how="left")
    V["net_pts_per_pt"] = sdiv(V["net_pts_n"], V["tot_pts"]); V = V.drop(columns=["tot_pts"])
    V = V.drop(columns=["net_pts_n"])

    _dbg("net")
    snv = rd(p("SnV"), ["SnV", "nonSnV"])
    t = snv[snv["row"].astype(str) == "SnV"]; v = t[["match_id", "player", "snv_pts"]].copy()
    n = snv[snv["row"].astype(str) == "nonSnV"][["match_id", "player", "snv_pts"]].rename(columns={"snv_pts": "non"})
    v = v.merge(n, on=["match_id", "player"], how="left"); v["snv_rate"] = sdiv(v["snv_pts"], pd.to_numeric(v["snv_pts"], errors="coerce") + pd.to_numeric(v["non"], errors="coerce"))
    V = V.merge(v[["match_id", "player", "snv_rate"]], on=["match_id", "player"], how="left")

    kp = rd(p("KeyPointsServe"), ["BP", "STotal"])
    bp = kp[kp["row"].astype(str) == "BP"][["match_id", "player", "pts", "pts_won"]].rename(columns={"pts": "bp_n", "pts_won": "bp_w"})
    al = kp[kp["row"].astype(str) == "STotal"][["match_id", "player", "pts", "pts_won"]].rename(columns={"pts": "s_n", "pts_won": "s_w"})
    k = bp.merge(al, on=["match_id", "player"], how="inner"); k["bp_serve_delta"] = sdiv(k["bp_w"], k["bp_n"]) - sdiv(k["s_w"], k["s_n"])
    V = V.merge(k[["match_id", "player", "bp_serve_delta"]], on=["match_id", "player"], how="left")

    V = V.merge(M[["match_id", "date", "Surface", "Round", "Tournament"]], on="match_id", how="left")
    V["tour"] = "ATP" if g == "m" else "WTA"
    V["pkey"] = V["player"].map(acm.norm_text)
    return V


STYLE_VARS = ["ace_rate", "df_rate", "first_in_pct", "first_won_pct", "second_won_pct", "unret_rate", "first_strike", "srv1_wide_share", "srv1_t_share",
              "srv1_body_share", "snv_rate", "ret_pts_won_pct", "ret_in_play", "ret_inplay_won", "ret_winner_rate", "ret_fh_won", "ret_bh_won", "ret_v1st_won",
              "ret_v2nd_won", "ret_deep_share", "ret_very_deep_share", "rally_short_share", "rally_mid_share", "rally_long_share", "rally_vlong_share",
              "rally_short_won", "rally_mid_won", "rally_long_won", "rally_vlong_won", "slice_rate", "net_shot_rate", "dropshot_rate", "fh_share",
              "dtl_share", "inside_out_share", "crosscourt_share", "net_pts_per_pt", "net_win_pct", "winner_per_pt", "ue_per_pt", "aggression",
              "fh_winner_share", "bh_ue_share", "bp_serve_delta"]
GROUP = {"Serve pattern": ["ace_rate", "df_rate", "first_in_pct", "first_won_pct", "second_won_pct", "unret_rate", "first_strike", "srv1_wide_share", "srv1_t_share", "srv1_body_share", "snv_rate"],
         "Return pattern": ["ret_pts_won_pct", "ret_in_play", "ret_inplay_won", "ret_winner_rate", "ret_fh_won", "ret_bh_won", "ret_v1st_won", "ret_v2nd_won", "ret_deep_share", "ret_very_deep_share"],
         "Rally profile": ["rally_short_share", "rally_mid_share", "rally_long_share", "rally_vlong_share", "rally_short_won", "rally_mid_won", "rally_long_won", "rally_vlong_won"],
         "Shot mix": ["slice_rate", "net_shot_rate", "dropshot_rate", "fh_share", "dtl_share", "inside_out_share", "crosscourt_share", "net_pts_per_pt", "net_win_pct"],
         "Aggression": ["winner_per_pt", "ue_per_pt", "aggression", "fh_winner_share", "bh_ue_share"],
         "Pressure": ["bp_serve_delta"]}


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp-dir", default="mcp")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--priced", default="apex_batch_a_rows.csv")
    ap.add_argument("--cache", default="apex_rows_cache.pkl")
    ap.add_argument("--odds-dir", default="odds")
    ap.add_argument("--test-from", type=int, default=2024)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    print(f"[{MARKER}] audit only -- no features joined, no residual test")
    if args.fetch or args.selftest:
        fetch(args.mcp_dir)

    charts = pd.concat([build_chart_vars(args.mcp_dir, "m"), build_chart_vars(args.mcp_dir, "w")], ignore_index=True)
    charts = charts[charts["date"] >= 20050101]
    charts["year"] = (charts["date"] // 10000).astype(int)
    charts["d"] = pd.to_datetime(charts["date"].astype(int).astype(str), format="%Y%m%d", errors="coerce").dt.date
    charts = charts[charts["d"].notna()]

    hr("1 -- charted matches by year (distinct matches with a stats row)")
    mc = charts.groupby(["tour", "year"])["match_id"].nunique().unstack(0).fillna(0).astype(int)
    print(mc.to_string())
    print(f"  total 2005+: ATP {charts[charts.tour=='ATP'].match_id.nunique():,}   WTA {charts[charts.tour=='WTA'].match_id.nunique():,}   player-charts {len(charts):,}")

    hr("7 -- style variable distributions (per chart, per player)")
    print(f"  {'group':16s} {'variable':22s} {'mean':>8s} {'median':>8s} {'p10':>8s} {'p90':>8s} {'missing%':>9s}")
    for gname, vs in GROUP.items():
        for v in vs:
            x = charts[v].astype(float)
            xv = x.dropna()
            print(f"  {gname:16s} {v:22s} {xv.mean():8.3f} {xv.median():8.3f} {xv.quantile(.1):8.3f} {xv.quantile(.9):8.3f} {x.isna().mean()*100:8.1f}%")

    # ---------------- profile index: charts per player sorted by date
    hist = defaultdict(list)
    for r in charts[["pkey", "d"]].itertuples(index=False):
        hist[r.pkey].append(r.d)
    for k in hist:
        hist[k].sort()
    def n_prior(pkey, d):
        L = hist.get(pkey)
        return bisect.bisect_left(L, d) if L else 0
    print(f"\n  players with >=3 / >=5 / >=10 charts (all-time): "
          + " / ".join(f"{sum(1 for L in hist.values() if len(L) >= k):,}" for k in (3, 5, 10)))

    if args.selftest:
        # rows = the charted matches themselves, to exercise the coverage code without Apex rows
        M = charts.drop_duplicates("match_id")[["match_id", "d", "tour", "year"]].copy()
        pl = charts.groupby("match_id")["player"].apply(list)
        M["player_a"] = M["match_id"].map(lambda m: pl[m][0]); M["player_b"] = M["match_id"].map(lambda m: pl[m][1] if len(pl[m]) > 1 else pl[m][0])
        rows = M.rename(columns={"d": "date"}); rows["level"] = "?"; rows["pinn_a"] = 0.5; rows["label"] = 1
        priced = rows
    else:
        if os.path.exists(args.priced):
            priced = pd.read_csv(args.priced, low_memory=False, usecols=lambda c: c in {"date", "year", "tour", "level", "player_a", "player_b", "label", "pinn_a", "surface"})
            priced["date"] = pd.to_datetime(priced["date"]).dt.date
            print(f"\n  priced rows loaded from {args.priced}: {len(priced):,}")
        else:
            rows = pd.read_pickle(args.cache); odds = acm.load_odds(args.odds_dir)
            priced = acm.market_join(rows, odds); priced = priced[priced["pinn_a"].notna()].reset_index(drop=True)
            print(f"\n  priced rows joined: {len(priced):,}")
        rows = pd.read_pickle(args.cache) if os.path.exists(args.cache) else priced

    def add_counts(D):
        D = D.copy()
        D["ka"] = D["player_a"].map(acm.norm_text); D["kb"] = D["player_b"].map(acm.norm_text)
        D["na"] = [n_prior(k, d) for k, d in zip(D["ka"], D["date"])]
        D["nb"] = [n_prior(k, d) for k, d in zip(D["kb"], D["date"])]
        return D
    rows = add_counts(rows); priced = add_counts(priced)

    hr("2/3 -- coverage of MAIN-TOUR rows (all rows in the cache) by profile depth")
    for k in (1, 3, 5, 10):
        a = (rows.na >= k).mean(); b = (rows.nb >= k).mean(); both = ((rows.na >= k) & (rows.nb >= k)).mean()
        print(f"  >= {k:2d} prior charts:  side A {a*100:5.1f}%   side B {b*100:5.1f}%   BOTH {both*100:5.1f}%   (n rows {len(rows):,})")
    print("  BOTH >= 5 by tour: " + ", ".join(f"{t} {100*((g.na>=5)&(g.nb>=5)).mean():.1f}%" for t, g in rows.groupby("tour")))

    hr("4 -- BOTH-player profile coverage by year / tour / level (rows in cache; min 3 | 5 | 10 charts)")
    def cov(D, k): return 100 * ((D.na >= k) & (D.nb >= k)).mean()
    print(f"  {'year':6s} {'n':>7s} {'ATP>=3':>7s} {'ATP>=5':>7s} {'ATP>=10':>8s}   {'WTA>=3':>7s} {'WTA>=5':>7s} {'WTA>=10':>8s}")
    for y, g in rows.groupby("year"):
        if y < 2012:
            continue
        ga, gw = g[g.tour == "ATP"], g[g.tour == "WTA"]
        print(f"  {y:<6d} {len(g):7,} {cov(ga,3):7.1f} {cov(ga,5):7.1f} {cov(ga,10):8.1f}   {cov(gw,3):7.1f} {cov(gw,5):7.1f} {cov(gw,10):8.1f}")
    print("  by level (2019+, both >= 5): " + ", ".join(f"{l} {cov(g,5):.0f}% (n={len(g):,})" for l, g in rows[rows.year >= 2019].groupby("level") if len(g) > 200))

    hr("5/6 -- PRICED rows with BOTH profiles: fit (<= %d) and score (%d+)" % (args.test_from - 1, args.test_from))
    print(f"  {'min charts':10s} {'fit rows':>9s} {'score rows':>10s} {'score ATP':>9s} {'score WTA':>9s} {'fit 2016+':>9s}")
    for k in (3, 5, 10):
        m = (priced.na >= k) & (priced.nb >= k)
        fit = priced[m & (priced.year < args.test_from)]; sc = priced[m & (priced.year >= args.test_from)]
        print(f"  {k:<10d} {len(fit):9,} {len(sc):10,} {int((sc.tour=='ATP').sum()):9,} {int((sc.tour=='WTA').sum()):9,} {int((fit.year>=2016).sum()):9,}")
    if not args.selftest:
        # selection check: is Pinnacle's accuracy different on covered vs uncovered priced rows?
        m5 = (priced.na >= 5) & (priced.nb >= 5)
        y = priced["label"].values; pa = priced["pinn_a"].values
        acc = lambda mk: (((pa[mk] >= 0.5).astype(int)) == y[mk]).mean()
        print(f"  selection check (2024+): Pinnacle favourite accuracy on covered rows {100*acc(m5.values & (priced.year>=args.test_from).values):.1f}%  vs uncovered {100*acc(~m5.values & (priced.year>=args.test_from).values):.1f}%")

    hr("8 -- detectability on the actual score sample")
    if not args.selftest:
        from sklearn.linear_model import LogisticRegression
        m5 = (priced.na >= 5) & (priced.nb >= 5)
        H = priced[m5 & (priced.year < args.test_from)]; S = priced[m5 & (priced.year >= args.test_from)]
        if len(H) > 500 and len(S) > 200:
            lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
            yH, yS = H["label"].values, S["label"].values
            base = LogisticRegression(max_iter=2000).fit(lg(H["pinn_a"].values).reshape(-1, 1), yH)
            p0 = base.predict_proba(lg(S["pinn_a"].values).reshape(-1, 1))[:, 1]
            ll0 = -(yS * np.log(p0) + (1 - yS) * np.log(1 - p0))
            rng = np.random.RandomState(0); ses = []; gains = []
            for i in range(30):
                zH = rng.normal(size=len(H)); zS = rng.normal(size=len(S))
                m = LogisticRegression(max_iter=2000).fit(np.column_stack([lg(H["pinn_a"].values), zH]), yH)
                p1 = m.predict_proba(np.column_stack([lg(S["pinn_a"].values), zS]))[:, 1]
                ll1 = -(yS * np.log(p1) + (1 - yS) * np.log(1 - p1))
                d = ll0 - ll1
                gains.append(d.mean()); ses.append(d.std() / np.sqrt(len(d)))
            print(f"  score rows n={len(S):,}: null-feature gain mean {np.mean(gains):+.5f}, spread (sd over 30 draws) {np.std(gains):.5f}, per-run SE {np.mean(ses):.5f}")
            print(f"  -> a gain of +0.002 would be about {0.002/np.mean(ses):.1f} standard errors above zero on this sample; realistically detectable if >= ~2 SE.")
            print(f"  -> minimum detectable gain here ~ {2*np.mean(ses):+.4f}   (Batch A had ~11,600 score rows; the bar was set with that in mind)")
        else:
            print("  too few covered priced rows to estimate")
    print(f"\n[{MARKER}] done -- audit only.")


if __name__ == "__main__":
    main()
