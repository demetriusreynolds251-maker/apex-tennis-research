#!/usr/bin/env python3
"""
apex_prop_link_study.py -- APEX-PROP-LINK-2026-08-21

Tests whether the SURVIVING moneyline findings carry over to prop outcomes.
NOT a winner model and NOT a search for new winner features. Questions:
  1. Frozen Fragility V3 score vs prop outcomes (price-controlled)
  2. Market-vs-model gap (elo_gap) vs prop outcomes
  3. Surface switch (each player's own) vs aces / double faults / total games / breaks
  4. Age gap vs prop outcomes
  5. Do high-fragility matches produce MORE VOLATILE prop outcomes (variance of
     the price-residual), not just different means?
  6. Which prop categories are LEAST explained by (winner, price) -- i.e. where
     the moneyline market has the least to say.

Discipline (same as every study this month): fit <=2023, verify on 2024+,
price controls in every regression, BH FDR 10% across all tests, retirements
excluded from totals/volatility but reported separately.

Commands:
  --build      one-time replay via apex_combined_model (year_from=2005,
               challengers EXCLUDED -- the validated cache settings); writes
               prop_rows.csv with each player's own pre-match rates + actual
               match prop outcomes
  --run        joins Pinnacle prices (apex_batch_a_rows.csv) + frozen V3
               fragility score, runs all six analyses -> prop_link_report.txt
  --selftest   synthetic: planted switch->aces and fragility->variance effects
               must be recovered; nulls must stay quiet
"""
import argparse, hashlib, json, math, os, re, sys
import numpy as np
import pandas as pd

MARKER = "APEX-PROP-LINK-2026-08-21"
ROWS_CSV = "prop_rows.csv"
ACM_SHA = "8d90fb5c89882c9aaba144d4227a4750e2485f2015f590483f4f1a510b52a12e"
LN10_400 = math.log(10) / 400.0
OUTCOMES = ["total_games", "total_breaks", "fav_aces", "dog_aces", "fav_dfs", "dog_dfs"]


def norm_name(s):
    return " ".join(sorted(re.sub(r"[^a-z ]", "", str(s).lower().strip()).split()))


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def ols(y, X):
    """OLS with heteroskedasticity-robust (HC1) t-stats. X includes intercept."""
    X = np.asarray(X, float); y = np.asarray(y, float)
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ (X.T @ y)
    e = y - X @ b
    meat = (X * (e ** 2)[:, None]).T @ X
    cov = XtX_inv @ meat @ XtX_inv * len(y) / max(len(y) - X.shape[1], 1)
    se = np.sqrt(np.maximum(np.diag(cov), 1e-12))
    return b, b / se, e


def norm_sf(z):
    from scipy.stats import norm
    return float(norm.sf(z))


def bh_flags(pvals, q=0.10):
    p = np.asarray(pvals, float); n = len(p)
    order = np.argsort(p); flags = np.zeros(n, bool); thresh = 0
    for rank, idx in enumerate(order, 1):
        if p[idx] <= q * rank / n:
            thresh = rank
    for rank, idx in enumerate(order, 1):
        if rank <= thresh:
            flags[idx] = True
    return flags


