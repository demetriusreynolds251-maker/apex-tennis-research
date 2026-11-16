#!/usr/bin/env python3
"""
apex_fragility_v2.py -- APEX-FRAGILITY-V2-2026-08-20

Fragility Score v2. NOT a winner model and NOT an attempt to beat Pinnacle.
Objective: score how vulnerable a market favorite is (0-100) and how
dangerous the underdog is (0-100), from a SMALL fixed set of components
that survived study 1, with plain-English reasons -- then judge the score
by one question only:

    Do higher fragility buckets lose more often than Pinnacle's price
    implied, on held-out 2024+ matches?

Components (fixed -- no feature pile):
    elo_gap            Elo-implied log-odds minus Pinnacle log-odds
                       (market discounting the favorite vs ratings)
    d_surface_switch   favorite switched surface (minus dog's switch)
    d_age              older favorite vs younger dog
    d_matches_14d      recent activity (negative = undercooked favorite)
    d_rank             log-rank edge vs dog
    d_rank_pts         rank-points edge vs dog
    is_slam            Grand Slam (protective)
    is_small_event     250 / International level (dog-friendly)
    is_bo5             best-of-5 (protective)
    is_qual_dog        underdog is a qualifier (only if Sackmann join given)

Modes:
  --run  --rows apex_batch_a_rows.csv --prob-col pinn_a \
         [--sackmann-dir "ATP & WTA, 1968-2026"]
      Fits on <=2023, evaluates 2024+ only. Writes fragility_v2_report.txt,
      fragility_v2_components.csv, fragility_v2_buckets.csv,
      fragility_v2_model.json (for live wiring later).
  --demo N        after --run artifacts exist: print N real 2024+ matches
                  in the Fragility Score card format.
  --selftest      synthetic: planted elo-gap + surface-switch effects must
                  be recovered and buckets must separate; nulls must not.
"""
import argparse, json, math, os, sys, glob, re
import numpy as np
import pandas as pd

MARKER = "APEX-FRAGILITY-V2-2026-08-20"
BANDS = [(0.50, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 1.001)]
BAND_NAMES = ["50-60%", "60-65%", "65-70%", "70-75%", "75-80%", "80%+"]
BUCKETS = [(0, 20), (21, 40), (41, 60), (61, 80), (81, 100)]
LN10_400 = math.log(10) / 400.0

REASON = {  # (text when component pushes fragility UP, text when it pushes DOWN)
    "elo_gap":          ("Market discounting favorite relative to ratings",
                         "Market agrees with (or exceeds) the ratings"),
    "d_surface_switch": ("Recent surface switch by the favorite",
                         "No surface-switch risk"),
    "d_age":            ("Older favorite versus younger opponent",
                         "No age-risk profile"),
    "d_matches_14d":    ("Low recent match activity (undercooked favorite)",
                         "Active recent match schedule"),
    "d_rank":           ("Ranking edge larger than the price implies",
                         "Ranking edge in line with the price"),
    "d_rank_pts":       ("Rank-points edge larger than the price implies",
                         "Rank-points edge in line with the price"),
    "is_slam":          ("", "Grand Slam environment (favorites safer here)"),
    "is_small_event":   ("Small-event environment (upset-friendly)", ""),
    "is_bo5":           ("", "Best-of-5 format (favorites safer here)"),
    "is_qual_dog":      ("Underdog is a qualifier (runs hot)", ""),
}
DOG_REASON = {  # underdog-side phrasing of the same components
    "elo_gap":          ("Market rates the underdog better than the ratings do", ""),
    "d_surface_switch": ("Opponent (favorite) just switched surfaces", ""),
    "d_age":            ("Young underdog against an older favorite", ""),
    "d_matches_14d":    ("Underdog match-sharp vs an undercooked favorite", ""),
    "d_rank":           ("", ""),
    "d_rank_pts":       ("", ""),
    "is_slam":          ("", ""),
    "is_small_event":   ("Small-event, best-of-3 style environment", ""),
    "is_bo5":           ("", ""),
    "is_qual_dog":      ("Qualifier momentum (matches already won this week)", ""),
}


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def irls_logistic(X, y, ridge=1e-3, iters=80):
    X = np.asarray(X, float); y = np.asarray(y, float)
    beta = np.zeros(X.shape[1])
    H = np.eye(X.shape[1])
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
    try:
        se = np.sqrt(np.maximum(np.diag(np.linalg.inv(H)), 0))
    except np.linalg.LinAlgError:
        return None, None
    return beta, se


