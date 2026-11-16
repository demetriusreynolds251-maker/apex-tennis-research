"""
test_market_edges.py
2026-08-15 — the two moneyline avenues that use the MARKET as an input
(rules suspended by user for research). Same scoreboard, same discipline:
tune on 2022-2023, open >= 2024 ONCE, alarms on.

AVENUE 1 — SOFT-BOOK PRICING OFF PINNACLE ("fair value" arbitrage-lite)
  Pinnacle's de-vigged price is treated as fair value. Whenever the BEST
  available price (MaxW/MaxL across listed books) implies a probability
  LOWER than Pinnacle's fair number by > thr, bet that side at the Max
  price. No model involved. Also shown for the AVERAGE price (a typical
  soft book you could actually get, not the single best).

AVENUE 1b — PINNACLE RECALIBRATION (favourite-longshot bias)
  Fit P(win) = logistic(a + b*logit(pinnacle_fair)) on TUNE. If b != 1 the
  book is systematically off (classic: underdogs over-priced). Bet where the
  recalibrated number disagrees with the raw one.

AVENUE 2 — BENTER COMBINATION (market price as the base, model as the correction)
  Fit P(win) = logistic( logit(pinnacle_fair), model inputs ... ) on TUNE.
  Candidates add progressively: +ELO std, +all ELO variants, +rank,
  +S5/S1/H2H. If the combined number is closer to the truth than Pinnacle
  alone on TEST (lower log loss), then bet where combined disagrees with
  the market -- at Pinnacle's price (hard) and at Max price (line shopping).

ALARMS: any candidate that beats Pinnacle by more than 0.02 log loss on TEST
is treated as a leak, not a win. Real edges here are small (LL -0.002 to
-0.008, ROI +1% to +5%).

USAGE (on the Mini, after build_walkforward_rows.py + build_elo_variants.py,
./odds/ populated):  python3 test_market_edges.py
"""
import os
import sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_edge_backtest import load_odds, match_rows, devig, TUNE_YEARS, TEST_MIN_YEAR, MIN_BETS_TO_TRUST

ROWS_CSV = "walkforward_rows.csv"
ELO_CSV = "elo_variants.csv"
VARIANTS = ["std", "welo", "mov", "surf", "dynk"]
THRESHOLDS = [0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10]
LEAK_LL_MARGIN = 0.02


def _ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _acc(p, y):
    return float(((p > 0.5).astype(int) == y).mean())


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _feat(df, cols):
    X = []
    for c in cols:
        v = pd.to_numeric(df[c], errors="coerce").values.astype(float)
        X.append(np.nan_to_num(v, nan=0.0))
        X.append(np.isnan(v).astype(float))
    return np.column_stack(X)


def bet_sim(p_model, p_ref, y, oa, ob, thr):
    """Bet 1u on side a if p_model - p_ref > thr (paid at oa), on side b if
    (1-p_model)-(1-p_ref) > thr (paid at ob). Returns n, hit, roi."""
    oa = np.nan_to_num(np.asarray(oa, float), nan=np.nan)
    ob = np.nan_to_num(np.asarray(ob, float), nan=np.nan)
    ea, eb = p_model - p_ref, (1 - p_model) - (1 - p_ref)
    bet_a = (ea > thr) & np.isfinite(oa)
    bet_b = (eb > thr) & np.isfinite(ob) & ~bet_a
    n = int(bet_a.sum() + bet_b.sum())
    if n == 0:
        return 0, float("nan"), float("nan")
    oa_c, ob_c = np.nan_to_num(oa, nan=1.0), np.nan_to_num(ob, nan=1.0)
    win_a, win_b = bet_a & (y == 1), bet_b & (y == 0)
    profit = float(((oa_c - 1) * win_a).sum()) - float((bet_a & (y == 0)).sum()) \
           + float(((ob_c - 1) * win_b).sum()) - float((bet_b & (y == 1)).sum())
    hits = int(win_a.sum() + win_b.sum())
    return n, hits / n, profit / n


