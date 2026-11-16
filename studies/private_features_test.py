#!/usr/bin/env python3
"""
private_features_test.py  --  2026-08-16   Project Apex Intelligence (OpenClaw / DEMETRIUS)
Track B, step 1.  Question: do "private-layer" features -- retirement history, fatigue/schedule
load, surface switch -- carry information that Pinnacle's price does NOT already have?

Method (the Benter test, time-split, threshold-free):
  1. Build per-player features from Sackmann-format match files, using ONLY matches before the
     match being predicted.
  2. Join each Pinnacle-priced match (tennis-data odds/*.xls*, PSW/PSL) to its Sackmann row by
     surname pair + date window (odds date within [tourney_date-1, tourney_date+16]), unique only.
  3. Randomise orientation (p1 = winner or loser, seeded) so labels are ~50/50.
  4. Baseline = Pinnacle de-vigged fair prob.  Model = logistic on logit(pinn) + feature diffs,
     fitted on TRAIN years, scored on TEST years by log-loss.  Report per-feature deltas too.
  PASS (per plan): test log-loss improves vs Pinnacle by >= 0.005.  ALARM if it improves by > 0.02
  (leak).  Anything ~0 = the price already knows it.

Data:
  --sack-dir DIR      folder with Sackmann-format CSVs (atp_matches_YYYY.csv / wta_matches_YYYY.csv)
                      OR any CSV(s) with columns: tourney_date, tourney_name, surface, round,
                      best_of, winner_name, loser_name, score, minutes  (tour optional)
  --odds-dir DIR      folder with tennis-data files atp_YYYY.xls(x) / wta_YYYY.xls(x)  (default odds/)
  If Dataset B is only in the warehouse, export it with (adjust table/column names):
     COPY (SELECT tourney_date, tourney_name, surface, round, best_of, winner_name, loser_name,
                  score, minutes FROM matches WHERE tourney_date >= '2005-01-01')
     TO '/tmp/sack_export.csv' CSV HEADER;
  and pass --matches-csv /tmp/sack_export.csv

Usage:
    python3 private_features_test.py --selftest
    python3 private_features_test.py --sack-dir sackmann/ --odds-dir odds/
    python3 private_features_test.py --matches-csv /tmp/sack_export.csv --odds-dir odds/
Options: --train-to 2021 --test-from 2024   (2022-23 reported as a middle block)
"""
import argparse, glob, os, re, sys, unicodedata
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

ROUND_ORDER = {"Q1": 0, "Q2": 1, "Q3": 2, "R128": 3, "R64": 4, "R32": 5, "R16": 6, "QF": 7, "SF": 8,
               "F": 9, "RR": 5, "BR": 8, "ER": 2}
FEATURES = ["ret_rate_prior", "ret_last10", "days_since_last", "matches_14d", "sets_14d",
            "minutes_14d", "distance_14d", "surface_switch", "weeks_streak"]


# ============================================================================ helpers
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def sets_played(score):
    """Count completed sets in a Sackmann score string; RET/W/O partial sets still count as played."""
    if not isinstance(score, str):
        return 0
    s = re.sub(r"\(.*?\)", "", score)
    return len([t for t in s.replace("RET", "").replace("W/O", "").split() if "-" in t])


def is_ret(score):
    return isinstance(score, str) and "RET" in score.upper()


def is_wo(score):
    return isinstance(score, str) and ("W/O" in score.upper() or "WALKOVER" in score.upper())


def to_date(x):
    if isinstance(x, (datetime, pd.Timestamp)):
        return pd.Timestamp(x).normalize()
    s = str(x).strip()
    if re.fullmatch(r"\d{8}", s):
        return pd.Timestamp(datetime.strptime(s, "%Y%m%d"))
    return pd.Timestamp(pd.to_datetime(s, errors="coerce")).normalize()