# --------------------------------------------------------------------- build
def build(sack_dir, year_from, include_challengers):
    assert os.path.exists("apex_combined_model.py"), "apex_combined_model.py missing"
    sha = hashlib.sha256(open("apex_combined_model.py", "rb").read()).hexdigest()
    print(MARKER, "-- BUILD  (acm sha %s%s)" % (sha[:16], "" if sha == ACM_SHA else "  WARNING: not v4"))
    sys.path.insert(0, os.getcwd())
    import apex_combined_model as acm
    from collections import defaultdict
    df = acm.load_sackmann(sack_dir, year_from, include_challengers)
    print("loaded %d matches (year_from=%d, challengers %s)"
          % (len(df), year_from, "in" if include_challengers else "OUT"))
    players = defaultdict(acm.PState)
    ages = {}
    rows = []
    W = {c: "w_%s" % c for c in acm.STAT_COLS}
    L = {c: "l_%s" % c for c in acm.STAT_COLS}
    for i, r in enumerate(df.itertuples(index=False)):
        if i % 50000 == 0 and i:
            print("  ... %s" % format(i, ","))
        rd = r._asdict()
        sw, sl, gw, gl, ret, wo = acm.parse_score(rd.get("score"))
        if wo:
            continue
        wn, ln = str(rd.get("winner_name")), str(rd.get("loser_name"))
        wid = rd.get("winner_id"); lid = rd.get("loser_id")
        wid = str(int(wid)) if acm.fnum(wid) is not None else "N:" + acm.norm_text(wn)
        lid = str(int(lid)) if acm.fnum(lid) is not None else "N:" + acm.norm_text(ln)
        today = rd["tdate"]; surface = rd["surface"]
        pw, pl = players[wid], players[lid]
        # ---- snapshot BEFORE update: own-level rates + switch + projected age
        if today.year >= 2005:
            fw = acm.features_for(pw, today, surface, pl.elo)
            fl = acm.features_for(pl, today, surface, pw.elo)
            wstats = {c: acm.fnum(rd.get(W[c])) for c in acm.STAT_COLS}
            lstats = {c: acm.fnum(rd.get(L[c])) for c in acm.STAT_COLS}
            def breaks_against(st):   # breaks suffered on own serve
                b, s = st.get("bpFaced"), st.get("bpSaved")
                return (b - s) if None not in (b, s) else None
            br_on_w = breaks_against(wstats)   # times W was broken (= L's breaks)
            br_on_l = breaks_against(lstats)
            rows.append({
                "date": today, "year": today.year, "tourney_id": str(rd.get("tourney_id")),
                "surface": surface, "best_of": acm.fnum(rd.get("best_of")) or 3,
                "level": str(rd.get("tourney_level")), "tour": rd["tour"],
                "w_name": wn, "l_name": ln,
                "w_elo": pw.elo, "l_elo": pl.elo,
                "w_ace_rate": fw["ace_rate"], "l_ace_rate": fl["ace_rate"],
                "w_df_rate": fw["df_rate"], "l_df_rate": fl["df_rate"],
                "w_hold": fw["hold_pct"], "l_hold": fl["hold_pct"],
                "w_switch": fw["surface_switch"], "l_switch": fl["surface_switch"],
                "w_age": acm.fnum(rd.get("winner_age")), "l_age": acm.fnum(rd.get("loser_age")),
                "w_ace": wstats.get("ace"), "l_ace": lstats.get("ace"),
                "w_df": wstats.get("df"), "l_df": lstats.get("df"),
                "games_total": gw + gl, "sets_total": sw + sl,
                "breaks_total": (br_on_w + br_on_l) if None not in (br_on_w, br_on_l) else None,
                "retired": int(ret)})
        # ---- state update, mirroring build_rows exactly
        exp_w = 1.0 / (1.0 + 10 ** ((pl.elo - pw.elo) / 400.0))
        wstats2 = {c: acm.fnum(rd.get(W[c])) for c in acm.STAT_COLS}
        lstats2 = {c: acm.fnum(rd.get(L[c])) for c in acm.STAT_COLS}
        minutes = acm.fnum(rd.get("minutes"))
        wrow = dict(wstats2, sets_w=sw, sets_l=sl, games_w=gw, games_l=gl,
                    minutes=minutes, retired_self=0)
        lrow = dict(lstats2, sets_w=sl, sets_l=sw, games_w=gl, games_l=gw,
                    minutes=minutes, retired_self=ret)
        elo_w, elo_l = pw.elo, pl.elo
        acm.update_state(pw, wrow, True, surface, today, exp_w, elo_l, lstats2)
        acm.update_state(pl, lrow, False, surface, today, 1 - exp_w, elo_w, wstats2)
        kw, kl = acm.k_factor(pw.n - 1), acm.k_factor(pl.n - 1)
        pw.elo += kw * (1 - exp_w); pl.elo -= kl * (1 - exp_w)
        pw.elo_hist.append((today, pw.elo)); pl.elo_hist.append((today, pl.elo))
        se_w, se_l = pw.surf_elo[surface], pl.surf_elo[surface]
        exp_s = 1.0 / (1.0 + 10 ** ((se_l - se_w) / 400.0))
        pw.surf_elo[surface] = se_w + kw * (1 - exp_s)
        pl.surf_elo[surface] = se_l - kl * (1 - exp_s)
    out = pd.DataFrame(rows)
    out.to_csv(ROWS_CSV, index=False)
    print("wrote %s: %d rows, %d with full outcome stats"
          % (ROWS_CSV, len(out), int(out["breaks_total"].notna().sum())))


