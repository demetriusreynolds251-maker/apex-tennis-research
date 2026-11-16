#!/usr/bin/env python3
"""
apex_fragility_study.py -- APEX-FRAGILITY-2026-08-20

Favorite Fragility + Underdog Threat study, anchored to Pinnacle's market
probability (NOT Elo). Compares, WITHIN the same Pinnacle probability band,
favorites that lost against favorites of the same price that won -- and the
mirror for underdogs. Output is descriptive evidence + candidate scores,
not a winner model and not a betting claim.

Modes (run in this order):
  python3 apex_fragility_study.py --audit \
      --rows apex_batch_a_rows.csv --cache apex_rows_cache.pkl
        -> matcher health check: coverage by year/round + elite players.
           The study refuses to run until this passes.
  python3 apex_fragility_study.py --run \
      --rows apex_batch_a_rows.csv [--sackmann-dir "ATP & WTA, 1968-2026"]
        -> full study. Writes fragility_report.txt, fragility_bands.csv,
           fragility_features.csv, underdog_features.csv,
           fragility_score_lift.csv
  python3 apex_fragility_study.py --selftest
        -> synthetic-data test: must recover a planted fragility feature
           and must NOT flag null features.

Honesty rules baked in:
  * favorite/underdog defined ONLY by Pinnacle fair probability
  * every comparison is within-band or controls for logit(price)
  * Benjamini-Hochberg correction across all features (expect false
    positives otherwise: ~30 features x 5 bands)
  * any flagged feature is re-checked walk-forward: sign fitted on <=2023
    must hold on 2024+ held-out favorites
  * candidate scores are fit <=2021, tuned 2022-23, evaluated 2024+ only
"""
import argparse, math, os, sys, glob, re
import numpy as np
import pandas as pd

MARKER = "APEX-FRAGILITY-2026-08-20"
BANDS = [(0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 1.001)]
BAND_NAMES = ["60-65%", "65-70%", "70-75%", "75-80%", "80%+"]
PROB_CANDIDATES = ["pinnacle_fair_prob", "pinn_fair_prob", "p_pinnacle", "pin_fair",
                   "fair_prob", "market_prob", "p_market", "pinnacle_prob", "p_fair"]
# columns that are (a - b) signed differences -> negate when favorite is b
NEG_EXTRA = ["ht_gap", "mu_serve_edge"]
SWAP_PAIRS = [("mu_a_serve_vs_b_return", "mu_b_serve_vs_a_return"),
              ("mu_a_break_vs_b_hold", "mu_b_break_vs_a_hold")]
KEEP_ASIS = ["h2h_total", "lefty_vs_righty", "is_wta", "is_bo5"]
NON_FEATURES = {"date", "year", "tour", "surface", "best_of", "level", "round",
                "tourney_id", "player_a", "player_b", "label"}
CATEGORICALS = ["round", "level", "surface", "is_bo5", "is_wta"]


# ----------------------------------------------------------------- utilities
def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def irls_logistic(X, y, ridge=1e-6, iters=60):
    """Plain logistic regression with covariance (for z-stats). X includes
    intercept column. Returns (beta, se) or (None, None) if it fails."""
    X = np.asarray(X, float); y = np.asarray(y, float)
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = np.clip(X @ beta, -30, 30)
        mu = 1 / (1 + np.exp(-eta))
        w = np.maximum(mu * (1 - mu), 1e-9)
        H = (X * w[:, None]).T @ X + ridge * np.eye(X.shape[1])
        g = X.T @ (y - mu) - ridge * beta
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return None, None
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    if not np.all(np.isfinite(beta)):
        return None, None
    try:
        cov = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return None, None
    return beta, np.sqrt(np.maximum(np.diag(cov), 0))


def norm_sf(z):
    from scipy.stats import norm
    return float(norm.sf(z))


def bh_flags(pvals, q=0.10):
    """Benjamini-Hochberg: returns boolean array of discoveries at FDR q."""
    p = np.asarray(pvals, float)
    n = len(p)
    order = np.argsort(p)
    flags = np.zeros(n, bool)
    thresh = 0
    for rank, idx in enumerate(order, start=1):
        if p[idx] <= q * rank / n:
            thresh = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= thresh:
            flags[idx] = True
    return flags


def norm_name(s):
    s = str(s).lower().strip()
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(sorted(s.split()))  # order-free tokens survive "Last First"