def norm_sf(z):
    from scipy.stats import norm
    return float(norm.sf(z))


def norm_name(s):
    s = re.sub(r"[^a-z ]", "", str(s).lower().strip())
    return " ".join(sorted(s.split()))


# ------------------------------------------------------------ favorite frame
def to_favorite_frame(df, pcol):
    d = df.copy()
    fav_is_a = d[pcol] >= 0.5
    d["fav_p"] = np.where(fav_is_a, d[pcol], 1 - d[pcol])
    d["fav_lost"] = np.where(fav_is_a, 1 - d["label"], d["label"]).astype(int)
    d["fav_name"] = np.where(fav_is_a, d.get("player_a", ""), d.get("player_b", ""))
    d["dog_name"] = np.where(fav_is_a, d.get("player_b", ""), d.get("player_a", ""))
    flip = ~fav_is_a
    for c in [x for x in d.columns if x.startswith("d_")]:
        if pd.api.types.is_numeric_dtype(d[c]):
            d.loc[flip, c] = -d.loc[flip, c]
    d["band"] = None
    for (lo, hi), nm in zip(BANDS, BAND_NAMES):
        m = (d["fav_p"] >= lo) & (d["fav_p"] < hi)
        d.loc[m, "band"] = nm
    return d


def join_qualifier_dog(d, sack_dir):
    files = []
    for pat in ("[12][0-9][0-9][0-9].csv", "[12][0-9][0-9][0-9]_wta.csv"):
        files += glob.glob(os.path.join(sack_dir, pat))
    if not files or "tourney_id" not in d.columns:
        print("  qualifier join skipped (no files or no tourney_id)")
        return d
    frames = []
    for f in files:
        try:
            frames.append(pd.read_csv(f, usecols=lambda c: c in
                          ("tourney_id", "winner_name", "loser_name",
                           "winner_entry", "loser_entry"), low_memory=False))
        except Exception:
            pass
    s = pd.concat(frames, ignore_index=True)
    ent = {}
    for tid, wn, ln, we, le in zip(s["tourney_id"], s["winner_name"], s["loser_name"],
                                   s.get("winner_entry"), s.get("loser_entry")):
        k = str(tid) + "|" + "|".join(sorted([norm_name(wn), norm_name(ln)]))
        ent[k] = (norm_name(wn), str(we).strip().upper(), norm_name(ln), str(le).strip().upper())
    vals = []
    hit = 0
    for tid, fn, dn in zip(d["tourney_id"], d["fav_name"], d["dog_name"]):
        k = str(tid) + "|" + "|".join(sorted([norm_name(fn), norm_name(dn)]))
        rec = ent.get(k)
        if rec is None:
            vals.append(np.nan); continue
        hit += 1
        wn, we, ln, le = rec
        e = we if norm_name(dn) == wn else (le if norm_name(dn) == ln else "")
        vals.append(1.0 if e == "Q" else 0.0)
    d["is_qual_dog"] = vals
    print("  qualifier join: %.1f%% of rows matched" % (100 * hit / max(len(d), 1)))
    return d


# ------------------------------------------------------------ components
def build_components(d):
    comp = pd.DataFrame(index=d.index)
    comp["elo_gap"] = d["d_elo"] * LN10_400 - logit(d["fav_p"].values)
    comp["d_surface_switch"] = d.get("d_surface_switch")
    comp["d_age"] = d.get("d_age")
    comp["d_matches_14d"] = d.get("d_matches_14d")
    comp["d_rank"] = d.get("d_rank")
    comp["d_rank_pts"] = d.get("d_rank_pts")
    lv = d["level"].astype(str) if "level" in d.columns else pd.Series("", index=d.index)
    comp["is_slam"] = (lv == "G").astype(float)
    comp["is_small_event"] = lv.isin(["250", "I"]).astype(float)
    comp["is_bo5"] = d["is_bo5"].astype(float) if "is_bo5" in d.columns else 0.0
    if "is_qual_dog" in d.columns:
        comp["is_qual_dog"] = d["is_qual_dog"]
    return comp


