#!/usr/bin/env python3
"""
apex_understand.py -- 2026-08-17   Understanding phase. NO new features.

Answers the nine open questions using the cached rows (apex_rows_cache.pkl):
  Q1 why Form dominates       -- each form component alone, leave-one-out inside Form,
                                 redundancy vs Elo, "is Form a short-horizon Elo?"
  Q2 why Serve/Return vanish  -- no-Form model, Serve+Return only, hold/break/hb only,
                                 point-level only, unique-vs-redundant per metric
  Q3 value of Hold+Break      -- alone, +Form, +Matchup, +Physical
  Q4 what beats Elo           -- per-match feature contributions (tree SHAP) on the
                                 disagreements, grouped: what was the tennis model seeing?
  Q5 surfaces                 -- Hard / Clay / Grass models, group weights per surface
  Q6 slams                    -- Slam vs non-Slam models, group weights
  Q7 confidence threshold     -- sweep: matches remaining, accuracy, drivers
  Q8 pure tennis model        -- no Elo, no rank, no opponent-Elo form features
  Q9 player types             -- rising, post-layoff, big server, specialists, veterans

USAGE:
  python3 apex_understand.py                 # needs apex_rows_cache.pkl + apex_combined_model.py
  python3 apex_understand.py --selftest
"""
import argparse, os, sys, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_combined_model as acm

MARKER = "APEX-UNDERSTAND-2026-08-17"
GROUPS = ["Rating", "Serve", "Return", "Form", "Physical", "Matchup", "Context"]
FORM = ["d_win_5", "d_win_10", "d_win_20", "d_games_dom_10", "d_sets_pct_10", "d_s_win_pct", "d_opp_elo_10", "d_adj_form_10", "d_s_n"]
ELO_DERIVED = ["d_opp_elo_10", "d_adj_form_10"]
HB = ["d_hold_pct", "d_break_pct", "d_hold_plus_break"]
POINT = ["d_svc_pts_won", "d_ret_pts_won", "d_first_won", "d_second_won", "d_first_in", "d_ace_rate", "d_df_rate", "d_bp_save", "d_bp_conv"]


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def acc(p, y):
    return float(((p >= 0.5).astype(int) == y).mean())


def se(p, n):
    return 100 * np.sqrt(p * (1 - p) / max(n, 1))


def gbm(tr, va, te, cols, seed):
    m, gain, _ = acm.fit_gbm(tr[cols], tr["label"], va[cols], va["label"], seed)
    return m, gain, m.predict_proba(te[cols])[:, 1]


def logit(trva, te, cols):
    m = acm.fit_logit(trva[cols].astype(float), trva["label"])
    return m.predict_proba(te[cols].astype(float))[:, 1]


def contribs(m, X):
    """Per-row, per-feature contributions (log-odds units) from the trees."""
    import xgboost as xgb
    b = m.get_booster()
    c = b.predict(xgb.DMatrix(X), pred_contribs=True)
    return pd.DataFrame(c[:, :-1], columns=X.columns)


def perm_shares(m, X, y, cols, seed):
    sh, drops = acm.group_shares_perm(m, X.reset_index(drop=True), y, cols, seed)
    return sh, drops