# ----------------------------------------------------------------- loading
def find_prob_col(df, override=None):
    if override:
        assert override in df.columns, "--prob-col %r not in file" % override
        return override
    hits = [c for c in df.columns if c in PROB_CANDIDATES]
    if not hits:
        hits = [c for c in df.columns
                if ("pin" in c.lower() or "market" in c.lower() or "fair" in c.lower())
                and ("prob" in c.lower() or "fair" in c.lower() or c.lower().startswith("p_"))
                and df[c].dtype != object]
        hits = [c for c in hits if df[c].dropna().between(0, 1).mean() > 0.99]
    if len(hits) != 1:
        print("Could not identify the Pinnacle fair-probability column.")
        print("Columns in file:", list(df.columns))
        print("Candidates found:", hits)
        print("Re-run with  --prob-col <name>")
        sys.exit(2)
    return hits[0]


def load_rows(path, prob_col_override=None):
    df = pd.read_csv(path, low_memory=False)
    pcol = find_prob_col(df, prob_col_override)
    assert "label" in df.columns, "no 'label' column (1 = player_a won)"
    df = df[df[pcol].notna()].copy()
    # orientation sanity: p must be P(player_a wins)
    conf = df[df[pcol] > 0.60]
    hit = float((conf["label"] == 1).mean()) if len(conf) > 200 else None
    if hit is not None and hit < 0.5:
        raise SystemExit("prob column %r looks INVERTED (favorites >60%% win only %.1f%%). "
                         "Stop and check the file." % (pcol, hit * 100))
    if "year" not in df.columns and "date" in df.columns:
        df["year"] = pd.to_datetime(df["date"]).dt.year
    return df, pcol


def to_favorite_frame(df, pcol):
    """One row per match, everything expressed from the FAVORITE's side."""
    d = df.copy()
    fav_is_a = d[pcol] >= 0.5
    d["fav_p"] = np.where(fav_is_a, d[pcol], 1 - d[pcol])
    d["fav_lost"] = np.where(fav_is_a, 1 - d["label"], d["label"]).astype(int)
    d["fav_name"] = np.where(fav_is_a, d.get("player_a", ""), d.get("player_b", ""))
    d["dog_name"] = np.where(fav_is_a, d.get("player_b", ""), d.get("player_a", ""))
    neg_cols = [c for c in d.columns if c.startswith("d_")] + \
               [c for c in NEG_EXTRA if c in d.columns]
    flip = ~fav_is_a
    for c in neg_cols:
        if pd.api.types.is_numeric_dtype(d[c]):
            d.loc[flip, c] = -d.loc[flip, c]
    for a, b in SWAP_PAIRS:
        if a in d.columns and b in d.columns:
            ta = d.loc[flip, a].copy()
            d.loc[flip, a] = d.loc[flip, b]
            d.loc[flip, b] = ta
    d["band"] = None
    for (lo, hi), nm in zip(BANDS, BAND_NAMES):
        m = (d["fav_p"] >= lo) & (d["fav_p"] < hi)
        d.loc[m, "band"] = nm
    d["n_missing_inputs"] = d[[c for c in d.columns if c.startswith("d_")]].isna().sum(axis=1)
    return d


def feature_columns(d):
    out = []
    for c in d.columns:
        if c in NON_FEATURES or c in ("fav_p", "fav_lost", "band", "fav_name", "dog_name"):
            continue
        if not pd.api.types.is_numeric_dtype(d[c]):
            continue
        if d[c].notna().sum() < 500 or d[c].nunique() < 3:
            if c not in ("d_retired_90d", "d_surface_switch", "d_left", "is_qual_dog",
                         "is_ll_dog", "is_wc_dog", "is_qual_fav", "is_ll_fav", "is_wc_fav"):
                continue
        out.append(c)
    return out