def sweep(label, p_model, p_ref, y, oa, ob, chosen=None):
    print(f"\n  {label}")
    print(f"    {'edge >':>7s} {'bets':>6s} {'hit%':>7s} {'ROI':>8s}")
    best = None
    for thr in THRESHOLDS:
        n, hit, roi = bet_sim(p_model, p_ref, y, oa, ob, thr)
        mark = " <== chosen" if chosen is not None and abs(thr - chosen) < 1e-9 else ""
        thin = "" if n >= MIN_BETS_TO_TRUST else "  (thin)"
        print(f"    {thr:>7.3f} {n:>6,d} {hit:>7.1%} {roi:>+8.2%}{thin}{mark}")
        if n >= MIN_BETS_TO_TRUST and (best is None or roi > best[1]):
            best = (thr, roi, n)
    return best


def load_all():
    rows = pd.read_csv(ROWS_CSV)
    rows["year"] = rows["year"].astype(int)
    rows = rows[rows["year"] >= TUNE_YEARS[0]].copy()
    ev = pd.read_csv(ELO_CSV)
    ev = ev[pd.to_datetime(ev["match_date"], errors="coerce").dt.year >= TUNE_YEARS[0]]
    key = ["match_date", "player_a", "player_b"]
    rows = rows[~rows.duplicated(key, keep=False)]
    ev = ev[~ev.duplicated(key, keep=False)]
    m = rows.merge(ev.drop(columns=["surface"]), on=key, how="left")
    od = load_odds()
    if od is None:
        return None
    mm = match_rows(m, od)
    mm = mm[~mm["comment"].str.contains("Retired|Walkover", case=False, na=False)].copy()
    for c in ("ps_a", "ps_b", "avg_a", "avg_b", "max_a", "max_b", "rank_a", "rank_b"):
        mm[c] = pd.to_numeric(mm[c], errors="coerce")
    mm["ps_imp_a"] = devig(mm["ps_a"].values, mm["ps_b"].values)
    mm = mm[mm["ps_imp_a"].notna()].copy()
    mm["ps_logit"] = _logit(mm["ps_imp_a"].values)
    mm["log_rank_ratio"] = np.log(mm["rank_b"]) - np.log(mm["rank_a"])
    # book margins for context
    mm["ps_overround"] = 1 / mm["ps_a"] + 1 / mm["ps_b"]
    return mm


