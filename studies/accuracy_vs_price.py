#!/usr/bin/env python3
"""
accuracy_vs_price.py  --  2026-08-16   Project Apex Intelligence (OpenClaw / DEMETRIUS)

The question: "What odds were attached to the matches where my system was 80% accurate?"
For every ENGINE confidence band (the engine's own pick, favourite or dog): how many picks, how often
the pick won, the average Pinnacle price on that pick, what that price IMPLIED, and flat-bet ROI.
If hit% ~= implied% in every band, then accuracy is exactly what the price charges for -- no profit
regardless of how high the band goes.

Reuses match_rows() from build_edge_backtest.py (2026-08-16 matcher). Reads walkforward_rows.csv +
odds/*.xls*.  No network.  Self-test on fake merged rows first.

Usage:
    python3 accuracy_vs_price.py --selftest
    python3 accuracy_vs_price.py                       # all matched years
    python3 accuracy_vs_price.py --years 2024,2025,2026
"""
import argparse, glob, os, sys, importlib
import numpy as np
import pandas as pd

BANDS = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 0.80),
         (0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.01)]


def load_odds_default(odds_dir="odds"):
    frames = []
    for fp in sorted(glob.glob(os.path.join(odds_dir, "*.xls*"))):
        try:
            d = pd.read_excel(fp)
        except Exception as e:
            print(f"  skip {os.path.basename(fp)}: {e}"); continue
        if not {"Date", "Winner", "Loser", "PSW", "PSL"}.issubset(d.columns):
            continue
        d["tour"] = "wta" if "wta" in os.path.basename(fp).lower() else "atp"
        frames.append(d)
    o = pd.concat(frames, ignore_index=True)
    o["Date"] = pd.to_datetime(o["Date"], errors="coerce")
    return o.dropna(subset=["Date"])