# ----------------------------------------------------------------- entry join
def join_entry_status(d, sack_dir):
    """Attach qualifier / lucky-loser / wild-card flags from Sackmann CSVs."""
    files = []
    for pat in ("[12][0-9][0-9][0-9].csv", "[12][0-9][0-9][0-9]_wta.csv"):
        files += glob.glob(os.path.join(sack_dir, pat))
    if not files:
        print("  entry join: no Sackmann CSVs found in %r -- skipping" % sack_dir)
        return d, 0.0
    frames = []
    for f in files:
        try:
            t = pd.read_csv(f, usecols=lambda c: c in
                            ("tourney_id", "winner_name", "loser_name",
                             "winner_entry", "loser_entry", "score"), low_memory=False)
            frames.append(t)
        except Exception:
            pass
    s = pd.concat(frames, ignore_index=True)
    s["k"] = s["tourney_id"].astype(str) + "|" + \
        [ "|".join(sorted([norm_name(w), norm_name(l)]))
          for w, l in zip(s["winner_name"], s["loser_name"]) ]
    ent = {}
    for k, we, le, wn, ln, sc in zip(s["k"], s.get("winner_entry"), s.get("loser_entry"),
                                     s["winner_name"], s["loser_name"], s.get("score")):
        ent[k] = (norm_name(wn), str(we), norm_name(ln), str(le),
                  "W/O" in str(sc).upper() or "WO" == str(sc).strip().upper())
    if "tourney_id" not in d.columns:
        print("  entry join: rows file has no tourney_id -- skipping")
        return d, 0.0
    kk = d["tourney_id"].astype(str) + "|" + \
        [ "|".join(sorted([norm_name(a), norm_name(b)]))
          for a, b in zip(d["fav_name"], d["dog_name"]) ]
    def flag(row_key, who_name, code):
        rec = ent.get(row_key)
        if rec is None:
            return np.nan
        wn, we, ln, le, _wo = rec
        e = we if norm_name(who_name) == wn else (le if norm_name(who_name) == ln else "")
        return 1.0 if str(e).strip().upper() == code else 0.0
    for code, tag in (("Q", "qual"), ("LL", "ll"), ("WC", "wc")):
        d["is_%s_fav" % tag] = [flag(k, n, code) for k, n in zip(kk, d["fav_name"])]
        d["is_%s_dog" % tag] = [flag(k, n, code) for k, n in zip(kk, d["dog_name"])]
    d["walkover"] = [ (ent[k][4] if k in ent else np.nan) for k in kk ]
    rate = float(np.mean([k in ent for k in kk]))
    print("  entry join: matched %.1f%% of rows to Sackmann entry status" % (rate * 100))
    d = d[d["walkover"] != True].copy()  # walkovers are not upsets; drop
    return d, rate


# ----------------------------------------------------------------- audit
def audit(rows_path, cache_path, prob_col=None):
    print(MARKER, "-- MATCHER AUDIT")
    df, pcol = load_rows(rows_path, prob_col)
    print("priced rows: %d  (prob column: %s)" % (len(df), pcol))
    ok = True
    if cache_path and os.path.exists(cache_path):
        cache = pd.read_pickle(cache_path)
        print("cache rows : %d" % len(cache))
        cy = cache.groupby("year").size()
        my = df.groupby("year").size()
        print("\ncoverage by year (matched / cache):")
        for y in sorted(set(cy.index) & set(my.index)):
            if y >= 2010:
                print("  %d: %6d / %6d  (%.0f%%)" % (y, my.get(y, 0), cy[y],
                                                     100 * my.get(y, 0) / max(cy[y], 1)))
        # elite-player canaries: top 20 cache players by appearances since 2020
        rec = cache[cache["year"] >= 2020]
        counts = pd.concat([rec["player_a"], rec["player_b"]]).value_counts().head(20)
        dfr = df[df["year"] >= 2020]
        mcounts = pd.concat([dfr["player_a"], dfr["player_b"]]).value_counts()
        print("\nelite canaries since 2020 (matched / cache):")
        worst = 1.0
        for p, n in counts.items():
            m = int(mcounts.get(p, 0))
            share = m / n
            worst = min(worst, share)
            print("  %-28s %5d / %5d  (%.0f%%)" % (p, m, n, 100 * share))
        if "round" in cache.columns:
            print("\nround mix (share of rows): cache vs matched")
            a = cache["round"].value_counts(normalize=True)
            b = df["round"].value_counts(normalize=True)
            for r in a.index[:10]:
                print("  %-6s cache %5.1f%%   matched %5.1f%%" %
                      (r, 100 * a[r], 100 * b.get(r, 0)))
        overall = len(df) / max(len(cache), 1)
        print("\noverall match share: %.0f%%   worst elite canary: %.0f%%" %
              (100 * overall, 100 * worst))
        if worst < 0.50 or overall < 0.40:
            ok = False
            print("AUDIT FAIL -- elite players or overall coverage still dropped. "
                  "The old +/-1-day matcher bug pattern. Fix the matcher before the study.")
        else:
            print("AUDIT PASS -- no elite-exclusion pattern; favorites/underdogs "
                  "can be taken from market prices.")
    else:
        print("(no cache file given -- coverage vs cache skipped; only priced-file checks run)")
    conf = df[df[pcol] > 0.60]
    print("calibration sanity: favorites priced >60%% won %.1f%% (n=%d)" %
          (100 * (conf["label"] == 1).mean(), len(conf)))
    if ok:
        open("fragility_audit.ok", "w").write(MARKER + "\n")
        if os.path.exists("fragility_audit.fail"):
            os.remove("fragility_audit.fail")
    else:
        open("fragility_audit.fail", "w").write(MARKER + "\n")
        if os.path.exists("fragility_audit.ok"):
            os.remove("fragility_audit.ok")
    return ok