def run():
    for f in (ROWS_CSV, ELO_CSV):
        if not os.path.exists(f):
            print(f"ERROR: {f} missing."); return
    mm = load_all()
    if mm is None or mm.empty:
        return
    tune = mm[(mm["year"] >= TUNE_YEARS[0]) & (mm["year"] <= TUNE_YEARS[1])].copy()
    test = mm[mm["year"] >= TEST_MIN_YEAR].copy()
    y_tu, y_te = tune["label_a_won"].values.astype(int), test["label_a_won"].values.astype(int)
    print(f"\nTUNE {TUNE_YEARS[0]}-{TUNE_YEARS[1]}: {len(tune):,}   TEST >= {TEST_MIN_YEAR}: {len(test):,}   "
          f"(Pinnacle overround median {mm['ps_overround'].median():.3f})")

    # =====================================================================
    print("\n" + "=" * 90)
    print("AVENUE 1 — SOFT-BOOK PRICING OFF PINNACLE FAIR VALUE (no model)")
    print("=" * 90)
    for label, ca, cb in (("Best price across books (Max)", "max_a", "max_b"), ("Average price (typical soft book)", "avg_a", "avg_b")):
        # 'model' here is Pinnacle fair; the reference is the soft book's own implied prob (with its vig)
        for split, df, y in (("TUNE", tune, y_tu), ("TEST", test, y_te)):
            imp_a = 1 / df[ca].values; imp_b = 1 / df[cb].values
            # edge on a = fair_a - implied_a ; edge on b = fair_b - implied_b (each side vs its OWN price)
            print(f"\n  {label} — {split}")
            print(f"    {'edge >':>7s} {'bets':>6s} {'hit%':>7s} {'ROI':>8s}")
            for thr in THRESHOLDS:
                fair = df["ps_imp_a"].values
                bet_a = ((fair - imp_a) > thr) & np.isfinite(df[ca].values)
                bet_b = (((1 - fair) - imp_b) > thr) & np.isfinite(df[cb].values) & ~bet_a
                n = int(bet_a.sum() + bet_b.sum())
                if n == 0:
                    print(f"    {thr:>7.3f} {0:>6d}"); continue
                oa = np.nan_to_num(df[ca].values, nan=1.0); ob = np.nan_to_num(df[cb].values, nan=1.0)
                win_a, win_b = bet_a & (y == 1), bet_b & (y == 0)
                profit = float(((oa - 1) * win_a).sum()) - float((bet_a & (y == 0)).sum()) \
                       + float(((ob - 1) * win_b).sum()) - float((bet_b & (y == 1)).sum())
                thin = "" if n >= MIN_BETS_TO_TRUST else "  (thin)"
                print(f"    {thr:>7.3f} {n:>6,d} {(win_a.sum()+win_b.sum())/n:>7.1%} {profit/n:>+8.2%}{thin}")
    print("\n  Read: positive ROI here = a soft book was offering better than Pinnacle-fair on that side.")
    print("  This is the edge most 'sharp' bettors live on. Caveat: closing prices only; soft books limit winners.")

    # =====================================================================
    print("\n" + "=" * 90)
    print("AVENUE 1b — IS PINNACLE ITSELF MISCALIBRATED? (favourite-longshot bias)")
    print("=" * 90)
    clf = LogisticRegression(C=1e6, max_iter=5000).fit(tune[["ps_logit"]].values, y_tu)
    b, a = float(clf.coef_[0][0]), float(clf.intercept_[0])
    print(f"  Fitted on TUNE: P = logistic({a:+.3f} + {b:.3f} * logit(pinnacle_fair))   (b>1 = favourites under-priced, b<1 = over-priced)")
    p_recal_te = clf.predict_proba(test[["ps_logit"]].values)[:, 1]
    p_recal_tu = clf.predict_proba(tune[["ps_logit"]].values)[:, 1]
    print(f"  TEST log loss: Pinnacle raw {_ll(test['ps_imp_a'].values, y_te):.4f}   recalibrated {_ll(p_recal_te, y_te):.4f}")
    # calibration table by decile
    print("  Pinnacle calibration on TEST (fair prob bucket -> actual win rate):")
    conf = np.maximum(test["ps_imp_a"].values, 1 - test["ps_imp_a"].values)
    won_fav = np.where(test["ps_imp_a"].values >= 0.5, y_te == 1, y_te == 0)
    for lo, hi in [(0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 0.85), (0.85, 0.9), (0.9, 0.95), (0.95, 1.01)]:
        msk = (conf >= lo) & (conf < hi)
        if msk.sum():
            print(f"    fair {lo:.2f}-{min(hi,1):.2f}: {int(msk.sum()):>5d} matches, favourite won {won_fav[msk].mean():.1%} (book implied ~{conf[msk].mean():.1%})")
    best = sweep("Bet where RECALIBRATED disagrees with raw Pinnacle, paid at Pinnacle — TUNE", p_recal_tu, tune["ps_imp_a"].values, y_tu, tune["ps_a"].values, tune["ps_b"].values)
    thr1b = best[0] if best else 0.02
    sweep("... same on TEST (threshold fixed from TUNE)", p_recal_te, test["ps_imp_a"].values, y_te, test["ps_a"].values, test["ps_b"].values, chosen=thr1b)
    sweep("... TEST, paid at MAX price", p_recal_te, test["ps_imp_a"].values, y_te, test["max_a"].values, test["max_b"].values, chosen=thr1b)

    # =====================================================================
    print("\n" + "=" * 90)
    print("AVENUE 2 — BENTER COMBINATION: Pinnacle price as base, model inputs as correction")
    print("=" * 90)
    combos = [
        ("Pinnacle only (raw)", None),
        ("Pinnacle + ELO std", ["ps_logit", "gap_std"]),
        ("Pinnacle + all 5 ELO variants", ["ps_logit"] + [f"gap_{v}" for v in VARIANTS]),
        ("Pinnacle + all ELO + rank", ["ps_logit"] + [f"gap_{v}" for v in VARIANTS] + ["log_rank_ratio"]),
        ("Pinnacle + all ELO + rank + S5/S1/H2H", ["ps_logit"] + [f"gap_{v}" for v in VARIANTS] + ["log_rank_ratio", "s5_raw", "s1_raw", "h2h_raw"]),
        ("Pinnacle + engine_prob (current live number)", ["ps_logit", "engine_prob"]),
    ]
    ll_book = _ll(test["ps_imp_a"].values, y_te)
    results = []
    print(f"  {'candidate':46s} {'tune LL':>8s} | {'test acc':>8s} {'test LL':>8s} {'vs book':>8s} | {'thr':>6s} {'bets@PS':>7s} {'ROI@PS':>8s} {'bets@MAX':>8s} {'ROI@MAX':>8s}")
    for name, cols in combos:
        if cols is None:
            p_tu, p_te = tune["ps_imp_a"].values, test["ps_imp_a"].values
        else:
            Xtu, Xte = _feat(tune, cols), _feat(test, cols)
            clf = LogisticRegression(C=1.0, max_iter=5000).fit(Xtu, y_tu)
            p_tu, p_te = clf.predict_proba(Xtu)[:, 1], clf.predict_proba(Xte)[:, 1]
        # threshold chosen on TUNE at Pinnacle price
        best = None
        for thr in THRESHOLDS:
            n, hit, roi = bet_sim(p_tu, tune["ps_imp_a"].values, y_tu, tune["ps_a"].values, tune["ps_b"].values, thr)
            if n >= MIN_BETS_TO_TRUST and (best is None or roi > best[1]):
                best = (thr, roi)
        thr = best[0] if best else 0.03
        n1, h1, r1 = bet_sim(p_te, test["ps_imp_a"].values, y_te, test["ps_a"].values, test["ps_b"].values, thr)
        n2, h2, r2 = bet_sim(p_te, test["ps_imp_a"].values, y_te, test["max_a"].values, test["max_b"].values, thr)
        tll, tell = _ll(p_tu, y_tu), _ll(p_te, y_te)
        results.append((name, tll, _acc(p_te, y_te), tell, tell - ll_book, thr, n1, r1, n2, r2))
        print(f"  {name:46s} {tll:8.4f} | {_acc(p_te, y_te):8.1%} {tell:8.4f} {tell - ll_book:+8.4f} | {thr:6.3f} {n1:7,d} {r1 if n1 else float('nan'):+8.2%} {n2:8,d} {r2 if n2 else float('nan'):+8.2%}")

    print("\n" + "=" * 90)
    print("VERDICT")
    print("=" * 90)
    for name, tll, acc, tell, d, thr, n1, r1, n2, r2 in results:
        if d < -LEAK_LL_MARGIN:
            print(f"  *** ALARM: '{name}' beats Pinnacle by {-d:.4f} log loss -- too good. Treat as leak; do not trust.")
    real = [r for r in results if r[0] != "Pinnacle only (raw)" and -LEAK_LL_MARGIN <= r[4] < 0]
    if real:
        print("  Combinations that are CLOSER TO THE TRUTH than Pinnacle alone on TEST (small = plausible = the Benter effect):")
        for r in sorted(real, key=lambda r: r[3]):
            print(f"    {r[0]:46s} LL {r[3]:.4f} ({r[4]:+.4f} vs book)   ROI@Pinnacle {r[7]:+.2%} on {r[6]:,}   ROI@Max {r[9]:+.2%} on {r[8]:,}")
        print("  A real, bankable edge = one of these with ROI >= +2% at MAX on >= 200 bets (Pinnacle-price ROI will usually be ~0 or slightly negative -- that's the vig).")
    else:
        print("  No combination beats Pinnacle's own number on TEST. The model inputs add nothing on top of the market on main tour.")
        print("  Then the only moneyline edges left are Avenue 1 (soft-book prices) and timing/lower tiers (needs logged prices).")


if __name__ == "__main__":
    run()
