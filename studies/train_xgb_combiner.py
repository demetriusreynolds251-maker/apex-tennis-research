"""
train_xgb_combiner.py
2026-08-15 — Step 2 of the XGBoost combiner experiment.

QUESTION THIS ANSWERS (and nothing else): does a LEARNED way of combining
the four real signals (ELO/S5/S1/H2H) beat the current hand-weighted
engine on matches it has never seen -- at a believable number, on
information that existed before each match?

HOW IT STAYS HONEST:
  1. Rows come from build_walkforward_rows.py -- the verbatim walk-forward
     loop from the real 69.8% backtest. Every signal is "as of the morning
     of the match." (Leak defence #1: don't rebuild the row logic.)
  2. Split BY TIME, never randomly:
       TRAIN   <= 2021   (the model studies these)
       VALID   2022-2023 (only for tuning knobs / early stopping)
       TEST    >= 2024   (the locked drawer -- opened ONCE, at the end)
  3. Features are ONLY: elo_gap, s5_raw, s1_raw, h2h_raw (missing = NaN,
     XGBoost handles that natively) + n_signals_included. No odds, no
     market data (Rule 9). engine_prob is NOT a feature -- it is the
     opponent in the head-to-head.
  4. Head-to-head is on the SAME test rows: XGBoost's P(a wins) vs the
     current engine's P(a wins), same matches, same information.
  5. Leak alarms:
       - shuffled-label control: train on scrambled outcomes -> must fall
         to ~50%. If it stays high, the features contain the answer.
       - suspiciously-high alarm: published pre-match ceiling ~70-72%.
         Anything > 74% on the test set is treated as a bug, not a win.
       - big-jump warning: XGB beating the engine by >2 pts using the SAME
         four signals is implausible -- flagged for a rows re-check.
     Honest limit: the scrambled-label check catches "the answer is in the
     features"; it does NOT catch "future data leaked into a feature" (a
     full-career ELO passes it). The ceiling + big-jump alarms are the
     defence for that kind, plus never rewriting the walk-forward loop.

VERDICT RULE (agreed with user): XGBoost ships ONLY if it beats the
current engine head-to-head on the held-out matches by a real margin,
at a plausible number. Otherwise we keep what we have.

USAGE (on the Mini, after build_walkforward_rows.py):
    python3 train_xgb_combiner.py
"""
import os
import sys
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss
import xgboost as xgb

ROWS_CSV = "walkforward_rows.csv"
MODEL_OUT = "xgb_combiner.json"

TRAIN_MAX_YEAR = 2021
VALID_YEARS = (2022, 2023)
TEST_MIN_YEAR = 2024

FEATURES = ["elo_gap", "s5_raw", "s1_raw", "h2h_raw", "n_signals_included"]
SUSPICIOUS_ACC = 0.74      # above the published ~70-72% ceiling => investigate, don't celebrate
TOO_CLOSE_LOW, TOO_CLOSE_HIGH = 0.45, 0.55   # same "no call" band the live engine uses
MIN_WIN_MARGIN_PP = 0.5    # XGB must beat the engine by at least this many accuracy points to "win"
BIG_JUMP_PP = 2.0          # a bigger jump than this from re-combining the SAME signals is a warning sign


def _acc(p, y):
    return float(((p > 0.5).astype(int) == y).mean())


def _confident_mask(p):
    return (p < TOO_CLOSE_LOW) | (p > TOO_CLOSE_HIGH)


def _band_report(name, p, y):
    """Accuracy by confidence band, mirroring confidence_band_breakdown.py."""
    conf = np.maximum(p, 1 - p)
    correct = ((p > 0.5).astype(int) == y)
    bands = [(0.55, 0.65), (0.65, 0.75), (0.75, 0.85), (0.85, 0.95), (0.95, 1.01)]
    print(f"  {name} by band:")
    for lo, hi in bands:
        m = (conf >= lo) & (conf < hi)
        n = int(m.sum())
        if n == 0:
            print(f"    {lo:.0%}-{min(hi,1.0):.0%}: 0 matches")
        else:
            print(f"    {lo:.0%}-{min(hi,1.0):.0%}: {n:>7d} matches, {correct[m].mean():.1%} correct")


def _by_signal_count(name, p, y, n_sig):
    print(f"  {name} by number of signals available:")
    for k in sorted(np.unique(n_sig)):
        m = n_sig == k
        pm, ym = p[m], y[m]
        cm = _confident_mask(pm)
        if cm.sum() == 0:
            print(f"    {k} signal(s): {int(m.sum()):>7d} matches, no confident calls")
            continue
        print(f"    {k} signal(s): {int(m.sum()):>7d} matches, {int(cm.sum()):>7d} confident calls, {_acc(pm[cm], ym[cm]):.1%} correct")