# ----------------------------------------------------------------- core study
def per_band_table(d, feats):
    rows = []
    for nm in BAND_NAMES:
        b = d[d["band"] == nm]
        won = b[b["fav_lost"] == 0]; lost = b[b["fav_lost"] == 1]
        rows.append({"band": nm, "n": len(b), "n_lost": len(lost),
                     "loss_rate": len(lost) / max(len(b), 1),
                     "implied_loss": 1 - b["fav_p"].mean() if len(b) else np.nan})
    return pd.DataFrame(rows)


def feature_tests(d, feats, side_label):
    """Per-band descriptive diffs + pooled price-controlled logistic z per feature."""
    from scipy.stats import mannwhitneyu
    out = []
    lp = logit(d["fav_p"].values)
    y = d["fav_lost"].values
    for c in feats:
        v = d[c].values.astype(float)
        m = np.isfinite(v)
        rec = {"feature": c, "n": int(m.sum())}
        # pooled, controlling for logit(price)
        if m.sum() >= 800 and np.nanstd(v[m]) > 0:
            vz = (v[m] - np.nanmean(v[m])) / np.nanstd(v[m])
            X = np.column_stack([np.ones(m.sum()), lp[m], vz])
            beta, se = irls_logistic(X, y[m])
            if beta is not None and se[2] > 0:
                z = beta[2] / se[2]
                rec.update({"pooled_coef": beta[2], "pooled_z": z,
                            "pooled_p": 2 * norm_sf(abs(z))})
        # per-band standardized mean differences (descriptive)
        for nm in BAND_NAMES:
            b = d[(d["band"] == nm) & np.isfinite(d[c].astype(float))]
            wonv = b.loc[b["fav_lost"] == 0, c].astype(float)
            lostv = b.loc[b["fav_lost"] == 1, c].astype(float)
            if len(wonv) >= 50 and len(lostv) >= 50:
                sd = np.sqrt((wonv.var() + lostv.var()) / 2)
                dcoh = (lostv.mean() - wonv.mean()) / sd if sd > 0 else 0.0
                try:
                    pv = mannwhitneyu(lostv, wonv, alternative="two-sided").pvalue
                except ValueError:
                    pv = 1.0
                rec["d_" + nm] = dcoh
                rec["p_" + nm] = pv
                rec["lost_mean_" + nm] = lostv.mean()
                rec["won_mean_" + nm] = wonv.mean()
        out.append(rec)
    t = pd.DataFrame(out)
    if "pooled_p" in t.columns:
        pv = t["pooled_p"].fillna(1.0).values
        t["bh_flag"] = bh_flags(pv, q=0.10)
    else:
        t["bh_flag"] = False
    t["side"] = side_label
    return t


def walkforward_check(d, flagged, report):
    """For each BH-flagged feature: coef sign fit on <=2023 must hold on 2024+."""
    tr = d[d["year"] <= 2023]; te = d[d["year"] >= 2024]
    report.append("\nWALK-FORWARD SIGN CHECK on flagged features "
                  "(fit <=2023, held-out 2024+, n_test=%d):" % len(te))
    keep = []
    for c in flagged:
        res = {}
        for name, part in (("fit", tr), ("test", te)):
            v = part[c].values.astype(float)
            m = np.isfinite(v)
            if m.sum() < 400 or np.nanstd(v[m]) == 0:
                res[name] = None; continue
            vz = (v[m] - np.nanmean(v[m])) / np.nanstd(v[m])
            X = np.column_stack([np.ones(m.sum()), logit(part["fav_p"].values[m]), vz])
            beta, se = irls_logistic(X, part["fav_lost"].values[m])
            res[name] = (beta[2], beta[2] / se[2]) if beta is not None else None
        if res.get("fit") and res.get("test"):
            same = np.sign(res["fit"][0]) == np.sign(res["test"][0])
            report.append("  %-24s fit z=%+.2f   2024+ z=%+.2f   sign holds: %s"
                          % (c, res["fit"][1], res["test"][1], "YES" if same else "no"))
            if same:
                keep.append(c)
        else:
            report.append("  %-24s insufficient data for the check" % c)
    return keep


