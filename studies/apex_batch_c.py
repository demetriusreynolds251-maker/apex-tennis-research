#!/usr/bin/env python3
"""
apex_batch_c.py -- 2026-08-17   Batch C: tactical style matchups vs Pinnacle's closing line.

Spec: both players need >= 5 PRIOR charted matches (Match Charting Project); a player's style profile is the
average of their last 20 prior charts (surface-agnostic, v1). Rows = priced main-tour matches (apex_batch_a_rows.csv).

Feature families
  1  individual style differences  d_<var> = A - B for the 44 chart variables
  2  style INTERACTIONS (12)      centred products, A-vs-B minus B-vs-A, e.g. A's 2nd-serve strength x B's 2nd-serve return
  3  style DISTANCE (4)           symmetric clash measures; tested as modifiers of Pinnacle's confidence
  4  matchup BLOCK                interactions + distances together (then + individual diffs)
Tests (all vs Pinnacle): logistic on logit(Pinnacle) + features, fit on priced rows <= 2023, scored 2024+;
pass = gain >= +0.002 logloss over the calibration refit; L2 (C=0.5) on the block to keep it honest.
Monotone tables: residual (A win - Pinnacle prob) by quintile of the fitted block score and of the top interaction.
Subsets: ATP, WTA, both players top-50, Slams (each fit and scored inside the subset). Plus a GBM check.

USAGE
  python3 apex_batch_c.py --sack-dir "ATP & WTA, 1968-2026"        # needs ./mcp/, apex_batch_a_rows.csv, apex_combined_model.py
  python3 apex_batch_c.py --selftest                                 # planted-interaction check on charted matches
"""
import argparse, bisect, os, sys, warnings
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_combined_model as acm
import apex_batch_c_audit as AUD

MARKER = "APEX-BATCH-C-2026-08-17"
VARS = AUD.STYLE_VARS
STYLE_ONLY = ["first_strike", "srv1_wide_share", "srv1_t_share", "srv1_body_share", "ret_in_play", "ret_deep_share", "ret_very_deep_share",
              "rally_short_share", "rally_mid_share", "rally_long_share", "rally_vlong_share", "slice_rate", "net_shot_rate", "dropshot_rate",
              "fh_share", "dtl_share", "inside_out_share", "crosscourt_share", "net_pts_per_pt", "winner_per_pt", "ue_per_pt", "aggression",
              "fh_winner_share", "bh_ue_share"]