# ----------------------------------------------------------------------- run
def load_joined(rows_path, batch_path, prob_col):
    pr = pd.read_csv(rows_path, low_memory=False)
    ba = pd.read_csv(batch_path, low_memory=False,
                     usecols=["date", "player_a", "player_b", prob_col])
    pr["key"] = [str(d)[:10] + "|" + "|".join(sorted((norm_name(a), norm_name(b))))
                 for d, a, b in zip(pr["date"], pr["w_name"], pr["l_name"])]
    ba["key"] = [str(d)[:10] + "|" + "|".join(sorted((norm_name(a), norm_name(b))))
                 for d, a, b in zip(ba["date"], ba["player_a"], ba["player_b"])]
    ba = ba.drop_duplicates("key", keep=False)
    pr = pr.drop_duplicates("key", keep=False)
    j = pr.merge(ba[["key", "player_a", prob_col]], on="key", how="inner")
    # favorite frame by market price
    a_is_w = [norm_name(a) == norm_name(w) for a, w in zip(j["player_a"], j["w_name"])]
    p_w = np.where(a_is_w, j[prob_col], 1 - j[prob_col])       # P(winner-of-record wins)
    fav_is_w = p_w >= 0.5
    j["fav_p"] = np.where(fav_is_w, p_w, 1 - p_w)
    j["fav_won"] = fav_is_w.astype(int)
    def pick(wcol, lcol, fav_side):
        return np.where(fav_side, j[wcol], j[lcol])
    for base in ("elo", "ace_rate", "df_rate", "hold", "switch", "age", "ace", "df"):
        j["fav_" + base] = pick("w_" + base, "l_" + base, fav_is_w)
        j["dog_" + base] = pick("w_" + base, "l_" + base, ~fav_is_w)
    j["fav_aces"] = j["fav_ace"]; j["dog_aces"] = j["dog_ace"]
    j["fav_dfs"] = j["fav_df"]; j["dog_dfs"] = j["dog_df"]
    j["total_games"] = j["games_total"]; j["total_breaks"] = j["breaks_total"]
    j["elo_gap"] = (j["fav_elo"] - j["dog_elo"]) * LN10_400 - logit(j["fav_p"])
    j["d_age"] = j["fav_age"] - j["dog_age"]
    # frozen fragility score from the live artifacts
    try:
        m = json.load(open("fragility_v3_model.json"))
        ref = json.load(open("fragility_v3_live_ref.json"))
        assert m["marker"] == "APEX-FRAGILITY-V3-2026-08-20"
        z = lambda c, x: (x - m["mu"][c]) / (m["sd"][c] or 1)
        delta = (m["beta"]["elo_gap"] * z("elo_gap", j["elo_gap"].fillna(m["med"]["elo_gap"]))
                 + m["beta"]["d_surface_switch"] * z("d_surface_switch",
                       (j["fav_switch"] - j["dog_switch"]).fillna(m["med"]["d_surface_switch"]))
                 + m["beta"]["d_age"] * z("d_age", j["d_age"].fillna(m["med"]["d_age"])))
        bands = [(0.50, .60, "50-60%"), (.60, .65, "60-65%"), (.65, .70, "65-70%"),
                 (.70, .75, "70-75%"), (.75, .80, "75-80%"), (.80, 1.001, "80%+")]
        score = np.full(len(j), np.nan)
        for lo, hi, nm in bands:
            refarr = np.array(ref["percentile_ref"].get(nm, []))
            msk = (j["fav_p"] >= lo) & (j["fav_p"] < hi)
            if len(refarr):
                score[msk.values] = 100 * np.searchsorted(refarr, delta[msk], side="right") / len(refarr)
        j["fragility"] = score
        print("frozen V3 fragility computed for %d rows" % int(np.isfinite(score).sum()))
    except Exception as e:
        print("NOTE: fragility unavailable (%s) -- tests 1 & 5 will be skipped" % e)
        j["fragility"] = np.nan
    return j


