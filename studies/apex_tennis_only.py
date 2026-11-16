#!/usr/bin/env python3
"""
apex_tennis_only.py -- 2026-08-17   Follow-up to the diagnosis. Still NO new features.

TEST 1  No-Rating model (Serve+Return+Form+Physical+Matchup+Context) -- full readout:
        accuracy, logloss, confidence bands, group contributions, top-20 features,
        disagreements vs Elo-only.
TEST 2  Serve+Return+Form only -- same full readout.
TEST 3  The matches where the No-Rating model and Elo-only disagree, sliced by
        tournament level, surface, tour, round, best-of, which side the tennis
        model backed (higher/lower ranked, higher/lower Elo), gap sizes, and
        player-profile differences (height, age, rest, form).
Also prints an apples-to-apples ONLY-Rating GBM so "tennis vs rating" is a fair
GBM-vs-GBM comparison, not GBM-vs-2-feature-logistic.

Uses the row cache written by apex_diagnose.py (apex_rows_cache.pkl).

USAGE:
  python3 apex_tennis_only.py                # uses apex_rows_cache.pkl
  python3 apex_tennis_only.py --selftest
"""
import argparse, os, sys, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_combined_model as acm

MARKER = "APEX-TENNIS-ONLY-2026-08-17"
GROUPS = ["Rating", "Serve", "Return", "Form", "Physical", "Matchup", "Context"]


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def acc(p, y):
    return float(((p >= 0.5).astype(int) == y).mean())


def se(p, n):
    return 100 * np.sqrt(p * (1 - p) / max(n, 1))


def full_readout(name, tr, va, te, cols, seed, p_elo):
    y = te["label"].values
    m, gain, kind = acm.fit_gbm(tr[cols], tr["label"], va[cols], va["label"], seed)
    p = m.predict_proba(te[cols])[:, 1]
    hr(f"{name}   ({len(cols)} features, {kind})")
    print(f"  accuracy {acc(p, y)*100:.2f}%  (+/- {se(acc(p,y), len(y)):.2f})   logloss {acm.logloss(p, y):.4f}   n={len(y):,}")
    print(f"  Elo-only logistic on same rows: {acc(p_elo, y)*100:.2f}%")
    print("  by year: " + "   ".join(f"{yv} {acc(p[te.year.values==yv], y[te.year.values==yv])*100:.2f}%" for yv in sorted(te.year.unique())))
    print("  by tour: " + "   ".join(f"{t} {acc(p[te.tour.values==t], y[te.tour.values==t])*100:.2f}%" for t in sorted(te.tour.unique())))
    print("  by level: " + "   ".join(f"{l} {acc(p[te.level.values==l], y[te.level.values==l])*100:.1f}% (n={int((te.level.values==l).sum())})"
                                       for l in te.level.value_counts().index[:6]))
    print("  confidence bands:")
    conf = np.abs(p - 0.5) + 0.5
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        mk = (conf >= lo) & (conf < hi)
        if mk.sum():
            print(f"    {lo:.2f}-{min(hi,1):.2f}: n={int(mk.sum()):5,}  acc {acc(p[mk], y[mk])*100:5.2f}%   avg conf {conf[mk].mean()*100:5.2f}%")
    grp = {c: acm.group_for(c) for c in cols}
    sh, drops = acm.group_shares_perm(m, te[cols].reset_index(drop=True), y, cols, seed)
    gs = acm.group_shares_gain(gain, cols) if gain is not None else {}
    print("  group contribution  (permutation share | gain share | accuracy pts lost when scrambled):")
    for g, v in sh.items():
        print(f"    {g:9s} {v:5.1f}% | {gs.get(g,0):5.1f}% | {drops[g]*100:+5.2f} pts")
    if gain is not None:
        gt = gain.sum() or 1
        print("  top 20 features by gain:")
        for c, v in gain.sort_values(ascending=False).head(20).items():
            print(f"    {c:28s} {100*v/gt:5.1f}%  [{grp[c]}]")
    pk, pe = (p >= 0.5).astype(int), (p_elo >= 0.5).astype(int)
    dis = pk != pe
    n = int(dis.sum())
    if n:
        r = (pk[dis] == y[dis]).mean()
        print(f"  disagreements with Elo-only: {n:,} ({100*n/len(y):.1f}%)   {name} right {100*r:.1f}%  (+/- {se(r,n):.1f})   Elo right {100*(1-r):.1f}%")
        for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.7), (0.7, 1.01)):
            mk = dis & (conf >= lo) & (conf < hi)
            if mk.sum():
                print(f"    model conf {lo:.2f}-{min(hi,1):.2f}: n={int(mk.sum()):4,}  model right {100*(pk[mk]==y[mk]).mean():5.1f}%")
    return m, p