# ============================================================================ features
def build_player_features(matches):
    """
    matches: DataFrame with tourney_date(datetime), round, surface, best_of, winner_name, loser_name,
             score, minutes.  Returns long DataFrame: one row per (match_idx, player) with features
             computed from that player's PRIOR matches only.
    """
    m = matches.copy()
    m["ro"] = m["round"].map(ROUND_ORDER).fillna(5)
    m["sets"] = m["score"].map(sets_played)
    m["ret"] = m["score"].map(is_ret)
    m["wo"] = m["score"].map(is_wo)
    m["minutes"] = pd.to_numeric(m["minutes"], errors="coerce")
    m["dist"] = ((m["best_of"].fillna(3) == 3) & (m["sets"] >= 3)) | ((m["best_of"] == 5) & (m["sets"] >= 5))
    m = m.sort_values(["tourney_date", "ro"]).reset_index(drop=False).rename(columns={"index": "match_idx"})

    rows = []
    for side, opp in (("winner_name", "loser_name"), ("loser_name", "winner_name")):
        d = m[["match_idx", "tourney_date", "ro", "surface", "sets", "ret", "wo", "minutes", "dist", side]].copy()
        d["player"] = d[side]; d["won"] = side == "winner_name"
        d["retired"] = d["ret"] & (side == "loser_name")     # the loser is the one who retired
        rows.append(d.drop(columns=[side]))
    L = pd.concat(rows).sort_values(["player", "tourney_date", "ro"]).reset_index(drop=True)

    out = np.full((len(L), len(FEATURES)), np.nan)
    for player, g in L.groupby("player", sort=False):
        idx = g.index.to_numpy()
        dates = g["tourney_date"].to_numpy()
        ret = g["retired"].to_numpy().astype(float)
        sets = g["sets"].to_numpy().astype(float)
        mins = np.nan_to_num(g["minutes"].to_numpy().astype(float))
        dist = g["dist"].to_numpy().astype(float)
        surf = g["surface"].astype(str).to_numpy()
        n = len(idx)
        cum_ret = np.concatenate([[0], np.cumsum(ret)])
        for k in range(n):
            prior_n = k
            ret_rate = cum_ret[k] / prior_n if prior_n else 0.0
            ret_last10 = ret[max(0, k - 10):k].sum()
            if k == 0:
                dsl = 60.0; m14 = s14 = mn14 = d14 = 0.0; sw = 0.0; streak = 0.0
            else:
                d0 = dates[k]
                dsl = min(60.0, (d0 - dates[k - 1]) / np.timedelta64(1, "D"))
                w = (dates[:k] >= d0 - np.timedelta64(14, "D")) & (dates[:k] < d0)
                m14 = w.sum(); s14 = sets[:k][w].sum(); mn14 = mins[:k][w].sum(); d14 = dist[:k][w].sum()
                sw = float(surf[k] != surf[k - 1] and dsl <= 14)
                # consecutive tournament weeks: count distinct prior tourney weeks within streak of <=8 days gaps
                streak = 0.0; j = k
                while j > 0 and (dates[j] - dates[j - 1]) / np.timedelta64(1, "D") <= 8:
                    if dates[j] != dates[j - 1]:
                        streak += 1
                    j -= 1
            out[idx[k]] = [ret_rate, ret_last10, dsl, m14, s14, mn14, d14, sw, streak]
    F = pd.DataFrame(out, columns=FEATURES)
    return pd.concat([L[["match_idx", "player", "won"]].reset_index(drop=True), F], axis=1)


# ============================================================================ odds join
def load_odds(odds_dir):
    frames = []
    for fp in sorted(glob.glob(os.path.join(odds_dir, "*.xls*")) + glob.glob(os.path.join(odds_dir, "*.csv"))):
        try:
            d = pd.read_csv(fp) if fp.endswith(".csv") else pd.read_excel(fp)
        except Exception as e:
            print(f"  skip {os.path.basename(fp)}: {e}"); continue
        need = {"Date", "Winner", "Loser", "PSW", "PSL"}
        if not need.issubset(d.columns):
            continue
        d = d[["Date", "Winner", "Loser", "PSW", "PSL"]].copy()
        d["tour"] = "wta" if "wta" in os.path.basename(fp).lower() else "atp"
        frames.append(d)
    if not frames:
        return pd.DataFrame(columns=["Date", "Winner", "Loser", "PSW", "PSL", "tour"])
    o = pd.concat(frames, ignore_index=True)
    o["Date"] = o["Date"].map(to_date)
    o["PSW"] = pd.to_numeric(o["PSW"], errors="coerce"); o["PSL"] = pd.to_numeric(o["PSL"], errors="coerce")
    o = o.dropna(subset=["Date", "PSW", "PSL"])
    o = o[(o.PSW > 1) & (o.PSL > 1)]
    return o.reset_index(drop=True)