def price_controls(j):
    lp = logit(j["fav_p"].values)
    return np.column_stack([np.ones(len(j)), lp, lp ** 2,
                            (j["best_of"] == 5).astype(float).values])


def run_tests(j, report):
    j = j[(j["retired"] == 0)].copy()      # totals/volatility need finished matches
    fit = j["year"] <= 2023; hold = j["year"] >= 2024
    report.append("rows (finished, priced): %d   fit<=2023: %d   holdout 2024+: %d"
                  % (len(j), int(fit.sum()), int(hold.sum())))
    tests = []   # (label, outcome, feature_series, extra_note)
    for y in OUTCOMES:
        if j["fragility"].notna().any():
            tests.append(("1 fragility -> %s" % y, y, j["fragility"] / 100.0))
        tests.append(("2 elo_gap -> %s" % y, y, j["elo_gap"]))
        tests.append(("4 age_gap -> %s" % y, y, j["d_age"]))
    # 3: each player's OWN switch vs own-side outcomes + match totals
    for who in ("fav", "dog"):
        for y in ("%s_aces" % who, "%s_dfs" % who):
            tests.append(("3 %s_switch -> %s" % (who, y), y, j["%s_switch" % who]))
        tests.append(("3 %s_switch -> total_games" % who, "total_games", j["%s_switch" % who]))
        tests.append(("3 %s_switch -> total_breaks" % who, "total_breaks", j["%s_switch" % who]))
    # own pre-match rate controls for ace/df outcomes (fair test of ADDED effect)
    rate_ctl = {"fav_aces": "fav_ace_rate", "dog_aces": "dog_ace_rate",
                "fav_dfs": "fav_df_rate", "dog_dfs": "dog_df_rate"}
    results = []
    for label, y, x in tests:
        base = price_controls(j)
        if y in rate_ctl:
            base = np.column_stack([base, j[rate_ctl[y]].fillna(j[rate_ctl[y]].median()).values])
        m = j[y].notna() & pd.Series(x).notna().values
        res = {"label": label}
        for nm, msk in (("fit", (m & fit).values), ("hold", (m & hold).values)):
            if msk.sum() < 500:
                continue
            yy = j.loc[msk, y].values.astype(float)
            xs = pd.Series(x)[msk].values.astype(float)
            xs = (xs - xs.mean()) / (xs.std() or 1)
            b, t, _ = ols(yy, np.column_stack([base[msk], xs]))
            res[nm + "_coef"] = b[-1]; res[nm + "_t"] = t[-1]
        if "fit_t" in res:
            res["p"] = 2 * norm_sf(abs(res["fit_t"]))
            results.append(res)
    pv = [r["p"] for r in results]
    fl = bh_flags(pv, 0.10)
    report.append("\n== TESTS 1-4: price-controlled effects (coef = outcome units per 1 SD;"
                  "\n   ace/DF tests also control the player's own pre-match rate;"
                  "\n   %d tests, BH FDR 10%%, ~%d false flags expected) =="
                  % (len(results), max(1, round(0.1 * fl.sum()))))
    report.append("  %-34s %9s %7s | %9s %7s  %s"
                  % ("test", "fit_coef", "fit_t", "hold_coef", "hold_t", "flag"))
    for r, f in sorted(zip(results, fl), key=lambda t: -abs(t[0]["fit_t"])):
        holds = ""
        if f and "hold_t" in r:
            holds = " *FLAG*" + (" sign-holds" if np.sign(r["fit_coef"]) == np.sign(r.get("hold_coef", 0)) else " sign-FLIPS")
        report.append("  %-34s %+9.3f %+7.2f | %+9.3f %+7.2f %s"
                      % (r["label"], r["fit_coef"], r["fit_t"],
                         r.get("hold_coef", float("nan")), r.get("hold_t", float("nan")), holds))
    # ---- 5: volatility -- |residual vs price-model| regressed on fragility
    if j["fragility"].notna().any():
        report.append("\n== TEST 5: are high-fragility matches more VOLATILE? ==")
        for y in ("total_games", "total_breaks"):
            m = j[y].notna() & j["fragility"].notna()
            base = price_controls(j)
            bfit = (m & fit).values
            b, _, efit = ols(j.loc[bfit, y].values, base[bfit])
            for nm, msk in (("fit", bfit), ("hold", (m & hold).values)):
                resid = np.abs(j.loc[msk, y].values - base[msk] @ b)
                fr = (j.loc[msk, "fragility"].values / 100.0)
                fr = (fr - fr.mean()) / (fr.std() or 1)
                bb, tt, _ = ols(resid, np.column_stack([base[msk], fr]))
                lo = resid[j.loc[msk, "fragility"].values <= 20].mean()
                hi = resid[j.loc[msk, "fragility"].values >= 80].mean()
                report.append("  %-13s %-4s |resid| per 1SD frag: %+6.3f (t=%+5.2f); "
                              "mean |resid| frag<=20: %.2f vs frag>=80: %.2f"
                              % (y, nm, bb[-1], tt[-1], lo, hi))
    # ---- 6: which prop categories are LEAST explained by (winner, price)
    report.append("\n== TEST 6: prop categories vs winner+price (holdout 2024+ R^2; "
                  "LOW = market's winner view says least -> most independent info) ==")
    hmask = hold.values
    for y in OUTCOMES:
        m = hmask & j[y].notna().values
        if m.sum() < 500:
            continue
        X = np.column_stack([price_controls(j)[m], j.loc[m, "fav_won"].values])
        yy = j.loc[m, y].values.astype(float)
        b, _, e = ols(yy, X)
        r2 = 1 - e.var() / yy.var()
        # and with the player's own rate added, how much does identity explain?
        extra = ""
        if y in ("fav_aces", "dog_aces", "fav_dfs", "dog_dfs"):
            rc = {"fav_aces": "fav_ace_rate", "dog_aces": "dog_ace_rate",
                  "fav_dfs": "fav_df_rate", "dog_dfs": "dog_df_rate"}[y]
            X2 = np.column_stack([X, j.loc[m, rc].fillna(j[rc].median()).values])
            _, _, e2 = ols(yy, X2)
            extra = "   (+own rate -> R^2 %.3f)" % (1 - e2.var() / yy.var())
        report.append("  %-13s R^2(winner+price) = %.3f%s" % (y, r2, extra))


