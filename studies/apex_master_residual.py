#!/usr/bin/env python3
"""
apex_master_residual.py -- 2026-08-17   MASTER RESIDUAL TEST.

Question: do the hundreds of tiny effects (ratings, form, serve/return, hold/break, matchup, physical, geography,
style) ADD UP to something on top of Pinnacle's closing line, or does the combined model still fail?

Inputs (all already on the Mini):
  apex_batch_a_rows.csv   priced rows (Pinnacle fair prob) with the 54 base features + geography features
  apex_batch_c_rows.pkl   style features for rows where both players had >= 5 charts (joined; NaN elsewhere + flag)

Models (fit <= 2021, tune 2022-23 for early stopping, score 2024+; logistic fit <= 2023):
  M0  Pinnacle alone (calibration refit)
  M1  Pinnacle + ALL families            -- (a) L2 logistic, (b) GBM with logit(Pinnacle) as a feature,
                                            (c) stack: GBM on features only -> its logit + logit(Pinnacle) in a logistic
  M2  Pinnacle + NON-RATING families      -- same three forms
Reports: logloss change with paired-bootstrap SE, accuracy, calibration deciles (Pinnacle vs best model),
by-year gains, family importance (GBM gain share + permutation loss on the residual model), and what happens
if you bet only where the master model disagrees with Pinnacle.

USAGE:  python3 apex_master_residual.py            |   python3 apex_master_residual.py --selftest
"""
import argparse, os, sys, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_combined_model as acm