# (A-side variable, B-side variable, label)
INTERACTIONS = [("first_strike", "ret_deep_share", "I1 first-strike serve x deep returner"),
                ("first_strike", "ret_in_play", "I2 first-strike serve x return-in-play rate"),
                ("second_won_pct", "ret_v2nd_won", "I3 2nd-serve strength x 2nd-serve return"),
                ("first_won_pct", "ret_v1st_won", "I4 1st-serve strength x 1st-serve return"),
                ("rally_short_share", "rally_long_won", "I5 short-point player x long-rally winner"),
                ("rally_vlong_share", "rally_vlong_won", "I6 grinder x grind-winner"),
                ("net_pts_per_pt", "ret_inplay_won", "I7 net-rusher x returner who wins in-play pts"),
                ("aggression", "ret_in_play", "I8 aggressor x consistent returner"),
                ("inside_out_share", "bh_ue_share", "I9 inside-out forehand x backhand-error prone"),
                ("srv1_t_share", "ret_bh_won", "I10 T-serve bias x backhand return strength"),
                ("slice_rate", "aggression", "I11 slicer x aggressor"),
                ("winner_per_pt", "ue_per_pt", "I12 power hitter x error-prone")]


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def logit_(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


# ----------------------------------------------------------------------------- profiles
def build_profiles(charts, window=20):
    """Per player: sorted list of (date, vector). Profile at date d = mean of last `window` charts strictly before d."""
    charts = charts.sort_values("d")
    per = defaultdict(lambda: ([], []))
    X = charts[VARS].astype(float).values
    for i, (k, d) in enumerate(zip(charts["pkey"].values, charts["d"].values)):
        per[k][0].append(d); per[k][1].append(X[i])
    per = {k: (v[0], np.array(v[1])) for k, v in per.items()}
    def profile(pkey, d, min_n=5):
        e = per.get(pkey)
        if e is None:
            return None, 0
        n = bisect.bisect_left(e[0], d)
        if n < min_n:
            return None, n
        seg = e[1][max(0, n - window):n]
        return np.nanmean(seg, axis=0), n
    return profile


def attach_style(rows, profile, min_n=5):
    A = np.full((len(rows), len(VARS)), np.nan); B = A.copy(); na = []; nb = []
    for i, r in enumerate(rows.itertuples(index=False)):
        pa, n1 = profile(acm.norm_text(r.player_a), r.date, min_n); pb, n2 = profile(acm.norm_text(r.player_b), r.date, min_n)
        na.append(n1); nb.append(n2)
        if pa is not None: A[i] = pa
        if pb is not None: B[i] = pb
    R = rows.copy()
    R["na"] = na; R["nb"] = nb
    for j, v in enumerate(VARS):
        R[f"a_{v}"] = A[:, j]; R[f"b_{v}"] = B[:, j]; R[f"d_{v}"] = A[:, j] - B[:, j]
    return R


def add_interactions(R, fit_mask):
    """Centre/scale each variable using fit-period profiles, then build A-vs-B minus B-vs-A products."""
    stats = {}
    for v in VARS:
        x = pd.concat([R.loc[fit_mask, f"a_{v}"], R.loc[fit_mask, f"b_{v}"]]).astype(float)
        stats[v] = (x.mean(), x.std() if x.std() > 0 else 1.0)
    z = lambda side, v: (R[f"{side}_{v}"] - stats[v][0]) / stats[v][1]
    names = []
    for xa, yb, lab in INTERACTIONS:
        col = "mu_" + lab.split()[0]
        R[col] = z("a", xa) * z("b", yb) - z("b", xa) * z("a", yb)
        names.append(col)
    # style distance (symmetric) on style-only axes, and per-axis absolute gaps
    Za = np.column_stack([z("a", v) for v in STYLE_ONLY]); Zb = np.column_stack([z("b", v) for v in STYLE_ONLY])
    R["style_dist"] = np.sqrt(np.nanmean((Za - Zb) ** 2, axis=1))
    R["gap_rally"] = (z("a", "rally_short_share") - z("b", "rally_short_share")).abs()
    R["gap_net"] = (z("a", "net_pts_per_pt") - z("b", "net_pts_per_pt")).abs()
    R["gap_aggr"] = (z("a", "aggression") - z("b", "aggression")).abs()
    # symmetric measures enter as modifiers of the market's confidence: logit(P) * dist
    for c in ("style_dist", "gap_rally", "gap_net", "gap_aggr"):
        R[f"{c}_x_logitP"] = logit_(R["pinn_a"].values) * (R[c] - R.loc[fit_mask, c].mean())
    return R, names, ["style_dist_x_logitP", "gap_rally_x_logitP", "gap_net_x_logitP", "gap_aggr_x_logitP"]


# ----------------------------------------------------------------------------- tests
def resid(H, S, feats, C=1.0):
    from sklearn.linear_model import LogisticRegression
    XH = np.column_stack([logit_(H["pinn_a"].values)] + [H[f].fillna(0).values for f in feats])
    XS = np.column_stack([logit_(S["pinn_a"].values)] + [S[f].fillna(0).values for f in feats])
    m = LogisticRegression(C=C, max_iter=5000).fit(XH, H["label"].values)
    p = m.predict_proba(XS)[:, 1]
    return acm.logloss(p, S["label"].values), m, p


def run_tests(T, test_from, mu, dist, title, C_block=0.5, quiet=False):
    H = T[T.year < test_from]; S = T[T.year >= test_from]
    if len(H) < 300 or len(S) < 150:
        print(f"  {title}: too few rows (fit {len(H):,}, score {len(S):,})"); return None
    ref, _, p_ref = resid(H, S, [])
    raw = acm.logloss(S["pinn_a"].values, S["label"].values)
    print(f"\n  {title}: fit {len(H):,}  score {len(S):,}   Pinnacle raw LL {raw:.4f}   refit {ref:.4f}")
    out = {}
    if not quiet:
        print("  (1) individual style differences, standalone:")
        rows_ = []
        for v in VARS:
            l_, m, _ = resid(H, S, [f"d_{v}"]); rows_.append((v, ref - l_, m.coef_[0][1]))
        rows_.sort(key=lambda t: -t[1])
        for v, g, c in rows_[:12]:
            print(f"      {v:22s} gain {g:+.4f}  coef {c:+.3f}   {'PASS' if g >= 0.002 else ''}")
        print(f"      ... {sum(1 for _, g, _ in rows_ if g >= 0.002)} of {len(rows_)} pass; worst {rows_[-1][0]} {rows_[-1][1]:+.4f}")
        out["indiv"] = rows_
    print("  (2) style INTERACTIONS, standalone:")
    ints = []
    for (xa, yb, lab), col in zip(INTERACTIONS, mu):
        l_, m, _ = resid(H, S, [col]); ints.append((lab, ref - l_, m.coef_[0][1], col))
    for lab, g, c, col in ints:
        print(f"      {lab:48s} gain {g:+.4f}  coef {c:+.3f}   {'PASS' if g >= 0.002 else ''}")
    out["ints"] = ints
    print("  (3) style DISTANCE modifiers, standalone:")
    for c in dist:
        l_, m, _ = resid(H, S, [c]); print(f"      {c:28s} gain {ref-l_:+.4f}  coef {m.coef_[0][1]:+.3f}   {'PASS' if ref-l_ >= 0.002 else ''}")
    print("  (4) BLOCKS:")
    for lab, fs in (("interactions (12)", mu), ("interactions + distances (16)", mu + dist), ("+ individual diffs (60)", mu + dist + [f"d_{v}" for v in VARS])):
        l_, m, p = resid(H, S, fs, C=C_block)
        print(f"      {lab:32s} LL {l_:.4f}  gain {ref-l_:+.4f}   {'PASS' if ref-l_ >= 0.002 else 'no'}")
        out[lab] = (ref - l_, p)
    return out


def mono(S, score, title, k=5):
    y = S["label"].values; pa = S["pinn_a"].values
    q = pd.qcut(pd.Series(score), k, labels=False, duplicates="drop")
    print(f"\n  {title}  (residual = A's win rate - Pinnacle's prob for A; bins = quintiles of the style score for A)")
    print(f"  {'bin':8s} {'n':>6s} {'score mean':>10s} {'A win%':>8s} {'Pinn':>8s} {'residual':>9s} {'+/-':>6s}")
    res = []
    for b in sorted(q.dropna().unique()):
        m = (q == b).values; n = int(m.sum()); w = y[m].mean(); p = pa[m].mean(); r = w - p
        res.append(r)
        print(f"  {int(b)+1:<8d} {n:6,} {score[m].mean():10.3f} {w*100:7.1f}% {p*100:7.1f}% {r*100:+8.2f} {100*np.sqrt(w*(1-w)/n):6.2f}")
    d = np.diff(res)
    print("  trend: " + ("monotone UP" if all(x >= -0.0005 for x in d) else ("monotone DOWN" if all(x <= 0.0005 for x in d) else "NOT monotone")))


def gbm_check(T, test_from, feats):
    try:
        import xgboost as xgb
    except ImportError:
        return
    H = T[T.year < test_from]; S = T[T.year >= test_from]
    XH = np.column_stack([logit_(H["pinn_a"].values)] + [H[f].values for f in feats]); XS = np.column_stack([logit_(S["pinn_a"].values)] + [S[f].values for f in feats])
    m = xgb.XGBClassifier(n_estimators=600, learning_rate=0.03, max_depth=3, subsample=0.8, colsample_bytree=0.7, min_child_weight=30, reg_lambda=3.0, tree_method="hist")
    m.fit(XH, H["label"].values)
    p = m.predict_proba(XS)[:, 1]
    from sklearn.linear_model import LogisticRegression
    ref = LogisticRegression(max_iter=2000).fit(logit_(H["pinn_a"].values).reshape(-1, 1), H["label"].values)
    p0 = ref.predict_proba(logit_(S["pinn_a"].values).reshape(-1, 1))[:, 1]
    print(f"\n  GBM (Pinnacle + block, nonlinear): LL {acm.logloss(p, S['label'].values):.4f} vs refit {acm.logloss(p0, S['label'].values):.4f}  gain {acm.logloss(p0, S['label'].values)-acm.logloss(p, S['label'].values):+.4f}")


def attach_ranks(R, sack_dir, year_from):
    df = acm.load_sackmann(sack_dir, year_from, False)
    key = {}
    for r in df[["tdate", "winner_name", "loser_name", "winner_rank", "loser_rank"]].itertuples(index=False):
        key[(r.tdate, frozenset({acm.norm_text(r.winner_name), acm.norm_text(r.loser_name)}))] = (acm.norm_text(r.winner_name), r.winner_rank, r.loser_rank)
    ra, rb = [], []
    for r in R.itertuples(index=False):
        k = key.get((r.date, frozenset({acm.norm_text(r.player_a), acm.norm_text(r.player_b)})))
        if k is None:
            ra.append(np.nan); rb.append(np.nan); continue
        wn, wr, lr = k
        if acm.norm_text(r.player_a) == wn: ra.append(wr); rb.append(lr)
        else: ra.append(lr); rb.append(wr)
    R["rank_a"] = pd.to_numeric(ra, errors="coerce"); R["rank_b"] = pd.to_numeric(rb, errors="coerce")
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp-dir", default="mcp")
    ap.add_argument("--priced", default="apex_batch_a_rows.csv")
    ap.add_argument("--sack-dir", default="ATP & WTA, 1968-2026")
    ap.add_argument("--year-from", type=int, default=2005)
    ap.add_argument("--test-from", type=int, default=2024)
    ap.add_argument("--min-charts", type=int, default=5)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    print(f"[{MARKER}] style matchups vs Pinnacle; both players >= {args.min_charts} prior charts; profile = last 20 charts")

    charts = pd.concat([AUD.build_chart_vars(args.mcp_dir, "m"), AUD.build_chart_vars(args.mcp_dir, "w")], ignore_index=True)
    charts = charts[charts["date"] >= 20050101]
    charts["d"] = pd.to_datetime(charts["date"].astype(int).astype(str), format="%Y%m%d", errors="coerce").dt.date
    charts = charts[charts["d"].notna()]
    profile = build_profiles(charts)

    if args.selftest:
        M = charts.drop_duplicates("match_id")[["match_id", "d", "tour"]].copy()
        pl = charts.groupby("match_id")["player"].apply(list)
        M["player_a"] = M["match_id"].map(lambda m: pl[m][0]); M["player_b"] = M["match_id"].map(lambda m: pl[m][1] if len(pl[m]) > 1 else pl[m][0])
        rows = M.rename(columns={"d": "date"}); rows["year"] = [d.year for d in rows["date"]]; rows["level"] = "G"
        rng = np.random.RandomState(1); rows["pinn_a"] = 1 / (1 + np.exp(-rng.normal(0, 1, len(rows)))); rows["label"] = 0
        R = attach_style(rows, profile, args.min_charts)
        R = R[(R.na >= args.min_charts) & (R.nb >= args.min_charts)].reset_index(drop=True)
        fit_mask = (R.year < args.test_from).values
        R, mu, dist = add_interactions(R, fit_mask)
        for lab, beta in (("NULL", 0.0), ("PLANTED I3 effect (beta 0.25 per sd)", 0.25)):
            T = R.copy(); T["label"] = (rng.rand(len(T)) < 1 / (1 + np.exp(-(logit_(T["pinn_a"].values) + beta * np.nan_to_num(T["mu_I3"].values))))).astype(int)
            print(f"\n--- {lab} ---")
            out = run_tests(T, args.test_from, mu, dist, "self-test rows", quiet=True)
        return

    priced = pd.read_csv(args.priced, low_memory=False, usecols=lambda c: c in {"date", "year", "tour", "level", "surface", "player_a", "player_b", "label", "pinn_a"})
    priced["date"] = pd.to_datetime(priced["date"]).dt.date
    R = attach_style(priced, profile, args.min_charts)
    both = (R.na >= args.min_charts) & (R.nb >= args.min_charts)
    print(f"priced rows {len(R):,}; both profiles: {int(both.sum()):,}  (fit {int((both & (R.year < args.test_from)).sum()):,} / score {int((both & (R.year >= args.test_from)).sum()):,})")
    R = R[both].reset_index(drop=True)
    R = attach_ranks(R, args.sack_dir, args.year_from)
    print(f"ranks attached for {R.rank_a.notna().mean()*100:.1f}% of rows")
    fit_mask = (R.year < args.test_from).values
    R, mu, dist = add_interactions(R, fit_mask)

    hr("A -- ALL rows (both tours)")
    out = run_tests(R, args.test_from, mu, dist, "ALL")
    S = R[R.year >= args.test_from].reset_index(drop=True)
    if out:
        g_block, p_block = out["interactions + distances (16)"]
        score = logit_(p_block) - logit_(S["pinn_a"].values)   # what the block added on top of the market, per row
        mono(S, score, "MONOTONE: fitted matchup block (what it added to Pinnacle)")
        best = max(out["ints"], key=lambda t: t[1])
        mono(S, S[best[3]].fillna(0).values, f"MONOTONE: strongest single interaction -- {best[0]}")
        gbm_check(R, args.test_from, mu + dist)

    hr("B -- subsets (each fit and scored inside the subset)")
    subsets = {"ATP": R.tour == "ATP", "WTA": R.tour == "WTA",
               "both top-50": (R.rank_a <= 50) & (R.rank_b <= 50),
               "Slams": R.level.astype(str) == "G"}
    for name, mk in subsets.items():
        run_tests(R[mk.values].reset_index(drop=True), args.test_from, mu, dist, name, quiet=True)

    hr("C -- robustness: profile depth")
    for k in (3, 10):
        Rk = attach_style(priced, profile, k); mk = (Rk.na >= k) & (Rk.nb >= k); Rk = Rk[mk].reset_index(drop=True)
        Rk, mu_k, dist_k = add_interactions(Rk, (Rk.year < args.test_from).values)
        run_tests(Rk, args.test_from, mu_k, dist_k, f"min {k} charts", quiet=True)

    R.to_pickle("apex_batch_c_rows.pkl")
    print(f"\n  saved -> apex_batch_c_rows.pkl   [{MARKER}]")
    print("  DECISION RULE: a style feature moves on only if gain >= +0.002 vs Pinnacle AND the block score is monotone; ")
    print("  a block pass that vanishes in the top-50 subset is a charting-selection artefact, not a style edge.")


if __name__ == "__main__":
    main()