def run(rows_path, batch_path, prob_col):
    print(MARKER, "-- RUN")
    j = load_joined(rows_path, batch_path, prob_col)
    report = [MARKER,
              "Question: do the surviving moneyline findings predict PROP outcomes?",
              "Not a winner model. Fit <=2023, verified on 2024+, price-controlled."]
    # retirement vs fragility, computed before exclusion
    if j["fragility"].notna().any():
        fin = j[j["fragility"].notna()]
        lo = fin[fin["fragility"] <= 20]["retired"].mean()
        hi = fin[fin["fragility"] >= 80]["retired"].mean()
        report.append("retirement rate: frag<=20 %.2f%% vs frag>=80 %.2f%% (n=%d/%d)"
                      % (100 * lo, 100 * hi, len(fin[fin["fragility"] <= 20]),
                         len(fin[fin["fragility"] >= 80])))
    run_tests(j, report)
    txt = "\n".join(report)
    open("prop_link_report.txt", "w").write(txt + "\n")
    print(txt)
    print("\nwritten: prop_link_report.txt")


# ------------------------------------------------------------------ selftest
def selftest():
    print(MARKER, "-- SELFTEST (synthetic)")
    import tempfile
    os.chdir(tempfile.mkdtemp())
    rng = np.random.default_rng(9)
    n = 40000
    year = rng.integers(2015, 2026, n)
    skill = rng.normal(0, 1.1, n)
    p = 1 / (1 + np.exp(-np.abs(skill)))          # favorite prob
    fav_rate = rng.normal(0.06, 0.02, n).clip(0.01)
    dog_rate = rng.normal(0.06, 0.02, n).clip(0.01)
    fav_switch = (rng.random(n) < 0.12).astype(float)
    dog_switch = (rng.random(n) < 0.12).astype(float)
    frag = rng.random(n) * 100
    base_games = 22 - 4 * np.abs(logit(p))
    games = base_games + rng.normal(0, 2.0 + 1.5 * (frag / 100), n)   # planted volatility
    fav_aces = (fav_rate * 80 - 1.2 * fav_switch                       # planted switch effect
                + rng.normal(0, 2, n)).clip(0)
    dog_aces = (dog_rate * 80 + rng.normal(0, 2, n)).clip(0)
    j = pd.DataFrame({"year": year, "fav_p": p, "best_of": 3, "retired": 0,
                      "fragility": frag, "elo_gap": rng.normal(0, .5, n),
                      "d_age": rng.normal(0, 5, n),
                      "fav_switch": fav_switch, "dog_switch": dog_switch,
                      "fav_ace_rate": fav_rate, "dog_ace_rate": dog_rate,
                      "fav_df_rate": 0.03, "dog_df_rate": 0.03,
                      "fav_won": (rng.random(n) < p).astype(int),
                      "total_games": games, "total_breaks": 5 + rng.normal(0, 2, n),
                      "fav_aces": fav_aces, "dog_aces": dog_aces,
                      "fav_dfs": rng.poisson(3, n).astype(float),
                      "dog_dfs": rng.poisson(3, n).astype(float)})
    report = []
    run_tests(j, report)
    txt = "\n".join(report); print(txt)
    sw = [l for l in report if "3 fav_switch -> fav_aces" in l][0]
    assert "*FLAG*" in sw and "sign-holds" in sw, "planted switch->aces not recovered: %s" % sw
    vol = [l for l in report if l.strip().startswith("total_games") and "hold" in l][0]
    t = float(vol.split("t=")[1].split(")")[0])
    assert t > 3, "planted volatility not recovered (t=%.2f)" % t
    null = [l for l in report if "4 age_gap -> dog_dfs" in l][0]
    assert "*FLAG*" not in null, "null flagged: %s" % null
    print("SELFTEST PASS -- planted switch->aces and fragility->volatility recovered, "
          "null age test quiet.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sack-dir", default="ATP & WTA, 1968-2026")
    ap.add_argument("--year-from", type=int, default=2005)
    ap.add_argument("--include-challengers", action="store_true")
    ap.add_argument("--rows", default=ROWS_CSV)
    ap.add_argument("--batch", default="apex_batch_a_rows.csv")
    ap.add_argument("--prob-col", default="pinn_a")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.build:
        build(a.sack_dir, a.year_from, a.include_challengers)
    elif a.run:
        run(a.rows, a.batch, a.prob_col)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
