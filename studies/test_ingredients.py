"""
test_ingredients.py
2026-08-15 — judges the ingredient upgrades on the SAME scoreboard as
build_edge_backtest.py: the main-tour matches with a Pinnacle closing price,
tuned on 2022-2023, reported once on >= 2024.

Candidates (each turned into P(player_a wins)):
  engine        the current live engine's blended probability            (control)
  elo_std       current ELO alone (K=32 win/loss)                       (control #2)
  elo_welo      Weighted Elo (games-share margin of victory)
  elo_mov       set-margin ELO
  elo_surf      surface-blended ELO
  elo_dynk      dynamic-K ELO
  rank          official rank alone (log rank ratio, fitted on TUNE)
  best_elo+rank the best ELO variant (chosen on TUNE) + rank, fitted on TUNE
  full          best ELO + rank + S5 + S1 + H2H, fitted on TUNE

Everything fitted is fitted on TUNE years only. TEST is opened once. The
question for each: closer to Pinnacle than the current engine (accuracy,
log loss), and does the ROI vs Pinnacle stop being negative.

RULE 9: odds are the scoreboard, never an input. Rank is NOT market data.

USAGE (on the Mini, after build_walkforward_rows.py + build_elo_variants.py,
with ./odds/ populated):  python3 test_ingredients.py
"""
import os
import sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elo_calculator import expected_score
from build_edge_backtest import load_odds, match_rows, devig, simulate, THRESHOLDS, MIN_BETS_TO_TRUST, TUNE_YEARS, TEST_MIN_YEAR

ROWS_CSV = "walkforward_rows.csv"
ELO_CSV = "elo_variants.csv"
VARIANTS = ["std", "welo", "mov", "surf", "dynk"]


def _ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _acc(p, y):
    return float(((p > 0.5).astype(int) == y).mean())


def _roi_at(df, p, thr):
    d = df.assign(engine_prob=p)
    n, h, pr = simulate(d, thr, "ps_a", "ps_b", "ps_imp_a")
    return n, (h / n if n else float("nan")), (pr / n if n else float("nan"))


def _best_thr(df, p):
    best = None
    for thr in THRESHOLDS:
        n, _, roi = _roi_at(df, p, thr)
        if n >= MIN_BETS_TO_TRUST and (best is None or roi > best[1]):
            best = (thr, roi)
    return best[0] if best else 0.05


def _feat(df, cols):
    """Numeric matrix with NaN -> 0 plus a missing-indicator per column."""
    X = []
    for c in cols:
        v = pd.to_numeric(df[c], errors="coerce").values.astype(float)
        X.append(np.nan_to_num(v, nan=0.0))
        X.append(np.isnan(v).astype(float))
    return np.column_stack(X)