def find_col(df, *cands):
    low = {c.lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in low:
            return low[c.lower()]
    return None


def table(df):
    """df needs: engine_prob (P a wins), label_a_won, pinn_a (decimal price on a), pinn_b."""
    p = df["engine_prob"].to_numpy(float); ya = df["label_a_won"].to_numpy(float)
    pa = df["pinn_a"].to_numpy(float); pb = df["pinn_b"].to_numpy(float)
    pick_a = p >= 0.5
    conf = np.where(pick_a, p, 1 - p)
    price = np.where(pick_a, pa, pb)
    won = np.where(pick_a, ya == 1, ya == 0)
    fa, fb = 1 / pa, 1 / pb
    fair_pick = np.where(pick_a, fa, fb) / (fa + fb)          # de-vigged fair prob of the pick
    rows = []
    for lo, hi in BANDS:
        m = (conf >= lo) & (conf < hi)
        n = int(m.sum())
        if n == 0:
            rows.append((f"{lo:.2f}-{min(hi,1):.2f}", 0, np.nan, np.nan, np.nan, np.nan, np.nan)); continue
        hit = won[m].mean()
        avg_price = price[m].mean()
        implied = (1 / price[m]).mean()
        fair = fair_pick[m].mean()
        pnl = np.where(won[m], price[m] - 1, -1.0)
        roi = pnl.mean()
        rows.append((f"{lo:.2f}-{min(hi,1):.2f}", n, hit, avg_price, implied, fair, roi))
    return rows, dict(n=len(df), acc=float(won.mean()), roi=float(np.where(won, price - 1, -1.0).mean()))


def print_table(rows, tot, title):
    print("\n" + "=" * 92 + f"\n{title}\n" + "=" * 92)
    print(f"  {'engine conf':12s} {'picks':>7s} {'hit%':>7s} {'avg price':>10s} {'price says':>11s} {'Pinn fair':>10s} {'flat ROI':>9s}")
    for band, n, hit, ap, imp, fair, roi in rows:
        if n == 0:
            print(f"  {band:12s} {n:7d}      --"); continue
        print(f"  {band:12s} {n:7d} {hit:7.1%} {ap:10.3f} {imp:11.1%} {fair:10.1%} {roi:+9.1%}")
    print(f"  {'ALL':12s} {tot['n']:7d} {tot['acc']:7.1%}                                    {tot['roi']:+9.1%}")
    print("\n  Read: 'hit%' = how often the engine's pick won in that band.  'price says' = what Pinnacle's price on that"
          "\n  pick implied (includes vig).  'Pinn fair' = same, vig removed.  If hit% ~ price says, the accuracy was already"
          "\n  paid for.  Profit only exists where hit% is clearly ABOVE 'price says' -- and stays there on hundreds of picks.")




DOG_BANDS = [(0.20, 0.25), (0.25, 0.30), (0.30, 0.35), (0.35, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 1.01)]
DIS_BANDS = [(-1, -0.10), (-0.10, -0.05), (-0.05, -0.02), (-0.02, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1)]


def dog_tables(df):
    """Market underdog = side with the higher Pinnacle price. Engine prob for the DOG, actual dog win%,
    Pinnacle implied/fair for the dog, and ROI of betting the dog -- by engine dog-prob band, then by
    (engine dog prob - Pinnacle fair dog prob) disagreement band."""
    p = df["engine_prob"].to_numpy(float); ya = df["label_a_won"].to_numpy(float)
    pa = df["pinn_a"].to_numpy(float); pb = df["pinn_b"].to_numpy(float)
    dog_is_a = pa > pb
    p_dog = np.where(dog_is_a, p, 1 - p)
    price_dog = np.where(dog_is_a, pa, pb)
    won_dog = np.where(dog_is_a, ya == 1, ya == 0)
    fa, fb = 1 / pa, 1 / pb
    fair_dog = np.where(dog_is_a, fa, fb) / (fa + fb)
    imp_dog = 1 / price_dog
    pnl = np.where(won_dog, price_dog - 1, -1.0)

    def bucketed(key, bands, label):
        print("\n" + "=" * 92 + f"\n{label}\n" + "=" * 92)
        print(f"  {'band':14s} {'dogs':>7s} {'dog won%':>9s} {'engine avg':>11s} {'price says':>11s} {'Pinn fair':>10s} {'ROI bet dog':>12s}")
        for lo, hi in bands:
            m = (key >= lo) & (key < hi); n = int(m.sum())
            if n == 0: continue
            print(f"  {lo:+.2f}..{hi:+.2f}   {n:7d} {won_dog[m].mean():9.1%} {p_dog[m].mean():11.1%} {imp_dog[m].mean():11.1%} {fair_dog[m].mean():10.1%} {pnl[m].mean():+12.1%}")
        print(f"  {'ALL':14s} {len(df):7d} {won_dog.mean():9.1%} {p_dog.mean():11.1%} {imp_dog.mean():11.1%} {fair_dog.mean():10.1%} {pnl.mean():+12.1%}")

    bucketed(p_dog, DOG_BANDS, "UNDERDOGS: engine's probability for the market underdog vs what actually happened (all matches)")
    bucketed(p_dog - fair_dog, DIS_BANDS, "UNDERDOGS: DISAGREEMENT (engine dog prob minus Pinnacle fair dog prob). Positive = engine likes the dog MORE than the market")
    print("\n  Read: the holy-grail row is one where 'engine avg' > 'Pinn fair' AND 'dog won%' lands near 'engine avg', not near"
          "\n  'Pinn fair', on hundreds of dogs -- with 'ROI bet dog' clearly positive. If 'dog won%' tracks 'Pinn fair' even when"
          "\n  the engine says more, the engine's extra optimism was not information.")


def selftest():
    rng = np.random.default_rng(0)
    n = 4000
    truth = rng.uniform(0.5, 0.97, n)                    # true P(a wins)
    engine = np.clip(truth + rng.normal(0, 0.03, n), 0.01, 0.99)
    ya = (rng.random(n) < truth).astype(int)
    vig = 1.03
    pa = 1 / (truth * vig); pb = 1 / ((1 - truth) * vig)
    df = pd.DataFrame(dict(engine_prob=engine, label_a_won=ya, pinn_a=pa, pinn_b=pb))
    rows, tot = table(df)
    # calibrated market: hit% should track 'price says' and ROI ~ -vig in every populated band
    bad = [r for r in rows if r[1] > 200 and abs(r[2] - r[4]) > 0.06]
    assert not bad, bad
    assert -0.08 < tot["roi"] < 0.0, tot
    # now a market that UNDER-prices favourites: engine should show hit% > price says and ROI > 0 in high bands
    pa2 = 1 / (np.clip(truth - 0.08, 0.05, 0.95) * vig); pb2 = 1 / ((1 - np.clip(truth - 0.08, 0.05, 0.95)) * vig)
    rows2, tot2 = table(pd.DataFrame(dict(engine_prob=engine, label_a_won=ya, pinn_a=pa2, pinn_b=pb2)))
    hi = [r for r in rows2 if r[0] >= "0.80" and r[1] > 100]
    assert hi and all(r[6] > 0 for r in hi), hi
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        dog_tables(df)
    assert "UNDERDOGS" in buf.getvalue() and "ALL" in buf.getvalue()
    print("SELFTEST PASSED (4 checks): calibrated market -> hit ~ price, ROI ~ -vig; mispriced market -> positive ROI shows up")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rows", default="walkforward_rows.csv")
    ap.add_argument("--odds-dir", default="odds")
    ap.add_argument("--years", default="")
    a = ap.parse_args()
    if a.selftest: selftest(); return

    sys.path.insert(0, os.getcwd())
    beb = importlib.import_module("build_edge_backtest")
    rows = pd.read_csv(a.rows, low_memory=False)
    print(f"  walkforward rows: {len(rows):,}")
    # prefer the project's own odds loader if it has one
    loader = next((getattr(beb, n) for n in dir(beb) if n.lower().startswith(("load_odds", "read_odds", "load_all_odds"))), None)
    od = loader() if loader else load_odds_default(a.odds_dir)
    print(f"  odds rows: {len(od):,}   (loader: {loader.__name__ if loader else 'built-in tennis-data reader'})")
    merged = beb.match_rows(rows, od)
    print(f"  matched: {len(merged):,}")
    if a.years:
        ys = [int(y) for y in a.years.split(",")]
        ycol = find_col(merged, "year") or "match_date"
        merged = merged[pd.to_datetime(merged[ycol], errors="coerce").dt.year.isin(ys)] if ycol == "match_date" else merged[merged[ycol].isin(ys)]
        print(f"  after year filter {ys}: {len(merged):,}")

    # the project's matcher already orients Pinnacle prices to side a / side b (ps_a, ps_b)
    psa = find_col(merged, "ps_a", "pinn_a", "pinnacle_a"); psb = find_col(merged, "ps_b", "pinn_b", "pinnacle_b")
    if psa and psb:
        m = merged.dropna(subset=[psa, psb, "engine_prob", "label_a_won"]).copy()
        m = m[(m[psa] > 1) & (m[psb] > 1)]
        m["pinn_a"] = m[psa].astype(float); m["pinn_b"] = m[psb].astype(float)
    else:
        psw = find_col(merged, "PSW", "ps_w"); psl = find_col(merged, "PSL", "ps_l")
        if not psw or not psl:
            print("  could not find Pinnacle price columns in matched frame. Columns are:\n  ", list(merged.columns)); sys.exit(1)
        m = merged.dropna(subset=[psw, psl, "engine_prob", "label_a_won"]).copy()
        m = m[(m[psw] > 1) & (m[psl] > 1)]
        m["pinn_a"] = np.where(m["label_a_won"] == 1, m[psw], m[psl])
        m["pinn_b"] = np.where(m["label_a_won"] == 1, m[psl], m[psw])
    print(f"  rows with Pinnacle price: {len(m):,}")
    rows_t, tot = table(m)
    print_table(rows_t, tot, "ENGINE PICKS vs THE PRICE ATTACHED (Pinnacle close), by engine confidence band")
    # favourite-side only view (what 'accuracy' usually means to a bettor)
    fav = m[np.where(m["engine_prob"] >= 0.5, m["pinn_a"], m["pinn_b"]) < np.where(m["engine_prob"] >= 0.5, m["pinn_b"], m["pinn_a"])]
    rows_f, tot_f = table(fav)
    print_table(rows_f, tot_f, "same, FAVOURITE picks only (engine agrees with the market on who is favourite)")
    dog_tables(m)


if __name__ == "__main__":
    main()