def seg(label, mask, pk, pe, y, min_n=40):
    n = int(mask.sum())
    if n < min_n:
        return
    r = (pk[mask] == y[mask]).mean()
    flag = " <-- tennis model clearly better" if r >= 0.5 + 2 * se(r, n) / 100 else (" <-- Elo clearly better" if r <= 0.5 - 2 * se(r, n) / 100 else "")
    print(f"    {label:34s} n={n:5,}  tennis right {100*r:5.1f}%  Elo right {100*(1-r):5.1f}%  (+/- {se(r,n):4.1f}){flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="apex_rows_cache.pkl")
    ap.add_argument("--test-from", type=int, default=2024)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        args.cache = "/tmp/apex_fake/rows.pkl"
        if not os.path.exists(args.cache):
            d = acm.make_fake("/tmp/apex_fake")
            df = acm.load_sackmann(d, 2015, False)
            acm.build_rows(df, 5, 7, True).to_pickle(args.cache)
    if not os.path.exists(args.cache):
        sys.exit(f"{args.cache} not found -- run apex_diagnose.py first (it writes the row cache).")
    rows = pd.read_pickle(args.cache)
    print(f"[{MARKER}] rows {len(rows):,} from {args.cache}")
    cols = acm.feature_columns(rows)
    grp = {c: acm.group_for(c) for c in cols}
    tr = rows[rows.year <= args.test_from - 3]
    va = rows[(rows.year > args.test_from - 3) & (rows.year < args.test_from)]
    te = rows[rows.year >= args.test_from].reset_index(drop=True)
    y = te["label"].values
    trva = pd.concat([tr, va])
    print(f"train {len(tr):,} / tune {len(va):,} / test {len(te):,}")
    print("  test rows by level: " + ", ".join(f"{l}={n:,}" for l, n in te.groupby("level").size().sort_values(ascending=False).items()))
    print("  test rows by round: " + ", ".join(f"{r}={n:,}" for r, n in te.groupby("round").size().sort_values(ascending=False).items()))

    elo_lr = acm.fit_logit(trva[["d_elo", "d_surf_elo"]], trva["label"])
    p_elo = elo_lr.predict_proba(te[["d_elo", "d_surf_elo"]])[:, 1]

    rating_cols = [c for c in cols if grp[c] == "Rating"]
    m_r, gain_r, _ = acm.fit_gbm(tr[rating_cols], tr["label"], va[rating_cols], va["label"], args.seed)
    p_rating = m_r.predict_proba(te[rating_cols])[:, 1]
    print(f"\nreference: ONLY-Rating GBM {acc(p_rating, y)*100:.2f}%   Elo-only logistic {acc(p_elo, y)*100:.2f}%")

    no_rating = [c for c in cols if grp[c] != "Rating"]
    m1, p1 = full_readout("TEST 1 -- NO-RATING model", tr, va, te, no_rating, args.seed, p_elo)

    srf = [c for c in cols if grp[c] in ("Serve", "Return", "Form")]
    m2, p2 = full_readout("TEST 2 -- SERVE + RETURN + FORM only", tr, va, te, srf, args.seed, p_elo)

    all_m, all_gain, _ = acm.fit_gbm(tr[cols], tr["label"], va[cols], va["label"], args.seed)
    p_all = all_m.predict_proba(te[cols])[:, 1]

    hr("HEAD-TO-HEAD SUMMARY (same held-out matches)")
    for name, p in (("ALL groups", p_all), ("NO-RATING", p1), ("SERVE+RETURN+FORM", p2), ("ONLY-Rating GBM", p_rating), ("Elo-only logistic", p_elo)):
        print(f"  {name:22s} acc {acc(p, y)*100:6.2f}%   logloss {acm.logloss(p, y):.4f}")
    pk1 = (p1 >= 0.5).astype(int); pkr = (p_rating >= 0.5).astype(int); pke = (p_elo >= 0.5).astype(int)
    d = pk1 != pkr
    if d.sum():
        r = (pk1[d] == y[d]).mean()
        print(f"  NO-RATING vs ONLY-Rating GBM (fair GBM-vs-GBM): disagree {int(d.sum()):,}   tennis right {100*r:.1f}% (+/- {se(r, int(d.sum())):.1f})   rating right {100*(1-r):.1f}%")

    # ------------------------------------------------------------ TEST 3
    hr("TEST 3 -- the disagreements: NO-RATING model vs Elo-only, where does the tennis model win?")
    dis = pk1 != pke
    n = int(dis.sum())
    r = (pk1[dis] == y[dis]).mean()
    print(f"  {n:,} disagreements   tennis right {100*r:.1f}% (+/- {se(r,n):.1f})   Elo right {100*(1-r):.1f}%")
    print("  (a flag prints only when a slice is >2 standard errors from 50/50; everything else is within noise)")
    D = te.copy(); D["pk1"] = pk1; D["pke"] = pke; D["conf1"] = np.abs(p1 - 0.5) + 0.5
    D["tennis_backed_lower_elo"] = ((D["pk1"] == 1) & (D["d_elo"] < 0)) | ((D["pk1"] == 0) & (D["d_elo"] > 0))
    D["tennis_backed_lower_rank"] = ((D["pk1"] == 1) & (D["d_rank"] > 0)) | ((D["pk1"] == 0) & (D["d_rank"] < 0))   # d_rank is log(rank): bigger = worse
    D["elo_gap"] = D["d_elo"].abs()

    def sgn(v):
        return np.where(D["pk1"] == 1, v, -v)   # value from the tennis-model pick's point of view
    D["pick_form20"] = sgn(D["d_win_20"].fillna(0)); D["pick_rest"] = sgn(D["d_days_since"].fillna(0))
    D["pick_ht"] = sgn(D["d_ht"].fillna(0)); D["pick_age"] = sgn(D["d_age"].fillna(0)); D["pick_hb"] = sgn(D["d_hold_plus_break"].fillna(0))
    D["pick_fatigue"] = sgn(D["d_matches_14d"].fillna(0))
    Dd = D[dis]; yk = y[dis]; pk = pk1[dis]; pe = pke[dis]

    print("\n  by tournament level:")
    for l, g in Dd.groupby("level"):
        seg(f"level {l}", (Dd.level == l).values, pk, pe, yk)
    print("  by surface:")
    for s_ in ("Hard", "Clay", "Grass"):
        seg(s_, (Dd.surface == s_).values, pk, pe, yk)
    print("  by tour / best-of:")
    for t in ("ATP", "WTA"):
        seg(t, (Dd.tour == t).values, pk, pe, yk)
    seg("best of 5", (Dd.best_of == 5).values, pk, pe, yk); seg("best of 3", (Dd.best_of == 3).values, pk, pe, yk)
    print("  by round:")
    for rd_ in ("R128", "R64", "R32", "R16", "QF", "SF", "F", "RR"):
        seg(rd_, (Dd["round"] == rd_).values, pk, pe, yk)
    print("  by which side the tennis model backed:")
    seg("backed LOWER-Elo player", Dd.tennis_backed_lower_elo.values, pk, pe, yk)
    seg("backed HIGHER-Elo player", ~Dd.tennis_backed_lower_elo.values, pk, pe, yk)
    seg("backed LOWER-ranked player", Dd.tennis_backed_lower_rank.values, pk, pe, yk)
    seg("backed HIGHER-ranked player", ~Dd.tennis_backed_lower_rank.values, pk, pe, yk)
    print("  by size of the Elo gap it went against:")
    for lo, hi in ((0, 25), (25, 50), (50, 100), (100, 9999)):
        seg(f"Elo gap {lo}-{hi}", ((Dd.elo_gap >= lo) & (Dd.elo_gap < hi)).values, pk, pe, yk)
    print("  by tennis-model confidence:")
    for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.7), (0.7, 1.01)):
        seg(f"conf {lo:.2f}-{min(hi,1):.2f}", ((Dd.conf1 >= lo) & (Dd.conf1 < hi)).values, pk, pe, yk)
    print("  by profile of the player the tennis model backed (relative to opponent):")
    seg("hotter form (win% last 20 > opp)", (Dd.pick_form20 > 0.1).values, pk, pe, yk)
    seg("colder form", (Dd.pick_form20 < -0.1).values, pk, pe, yk)
    seg("better hold+break", (Dd.pick_hb > 0.02).values, pk, pe, yk)
    seg("worse hold+break", (Dd.pick_hb < -0.02).values, pk, pe, yk)
    seg("more rest (days since > opp)", (Dd.pick_rest > 3).values, pk, pe, yk)
    seg("less rest", (Dd.pick_rest < -3).values, pk, pe, yk)
    seg("played MORE in last 14d", (Dd.pick_fatigue > 0).values, pk, pe, yk)
    seg("played FEWER in last 14d", (Dd.pick_fatigue < 0).values, pk, pe, yk)
    seg("taller by 5cm+", (Dd.pick_ht >= 5).values, pk, pe, yk)
    seg("shorter by 5cm+", (Dd.pick_ht <= -5).values, pk, pe, yk)
    seg("younger by 3y+", (Dd.pick_age <= -3).values, pk, pe, yk)
    seg("older by 3y+", (Dd.pick_age >= 3).values, pk, pe, yk)
    # ---- top-100 highest-confidence disagreements, human-readable
    hr("TOP 100 highest-confidence disagreements (NO-RATING vs Elo) -- for eyeballing")
    T = Dd.copy()
    T["p_tennis_a"] = p1[dis]
    T["p_elo_a"] = p_elo[dis]
    T["elo_pick"] = np.where(T["pke"] == 1, T["player_a"], T["player_b"])
    T["tennis_pick"] = np.where(T["pk1"] == 1, T["player_a"], T["player_b"])
    T["winner"] = np.where(T["label"] == 1, T["player_a"], T["player_b"])
    T["tennis_right"] = (T["tennis_pick"] == T["winner"]).map({True: "YES", False: "no"})
    T = T.sort_values("conf1", ascending=False)
    top = T.head(100)
    print(f"  {'date':10s} {'lvl':3s} {'surf':5s} {'rnd':4s}  {'player A':22s} {'player B':22s} {'Elo pick':22s} {'tennis pick':22s} {'conf':5s} {'winner':22s} tennis?")
    for r in top.itertuples(index=False):
        print(f"  {str(r.date):10s} {str(r.level)[:3]:3s} {str(r.surface)[:5]:5s} {str(r.round)[:4]:4s}  {r.player_a[:22]:22s} {r.player_b[:22]:22s} "
              f"{r.elo_pick[:22]:22s} {r.tennis_pick[:22]:22s} {r.conf1*100:4.0f}%  {r.winner[:22]:22s} {r.tennis_right}")
    print(f"  top-100 tennis-model hit rate: {100*(top['tennis_right']=='YES').mean():.1f}%")
    top[["date", "tour", "level", "surface", "round", "player_a", "player_b", "elo_pick", "tennis_pick", "conf1", "p_tennis_a", "p_elo_a", "winner", "tennis_right",
         "d_elo", "d_rank", "d_hold_plus_break", "d_win_20", "d_days_since", "d_ht", "d_age"]].to_csv("apex_top100_disagreements.csv", index=False)
    print("  saved -> apex_top100_disagreements.csv")
    out = "apex_disagreements_no_rating_vs_elo.csv"
    Dd.to_csv(out, index=False)
    print(f"\n  saved the {n:,} disagreement rows -> {out}   [{MARKER}]")


if __name__ == "__main__":
    main()
