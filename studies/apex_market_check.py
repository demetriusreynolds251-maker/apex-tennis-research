#!/usr/bin/env python3
"""
apex_market_check.py -- 2026-08-17   Market-comparison study. Existing models, existing data, no new features.

Question: do the signals that let the tennis model beat Elo (age, rest, workload, matchup, clay)
also beat Pinnacle, or does the market already price them?

Uses apex_rows_cache.pkl (rows) + tennis-data.co.uk files in ./odds/ (Pinnacle closing prices,
PSW/PSL; Avg used where PS missing). Pinnacle prices are joined AFTER modelling and used only here.

Reports
  0  coverage of the Pinnacle join
  A  all NO-RATING vs Elo disagreements: n, NO-RATING acc, Elo acc, Pinnacle-fav acc, loglosses
  B  same at NO-RATING confidence >= .55 / .60 / .65 (also ALL-model and PURE at the same gates)
  C  NO-RATING vs Pinnacle disagreements: model right / Pinnacle right, gated, and sliced by
     Clay / Hard / Grass / ATP / WTA / Slam / non-Slam
  D  do age / rest / workload / matchup effects survive Pinnacle?
       (i)  per-match drivers on NO-RATING-vs-Pinnacle disagreements -> hit rate by dominant group
       (ii) player-type slices vs Pinnacle (younger&colder, opp off layoff, big server, workload, hold+break, clay)
       (iii) residual test: logistic on logit(Pinnacle) + feature diffs, fit on years <= 2023, scored 2024+;
             logloss vs Pinnacle alone. If a feature improves logloss on top of Pinnacle, the market
             did NOT fully price it.
  E  flat-stake result if the gated picks had been bet at Pinnacle's own price (context only)

USAGE:  python3 apex_market_check.py            (needs apex_combined_model.py, apex_rows_cache.pkl, ./odds/)
        python3 apex_market_check.py --selftest
"""
import argparse, os, sys, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_combined_model as acm

MARKER = "APEX-MARKET-2026-08-17"
GROUPS = ["Rating", "Serve", "Return", "Form", "Physical", "Matchup", "Context"]
ELO_DERIVED = ["d_opp_elo_10", "d_adj_form_10"]
CIRC = ["d_age", "d_days_since", "d_matches_14d", "d_minutes_14d", "d_sets_14d", "d_retired_90d", "d_ret_rate",
        "d_surface_switch", "mu_serve_edge", "d_hold_plus_break", "d_games_dom_10", "d_win_20", "d_h2h", "d_ht", "d_left"]


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def acc(p, y):
    return float(((p >= 0.5).astype(int) == y).mean())


def se(p, n):
    return 100 * np.sqrt(p * (1 - p) / max(n, 1))


def ll(p, y):
    return acm.logloss(np.asarray(p, dtype=float), y)


def logit_(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


def contribs(m, X):
    import xgboost as xgb
    c = m.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)
    return pd.DataFrame(c[:, :-1], columns=X.columns)