def run():
    for f in (ROWS_CSV, ELO_CSV):
        if not os.path.exists(f):
            print(f"ERROR: {f} missing."); return
    rows = pd.read_csv(ROWS_CSV)
    rows["year"] = rows["year"].astype(int)
    rows = rows[rows["year"] >= TUNE_YEARS[0]].copy()
    ev = pd.read_csv(ELO_CSV)
    ev = ev[pd.to_datetime(ev["match_date"], errors="coerce").dt.year >= TUNE_YEARS[0]]
    key = ["match_date", "player_a", "player_b"]
    # same pair on the same date twice cannot be joined unambiguously -- drop those keys on BOTH sides, never guess
    dup_r = rows.duplicated(key, keep=False); dup_e = ev.duplicated(key, keep=False)
    if dup_r.any() or dup_e.any():
        print(f"  Dropping ambiguous same-day repeat pairings: {int(dup_r.sum())} model rows, {int(dup_e.sum())} variant rows")
    rows = rows[~dup_r].copy(); ev = ev[~dup_e].copy()
    m = rows.merge(ev.drop(columns=["surface"]), on=key, how="left")
    print(f"Model rows {TUNE_YEARS[0]}+: {len(rows):,}; with ELO variants attached: {int(m['gap_std'].notna().sum()):,}")
    # sanity: the std variant must reproduce the live engine's own elo_gap
    both = m[m["elo_gap"].notna() & m["gap_std"].notna()]
    diff = float((both["elo_gap"] - both["gap_std"]).abs().max()) if len(both) else float("nan")
    print(f"  Control check: max |live elo_gap - rebuilt gap_std| = {diff:.4f}  (must be ~0)")
    if not (diff < 0.01):
        print("  *** The rebuilt standard ELO does NOT match the live one -- stop and investigate before trusting variants.")
        return

    print("\nLoading odds (scoreboard only)...")
    od = load_odds()
    if od is None:
        return
    mm = match_rows(m, od)
    mm = mm[~mm["comment"].str.contains("Retired|Walkover", case=False, na=False)].copy()
    mm["ps_imp_a"] = devig(mm["ps_a"].values, mm["ps_b"].values)
    mm = mm[mm["ps_imp_a"].notna()].copy()
    mm["log_rank_ratio"] = np.log(pd.to_numeric(mm["rank_b"], errors="coerce")) - np.log(pd.to_numeric(mm["rank_a"], errors="coerce"))
    for v in VARIANTS:
        g = pd.to_numeric(mm[f"gap_{v}"], errors="coerce")
        mm[f"p_{v}"] = [expected_score(1500 + x, 1500) if pd.notna(x) else np.nan for x in g]

    tune = mm[(mm["year"] >= TUNE_YEARS[0]) & (mm["year"] <= TUNE_YEARS[1])].copy()
    test = mm[mm["year"] >= TEST_MIN_YEAR].copy()
    y_tu, y_te = tune["label_a_won"].values.astype(int), test["label_a_won"].values.astype(int)
    print(f"\nTUNE {TUNE_YEARS[0]}-{TUNE_YEARS[1]}: {len(tune):,} matches with Pinnacle price   TEST >= {TEST_MIN_YEAR}: {len(test):,}")

    results = []   # (name, tune_ll, test_acc, test_ll, thr, n_bets, hit, roi)

    def score(name, p_tune, p_test):
        thr = _best_thr(tune, p_tune)
        n, hit, roi = _roi_at(test, p_test, thr)
        results.append((name, _ll(p_tune, y_tu), _acc(p_test, y_te), _ll(p_test, y_te), thr, n, hit, roi))

    # book itself
    score("PINNACLE (book itself)", tune["ps_imp_a"].values, test["ps_imp_a"].values)
    # current engine
    score("engine (current live)", tune["engine_prob"].values, test["engine_prob"].values)
    # ELO variants alone (rows lacking a variant fall back to 0.5 -- same as engine's honest 'no signal')
    for v in VARIANTS:
        score(f"elo_{v} alone", tune[f"p_{v}"].fillna(0.5).values, test[f"p_{v}"].fillna(0.5).values)
    # pick best ELO variant on TUNE by log loss (never on test)
    best_v = min(VARIANTS, key=lambda v: _ll(tune[f"p_{v}"].fillna(0.5).values, y_tu))
    print(f"\nBest ELO variant on TUNE (by log loss): {best_v}")

    # fitted combos (fit on TUNE only)
    def fit_eval(name, cols):
        Xtu, Xte = _feat(tune, cols), _feat(test, cols)
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(Xtu, y_tu)
        score(name, clf.predict_proba(Xtu)[:, 1], clf.predict_proba(Xte)[:, 1])
        return clf
    fit_eval("rank alone (fitted)", ["log_rank_ratio"])
    fit_eval(f"elo_std + rank (fitted)", ["gap_std", "log_rank_ratio"])
    fit_eval(f"elo_{best_v} + rank (fitted)", [f"gap_{best_v}", "log_rank_ratio"])
    fit_eval(f"elo_{best_v} + rank + S5/S1/H2H (fitted)", [f"gap_{best_v}", "log_rank_ratio", "s5_raw", "s1_raw", "h2h_raw"])
    fit_eval(f"ALL elo variants + rank + S5/S1/H2H (fitted)", [f"gap_{v}" for v in VARIANTS] + ["log_rank_ratio", "s5_raw", "s1_raw", "h2h_raw"])

    print("\n" + "=" * 100)
    print(f"RESULTS ON TEST YEARS >= {TEST_MIN_YEAR}  ({len(test):,} main-tour matches with a Pinnacle price)")
    print("=" * 100)
    print(f"  {'candidate':44s} {'tune LL':>8s} | {'test acc':>8s} {'test LL':>8s} | {'thr':>5s} {'bets':>6s} {'hit':>6s} {'ROI vs Pinnacle':>16s}")
    for name, tll, acc, ll, thr, n, hit, roi in results:
        print(f"  {name:44s} {tll:8.4f} | {acc:8.1%} {ll:8.4f} | {thr:5.2f} {n:6,d} {hit:6.1%} {roi:16.2%}")
    print("\n  Read it like this: lower log loss = closer to the truth. Anything above the engine row that also")
    print("  turns ROI positive (>= +2%) on >= 200 bets is a real ingredient. Anything that only moves accuracy")
    print("  a hair but leaves ROI negative is not worth shipping yet.")
    book = next(r for r in results if r[0].startswith("PINNACLE"))
    for r in results:
        if r[0].startswith("PINNACLE"):
            continue
        if r[2] > book[2] + 0.02 or r[3] < book[3] - 0.02:
            print(f"\n  *** ALARM: '{r[0]}' beats PINNACLE ITSELF by a wide margin (acc {r[2]:.1%} vs {book[2]:.1%}, LL {r[3]:.4f} vs {book[3]:.4f}).")
            print("  *** No pre-match model does that. Treat as a leak in that candidate's inputs. Do NOT ship it.")
    eng = next(r for r in results if r[0].startswith("engine"))
    improved = [r for r in results if r[0] not in ("PINNACLE (book itself)",) and not r[0].startswith("engine")
                and r[3] < eng[3] and r[5] >= MIN_BETS_TO_TRUST]
    print("\n  Candidates that beat the current engine on test log loss:")
    for r in sorted(improved, key=lambda r: r[3]):
        print(f"    {r[0]:44s} LL {r[3]:.4f} (engine {eng[3]:.4f})   ROI {r[7]:+.2%} on {r[5]:,} bets")
    if not improved:
        print("    none.")


if __name__ == "__main__":
    run()