def candidate_score(d, feats, report, label):
    """L2 logistic on logit(price)+features. Fit <=2021, tune 2022-23, evaluate 2024+.
    Report within-band lift of the top-20% score, not a betting result."""
    from sklearn.linear_model import LogisticRegression
    dd = d.copy()
    for c in feats:
        med = dd.loc[dd["year"] <= 2021, c].median()
        dd[c + "_mi"] = dd[c].isna().astype(float)
        dd[c] = dd[c].fillna(med)
    cols = feats + [c + "_mi" for c in feats]
    tr = dd[dd["year"] <= 2021]; tu = dd[dd["year"].between(2022, 2023)]; te = dd[dd["year"] >= 2024]
    if len(tr) < 2000 or len(te) < 500:
        report.append("\n%s SCORE: not enough rows for walk-forward split -- skipped" % label)
        return None
    mu = tr[cols].mean(); sd = tr[cols].std().replace(0, 1)
    def design(part):
        Z = (part[cols] - mu) / sd
        return np.column_stack([logit(part["fav_p"].values), Z.values])
    best = None
    for C in (0.01, 0.03, 0.1, 0.3):
        clf = LogisticRegression(C=C, max_iter=2000)
        clf.fit(design(tr), tr["fav_lost"])
        p = clf.predict_proba(design(tu))[:, 1]
        ll = -np.mean(tu["fav_lost"] * np.log(np.clip(p, 1e-9, 1)) +
                      (1 - tu["fav_lost"]) * np.log(np.clip(1 - p, 1e-9, 1)))
        if best is None or ll < best[0]:
            best = (ll, C, clf)
    clf = LogisticRegression(C=best[1], max_iter=2000)
    fit_all = pd.concat([tr, tu])
    clf.fit(design(fit_all), fit_all["fav_lost"])
    te = te.copy()
    te["score"] = clf.predict_proba(design(te))[:, 1]
    report.append("\n%s SCORE (candidate, C=%.2g)  -- 2024+ held-out lift, within band:" % (label, best[1]))
    report.append("  band     n_test  base_loss%  top20%_score_loss%  lift  (SE)")
    lift_rows = []
    for nm in BAND_NAMES:
        b = te[te["band"] == nm]
        if len(b) < 150:
            continue
        thr = b["score"].quantile(0.80)
        top = b[b["score"] >= thr]
        base = b["fav_lost"].mean(); tl = top["fav_lost"].mean()
        se = math.sqrt(tl * (1 - tl) / max(len(top), 1) + base * (1 - base) / len(b))
        report.append("  %-7s %6d   %6.1f       %6.1f          %+5.1f  (%.1f)"
                      % (nm, len(b), 100 * base, 100 * tl, 100 * (tl - base), 100 * se))
        lift_rows.append({"band": nm, "n": len(b), "base_loss": base,
                          "top20_loss": tl, "lift": tl - base, "se": se})
    coefs = pd.Series(clf.coef_[0][1:], index=cols).sort_values(key=abs, ascending=False)
    report.append("  top score drivers: " + ", ".join(
        "%s %+0.3f" % (k, v) for k, v in coefs.head(8).items()))
    return pd.DataFrame(lift_rows), te[["band", "score", "fav_lost"]]


def categorical_tables(d, report):
    from scipy.stats import chi2_contingency
    report.append("\nCATEGORICAL VARIABLES (within-band loss rates):")
    for c in [x for x in CATEGORICALS if x in d.columns]:
        report.append("  -- %s --" % c)
        for nm in BAND_NAMES:
            b = d[d["band"] == nm]
            if len(b) < 400:
                continue
            g = b.groupby(c)["fav_lost"].agg(["mean", "size"])
            g = g[g["size"] >= 80]
            if len(g) < 2:
                continue
            ct = pd.crosstab(b[c], b["fav_lost"])
            try:
                pv = chi2_contingency(ct)[1]
            except ValueError:
                pv = 1.0
            parts = ", ".join("%s %.1f%% (n=%d)" % (i, 100 * r["mean"], r["size"])
                              for i, r in g.iterrows())
            report.append("    %-7s p=%.3f   %s" % (nm, pv, parts))