def report_subset(title, T, mask, cols_p):
    n = int(mask.sum())
    print(f"\n  {title}: n={n:,}")
    if n < 20:
        print("    (too few)"); return
    S = T[mask]; y = S["label"].values
    for name, col in cols_p:
        p = S[col].values
        print(f"    {name:20s} acc {acc(p, y)*100:5.1f}% (+/- {se(acc(p,y), n):.1f})   logloss {ll(p, y):.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="apex_rows_cache.pkl")
    ap.add_argument("--odds-dir", default="odds")
    ap.add_argument("--test-from", type=int, default=2024)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        args.cache = "/tmp/apex_fake/rows.pkl"; args.odds_dir = "/tmp/apex_fake/odds"
        if not os.path.exists(args.cache):
            d = acm.make_fake("/tmp/apex_fake"); df = acm.load_sackmann(d, 2015, False)
            acm.build_rows(df, 5, 7, True).to_pickle(args.cache)
    rows = pd.read_pickle(args.cache)
    print(f"[{MARKER}] rows {len(rows):,}   market used for evaluation only")
    cols = acm.feature_columns(rows)
    grp = {c: acm.group_for(c) for c in cols}
    tr = rows[rows.year <= args.test_from - 3]
    va = rows[(rows.year > args.test_from - 3) & (rows.year < args.test_from)]
    te = rows[rows.year >= args.test_from].reset_index(drop=True)
    trva = pd.concat([tr, va]); y = te["label"].values
    no_rating = [c for c in cols if grp[c] != "Rating"]
    pure = [c for c in no_rating if c not in ELO_DERIVED]

    # models (same as before)
    m_all, _, _ = acm.fit_gbm(tr[cols], tr["label"], va[cols], va["label"], args.seed)
    m_nr, _, _ = acm.fit_gbm(tr[no_rating], tr["label"], va[no_rating], va["label"], args.seed)
    m_pu, _, _ = acm.fit_gbm(tr[pure], tr["label"], va[pure], va["label"], args.seed)
    elo_lr = acm.fit_logit(trva[["d_elo", "d_surf_elo"]].astype(float), trva["label"])
    te["p_all"] = m_all.predict_proba(te[cols])[:, 1]
    te["p_nr"] = m_nr.predict_proba(te[no_rating])[:, 1]
    te["p_pure"] = m_pu.predict_proba(te[pure])[:, 1]
    te["p_elo"] = elo_lr.predict_proba(te[["d_elo", "d_surf_elo"]].astype(float))[:, 1]

    # ---------------------------------------------------------------- 0 join
    hr("0 -- Pinnacle join (tennis-data files, tournament-span matcher, unique pairing)")
    odds = acm.load_odds(args.odds_dir) if os.path.isdir(args.odds_dir) else None
    if odds is None:
        sys.exit("no odds files found -- put tennis-data.co.uk xls/xlsx/csv files in ./odds/")
    te = acm.market_join(te, odds)
    T = te[te["pinn_a"].notna()].reset_index(drop=True)
    print(f"  test rows {len(te):,}  matched to a Pinnacle price {len(T):,} ({100*len(T)/len(te):.1f}%)")
    print("  matched by year: " + ", ".join(f"{yv}={n:,}" for yv, n in T.groupby("year").size().items()))
    print("  matched by tour: " + ", ".join(f"{t}={n:,}" for t, n in T.groupby("tour").size().items()))
    if len(T) < 500:
        sys.exit("too few matched rows to say anything")
    yT = T["label"].values
    P = {"NO-RATING": "p_nr", "PURE": "p_pure", "ALL groups": "p_all", "Elo-only": "p_elo", "Pinnacle (fair)": "pinn_a"}
    print("\n  on ALL matched rows:")
    for name, col in P.items():
        print(f"    {name:16s} acc {acc(T[col].values, yT)*100:5.2f}%   logloss {ll(T[col].values, yT):.4f}")
    print("  (Pinnacle's own favourite accuracy is the bar; a model 'beating Elo' but below this line is not beating the market)")

    # ---------------------------------------------------------------- A/B
    hr("A/B -- NO-RATING vs Elo disagreements, on Pinnacle-priced matches, by NO-RATING confidence gate")
    pk_nr = (T["p_nr"] >= 0.5).astype(int).values; pk_e = (T["p_elo"] >= 0.5).astype(int).values
    pk_pn = (T["pinn_a"] >= 0.5).astype(int).values
    dis_e = pk_nr != pk_e
    conf_nr = np.abs(T["p_nr"].values - 0.5) + 0.5
    cols_p = [("NO-RATING", "p_nr"), ("Elo-only", "p_elo"), ("Pinnacle fav", "pinn_a"), ("ALL groups", "p_all"), ("PURE", "p_pure")]
    report_subset("A) all NO-RATING-vs-Elo disagreements", T, dis_e, cols_p)
    for thr in (0.55, 0.60, 0.65):
        report_subset(f"B) disagreements at NO-RATING confidence >= {thr:.2f}", T, dis_e & (conf_nr >= thr), cols_p)
    print("\n  same gates, but did the tennis pick beat PINNACLE'S pick on those matches?")
    for thr in (0.50, 0.55, 0.60, 0.65):
        mk = dis_e & (conf_nr >= thr)
        n = int(mk.sum())
        if n < 20:
            continue
        agree_pn = (pk_nr[mk] == pk_pn[mk]).mean()
        r_m = (pk_nr[mk] == yT[mk]).mean(); r_p = (pk_pn[mk] == yT[mk]).mean()
        print(f"    gate >= {thr:.2f}: n={n:5,}  tennis pick = Pinnacle pick on {agree_pn*100:5.1f}%   tennis right {r_m*100:5.1f}%   Pinnacle right {r_p*100:5.1f}%")
    print("  reading: if the tennis pick equals Pinnacle's pick most of the time at these gates, 'beating Elo' was")
    print("  mostly 'agreeing with the market where Elo was stale' -- an internal improvement, not an edge.")

    # ---------------------------------------------------------------- C
    hr("C -- NO-RATING vs PINNACLE disagreements: who identifies the winner?")
    dis_p = pk_nr != pk_pn
    def dline(label, mask, model_pk=pk_nr, pcol="p_nr"):
        n = int(mask.sum())
        if n < 25:
            print(f"    {label:38s} n={n:5,}  (too few)"); return
        r = (model_pk[mask] == yT[mask]).mean()
        flag = " <-- model clearly better" if r > 0.5 + 2 * se(r, n) / 100 else (" <-- Pinnacle clearly better" if r < 0.5 - 2 * se(r, n) / 100 else "")
        print(f"    {label:38s} n={n:5,}  model right {r*100:5.1f}% (+/- {se(r,n):4.1f})   Pinnacle right {100*(1-r):5.1f}%   "
              f"LL model {ll(T[pcol].values[mask], yT[mask]):.3f} vs Pinn {ll(T['pinn_a'].values[mask], yT[mask]):.3f}{flag}")
    print("  overall and by confidence gate:")
    for thr in (0.50, 0.55, 0.60, 0.65, 0.70):
        dline(f"NO-RATING conf >= {thr:.2f}", dis_p & (conf_nr >= thr))
    conf_all = np.abs(T["p_all"].values - 0.5) + 0.5; pk_all = (T["p_all"] >= 0.5).astype(int).values
    conf_pu = np.abs(T["p_pure"].values - 0.5) + 0.5; pk_pu = (T["p_pure"] >= 0.5).astype(int).values
    print("  ALL-groups model vs Pinnacle:")
    for thr in (0.50, 0.55, 0.60, 0.65):
        dline(f"ALL conf >= {thr:.2f}", (pk_all != pk_pn) & (conf_all >= thr), pk_all, "p_all")
    print("  PURE tennis model vs Pinnacle:")
    for thr in (0.50, 0.55, 0.60, 0.65):
        dline(f"PURE conf >= {thr:.2f}", (pk_pu != pk_pn) & (conf_pu >= thr), pk_pu, "p_pure")
    print("  by slice (NO-RATING vs Pinnacle, all disagreements | at conf >= .55):")
    slices = {"Clay": T.surface.values == "Clay", "Hard": T.surface.values == "Hard", "Grass": T.surface.values == "Grass",
              "ATP": T.tour.values == "ATP", "WTA": T.tour.values == "WTA",
              "Slams": T.level.astype(str).values == "G", "non-Slams": T.level.astype(str).values != "G"}
    for name, sm in slices.items():
        dline(f"{name} (all)", dis_p & sm)
        dline(f"{name} (conf >= .55)", dis_p & sm & (conf_nr >= 0.55))

    # ---------------------------------------------------------------- D
    hr("D -- do the age / rest / workload / matchup effects survive Pinnacle?")
    print("  (i) per-match drivers of NO-RATING-vs-Pinnacle disagreements -> hit rate vs Pinnacle by dominant group")
    C = contribs(m_nr, T[no_rating])
    sign = np.where(pk_nr == 1, 1.0, -1.0)
    Cp = C.mul(sign, axis=0)
    G = pd.DataFrame({g: Cp[[c for c in no_rating if grp[c] == g]].sum(axis=1) for g in GROUPS if any(grp[c] == g for c in no_rating)})
    dom = G.clip(lower=0).idxmax(axis=1).values
    for g in pd.unique(dom):
        mk = dis_p & (dom == g)
        dline(f"driver {g}", mk)
        mk2 = mk & (conf_nr >= 0.55)
        dline(f"driver {g} (conf >= .55)", mk2)
    print("  top pushers on disagreements with Pinnacle (mean contribution, model-right vs model-wrong):")
    right = pk_nr == yT
    for c, v in Cp[dis_p].mean().sort_values(ascending=False).head(10).items():
        print(f"    {c:24s} all {v:+.3f}   right {Cp[dis_p & right][c].mean():+.3f}   wrong {Cp[dis_p & ~right][c].mean():+.3f}   [{grp[c]}]")

    print("\n  (ii) player-type slices vs Pinnacle (from the tennis pick's point of view; disagreements only)")
    def pv(col):
        return np.where(pk_nr == 1, T[col].fillna(0).values, -T[col].fillna(0).values)
    types = {
        "younger 3y+ AND colder form": (pv("d_age") <= -3) & (pv("d_win_20") < -0.05),
        "younger 3y+ (any form)": pv("d_age") <= -3,
        "older 3y+ (any form)": pv("d_age") >= 3,
        "opponent off 60d+ layoff": pv("d_days_since") <= -60,
        "pick off 60d+ layoff": pv("d_days_since") >= 60,
        "big server (ace rate +3pts)": pv("d_ace_rate") >= 0.03,
        "played 3+ more matches in 14d": pv("d_matches_14d") >= 3,
        "played 3+ FEWER in 14d": pv("d_matches_14d") <= -3,
        "less rest (3+ fewer days)": pv("d_days_since") <= -3,
        "better hold+break by 5pts+": pv("d_hold_plus_break") >= 0.05,
        "serve-vs-return edge (mu_serve_edge > .05)": pv("mu_serve_edge") >= 0.05,
        "clay match": T.surface.values == "Clay",
        "backed Pinnacle underdog < 35%": np.where(pk_nr == 1, T["pinn_a"].values, 1 - T["pinn_a"].values) < 0.35,
        "backed Pinnacle underdog 35-50%": (np.where(pk_nr == 1, T["pinn_a"].values, 1 - T["pinn_a"].values) >= 0.35),
    }
    for name, mk in types.items():
        dline(name, dis_p & mk)

    print("\n  (iii) residual test: does each feature add information ON TOP of Pinnacle?  logistic on logit(Pinnacle) + feature,")
    print("        fitted on Pinnacle-priced matches in years <= %d, scored on %d+; logloss vs Pinnacle alone." % (args.test_from - 1, args.test_from))
    hist = rows[rows.year < args.test_from].reset_index(drop=True)
    hist = acm.market_join(hist, odds)
    H = hist[hist["pinn_a"].notna()].reset_index(drop=True)
    print(f"        history rows with a Pinnacle price: {len(H):,}   (years {H.year.min() if len(H) else '-'}..{H.year.max() if len(H) else '-'})")
    if len(H) < 2000:
        print("        too few priced history rows for the residual test (odds files may not cover the training years)")
    else:
        from sklearn.linear_model import LogisticRegression
        yH = H["label"].values
        base_te = ll(T["pinn_a"].values, yT)
        cal = {}
        def resid(feats, label):
            XH = np.column_stack([logit_(H["pinn_a"].values)] + [H[f].fillna(0).values for f in feats])
            XT = np.column_stack([logit_(T["pinn_a"].values)] + [T[f].fillna(0).values for f in feats])
            m = LogisticRegression(C=1.0, max_iter=2000).fit(XH, yH)
            p = m.predict_proba(XT)[:, 1]
            l_ = ll(p, yT)
            if not feats:
                cal["base"] = l_
            ref = cal.get("base", base_te)
            d = ref - l_
            coef = m.coef_[0]
            print(f"        {label:44s} logloss {l_:.4f}   vs Pinnacle raw {base_te:.4f} / refit {ref:.4f}   gain vs refit {d:+.4f}   pinnacle-weight {coef[0]:.2f}"
                  + ("   <-- market did NOT fully price this" if (feats and d >= 0.002) else ("" if not feats else "   (nothing beyond the market)")))
        resid([], "Pinnacle alone (calibration refit)")
        for f in CIRC:
            if f in H.columns:
                resid([f], f)
        resid([f for f in CIRC if f in H.columns], "ALL circumstance/matchup features together")
        resid(["d_age", "d_days_since", "d_matches_14d", "d_minutes_14d"], "age + rest + workload only")
        # tennis-model probability itself on top of Pinnacle
        H["p_nr"] = m_nr.predict_proba(H[no_rating])[:, 1]   # NOTE: H includes training years -> in-sample for the GBM; caveat below
        XH = np.column_stack([logit_(H["pinn_a"].values), logit_(H["p_nr"].values)]); XT = np.column_stack([logit_(T["pinn_a"].values), logit_(T["p_nr"].values)])
        m = LogisticRegression(C=1.0, max_iter=2000).fit(XH, yH); p = m.predict_proba(XT)[:, 1]
        print(f"        {'NO-RATING probability on top of Pinnacle':44s} logloss {ll(p, yT):.4f}   gain vs refit {cal.get('base', base_te)-ll(p,yT):+.4f}   weights pinn {m.coef_[0][0]:.2f} / model {m.coef_[0][1]:.2f}")
        print("        (caveat: the model's history probabilities are in-sample for years <= 2023, which flatters its weight; the 2024+ logloss is honest)")

    # ---------------------------------------------------------------- E
    hr("E -- context only: flat-stake result if the gated tennis picks had been bet at Pinnacle's fair price")
    for thr in (0.50, 0.55, 0.60, 0.65):
        mk = dis_p & (conf_nr >= thr)
        n = int(mk.sum())
        if n < 20:
            continue
        p_pick = np.where(pk_nr[mk] == 1, T["pinn_a"].values[mk], 1 - T["pinn_a"].values[mk])   # Pinnacle fair prob of the pick
        won = pk_nr[mk] == yT[mk]
        ret = np.where(won, 1 / p_pick - 1, -1.0)
        print(f"    gate >= {thr:.2f}: n={n:5,}  hit {won.mean()*100:5.1f}%  avg fair price {np.mean(1/p_pick):.2f}  return per unit {ret.mean()*100:+5.1f}%  (+/- {100*ret.std()/np.sqrt(n):.1f})")
    print("    (fair price = no vig; a real book pays less. Positive here at >2 SE would be the first sign of a real edge.)")
    T.to_csv("apex_market_check_rows.csv", index=False)
    print(f"\n  saved matched rows with all model probabilities + Pinnacle -> apex_market_check_rows.csv   [{MARKER}]")


if __name__ == "__main__":
    main()