def fit_model(d, comp, report):
    """Fit <=2023 jointly; refit same spec on 2024+ alone for the per-component
    holdout check. Returns model dict for scoring."""
    names = list(comp.columns)
    fit_m = d["year"] <= 2023
    te_m = d["year"] >= 2024
    med = comp[fit_m].median()
    filled = comp.fillna(med)
    mu = filled[fit_m].mean(); sd = filled[fit_m].std().replace(0, 1)
    Z = (filled - mu) / sd
    lp = logit(d["fav_p"].values)
    y = d["fav_lost"].values

    def fit_on(mask):
        X = np.column_stack([np.ones(mask.sum()), lp[mask.values], Z[mask].values])
        return irls_logistic(X, y[mask.values])

    b_fit, se_fit = fit_on(fit_m)
    b_te, se_te = fit_on(te_m)
    assert b_fit is not None and b_te is not None, "model fit failed"
    report.append("\nCOMPONENT TABLE  (joint model, price-controlled; effect size = "
                  "prob-point change in a 72% favorite's loss chance per +1 SD)")
    report.append("  %-18s %10s %8s %8s | %10s %8s | %-9s %s"
                  % ("component", "in_coef", "in_z", "in_p", "hold_coef", "hold_z",
                     "sign_holds", "effect@72%"))
    base = 0.28
    rows = []
    for i, c in enumerate(names):
        bf, zf = b_fit[2 + i], b_fit[2 + i] / max(se_fit[2 + i], 1e-9)
        bt, zt = b_te[2 + i], b_te[2 + i] / max(se_te[2 + i], 1e-9)
        pf = 2 * norm_sf(abs(zf))
        eff = 1 / (1 + math.exp(-(math.log(base / (1 - base)) + bf))) - base
        holds = "YES" if np.sign(bf) == np.sign(bt) else "no"
        report.append("  %-18s %+10.3f %+8.2f %8.3f | %+10.3f %+8.2f | %-9s %+5.1f pts"
                      % (c, bf, zf, pf, bt, zt, holds, 100 * eff))
        rows.append({"component": c, "in_coef": bf, "in_z": zf, "in_p": pf,
                     "holdout_coef": bt, "holdout_z": zt, "sign_holds": holds,
                     "effect_pts_at_72": 100 * eff,
                     "direction": "raises fragility" if bf > 0 else "lowers fragility"})
    model = {"marker": MARKER, "components": names,
             "median": {c: float(med[c]) for c in names},
             "mu": {c: float(mu[c]) for c in names},
             "sd": {c: float(sd[c]) for c in names},
             "beta": {c: float(b_fit[2 + i]) for i, c in enumerate(names)},
             "intercept": float(b_fit[0]), "price_coef": float(b_fit[1])}
    # fragility delta = component-only linear term (price excluded on purpose)
    delta = Z.values @ np.array([model["beta"][c] for c in names])
    d = d.copy()
    d["delta"] = delta
    # percentile map WITHIN BAND from the fit years only -> score is price-balanced
    pct = {}
    for nm in BAND_NAMES:
        ref = np.sort(d.loc[fit_m & (d["band"] == nm), "delta"].values)
        if len(ref) >= 200:
            pct[nm] = ref
    def score_row(band, dl):
        ref = pct.get(band)
        if ref is None:
            return np.nan
        return 100.0 * np.searchsorted(ref, dl, side="right") / len(ref)
    d["fragility"] = [score_row(b, x) for b, x in zip(d["band"], d["delta"])]
    model["percentile_ref"] = {k: v.tolist()[::max(1, len(v) // 400)] for k, v in pct.items()}
    return d, model, pd.DataFrame(rows), Z, names


def bucket_eval(d, report):
    te = d[(d["year"] >= 2024) & d["fragility"].notna()].copy()
    report.append("\nTHE KEY TABLE -- 2024+ held-out favorites by Fragility Score bucket")
    report.append("(score is a within-band percentile, so buckets hold similar prices; "
                  "'excess' = actual loss % minus what Pinnacle's own prices implied)")
    report.append("  bucket   n      mean_fav_p  fav_won%  fav_lost%  market_implied_lost%  excess  (SE)")
    out = []
    for lo, hi in BUCKETS:
        b = te[(te["fragility"] >= lo) & (te["fragility"] <= hi)]
        if len(b) < 100:
            continue
        lost = b["fav_lost"].mean()
        imp = 1 - b["fav_p"].mean()
        se = math.sqrt(lost * (1 - lost) / len(b))
        report.append("  %2d-%-3d %6d     %5.1f%%     %5.1f     %5.1f          %5.1f         %+5.1f  (%.1f)"
                      % (lo, hi, len(b), 100 * b["fav_p"].mean(), 100 * (1 - lost),
                         100 * lost, 100 * imp, 100 * (lost - imp), 100 * se))
        out.append({"bucket": "%d-%d" % (lo, hi), "n": len(b),
                    "mean_fav_p": b["fav_p"].mean(), "fav_lost": lost,
                    "market_implied": imp, "excess": lost - imp, "se": se})
    # pooled trend: does the score predict losses beyond price, on 2024+ only?
    X = np.column_stack([np.ones(len(te)), logit(te["fav_p"].values),
                         te["fragility"].values / 100.0])
    beta, se = irls_logistic(X, te["fav_lost"].values)
    z = beta[2] / se[2]
    report.append("  pooled 2024+ trend (score beyond price): z=%+.2f  p=%.4f  %s"
                  % (z, 2 * norm_sf(abs(z)),
                     "-> score carries real out-of-sample signal" if z > 1.96 else
                     "-> NOT significant out-of-sample; treat the score as descriptive only"))
    return pd.DataFrame(out), z


def reasons_for(row, Z, names, model, side="fav", top_k=4):
    contrib = [(c, model["beta"][c] * Z.loc[row.name, c]) for c in names]
    contrib.sort(key=lambda t: -abs(t[1]))
    texts = []
    table = REASON if side == "fav" else DOG_REASON
    for c, v in contrib:
        if len(texts) >= top_k:
            break
        pos, neg = table.get(c, ("", ""))
        t = pos if v > 0.05 else (neg if v < -0.05 else "")
        if t:
            texts.append(t)
    if not texts:
        texts = ["No strong risk factors either way"] if side == "fav" else \
                ["No strong threat factors either way"]
    return texts


def print_card(row, Z, names, model):
    frag = row["fragility"]
    print("Favorite: %s   vs   %s" % (row.get("fav_name", "?"), row.get("dog_name", "?")))
    print("Favorite Probability (Pinnacle): %.0f%%" % (100 * row["fav_p"]))
    print("Fragility Score: %d" % round(frag))
    print("Reasons:")
    for t in reasons_for(row, Z, names, model, "fav"):
        print("  - %s" % t)
    print("Underdog Threat Score: %d" % round(frag))
    dogr = reasons_for(row, Z, names, model, "dog")
    if dogr:
        print("Threat reasons:")
        for t in dogr:
            print("  - %s" % t)
    if "fav_lost" in row.index and not pd.isna(row.get("fav_lost")):
        print("Actual result: favorite %s" % ("LOST" if row["fav_lost"] == 1 else "won"))
    print()


# ------------------------------------------------------------ run / demo
def load(rows_path, prob_col):
    df = pd.read_csv(rows_path, low_memory=False)
    assert prob_col in df.columns, "--prob-col %r not in file" % prob_col
    df = df[df[prob_col].notna()].copy()
    conf = df[df[prob_col] > 0.60]
    if len(conf) > 200 and (conf["label"] == 1).mean() < 0.5:
        raise SystemExit("prob column looks inverted -- stop")
    if "year" not in df.columns and "date" in df.columns:
        df["year"] = pd.to_datetime(df["date"]).dt.year
    return df


def run(rows_path, prob_col, sack_dir):
    print(MARKER, "-- RUN")
    df = load(rows_path, prob_col)
    d = to_favorite_frame(df, prob_col)
    if sack_dir:
        d = join_qualifier_dog(d, sack_dir)
    d = d[d["band"].notna()].copy()
    report = ["%s\nGOAL: identify vulnerable market favorites / dangerous underdogs."
              "\nNOT a winner model. NOT judged by beating Pinnacle -- judged by whether"
              "\nhigh-fragility buckets lose more than Pinnacle's own price implied."
              "\nrows: %d (favorites 50%%+, all bands incl. 50-60 for context)" % (MARKER, len(d))]
    comp = build_components(d)
    d, model, comp_table, Z, names = fit_model(d, comp, report)
    buckets, trend_z = bucket_eval(d, report)
    report.append("\nSCORE DEFINITION (for live wiring): fragility delta = sum of "
                  "beta_i * z(component_i); score = within-band percentile of delta "
                  "against 2010-2023 favorites. Underdog Threat Score is the same "
                  "quantity read from the dog's side -- one model, two presentations "
                  "(a fragile favorite IS a dangerous underdog situation).")
    txt = "\n".join(report)
    open("fragility_v2_report.txt", "w").write(txt + "\n")
    comp_table.to_csv("fragility_v2_components.csv", index=False)
    buckets.to_csv("fragility_v2_buckets.csv", index=False)
    json.dump(model, open("fragility_v2_model.json", "w"), indent=1)
    # stash scored 2024+ rows for --demo
    keep = ["fav_name", "dog_name", "fav_p", "band", "fragility", "fav_lost", "year"]
    st = d[d["year"] >= 2024][keep].join(Z[d["year"] >= 2024])
    st.to_pickle("fragility_v2_scored.pkl")
    print(txt)
    print("\nwritten: fragility_v2_report.txt, fragility_v2_components.csv, "
          "fragility_v2_buckets.csv, fragility_v2_model.json")
    print("demo cards:  python3 apex_fragility_v2.py --demo 4")


def demo(n):
    model = json.load(open("fragility_v2_model.json"))
    st = pd.read_pickle("fragility_v2_scored.pkl")
    names = model["components"]
    names = [c for c in names if c in st.columns]
    hi = st[st["fragility"] >= 80].sample(min(n // 2 + 1, (st["fragility"] >= 80).sum()),
                                          random_state=3)
    lo = st[st["fragility"] <= 20].sample(min(n // 2, (st["fragility"] <= 20).sum()),
                                          random_state=3)
    for _, row in pd.concat([hi, lo]).iterrows():
        print_card(row, st, names, model)


# ------------------------------------------------------------ selftest
def selftest():
    print(MARKER, "-- SELFTEST (synthetic)")
    rng = np.random.default_rng(11)
    n = 60000
    year = rng.integers(2015, 2026, n)
    skill = rng.normal(0, 1.1, n)
    market_lo = skill                                   # market log-odds for player a
    gap = rng.normal(0, 0.5, n)                         # elo overshoot vs market (a-frame)
    sw_a = (rng.random(n) < 0.10).astype(float)
    sw_b = (rng.random(n) < 0.10).astype(float)
    sign = np.where(1 / (1 + np.exp(-market_lo)) >= 0.5, 1.0, -1.0)
    # true outcome: market calibrated on average, but elo-overrated favs and
    # surface-switching favs lose more
    lin = market_lo - 0.18 * gap - 0.30 * (sw_a - sw_b)
    label = (rng.random(n) < 1 / (1 + np.exp(-lin))).astype(int)
    p_a = 1 / (1 + np.exp(-market_lo))
    d_elo = (market_lo + gap) / LN10_400                # elo points implying skill+gap
    df = pd.DataFrame({"label": label, "year": year, "player_a": "A", "player_b": "B",
                       "tourney_id": "t", "pinn_a": p_a, "d_elo": d_elo,
                       "d_surface_switch": sw_a - sw_b,
                       "d_age": rng.normal(0, 1, n), "d_matches_14d": rng.normal(0, 1, n),
                       "d_rank": rng.normal(0, 1, n), "d_rank_pts": rng.normal(0, 1, n),
                       "level": "250", "is_bo5": 0})
    d = to_favorite_frame(df, "pinn_a")
    d = d[d["band"].notna()].copy()
    report = []
    comp = build_components(d)
    d, model, table, Z, names = fit_model(d, comp, report)
    buckets, trend_z = bucket_eval(d, report)
    print("\n".join(report))
    t = table.set_index("component")
    assert t.loc["elo_gap", "in_z"] > 3 and t.loc["elo_gap", "sign_holds"] == "YES", "elo_gap not recovered"
    assert t.loc["d_surface_switch", "in_z"] > 3 and t.loc["d_surface_switch", "sign_holds"] == "YES", "surface switch not recovered"
    nz = [abs(t.loc[c, "in_z"]) for c in ("d_age", "d_matches_14d", "d_rank", "d_rank_pts")]
    assert sum(z > 3 for z in nz) == 0, "null component falsely strong"
    assert trend_z > 3, "bucket trend not recovered out-of-sample"
    ex = {r["bucket"]: r["excess"] for _, r in buckets.iterrows()}
    assert ex["81-100"] > ex["0-20"] + 0.02, "top bucket not separating from bottom"
    assert ex["81-100"] > 0, "top bucket excess not positive"
    # card printing sanity
    st = d[d["year"] >= 2024].join(Z[d["year"] >= 2024], rsuffix="_z")
    row = st[st["fragility"] >= 90].iloc[0]
    print_card(row, Z, names, model)
    print("SELFTEST PASS -- planted gap + surface effects recovered, nulls quiet, "
          "buckets separate on held-out years, cards render.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--demo", type=int, default=0)
    ap.add_argument("--rows", default="apex_batch_a_rows.csv")
    ap.add_argument("--prob-col", default="pinn_a")
    ap.add_argument("--sackmann-dir", default=None)
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.demo:
        demo(a.demo)
    elif a.run:
        run(a.rows, a.prob_col, a.sackmann_dir)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