def run_study(rows_path, prob_col=None, sack_dir=None, out_prefix=""):
    if not os.path.exists("fragility_audit.ok"):
        raise SystemExit("Refusing to run: no fragility_audit.ok in this folder. "
                         "Run --audit first (it must PASS).")
    print(MARKER, "-- STUDY RUN")
    df, pcol = load_rows(rows_path, prob_col)
    d = to_favorite_frame(df, pcol)
    if sack_dir:
        d, _ = join_entry_status(d, sack_dir)
    d = d[d["band"].notna()].copy()
    feats = feature_columns(d)
    report = ["%s\nrows in bands 60%%+: %d   features tested: %d   prob col: %s"
              % (MARKER, len(d), len(feats), pcol)]
    bands = per_band_table(d, feats)
    report.append("\nBAND OVERVIEW (does the market itself calibrate?):")
    for _, r in bands.iterrows():
        report.append("  %-7s n=%6d  favorites lost %.1f%%  (market implied %.1f%%)"
                      % (r["band"], r["n"], 100 * r["loss_rate"], 100 * r["implied_loss"]))

    # ---------------- favorite fragility
    ft = feature_tests(d, feats, "favorite")
    flagged = list(ft.loc[ft["bh_flag"], "feature"])
    report.append("\nFAVORITE FRAGILITY -- features where losing favorites differ from "
                  "winning favorites at the same price")
    report.append("(pooled logistic controls for logit(Pinnacle prob); BH FDR 10%%; "
                  "%d of %d features flagged; ~%.0f false flags expected by chance at q=0.10)"
                  % (len(flagged), len(feats), 0.10 * max(len(flagged), 1)))
    show = ft.dropna(subset=["pooled_z"]).sort_values("pooled_z", key=abs, ascending=False)
    for _, r in show.head(20).iterrows():
        mark = " *FLAG*" if r["bh_flag"] else ""
        direction = "MORE" if r["pooled_coef"] > 0 else "less"
        report.append("  %-26s z=%+6.2f  (losing favorites have %s of this)%s"
                      % (r["feature"], r["pooled_z"], direction, mark))
    survivors = walkforward_check(d, flagged, report)
    report.append("FRAGILITY FACTORS (flagged AND sign holds on 2024+): "
                  + (", ".join(survivors) if survivors else "none"))

    # ---------------- underdog threat (mirror; dog frame = negated fav frame)
    report.append("\nUNDERDOG THREAT -- same matches read from the underdog's side.")
    report.append("A dog-side feature with positive z means dogs who WIN carry more of it "
                  "than dogs at the same price who lose. (Numerically the mirror of the "
                  "fragility table for d_* features; dog-specific flags below are new.)")
    dog_feats = [c for c in ("is_qual_dog", "is_ll_dog", "is_wc_dog") if c in d.columns]
    for c in dog_feats + ["n_missing_inputs", "d_n_prior", "d_days_since"]:
        if c not in d.columns:
            continue
        v = d[c].astype(float).values
        m = np.isfinite(v)
        if m.sum() < 800 or np.nanstd(v[m]) == 0:
            continue
        # dog wins == fav_lost; dog-frame value of d_* is the negative of fav frame
        vz = (v[m] - np.nanmean(v[m])) / np.nanstd(v[m])
        if c.startswith("d_"):
            vz = -vz
        X = np.column_stack([np.ones(m.sum()), logit(d["fav_p"].values[m]), vz])
        beta, se = irls_logistic(X, d["fav_lost"].values[m])
        if beta is not None:
            report.append("  %-26s z=%+6.2f  (dog-side)" % (c, beta[2] / se[2]))
    categorical_tables(d, report)

    # ---------------- candidate scores
    frag_lift, frag_scores = (None, None)
    res = candidate_score(d, feats, report, "FRAGILITY")
    if res is not None:
        frag_lift, frag_scores = res
    report.append("\nREADING GUIDE / HONESTY NOTES:")
    report.append("  * Everything above is within-band or price-controlled: it can NOT "
                  "rediscover 'bigger favorites lose less'.")
    report.append("  * A flagged feature means losing favorites measurably differ from "
                  "same-priced winning favorites. It does NOT yet mean a bet is +EV; "
                  "prior residual tests say most global effects are already in the price.")
    report.append("  * The candidate score lift table is the first honest evidence: if "
                  "top-20%% fragility favorites lose meaningfully more than their band's "
                  "base rate on 2024+ data, there is something to take to the ROI stage.")
    txt = "\n".join(report)
    open(out_prefix + "fragility_report.txt", "w").write(txt + "\n")
    bands.to_csv(out_prefix + "fragility_bands.csv", index=False)
    ft.to_csv(out_prefix + "fragility_features.csv", index=False)
    ft[ft["bh_flag"]].to_csv(out_prefix + "underdog_features.csv", index=False)
    if frag_lift is not None:
        frag_lift.to_csv(out_prefix + "fragility_score_lift.csv", index=False)
    print(txt)
    print("\nwritten: fragility_report.txt, fragility_bands.csv, "
          "fragility_features.csv, underdog_features.csv, fragility_score_lift.csv")