def line(name, p, y, ref=None):
    a = acc(p, y)
    extra = f"   vs ref {(a-ref)*100:+.2f}" if ref is not None else ""
    print(f"  {name:44s} acc {a*100:6.2f}% (+/- {se(a, len(y)):.2f})   logloss {acm.logloss(p, y):.4f}{extra}")
    return a


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
            d = acm.make_fake("/tmp/apex_fake"); df = acm.load_sackmann(d, 2015, False)
            acm.build_rows(df, 5, 7, True).to_pickle(args.cache)
    rows = pd.read_pickle(args.cache)
    print(f"[{MARKER}] rows {len(rows):,}   understanding phase, no new features")
    cols = acm.feature_columns(rows)
    grp = {c: acm.group_for(c) for c in cols}
    tr = rows[rows.year <= args.test_from - 3]
    va = rows[(rows.year > args.test_from - 3) & (rows.year < args.test_from)]
    te = rows[rows.year >= args.test_from].reset_index(drop=True)
    trva = pd.concat([tr, va]); y = te["label"].values
    print(f"train {len(tr):,} / tune {len(va):,} / test {len(te):,}")
    form = [c for c in FORM if c in cols]
    serve = [c for c in cols if grp[c] == "Serve"]; ret = [c for c in cols if grp[c] == "Return"]
    phys = [c for c in cols if grp[c] == "Physical"]; mu = [c for c in cols if grp[c] == "Matchup"]
    ctx = [c for c in cols if grp[c] == "Context"]; rating = [c for c in cols if grp[c] == "Rating"]
    no_rating = [c for c in cols if grp[c] != "Rating"]

    p_elo = logit(trva, te, ["d_elo", "d_surf_elo"]); a_elo = acc(p_elo, y)
    m_nr, gain_nr, p_nr = gbm(tr, va, te, no_rating, args.seed); a_nr = acc(p_nr, y)
    print(f"reference: NO-RATING GBM {a_nr*100:.2f}%   Elo-only logistic {a_elo*100:.2f}%")

    # ---------------------------------------------------------------- Q1
    hr("Q1 -- WHY DOES FORM DOMINATE?")
    print("  (a) each Form component ALONE (logistic), and its correlation with d_elo:")
    for c in form:
        p = logit(trva, te, [c])
        r = np.corrcoef(rows[c].fillna(0), rows["d_elo"].fillna(0))[0, 1]
        print(f"    {c:18s} alone {acc(p, y)*100:5.2f}%   corr with d_elo {r:+.3f}")
    print("  (b) Form-only GBM, then leave one component out (drop = that component's UNIQUE value):")
    m_f, gain_f, p_f = gbm(tr, va, te, form, args.seed); a_f = acc(p_f, y)
    print(f"    Form only (all {len(form)}):        {a_f*100:5.2f}%")
    for c in form:
        cc = [x for x in form if x != c]
        _, _, p = gbm(tr, va, te, cc, args.seed)
        print(f"    without {c:18s} {acc(p, y)*100:5.2f}%   ({(acc(p, y)-a_f)*100:+.2f})")
    print("  (c) is Form a short-horizon Elo?  Form-only vs Elo-only, and how often they agree:")
    agree = ((p_f >= 0.5) == (p_elo >= 0.5)).mean()
    print(f"    Form-only {a_f*100:.2f}%   Elo-only {a_elo*100:.2f}%   same pick on {agree*100:.1f}% of matches")
    both = pd.DataFrame({"f": p_f, "e": p_elo}); print(f"    correlation of the two probabilities: {both.corr().iloc[0,1]:.3f}")
    print("    reading: if the two agree on ~85%+ of matches and correlate ~0.8+, Form is largely a fresher,")
    print("    shorter-memory version of Elo (recent results) rather than a different kind of information.")

    # ---------------------------------------------------------------- Q2
    hr("Q2 -- WHY DO SERVE AND RETURN NOT SHOW UP?")
    print("  models on the same split (reference NO-RATING = %.2f%%):" % (a_nr * 100))
    tests = {
        "A) NO-RATING minus Form (Serve+Return+Physical+Matchup+Context)": [c for c in no_rating if c not in form],
        "B) Serve + Return only": serve + ret,
        "C) Hold%, Break%, Hold+Break only": [c for c in HB if c in cols],
        "D) point-level stats only": [c for c in POINT if c in cols],
        "E) Serve + Return + Matchup (serve-vs-return cross terms)": serve + ret + mu,
    }
    res_q2 = {}
    for k, cc in tests.items():
        _, _, p = gbm(tr, va, te, cc, args.seed)
        res_q2[k] = line(k, p, y, a_nr)
    print("  unique vs redundant, per serve/return metric (NO-RATING model): accuracy lost when scrambled,")
    print("  and how much of the metric is already explained by Form (R^2):")
    from sklearn.linear_model import LinearRegression
    Xte = te[no_rating].reset_index(drop=True)
    rng = np.random.RandomState(args.seed)
    base = acc(m_nr.predict_proba(Xte)[:, 1], y)
    for c in serve + ret:
        d = 0.0
        for _ in range(2):
            Xp = Xte.copy(); Xp[c] = Xp[c].values[rng.permutation(len(Xp))]
            d += base - acc(m_nr.predict_proba(Xp)[:, 1], y)
        M = rows[[c] + form].dropna()
        r2 = LinearRegression().fit(M[form], M[c]).score(M[form], M[c]) if len(M) > 500 else np.nan
        r_win = np.corrcoef(rows[c].fillna(0), rows["label"])[0, 1]
        print(f"    {c:20s} corr(win) {r_win:+.3f}   R^2 explained by Form {r2:.3f}   scrambled loss {d/2*100:+.2f} pts")
    print("  reading: high corr(win) + high R^2-by-Form + ~0 scrambled loss = real signal, but ALREADY INSIDE FORM.")

    # ---------------------------------------------------------------- Q3
    hr("Q3 -- TRUE VALUE OF HOLD+BREAK")
    hb = ["d_hold_plus_break"]
    for k, cc in (("Hold+Break alone", hb), ("Hold+Break + Form", hb + form), ("Form alone", form),
                  ("Hold+Break + Matchup", hb + mu), ("Matchup alone", mu),
                  ("Hold+Break + Physical", hb + phys), ("Physical alone", phys)):
        _, _, p = gbm(tr, va, te, cc, args.seed) if len(cc) > 1 else (None, None, logit(trva, te, cc))
        line(k, p, y)
    print("  reading: incremental value of Hold+Break = (X + Hold+Break) minus (X alone).")

    # ---------------------------------------------------------------- Q4
    hr("Q4 -- WHAT PART OF TENNIS REALITY BEATS ELO?  (per-match tree contributions on disagreements)")
    pk_nr = (p_nr >= 0.5).astype(int); pk_e = (p_elo >= 0.5).astype(int)
    dis = pk_nr != pk_e
    C = contribs(m_nr, te[no_rating])
    # contribution toward the TENNIS MODEL'S PICK (positive = pushed toward the pick)
    sign = np.where(pk_nr == 1, 1.0, -1.0)
    Cp = C.mul(sign, axis=0)
    G = pd.DataFrame({g: Cp[[c for c in no_rating if grp[c] == g]].sum(axis=1) for g in GROUPS if any(grp[c] == g for c in no_rating)})
    right = (pk_nr == y)
    def show(mask, title):
        n = int(mask.sum())
        if n == 0:
            return
        gm = G[mask].clip(lower=0); tot = gm.sum(axis=1).replace(0, np.nan)
        share = (gm.div(tot, axis=0)).mean().sort_values(ascending=False)
        print(f"  {title} (n={n:,}): average share of the push toward the tennis pick, by group")
        for g, v in share.items():
            print(f"    {g:9s} {v*100:5.1f}%")
        dom = gm.idxmax(axis=1).value_counts()
        print("    dominant group counts: " + ", ".join(f"{g}={int(v)}" for g, v in dom.items()))
    show(dis, "ALL disagreements")
    show(dis & right, "disagreements the tennis model GOT RIGHT")
    show(dis & ~right, "disagreements the tennis model GOT WRONG")
    print("  top 12 individual features pushing the tennis pick on disagreements (mean contribution, right vs wrong):")
    tops = Cp[dis].mean().sort_values(ascending=False).head(12)
    for c, v in tops.items():
        print(f"    {c:26s} all {v:+.3f}   when right {Cp[dis & right][c].mean():+.3f}   when wrong {Cp[dis & ~right][c].mean():+.3f}   [{grp[c]}]")
    print("  which profile benefits: on disagreements, accuracy of the tennis pick when a group was the dominant driver:")
    dom_all = G[dis].clip(lower=0).idxmax(axis=1)
    for g in dom_all.unique():
        mk = (dom_all == g).values
        yy = y[dis][mk]; pp = pk_nr[dis][mk]
        if len(yy) >= 30:
            r = (pp == yy).mean()
            print(f"    driver {g:9s} n={len(yy):5,}  tennis right {r*100:5.1f}% (+/- {se(r, len(yy)):.1f})")

    # ---------------------------------------------------------------- Q5 / Q6
    def per_slice(title, masks):
        hr(title)
        for name, (mtr, mva, mte) in masks.items():
            if mte.sum() < 300 or mtr.sum() < 2000:
                print(f"  {name}: too few rows (test {int(mte.sum())})"); continue
            trs, vas, tes = tr[mtr.values], va[mva.values], te[mte.values].reset_index(drop=True)
            ys = tes["label"].values
            m_all, g_all, p_all = gbm(trs, vas, tes, cols, args.seed)
            m_n, g_n, p_n = gbm(trs, vas, tes, no_rating, args.seed)
            pe = logit(pd.concat([trs, vas]), tes, ["d_elo", "d_surf_elo"])
            _, _, ph = (None, None, logit(pd.concat([trs, vas]), tes, ["d_hold_plus_break"]))
            print(f"\n  {name}: test n={len(tes):,}   ALL {acc(p_all, ys)*100:.2f}%   NO-RATING {acc(p_n, ys)*100:.2f}%   "
                  f"Elo-only {acc(pe, ys)*100:.2f}%   Hold+Break-only {acc(ph, ys)*100:.2f}%")
            sh, drops = perm_shares(m_all, tes[cols], ys, cols, args.seed)
            print("    ALL-model group weights (permutation): " + "  ".join(f"{g} {v:.0f}%" for g, v in sh.items() if v > 0))
            gt = g_all.sum() or 1
            print("    ALL-model top 6 by gain: " + ", ".join(f"{c} {100*v/gt:.0f}%" for c, v in g_all.sort_values(ascending=False).head(6).items()))
            sh2, _ = perm_shares(m_n, tes[no_rating], ys, no_rating, args.seed)
            print("    NO-RATING group weights (permutation): " + "  ".join(f"{g} {v:.0f}%" for g, v in sh2.items() if v > 0))
            d = (p_n >= 0.5).astype(int) != (pe >= 0.5).astype(int)
            if d.sum() >= 30:
                r = ((p_n[d] >= 0.5).astype(int) == ys[d]).mean()
                print(f"    NO-RATING vs Elo disagreements {int(d.sum()):,}: tennis right {r*100:.1f}% (+/- {se(r, int(d.sum())):.1f})")
    per_slice("Q5 -- IS CLAY DIFFERENT?  (separate models per surface)",
              {s: ((tr.surface == s), (va.surface == s), (te.surface == s)) for s in ("Hard", "Clay", "Grass")})
    is_slam = lambda d: d.level.astype(str) == "G"
    per_slice("Q6 -- GRAND SLAMS vs everything else (separate models)",
              {"Slams (level G)": (is_slam(tr), is_slam(va), is_slam(te)), "non-Slam": (~is_slam(tr), ~is_slam(va), ~is_slam(te))})
    print("  note: Slam matches are best-of-5 for men, and Slam draws are 128 = many first-round mismatches;")
    print("  both make current level of play count for more than in short best-of-3 250 events.")

    # ---------------------------------------------------------------- Q7
    hr("Q7 -- HIGH-CONFIDENCE DISAGREEMENTS: threshold sweep (NO-RATING vs Elo-only)")
    conf = np.abs(p_nr - 0.5) + 0.5
    print(f"  {'threshold':>9s} {'n disagree':>10s} {'tennis right':>12s} {'+/-':>5s} {'Elo right':>9s}   {'n ALL matches >= thr':>20s} {'acc ALL':>7s}")
    for thr in (0.50, 0.52, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70):
        mk = dis & (conf >= thr)
        n = int(mk.sum())
        if n == 0:
            continue
        r = (pk_nr[mk] == y[mk]).mean()
        ma = conf >= thr
        print(f"  {thr:9.2f} {n:10,} {r*100:11.1f}% {se(r, n):5.1f} {100*(1-r):8.1f}%   {int(ma.sum()):20,} {acc(p_nr[ma], y[ma])*100:6.2f}%")
    print("  drivers of high-confidence (>=0.58) disagreements vs low-confidence (<0.55), by group share of the push:")
    show(dis & (conf >= 0.58), "high-confidence disagreements")
    show(dis & (conf < 0.55), "low-confidence disagreements")

    # ---------------------------------------------------------------- Q8
    hr("Q8 -- PURE TENNIS MODEL (no Elo, surface Elo, rank, rank pts, and no opponent-Elo form features)")
    pure = [c for c in no_rating if c not in ELO_DERIVED]
    m_p, gain_p, p_p = gbm(tr, va, te, pure, args.seed)
    a_p = line(f"PURE tennis ({len(pure)} features)", p_p, y)
    line("NO-RATING (for reference)", p_nr, y); line("Elo-only logistic", p_elo, y)
    print("  by year: " + "   ".join(f"{yv} {acc(p_p[te.year.values==yv], y[te.year.values==yv])*100:.2f}%" for yv in sorted(te.year.unique())))
    sh, drops = perm_shares(m_p, te[pure], y, pure, args.seed)
    print("  group weights (permutation): " + "  ".join(f"{g} {v:.0f}%" for g, v in sh.items() if v > 0))
    gt = gain_p.sum() or 1
    print("  top 10 by gain: " + ", ".join(f"{c} {100*v/gt:.1f}%" for c, v in gain_p.sort_values(ascending=False).head(10).items()))
    d = (p_p >= 0.5).astype(int) != pk_e
    r = ((p_p[d] >= 0.5).astype(int) == y[d]).mean()
    print(f"  PURE vs Elo-only disagreements {int(d.sum()):,}: pure right {r*100:.1f}% (+/- {se(r, int(d.sum())):.1f})")
    cp = np.abs(p_p - 0.5) + 0.5
    for thr in (0.55, 0.60):
        mk = d & (cp >= thr); n = int(mk.sum())
        if n:
            r = ((p_p[mk] >= 0.5).astype(int) == y[mk]).mean()
            print(f"    at pure-confidence >= {thr:.2f}: n={n:,}  pure right {r*100:.1f}% (+/- {se(r, n):.1f})")

    # ---------------------------------------------------------------- Q9
    hr("Q9 -- PLAYER TYPES: where does the tennis model (NO-RATING) beat Elo?  (disagreements only)")
    print("  types are defined from the A-minus-B differences available in the rows, from the tennis pick's point of view;")
    print("  a flag prints only when >2 standard errors from 50/50; ~15 slices are tested, so expect ~1 false flag by chance.")
    D = te.copy()
    def pv(col):   # value from the tennis pick's point of view
        return np.where(pk_nr == 1, D[col].fillna(0), -D[col].fillna(0))
    T = {
        "younger 3y+ AND hotter form (rising)": (pv("d_age") <= -3) & (pv("d_win_20") > 0.05),
        "younger 3y+ AND colder form": (pv("d_age") <= -3) & (pv("d_win_20") < -0.05),
        "older 5y+ AND colder form (veteran declining?)": (pv("d_age") >= 5) & (pv("d_win_20") < -0.05),
        "older 5y+ AND hotter form": (pv("d_age") >= 5) & (pv("d_win_20") > 0.05),
        "coming off a layoff (60+ days more rest than opp)": pv("d_days_since") >= 60,
        "opponent coming off a layoff": pv("d_days_since") <= -60,
        "big server (ace rate 3pts+ higher)": pv("d_ace_rate") >= 0.03,
        "weaker server (ace rate 3pts+ lower)": pv("d_ace_rate") <= -0.03,
        "surface specialist (surface win% beats own overall by 10+)": (pv("d_s_win_pct") - pv("d_win_20")) >= 0.10,
        "surface liability (surface win% below own overall by 10+)": (pv("d_s_win_pct") - pv("d_win_20")) <= -0.10,
        "better hold+break by 5pts+": pv("d_hold_plus_break") >= 0.05,
        "worse hold+break by 5pts+": pv("d_hold_plus_break") <= -0.05,
        "much lower Elo (100+ below)": pv("d_elo") <= -100,
        "played 3+ more matches in 14d (match-tight)": pv("d_matches_14d") >= 3,
        "retired in last 90d (pick)": pv("d_retired_90d") >= 1,
        "opponent retired in last 90d": pv("d_retired_90d") <= -1,
    }
    for name, mk in T.items():
        mk = mk & dis
        n = int(mk.sum())
        if n < 30:
            print(f"    {name:52s} n={n:4,}  (too few)"); continue
        r = (pk_nr[mk] == y[mk]).mean()
        flag = " <-- tennis clearly better" if r > 0.5 + 2 * se(r, n) / 100 else (" <-- Elo clearly better" if r < 0.5 - 2 * se(r, n) / 100 else "")
        print(f"    {name:52s} n={n:4,}  tennis right {r*100:5.1f}% (+/- {se(r,n):4.1f}){flag}")

    hr("SUMMARY (numbers only -- read together)")
    print(f"  Elo-only {a_elo*100:.2f}%   NO-RATING {a_nr*100:.2f}%   PURE tennis {a_p*100:.2f}%   Form-only {a_f*100:.2f}%")
    for k, v in res_q2.items():
        print(f"  {k[:60]:60s} {v*100:.2f}%")
    print(f"[{MARKER}] done -- no features added.")


if __name__ == "__main__":
    main()