def odds_name_parts(name):
    """'Djokovic N.' -> ('djokovic', 'n'); 'Carreno Busta P.' -> ('carreno busta','p'); 'O Connell C.' ok."""
    toks = norm(name).split()
    inits = [t for t in toks if len(t) == 1]
    sur = " ".join(t for t in toks if len(t) > 1)
    return sur, (inits[0] if inits else "")


def db_name_matches(odds_name, db_name):
    sur, ini = odds_name_parts(odds_name)
    dn = norm(db_name)
    if not sur or sur not in dn:
        return False
    toks = dn.split()
    if toks and sur.split()[0] == toks[0] and len(toks) > 1:
        return False                        # surname can't be the DB first token (sibling guard)
    if ini and not any(t.startswith(ini) for t in toks[:-1] or toks):
        return False
    return True


def join_odds(matches, odds):
    """For each odds row find exactly one Sackmann match (same surname pair, date window). Returns DataFrame
    of matched pairs: match_idx, PSW, PSL, odds_date."""
    m = matches.reset_index(drop=False).rename(columns={"index": "match_idx"})
    m["w_sur"] = m["winner_name"].map(lambda x: norm(x).split()[-1] if norm(x) else "")
    m["l_sur"] = m["loser_name"].map(lambda x: norm(x).split()[-1] if norm(x) else "")
    by_date = m.sort_values("tourney_date")
    dates = by_date["tourney_date"].to_numpy()
    out = []
    for r in odds.itertuples(index=False):
        lo = np.datetime64(r.Date - timedelta(days=16)); hi = np.datetime64(r.Date + timedelta(days=1))
        i0 = np.searchsorted(dates, lo, "left"); i1 = np.searchsorted(dates, hi, "right")
        cand = by_date.iloc[i0:i1]
        wsur, _ = odds_name_parts(r.Winner); lsur, _ = odds_name_parts(r.Loser)
        if not wsur or not lsur:
            continue
        cand = cand[cand["w_sur"].map(lambda s: s in wsur or wsur.endswith(s)) &
                    cand["l_sur"].map(lambda s: s in lsur or lsur.endswith(s))]
        cand = cand[cand.apply(lambda x: db_name_matches(r.Winner, x.winner_name) and
                                         db_name_matches(r.Loser, x.loser_name), axis=1)] if len(cand) else cand
        if len(cand) == 1:
            out.append((int(cand.iloc[0]["match_idx"]), float(r.PSW), float(r.PSL), r.Date))
    return pd.DataFrame(out, columns=["match_idx", "PSW", "PSL", "odds_date"])


# ============================================================================ model
def logit(p): p = np.clip(p, 1e-6, 1 - 1e-6); return np.log(p / (1 - p))
def sigmoid(z): return 1 / (1 + np.exp(-z))
def logloss(y, p): p = np.clip(p, 1e-6, 1 - 1e-6); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_logistic(X, y, l2=1.0, iters=50):
    """Newton's method, L2 on all but intercept. X includes intercept column 0."""
    w = np.zeros(X.shape[1])
    R = np.eye(X.shape[1]) * l2; R[0, 0] = 0
    for _ in range(iters):
        p = sigmoid(X @ w)
        g = X.T @ (p - y) + R @ w
        H = (X.T * (p * (1 - p))) @ X + R
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def design(df, cols, mu=None, sd=None):
    Z = df[cols].to_numpy(dtype=float)
    if mu is None:
        mu = Z.mean(0); sd = Z.std(0) + 1e-9
    Z = (Z - mu) / sd
    X = np.column_stack([np.ones(len(df)), logit(df["pinn"].to_numpy()), Z])
    return X, mu, sd