MARKER = "APEX-MASTER-2026-08-17"
GEO = ["d_travel_km", "d_km_30d", "d_km_60d", "d_tz_abs", "d_tz_east", "d_tz_west", "d_days_since_arrival", "d_alt_change", "d_alt_rec_x_alt", "d_indoor_rec_x_indoor"]
SKIP = {"date", "year", "tour", "surface", "level", "round", "tourney_id", "player_a", "player_b", "label", "best_of", "pinn_a", "geo_hit",
        "indoor_match", "venue_alt", "engine_a", "p_gbm", "p_logit", "p_elo", "na", "nb", "rank_a", "rank_b"}


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def logit_(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


def family(c):
    if c in GEO or c.startswith("a_travel") or c.startswith("a_km") or c.startswith("a_tz") or c.startswith("a_days") or c.startswith("a_alt") or c.startswith("a_indoor") \
       or c.startswith("b_travel") or c.startswith("b_km") or c.startswith("b_tz") or c.startswith("b_days") or c.startswith("b_alt") or c.startswith("b_indoor"):
        return "Geography"
    if c.startswith("mu_I") or c.startswith("style_") or c.startswith("gap_") or c == "has_style" or c.startswith("s_d_"):
        return "Style"
    g = acm.group_for(c)
    if g in ("Serve", "Return") and ("hold" in c or "break" in c or "bp_" in c):
        return "Hold/Break"
    return g


def ll_rows(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot_se(d, n=500, seed=0):
    rng = np.random.RandomState(seed); m = []
    for _ in range(n):
        idx = rng.randint(0, len(d), len(d)); m.append(d[idx].mean())
    return float(np.std(m))


def fit_logistic(H, S, feats, C=0.3):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    XH = np.column_stack([logit_(H["pinn_a"].values)] + [H[f].astype(float).values for f in feats])
    XS = np.column_stack([logit_(S["pinn_a"].values)] + [S[f].astype(float).values for f in feats])
    m = make_pipeline(SimpleImputer(strategy="constant", fill_value=0.0), StandardScaler(), LogisticRegression(C=C, max_iter=5000))
    m.fit(XH, H["label"].values)
    return m.predict_proba(XS)[:, 1]


def fit_gbm(tr, va, S, feats, with_pinn, seed=7):
    import xgboost as xgb
    def X(D):
        cols = [D[f].astype(float).values for f in feats]
        if with_pinn:
            cols = [logit_(D["pinn_a"].values)] + cols
        return np.column_stack(cols)
    m = xgb.XGBClassifier(n_estimators=2000, learning_rate=0.02, max_depth=3, subsample=0.8, colsample_bytree=0.6, min_child_weight=50,
                          reg_lambda=5.0, tree_method="hist", eval_metric="logloss", early_stopping_rounds=100, random_state=seed, n_jobs=4)
    m.fit(X(tr), tr["label"].values, eval_set=[(X(va), va["label"].values)], verbose=False)
    imp = m.get_booster().get_score(importance_type="total_gain")
    names = (["logit_pinnacle"] if with_pinn else []) + feats
    gain = pd.Series({names[int(k[1:])]: v for k, v in imp.items()})
    return m, m.predict_proba(X(S))[:, 1], gain, X


def stack(tr, va, S, feats):
    """GBM on features only (no market) -> its logit, then logistic(logit(P), logit(gbm)) fit on tune+train out-of-fold-ish (use va)."""
    m, p_S, gain, X = fit_gbm(tr, va, S, feats, with_pinn=False)
    from sklearn.linear_model import LogisticRegression
    p_va = m.predict_proba(X(va))[:, 1]
    lg = LogisticRegression(max_iter=2000).fit(np.column_stack([logit_(va["pinn_a"].values), logit_(p_va)]), va["label"].values)
    p = lg.predict_proba(np.column_stack([logit_(S["pinn_a"].values), logit_(p_S)]))[:, 1]
    return p, lg.coef_[0], gain


def calib_table(p, y, title):
    q = pd.qcut(pd.Series(p), 10, labels=False, duplicates="drop")
    print(f"  {title}: {'decile':7s} {'n':>6s} {'mean pred':>10s} {'actual':>8s} {'gap':>7s}")
    for b in sorted(q.dropna().unique()):
        m = (q == b).values
        print(f"  {'':9s} {int(b)+1:<7d} {int(m.sum()):6,} {p[m].mean()*100:9.1f}% {y[m].mean()*100:7.1f}% {(y[m].mean()-p[m].mean())*100:+6.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--priced", default="apex_batch_a_rows.csv")
    ap.add_argument("--style", default="apex_batch_c_rows.pkl")
    ap.add_argument("--test-from", type=int, default=2024)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    print(f"[{MARKER}] every feature family on top of Pinnacle at once")

    if args.selftest:
        rng = np.random.RandomState(0); n = 12000
        R = pd.DataFrame({"year": rng.choice(range(2012, 2027), n), "label": 0, "date": "2020-01-01", "player_a": "a", "player_b": "b", "tour": "ATP", "level": "A"})
        R["pinn_a"] = 1 / (1 + np.exp(-rng.normal(0, 1, n)))
        for c in ["d_elo", "d_surf_elo", "d_win_20", "d_hold_pct", "d_break_pct", "d_svc_pts_won", "d_ret_pts_won", "d_h2h", "d_age", "d_days_since"] + GEO:
            R[c] = rng.normal(0, 1, n)
        R["mu_I3"] = rng.normal(0, 1, n); R.loc[rng.rand(n) < 0.6, "mu_I3"] = np.nan
        R["label"] = (rng.rand(n) < 1 / (1 + np.exp(-(logit_(R["pinn_a"].values) + 0.0 * R["d_elo"].values)))).astype(int)
        S_style = None
    else:
        R = pd.read_csv(args.priced, low_memory=False)
        R["date"] = pd.to_datetime(R["date"]).dt.date
        print(f"priced rows: {len(R):,}")
        S_style = pd.read_pickle(args.style) if os.path.exists(args.style) else None

    if S_style is not None:
        keep = ["date", "player_a", "player_b"] + [c for c in S_style.columns if c.startswith("mu_") or c in ("style_dist", "gap_rally", "gap_net", "gap_aggr")
                                                    or c.startswith("style_dist_x") or c.startswith("gap_") ]
        st = S_style[keep].drop_duplicates(["date", "player_a", "player_b"])
        st = st.rename(columns={c: c for c in st.columns})
        R = R.merge(st, on=["date", "player_a", "player_b"], how="left")
        print(f"style features joined for {R['mu_I1'].notna().mean()*100:.1f}% of priced rows (NaN + flag elsewhere)")
    R["has_style"] = R[[c for c in R.columns if c.startswith("mu_I")]].notna().any(axis=1).astype(int) if any(c.startswith("mu_I") for c in R.columns) else 0

    feats = [c for c in R.columns if c not in SKIP and (c.startswith("d_") or c.startswith("mu_") or c.startswith("h2h") or c in ("lefty_vs_righty", "ht_gap", "is_wta", "is_bo5", "has_style")
                                                            or c.startswith("style_dist_x") or c.startswith("gap_"))]
    feats = [c for c in feats if R[c].dtype != object]
    fam = {c: family(c) for c in feats}
    print(f"features: {len(feats)}  by family: " + ", ".join(f"{g}={sum(1 for c in feats if fam[c]==g)}" for g in sorted(set(fam.values()))))
    non_rating = [c for c in feats if fam[c] != "Rating"]

    tr = R[R.year <= args.test_from - 3]; va = R[(R.year > args.test_from - 3) & (R.year < args.test_from)]; H = R[R.year < args.test_from]; S = R[R.year >= args.test_from].reset_index(drop=True)
    y = S["label"].values
    print(f"train {len(tr):,} / tune {len(va):,} / score {len(S):,} ({args.test_from}+)")

    hr("M0 -- Pinnacle alone")
    p0 = fit_logistic(H, S, [])
    l0 = ll_rows(p0, y); raw = ll_rows(S["pinn_a"].values, y)
    print(f"  raw Pinnacle LL {raw.mean():.4f}   calibration refit LL {l0.mean():.4f}   accuracy {(( (p0>=.5).astype(int))==y).mean()*100:.2f}%")

    results = {}
    def report(name, p):
        l = ll_rows(p, y); d = l0 - l
        se = boot_se(d)
        acc = (((p >= .5).astype(int)) == y).mean()
        print(f"  {name:44s} LL {l.mean():.4f}   gain vs Pinnacle {d.mean():+.4f} (+/- {se:.4f}, {d.mean()/se if se>0 else 0:+.1f} SE)   acc {acc*100:.2f}%   {'PASS' if d.mean() >= 0.002 else 'no'}")
        results[name] = (p, d.mean(), se)
        return d
    hr("M1 -- Pinnacle + ALL feature families")
    report("logistic (L2)", fit_logistic(H, S, feats))
    m_all, p_g, gain_all, X_all = fit_gbm(tr, va, S, feats, with_pinn=True); report("GBM (Pinnacle as a feature)", p_g)
    p_st, coef_st, gain_st = stack(tr, va, S, feats); report(f"stack (GBM-on-features + Pinnacle; weights P {coef_st[0]:.2f} / model {coef_st[1]:.2f})", p_st)
    hr("M2 -- Pinnacle + NON-RATING families only")
    report("logistic (L2)", fit_logistic(H, S, non_rating))
    m_nr, p_gn, gain_nr, _ = fit_gbm(tr, va, S, non_rating, with_pinn=True); report("GBM (Pinnacle as a feature)", p_gn)
    p_stn, coef_stn, _ = stack(tr, va, S, non_rating); report(f"stack (weights P {coef_stn[0]:.2f} / model {coef_stn[1]:.2f})", p_stn)

    hr("by year (best of M1 forms vs Pinnacle refit)")
    best_name = max(results, key=lambda k: results[k][1]); pb = results[best_name][0]
    print(f"  best form: {best_name}")
    for yv in sorted(S.year.unique()):
        m = (S.year == yv).values
        print(f"    {yv}: n={int(m.sum()):5,}  Pinnacle LL {l0[m].mean():.4f}   model {ll_rows(pb[m], y[m]).mean():.4f}   gain {(l0[m]-ll_rows(pb[m], y[m])).mean():+.4f}")

    hr("calibration (score rows)")
    calib_table(p0, y, "Pinnacle refit")
    calib_table(pb, y, "best model   ")

    hr("family importance")
    gt = gain_all.sum() or 1
    fam_gain = {}
    for c, v in gain_all.items():
        fam_gain[family(c) if c != "logit_pinnacle" else "Pinnacle"] = fam_gain.get(family(c) if c != "logit_pinnacle" else "Pinnacle", 0) + v
    print("  GBM gain share (Pinnacle + all):  " + ", ".join(f"{g} {100*v/gt:.1f}%" for g, v in sorted(fam_gain.items(), key=lambda kv: -kv[1])))
    print("  permutation on the score set (LL lost when a family is scrambled, GBM Pinnacle+all):")
    Xs = X_all(S); base = ll_rows(m_all.predict_proba(Xs)[:, 1], y).mean(); rng = np.random.RandomState(0)
    names = ["logit_pinnacle"] + feats
    for g in sorted(set(fam.values())) + ["Pinnacle"]:
        idx = [i for i, nme in enumerate(names) if (nme == "logit_pinnacle" and g == "Pinnacle") or (nme != "logit_pinnacle" and fam.get(nme) == g)]
        if not idx: continue
        Xp = Xs.copy(); perm = rng.permutation(len(Xp)); Xp[:, idx] = Xp[perm][:, idx]
        print(f"    {g:11s} +{(ll_rows(m_all.predict_proba(Xp)[:, 1], y).mean()-base):.4f} LL")
    print("  top 15 individual features by GBM gain:")
    for c, v in gain_all.sort_values(ascending=False).head(15).items():
        print(f"    {c:28s} {100*v/gt:5.1f}%  [{'Pinnacle' if c=='logit_pinnacle' else family(c)}]")

    hr("if you only bet where the master model disagrees with Pinnacle (best form)")
    pk = (pb >= .5).astype(int); pp = (S["pinn_a"].values >= .5).astype(int); dis = pk != pp
    if dis.sum():
        r = (pk[dis] == y[dis]).mean()
        print(f"  disagreements {int(dis.sum()):,} of {len(S):,}: model right {r*100:.1f}% (+/- {100*np.sqrt(r*(1-r)/dis.sum()):.1f})   Pinnacle right {100*(1-r):.1f}%")
        for lo, hi in ((0.0, 0.03), (0.03, 0.06), (0.06, 1.0)):
            e = np.abs(pb - S["pinn_a"].values); m = dis & (e >= lo) & (e < hi)
            if m.sum() >= 30:
                print(f"    |model - Pinnacle| {lo:.2f}-{hi:.2f}: n={int(m.sum()):4,}  model right {100*(pk[m]==y[m]).mean():.1f}%")
    print(f"\n[{MARKER}] done.  Verdict rule: only a gain >= +0.002 that is >= 2 SE and holds across years counts.")


if __name__ == "__main__":
    main()