def _fit(X_tr, y_tr, X_va, y_va, seed=42):
    model = xgb.XGBClassifier(
        n_estimators=3000,
        learning_rate=0.03,
        max_depth=4,
        min_child_weight=50,
        subsample=0.8,
        colsample_bytree=1.0,
        reg_lambda=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        early_stopping_rounds=100,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    return model


def run():
    if not os.path.exists(ROWS_CSV):
        print(f"ERROR: {ROWS_CSV} not found. Run build_walkforward_rows.py first.")
        return
    df = pd.read_csv(ROWS_CSV)
    df["year"] = df["year"].astype(int)
    for c in ("elo_gap", "s5_raw", "s1_raw", "h2h_raw", "engine_prob"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df["engine_prob"].notna()].reset_index(drop=True)

    train = df[df["year"] <= TRAIN_MAX_YEAR]
    valid = df[(df["year"] >= VALID_YEARS[0]) & (df["year"] <= VALID_YEARS[1])]
    test = df[df["year"] >= TEST_MIN_YEAR]

    print("=" * 72)
    print("DATA (split by TIME, never randomly)")
    print("=" * 72)
    print(f"  Total rows with >=1 real signal: {len(df):,}")
    print(f"  TRAIN  (<= {TRAIN_MAX_YEAR}):        {len(train):,}")
    print(f"  VALID  ({VALID_YEARS[0]}-{VALID_YEARS[1]}):        {len(valid):,}  (tuning/early-stop only)")
    print(f"  TEST   (>= {TEST_MIN_YEAR}):         {len(test):,}  (locked drawer, opened once below)")
    if len(train) < 10000 or len(valid) < 1000 or len(test) < 1000:
        print("\n  ERROR: a split is too small to trust. Check the year column / date format.")
        return

    X_tr, y_tr = train[FEATURES].values, train["label_a_won"].values.astype(int)
    X_va, y_va = valid[FEATURES].values, valid["label_a_won"].values.astype(int)
    X_te, y_te = test[FEATURES].values, test["label_a_won"].values.astype(int)
    p_eng_te = test["engine_prob"].values
    n_sig_te = test["n_signals_included"].values.astype(int)

    # ── 1. Train ──
    print("\n" + "=" * 72)
    print("TRAINING (on <= %d, early-stopped on %d-%d)" % (TRAIN_MAX_YEAR, *VALID_YEARS))
    print("=" * 72)
    model = _fit(X_tr, y_tr, X_va, y_va)
    print(f"  Trees used: {model.best_iteration + 1}")
    p_va = model.predict_proba(X_va)[:, 1]
    print(f"  Validation accuracy (all rows): {_acc(p_va, y_va):.1%}   AUC {roc_auc_score(y_va, p_va):.4f}")
    imp = model.get_booster().get_score(importance_type="gain")
    total_gain = sum(imp.values()) or 1.0
    print("  Feature importance (share of gain):")
    for i, f in enumerate(FEATURES):
        print(f"    {f:22s} {imp.get(f'f{i}', 0.0) / total_gain:.1%}")

    # ── 2. Leak alarm: shuffled labels must collapse to ~50% ──
    print("\n" + "=" * 72)
    print("LEAK CHECK #1 — train on SCRAMBLED outcomes (must land near 50%)")
    print("=" * 72)
    rng = np.random.default_rng(0)
    y_tr_shuf = rng.permutation(y_tr)
    y_va_shuf = rng.permutation(y_va)
    shuf_model = _fit(X_tr, y_tr_shuf, X_va, y_va_shuf, seed=1)
    p_shuf_te = shuf_model.predict_proba(X_te)[:, 1]
    # NOTE: plain accuracy at a 50% cutoff is the WRONG yardstick here -- a
    # model that learned nothing but leans 0.3% one way still "picks" a side.
    # What matters: does it ever become CONFIDENT, and is it any better than
    # a coin flip at log loss (coin flip = 0.6931)?
    shuf_conf_share = float(_confident_mask(p_shuf_te).mean())
    shuf_ll = log_loss(y_te, np.clip(p_shuf_te, 1e-6, 1-1e-6))
    print(f"  Scrambled-label model on TEST: {shuf_conf_share:.2%} confident calls, "
          f"log loss {shuf_ll:.4f} (coin flip = 0.6931), "
          f"predictions range {p_shuf_te.min():.3f}-{p_shuf_te.max():.3f}")
    leak_alarm = shuf_conf_share > 0.01 or shuf_ll < 0.685
    if leak_alarm:
        print("  *** ALARM: a model trained on nonsense became confident / beat a coin flip.")
        print("  *** The features may contain the answer. Do NOT trust anything below.")
    else:
        print("  OK -- nonsense in, flat coin-flip out. Features do not carry the answer directly.")

    # ── 3. Open the drawer ONCE ──
    print("\n" + "=" * 72)
    print(f"HEAD-TO-HEAD ON THE LOCKED TEST SET (>= {TEST_MIN_YEAR}) — same {len(test):,} real matches")
    print("=" * 72)
    p_xgb_te = model.predict_proba(X_te)[:, 1]

    xgb_acc_all, eng_acc_all = _acc(p_xgb_te, y_te), _acc(p_eng_te, y_te)
    xgb_auc, eng_auc = roc_auc_score(y_te, p_xgb_te), roc_auc_score(y_te, p_eng_te)
    xgb_ll, eng_ll = log_loss(y_te, np.clip(p_xgb_te, 1e-6, 1-1e-6)), log_loss(y_te, np.clip(p_eng_te, 1e-6, 1-1e-6))
    print(f"  {'':28s}{'XGBoost':>12s}{'Current engine':>18s}")
    print(f"  {'Accuracy (all rows)':28s}{xgb_acc_all:>12.1%}{eng_acc_all:>18.1%}")
    print(f"  {'AUC':28s}{xgb_auc:>12.4f}{eng_auc:>18.4f}")
    print(f"  {'Log loss (lower=better)':28s}{xgb_ll:>12.4f}{eng_ll:>18.4f}")

    # Confident calls, each on its OWN confident subset (what you'd actually bet)
    m_x, m_e = _confident_mask(p_xgb_te), _confident_mask(p_eng_te)
    xgb_acc_c, eng_acc_c = _acc(p_xgb_te[m_x], y_te[m_x]), _acc(p_eng_te[m_e], y_te[m_e])
    print(f"\n  Confident calls (outside {TOO_CLOSE_LOW:.0%}-{TOO_CLOSE_HIGH:.0%}), each model's own set:")
    print(f"    XGBoost:        {int(m_x.sum()):>7,} calls, {xgb_acc_c:.1%} correct")
    print(f"    Current engine: {int(m_e.sum()):>7,} calls, {eng_acc_c:.1%} correct")

    # Apples-to-apples: rows where the ENGINE is confident -- how does each do there?
    print(f"\n  Same {int(m_e.sum()):,} matches where the current engine makes a confident call:")
    print(f"    XGBoost accuracy on those:        {_acc(p_xgb_te[m_e], y_te[m_e]):.1%}")
    print(f"    Current engine accuracy on those: {eng_acc_c:.1%}")

    print()
    _band_report("XGBoost", p_xgb_te, y_te)
    _band_report("Current engine", p_eng_te, y_te)
    print()
    _by_signal_count("XGBoost", p_xgb_te, y_te, n_sig_te)
    _by_signal_count("Current engine", p_eng_te, y_te, n_sig_te)

    # ── 4. Alarms + verdict ──
    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    suspicious = xgb_acc_c > SUSPICIOUS_ACC or xgb_acc_all > SUSPICIOUS_ACC or leak_alarm
    if leak_alarm:
        print("  *** ALARM: scrambled-label leak check failed (see above).")
    if xgb_acc_c > SUSPICIOUS_ACC or xgb_acc_all > SUSPICIOUS_ACC:
        print(f"  *** ALARM: XGBoost accuracy above {SUSPICIOUS_ACC:.0%} -- that is ABOVE the published")
        print("  *** pre-match ceiling (~70-72%). Treat as a probable leak. Investigate before believing.")
    margin_pp = (xgb_acc_c - eng_acc_c) * 100
    auc_gain = xgb_auc - eng_auc
    print(f"  Confident-call accuracy: XGBoost {xgb_acc_c:.1%} vs engine {eng_acc_c:.1%}  (margin {margin_pp:+.2f} pts)")
    print(f"  AUC:                     XGBoost {xgb_auc:.4f} vs engine {eng_auc:.4f}  ({auc_gain:+.4f})")
    if margin_pp > BIG_JUMP_PP:
        print(f"  *** WARNING: a jump of {margin_pp:+.1f} pts from re-combining the SAME four signals is bigger")
        print(f"  *** than the literature suggests is possible. Not blocked, but re-check the rows before believing.")
    if suspicious:
        print("  => NO SHIP. Resolve the alarm first.")
    elif margin_pp >= MIN_WIN_MARGIN_PP and auc_gain > 0 and xgb_ll < eng_ll:
        print(f"  => XGBoost WINS on held-out matches (accuracy, AUC, and log loss all better).")
        print(f"     Model saved to {MODEL_OUT}. Next step: wire as the combiner behind a flag, verify on live transcripts.")
        model.save_model(MODEL_OUT)
    else:
        print("  => XGBoost does NOT clearly beat the current engine on held-out matches. KEEP the current engine.")
        print("     (Small/negative margin, or mixed metrics -- not worth the added complexity.)")


if __name__ == "__main__":
    run()