def build_dataset(matches, feats, joined, seed=7):
    """One row per matched match, random orientation. Columns: year, pinn, y, feature diffs."""
    fw = feats[feats["won"]].set_index("match_idx"); fl = feats[~feats["won"]].set_index("match_idx")
    rng = np.random.default_rng(seed)
    rows = []
    for r in joined.itertuples(index=False):
        if r.match_idx not in fw.index or r.match_idx not in fl.index:
            continue
        a, b = 1 / r.PSW, 1 / r.PSL
        pw = a / (a + b)
        flip = rng.random() < 0.5
        w = fw.loc[r.match_idx, FEATURES].to_numpy(float); l = fl.loc[r.match_idx, FEATURES].to_numpy(float)
        diff = (l - w) if flip else (w - l)
        rows.append([r.odds_date.year, (1 - pw) if flip else pw, 0 if flip else 1, *diff])
    return pd.DataFrame(rows, columns=["year", "pinn", "y", *[f"d_{f}" for f in FEATURES]])


def evaluate(D, train_to, test_from, quiet=False):
    tr = D[D.year <= train_to]; mid = D[(D.year > train_to) & (D.year < test_from)]; te = D[D.year >= test_from]
    cols = [f"d_{f}" for f in FEATURES]
    res = {}
    if len(tr) < 200 or len(te) < 100:
        print(f"  not enough rows (train {len(tr)}, test {len(te)})"); return None
    X, mu, sd = design(tr, cols); w = fit_logistic(X, tr.y.to_numpy(float))
    for name, part in (("TRAIN", tr), ("MID 22-23", mid), ("TEST", te)):
        if len(part) == 0: continue
        Xp, _, _ = design(part, cols, mu, sd)
        p_model = sigmoid(Xp @ w); ll_p = logloss(part.y.to_numpy(float), part.pinn.to_numpy()); ll_m = logloss(part.y.to_numpy(float), p_model)
        res[name] = (len(part), ll_p, ll_m)
        if not quiet:
            print(f"  {name:10s} n={len(part):6d}  LL Pinnacle {ll_p:.4f}   LL Pinnacle+features {ll_m:.4f}   delta {ll_p-ll_m:+.4f}")
        if name == "TEST" and not quiet:
            # value bets: model disagrees with Pinnacle by >= 0.03 -> bet at Pinnacle price (closing, so pessimistic)
            y = part.y.to_numpy(float); pinn = part.pinn.to_numpy()
            side1 = p_model - pinn >= 0.03; side0 = pinn - p_model >= 0.03
            pnl = 0.0; n = 0
            for i in np.where(side1)[0]:
                pnl += (1 / pinn[i] - 1) if y[i] == 1 else -1; n += 1
            for i in np.where(side0)[0]:
                pnl += (1 / (1 - pinn[i]) - 1) if y[i] == 0 else -1; n += 1
            if n:
                print(f"             disagreement bets (>=0.03 vs Pinnacle CLOSE): {n}  ROI {pnl/n:+.1%}  (SE ~{1.0/np.sqrt(n):.1%})")
    if not quiet:
        print("  per-feature (TEST, each alone on top of Pinnacle):")
        for c in cols:
            X1, mu1, sd1 = design(tr, [c]); w1 = fit_logistic(X1, tr.y.to_numpy(float))
            Xt, _, _ = design(te, [c], mu1, sd1)
            print(f"    {c:20s} delta {res['TEST'][1]-logloss(te.y.to_numpy(float), sigmoid(Xt @ w1)):+.4f}   coef {w1[2]:+.3f}")
    return res