# ----------------------------------------------------------------- selftest
def selftest():
    print(MARKER, "-- SELFTEST (synthetic)")
    rng = np.random.default_rng(7)
    n = 60000
    year = rng.integers(2015, 2026, n)
    skill = rng.normal(0, 1.2, n)                       # true a-vs-b edge
    frag_fav = rng.normal(0, 1, n)                       # fragility trait OF THE FAVORITE
    nulls = {("null%d" % i): rng.normal(0, 1, n) for i in range(10)}
    # market knows skill but NOT the favorite's fragility trait
    p_market = 1 / (1 + np.exp(-skill))
    sign = np.where(p_market > 0.5, 1.0, -1.0)           # +1 if a is the favorite
    lin = skill - 0.22 * frag_fav * sign                 # fragile favorite -> loses more
    label = (rng.random(n) < 1 / (1 + np.exp(-lin))).astype(int)
    # stored in a-frame (a minus b), so the study's fav-frame flip must recover it
    df = pd.DataFrame({"label": label, "year": year, "player_a": "A", "player_b": "B",
                       "tourney_id": "t", "p_fair": p_market, "d_frag1": frag_fav * sign})
    for k, v in nulls.items():
        df["d_" + k] = v
    open("fragility_audit.ok", "w").write(MARKER + "\n")
    d = to_favorite_frame(df, "p_fair")
    d = d[d["band"].notna()]
    feats = feature_columns(d)
    ft = feature_tests(d, feats, "favorite")
    ft = ft.set_index("feature")
    z_frag = ft.loc["d_frag1", "pooled_z"]
    z_null_max = ft.loc[[i for i in ft.index if "null" in i], "pooled_z"].abs().max()
    n_false = int(ft.loc[[i for i in ft.index if "null" in i], "bh_flag"].sum())
    print("planted fragility z=%.1f (must be > 5)" % z_frag)
    print("max |z| among 10 nulls = %.2f, false BH flags = %d (must be <= 1)"
          % (z_null_max, n_false))
    assert z_frag > 5, "planted signal not recovered"
    assert ft.loc["d_frag1", "bh_flag"], "planted signal not flagged"
    assert n_false <= 1, "too many false positives"
    rep = []
    surv = walkforward_check(d, ["d_frag1"], rep)
    assert "d_frag1" in surv, "planted signal failed walk-forward"
    res = candidate_score(d, feats, rep, "FRAGILITY")
    assert res is not None
    lift, _ = res
    print("\n".join(rep))
    assert (lift["lift"] > 0).mean() >= 0.6, "score lift not positive on planted data"
    os.remove("fragility_audit.ok")
    print("SELFTEST PASS -- planted fragility recovered, nulls stay quiet, "
          "walk-forward holds, score lift positive.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rows", default="apex_batch_a_rows.csv")
    ap.add_argument("--cache", default="apex_rows_cache.pkl")
    ap.add_argument("--prob-col", default=None)
    ap.add_argument("--sackmann-dir", default=None)
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.audit:
        audit(a.rows, a.cache, a.prob_col)
    elif a.run:
        run_study(a.rows, a.prob_col, a.sackmann_dir)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