def verdict(res):
    if not res or "TEST" not in res: return
    n, llp, llm = res["TEST"]; d = llp - llm
    print("\n" + "=" * 72 + "\nVERDICT (Track B step 1: private features on top of Pinnacle CLOSE)\n" + "=" * 72)
    print(f"  TEST rows {n}   Pinnacle LL {llp:.4f}   +features LL {llm:.4f}   improvement {d:+.4f}")
    if d > 0.02:   print("  ALARM: improvement > 0.02 -- treat as a LEAK / data error until proven otherwise.")
    elif d >= 0.005: print("  PASS: features carry information the closing price did not fully have. Wire into the opening-line test (A1).")
    elif d > 0.001: print("  WEAK: a sliver. Not enough vs the close; may still matter vs the OPENER (A1) -- test there before building more.")
    else:          print("  FAIL: ~zero. The price already knows these. Do NOT build a scraping pipeline on them; try the next signal set.")


# ============================================================================ self-test
def _synthetic(n_players=40, n_weeks=120, seed=1, planted=True):
    rng = np.random.default_rng(seed)
    skill = rng.normal(0, 1, n_players)
    def tag(i): return chr(97 + i // 26) + chr(97 + i % 26)
    names = [f"Given{tag(i).upper()} Sur{tag(i)}" for i in range(n_players)]
    sur = [f"Sur{tag(i)} G." for i in range(n_players)]
    rows = []; odds = []
    date = pd.Timestamp("2015-01-05")
    last_played = {i: None for i in range(n_players)}
    for wk in range(n_weeks):
        # each week: 16 random players play a small event over rounds
        ps = rng.choice(n_players, 16, replace=False)
        alive = list(ps); rnd = ["R16", "QF", "SF", "F"]; ri = 0
        while len(alive) > 1:
            nxt = []
            for a, b in zip(alive[::2], alive[1::2]):
                # planted effect: a player who played last week (fatigue) is weaker by 0.6 skill units
                fa = skill[a] - (0.6 if planted and last_played[a] == wk - 1 else 0)
                fb = skill[b] - (0.6 if planted and last_played[b] == wk - 1 else 0)
                p_a = sigmoid(fa - fb)
                a_wins = rng.random() < p_a
                w, l = (a, b) if a_wins else (b, a)
                sets = 2 if rng.random() < 0.65 else 3
                score = " ".join(["6-4"] * sets) + (" RET" if rng.random() < 0.03 else "")
                rows.append({"tourney_date": date, "tourney_name": f"Ev{wk}", "surface": "Hard", "round": rnd[ri],
                             "best_of": 3, "winner_name": names[w], "loser_name": names[l], "score": score,
                             "minutes": 60 * sets + rng.integers(-10, 10)})
                # Pinnacle "knows" skill but NOT the fatigue (that's the point of the test)
                pk = sigmoid(skill[a] - skill[b]); pw = pk if a_wins else 1 - pk
                vig = 1.03
                odds.append({"Date": date + timedelta(days=ri), "Winner": sur[w], "Loser": sur[l],
                             "PSW": 1 / (pw * vig), "PSL": 1 / ((1 - pw) * vig)})
                nxt.append(w)
            alive = nxt; ri += 1
        for p in ps: last_played[p] = wk
        date += timedelta(days=7)
    return pd.DataFrame(rows), pd.DataFrame(odds)


def selftest():
    n = 0
    def ok(c, msg):
        nonlocal n; n += 1
        if not c: print(f"SELFTEST FAIL #{n}: {msg}"); sys.exit(1)
        print(f"  ok #{n}: {msg}")
    ok(sets_played("6-4 3-6 7-6(5)") == 3, "sets_played handles tiebreak")
    ok(sets_played("6-4 2-1 RET") == 2 and is_ret("6-4 2-1 RET"), "RET parsed")
    ok(is_wo("W/O"), "walkover parsed")
    ok(odds_name_parts("Carreno Busta P.") == ("carreno busta", "p"), "odds surname multi-token")
    ok(db_name_matches("Zverev A.", "Alexander Zverev") and not db_name_matches("Zverev A.", "Mischa Zverev"), "initial guard")
    ok(db_name_matches("O Connell C.", "Christopher O'Connell"), "apostrophe")
    m, o = _synthetic(n_players=60, n_weeks=300, planted=True)
    feats = build_player_features(m)
    ok(set(FEATURES).issubset(feats.columns) and len(feats) == 2 * len(m), "features built, 2 rows per match")
    ok(feats["days_since_last"].between(0, 60).all(), "days_since_last bounded")
    ok(feats["ret_rate_prior"].between(0, 1).all(), "ret_rate in [0,1]")
    j = join_odds(m, o)
    ok(len(j) >= 0.9 * len(o), f"join matched {len(j)}/{len(o)} synthetic odds rows")
    D = build_dataset(m, feats, j)
    ok(0.4 < D.y.mean() < 0.6, "orientation randomised (~50% labels)")
    ok(abs(D.pinn.mean() - 0.5) < 0.05, "Pinnacle probs symmetric after flip")
    res = evaluate(D, train_to=2018, test_from=2019, quiet=True)
    d = res["TEST"][1] - res["TEST"][2]
    ok(d > 0.002, f"planted fatigue effect detected on TEST (delta {d:+.4f})")
    m2, o2 = _synthetic(n_players=60, n_weeks=300, planted=False, seed=3)
    f2 = build_player_features(m2); j2 = join_odds(m2, o2); D2 = build_dataset(m2, f2, j2)
    res2 = evaluate(D2, train_to=2018, test_from=2019, quiet=True)
    d2 = res2["TEST"][1] - res2["TEST"][2]
    ok(abs(d2) < 0.004, f"no planted effect -> ~zero delta (delta {d2:+.4f}); no leak in the pipeline")
    print(f"\nSELFTEST PASSED ({n} checks)")


# ============================================================================ main
def load_matches(sack_dir, matches_csv):
    files = [matches_csv] if matches_csv else sorted(glob.glob(os.path.join(sack_dir, "*matches*.csv")))
    frames = []
    for fp in files:
        d = pd.read_csv(fp, low_memory=False)
        need = ["tourney_date", "tourney_name", "surface", "round", "best_of", "winner_name", "loser_name", "score", "minutes"]
        missing = [c for c in need if c not in d.columns]
        if missing:
            print(f"  skip {os.path.basename(fp)}: missing {missing}"); continue
        frames.append(d[need])
    if not frames:
        print("no match files loaded"); sys.exit(1)
    m = pd.concat(frames, ignore_index=True)
    m["tourney_date"] = m["tourney_date"].map(to_date)
    m = m.dropna(subset=["tourney_date", "winner_name", "loser_name"]).reset_index(drop=True)
    print(f"  matches loaded: {len(m):,}  ({m.tourney_date.min().date()} .. {m.tourney_date.max().date()})")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sack-dir", default="sackmann")
    ap.add_argument("--matches-csv", default=None)
    ap.add_argument("--odds-dir", default="odds")
    ap.add_argument("--train-to", type=int, default=2021)
    ap.add_argument("--test-from", type=int, default=2024)
    ap.add_argument("--save", default="private_features_dataset.csv")
    a = ap.parse_args()
    if a.selftest: selftest(); return
    print("== 1. matches =="); m = load_matches(a.sack_dir, a.matches_csv)
    print("== 2. features (prior-only) =="); f = build_player_features(m); print(f"  feature rows: {len(f):,}")
    print("== 3. Pinnacle odds =="); o = load_odds(a.odds_dir); print(f"  odds rows with Pinnacle: {len(o):,}")
    print("== 4. join =="); j = join_odds(m, o); print(f"  matched: {len(j):,} of {len(o):,} odds rows ({len(j)/max(1,len(o)):.0%})")
    D = build_dataset(m, f, j); D.to_csv(a.save, index=False); print(f"  dataset rows: {len(D):,}  saved -> {a.save}")
    print("== 5. held-out test =="); res = evaluate(D, a.train_to, a.test_from); verdict(res)


if __name__ == "__main__":
    main()
