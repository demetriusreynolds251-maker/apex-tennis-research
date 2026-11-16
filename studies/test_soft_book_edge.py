"""
test_soft_book_edge.py — 2026-08-16
The soft-book edge, judged on the ODDS FILES ALONE. No model, no warehouse,
no matcher. Reads every odds/*.xls* file present (2010-2026 once fetched).

THE BET (Avenue 1, unchanged): for each match, take Pinnacle's de-vigged
"fair" probability for each side. If the best listed price (Max) on a side
implies a probability at least THRESHOLD lower than Pinnacle-fair, bet 1 unit
on that side at the Max price. Both sides can qualify (rare; that is an
arbitrage between books) and both are then bet.

HOW IT STAYS HONEST
  - THRESHOLD = 0.02 was chosen on 2022-2023 (test_market_edges.py, 2026-08-15)
    and is FIXED here. 2010-2021 are brand-new held-out years for it, and
    2024+ was already the held-out block. Other thresholds are printed for
    context only -- do not re-pick on the years you report.
  - Retirements / walkovers excluded (settlement rules differ by book).
  - A row must carry BOTH a Pinnacle price and a Max price on the bet side.
  - Standard error of ROI is printed so "+4% on 900 bets" reads as "+4% +/- 4%".
  - Sanity alarms: ROI above +15% on 200+ bets, or a year whose Max is BELOW
    Pinnacle on the same side more than 5% of the time, is flagged as suspect
    data (stale / palpable-error lines) rather than celebrated.

CAVEATS THAT NO BACKTEST REMOVES: these are CLOSING prices; Max is the best of
several books, and you would have had to actually get that price at a book
that keeps taking your bets. Older years may have fewer books behind "Max".

OUTLIER CHECK (--sane, added 2026-08-16 after the first real run): drop any bet
whose Max price is more than SANE_RATIO x Pinnacle's price on that side, or
above SANE_MAX_ODDS. Prices like that are error / stale lines nobody actually
gets; if the edge only lives there, it is not bettable. Run both ways and
compare -- the plain run is the reference, --sane is the honest floor.

USAGE (from the project folder):
    python3 test_soft_book_edge.py --selftest      # fake data, must print ALL CHECKS PASSED
    python3 test_soft_book_edge.py                 # real run on ./odds/*.xls*
    python3 test_soft_book_edge.py --sane          # same, with error/stale lines excluded
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

THRESHOLD = 0.02                       # fixed on 2022-23 (2026-08-15); do NOT re-tune here
CONTEXT_THRESHOLDS = [0.00, 0.01, 0.02, 0.03, 0.04, 0.05]
MIN_BETS_TO_TRUST = 200
NEW_HELDOUT_YEARS = (2010, 2021)       # never seen by any script before 2026-08-16
TUNE_YEARS = (2022, 2023)
TEST_MIN_YEAR = 2024
ALARM_ROI = 0.15
ALARM_MAX_BELOW_PS = 0.05
SANE = False                           # set by --sane
SANE_RATIO = 1.25                      # Max may be at most 25% better than Pinnacle's own price
SANE_MAX_ODDS = 10.0                   # and never above 10.0
MAX_YEAR = 2026                        # one WTA row is dated 2029 (file typo) -- dropped


# --------------------------------------------------------------- loading ----
def load_odds_files():
    files = sorted(glob.glob(os.path.join("odds", "*.xls*")))
    if not files:
        print("ERROR: no files in ./odds/. Run fetch_odds_history.sh first.")
        return None
    frames = []
    for f in files:
        tour = "wta" if os.path.basename(f).lower().startswith("wta") else "atp"
        try:
            df = pd.read_excel(f)
        except ImportError as e:
            print(f"  CANNOT READ {os.path.basename(f)}: {e}\n  -> pip3 install --user xlrd   (needed for .xls files)")
            continue
        except Exception as e:
            print(f"  skip {os.path.basename(f)}: {e}")
            continue
        df.columns = [str(c).strip() for c in df.columns]
        df["tour"] = tour
        df["_file"] = os.path.basename(f)
        frames.append(df)
        print(f"  loaded {os.path.basename(f)}: {len(df):,} rows")
    if not frames:
        return None
    od = pd.concat(frames, ignore_index=True)
    return prep(od)


def prep(od: pd.DataFrame) -> pd.DataFrame:
    """Normalise columns; works for the fake-data self-test too."""
    od = od.copy()
    od["Date"] = pd.to_datetime(od["Date"], errors="coerce")
    for c in ("PSW", "PSL", "MaxW", "MaxL", "AvgW", "AvgL"):
        od[c] = pd.to_numeric(od[c], errors="coerce") if c in od.columns else np.nan
    od["Comment"] = od["Comment"].astype(str) if "Comment" in od.columns else "Completed"
    if "tour" not in od.columns:
        od["tour"] = "atp"
    od = od[od["Date"].notna()].copy()
    od["year"] = od["Date"].dt.year.astype(int)
    od = od[od["year"] <= MAX_YEAR].copy()
    od["ret_wo"] = od["Comment"].str.contains("Retired|Walkover|Disqualified", case=False, na=False)
    # Pinnacle fair prob of the WINNER side (vig removed); loser side = 1 - that
    with np.errstate(divide="ignore", invalid="ignore"):
        iw, il = 1.0 / od["PSW"], 1.0 / od["PSL"]
        od["ps_fair_w"] = iw / (iw + il)
        od["imp_max_w"] = 1.0 / od["MaxW"]
        od["imp_max_l"] = 1.0 / od["MaxL"]
    od["edge_w"] = od["ps_fair_w"] - od["imp_max_w"]           # >0: soft book too generous on the winner
    od["edge_l"] = (1.0 - od["ps_fair_w"]) - od["imp_max_l"]   # >0: soft book too generous on the loser
    # sanity masks per side (used only when --sane): price must be gettable, not a freak line
    od["sane_w"] = (od["MaxW"] <= SANE_RATIO * od["PSW"]) & (od["MaxW"] <= SANE_MAX_ODDS)
    od["sane_l"] = (od["MaxL"] <= SANE_RATIO * od["PSL"]) & (od["MaxL"] <= SANE_MAX_ODDS)
    return od


def side_masks(df: pd.DataFrame):
    """(winner-side ok, loser-side ok) base masks: completed match, Pinnacle price, Max present, [sane]."""
    ok = ~df["ret_wo"] & df["ps_fair_w"].notna()
    w = ok & df["MaxW"].notna()
    l = ok & df["MaxL"].notna()
    if SANE:
        w = w & df["sane_w"].fillna(False)
        l = l & df["sane_l"].fillna(False)
    return w, l


# --------------------------------------------------------------- betting ----
def bets_at(df: pd.DataFrame, thr: float) -> np.ndarray:
    """Per-bet profit array (1u flat) for all qualifying bets in df at threshold thr.
    Winner-side bets pay MaxW-1; loser-side bets lose 1. Both sides may qualify."""
    w_ok, l_ok = side_masks(df)
    bw = w_ok & (df["edge_w"] > thr)
    bl = l_ok & (df["edge_l"] > thr)
    prof_w = (df.loc[bw, "MaxW"].values - 1.0)
    prof_l = -np.ones(int(bl.sum()))
    return np.concatenate([prof_w, prof_l])


def summarise(prof: np.ndarray):
    n = len(prof)
    if n == 0:
        return 0, float("nan"), float("nan"), float("nan")
    roi = prof.mean()
    se = prof.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    hit = float((prof > 0).mean())
    return n, roi, se, hit


def line(label, prof, alarm=True):
    n, roi, se, hit = summarise(prof)
    thin = "" if n >= MIN_BETS_TO_TRUST else "  (thin)"
    flag = ""
    if alarm and n >= MIN_BETS_TO_TRUST and roi > ALARM_ROI:
        flag = "  <-- ALARM: too good; suspect stale/error lines, check before believing"
    if n:
        print(f"    {label:28s} {n:>6,d} bets  {hit:>6.1%} hit  ROI {roi:>+7.2%}  +/-{se:.1%}{thin}{flag}")
    else:
        print(f"    {label:28s} {n:>6,d} bets")


def block(title, df):
    print(f"\n  {title}")
    for thr in CONTEXT_THRESHOLDS:
        tag = "  <== FIXED threshold" if abs(thr - THRESHOLD) < 1e-9 else ""
        line(f"edge > {thr:.2f}{tag}", bets_at(df, thr))


def per_year_table(od: pd.DataFrame):
    print("\n  Per-year coverage and result at the FIXED threshold:")
    print(f"    {'year':>4s} {'tour':>4s} {'rows':>6s} {'w/ PS':>6s} {'w/ Max':>6s} {'Max<PS%':>7s} {'bets':>6s} {'hit%':>6s} {'ROI':>8s} {'+/-':>6s}")
    for (y, t), g in od.groupby(["year", "tour"]):
        has_ps = g["ps_fair_w"].notna()
        has_max = g["MaxW"].notna() & g["MaxL"].notna()
        both = has_ps & has_max
        below = float(((g.loc[both, "MaxW"] < g.loc[both, "PSW"]) | (g.loc[both, "MaxL"] < g.loc[both, "PSL"])).mean()) if both.any() else float("nan")
        n, roi, se, hit = summarise(bets_at(g, THRESHOLD))
        warn = "  <-- Max below Pinnacle too often: fewer books / odd data this year" if below == below and below > ALARM_MAX_BELOW_PS else ""
        print(f"    {y:>4d} {t:>4s} {len(g):>6,d} {int(has_ps.sum()):>6,d} {int(has_max.sum()):>6,d} {below:>7.1%} {n:>6,d} {hit:>6.1%} {roi:>+8.2%} {se:>6.1%}{warn}")


def by_bucket(df: pd.DataFrame):
    """Does the edge get BETTER as the gap gets bigger? (it should, if it's real)"""
    print("\n  By size of the gap (edge bucket, all qualifying bets, both sides):")
    edges = [(0.02, 0.03), (0.03, 0.04), (0.04, 0.06), (0.06, 0.10), (0.10, 9)]
    for lo, hi in edges:
        w_ok, l_ok = side_masks(df)
        bw = w_ok & (df["edge_w"] > lo) & (df["edge_w"] <= hi)
        bl = l_ok & (df["edge_l"] > lo) & (df["edge_l"] <= hi)
        prof = np.concatenate([df.loc[bw, "MaxW"].values - 1.0, -np.ones(int(bl.sum()))])
        line(f"gap {lo:.2f}-{hi if hi < 9 else '..':>4}", prof, alarm=False)


def by_side_and_tour(df: pd.DataFrame):
    print("\n  Favourite vs underdog (which side the soft book was generous on):")
    w_ok, l_ok = side_masks(df)
    fav_w = df["ps_fair_w"] >= 0.5
    for label, mask_w, mask_l in (("backing the FAVOURITE", fav_w, ~fav_w), ("backing the UNDERDOG", ~fav_w, fav_w)):
        bw = w_ok & mask_w & (df["edge_w"] > THRESHOLD)
        bl = l_ok & mask_l & (df["edge_l"] > THRESHOLD)
        prof = np.concatenate([df.loc[bw, "MaxW"].values - 1.0, -np.ones(int(bl.sum()))])
        line(label, prof, alarm=False)
    print("\n  By tour:")
    for t, g in df.groupby("tour"):
        line(t.upper(), bets_at(g, THRESHOLD), alarm=False)


# ------------------------------------------------------------------ run ----
def run():
    global SANE
    print("=" * 78)
    print("SOFT-BOOK PRICE vs PINNACLE FAIR — odds files only, no model" + ("   [--sane: freak lines excluded]" if SANE else ""))
    print("=" * 78)
    od = load_odds_files()
    if od is None:
        return
    if SANE:
        # how many qualifying bets does the sanity rule remove?
        SANE = False
        n_plain = len(bets_at(od, THRESHOLD))
        SANE = True
        n_sane = len(bets_at(od, THRESHOLD))
        print(f"\n  --sane rule: Max <= {SANE_RATIO:.2f} x Pinnacle price and Max <= {SANE_MAX_ODDS:.0f}. "
              f"At the fixed threshold this removes {n_plain - n_sane:,} of {n_plain:,} bets ({(n_plain - n_sane) / max(n_plain, 1):.1%}).")
    print(f"\n  Total rows: {len(od):,}   years {od['year'].min()}-{od['year'].max()}   "
          f"ret/wo excluded: {int(od['ret_wo'].sum()):,}")
    per_year_table(od)

    new = od[(od["year"] >= NEW_HELDOUT_YEARS[0]) & (od["year"] <= NEW_HELDOUT_YEARS[1])]
    tune = od[(od["year"] >= TUNE_YEARS[0]) & (od["year"] <= TUNE_YEARS[1])]
    test = od[od["year"] >= TEST_MIN_YEAR]

    print("\n" + "=" * 78)
    print(f"THE JUDGEMENT: {NEW_HELDOUT_YEARS[0]}-{NEW_HELDOUT_YEARS[1]} at the FIXED threshold {THRESHOLD:.2f} (never seen before today)")
    print("=" * 78)
    block(f"NEW held-out {NEW_HELDOUT_YEARS[0]}-{NEW_HELDOUT_YEARS[1]}", new)
    by_bucket(new)
    by_side_and_tour(new)

    print("\n" + "=" * 78)
    print("FOR REFERENCE (already seen): the years the threshold came from, and the 2024+ block")
    print("=" * 78)
    block(f"TUNE {TUNE_YEARS[0]}-{TUNE_YEARS[1]} (threshold was picked here)", tune)
    block(f"TEST {TEST_MIN_YEAR}+ (opened 2026-08-15)", test)

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    n, roi, se, hit = summarise(bets_at(new, THRESHOLD))
    n2, roi2, se2, _ = summarise(bets_at(pd.concat([new, test]), THRESHOLD))
    if n < MIN_BETS_TO_TRUST:
        print(f"  Only {n} bets in {NEW_HELDOUT_YEARS[0]}-{NEW_HELDOUT_YEARS[1]} -- the old files may lack Pinnacle/Max prices. See the per-year table.")
        return
    print(f"  {NEW_HELDOUT_YEARS[0]}-{NEW_HELDOUT_YEARS[1]}, gap > {THRESHOLD:.2f}, paid at Max: {n:,} bets, ROI {roi:+.2%} +/- {se:.1%} (1 SE), hit {hit:.1%}")
    print(f"  All held-out years together ({NEW_HELDOUT_YEARS[0]}-{NEW_HELDOUT_YEARS[1]} + {TEST_MIN_YEAR}+): {n2:,} bets, ROI {roi2:+.2%} +/- {se2:.1%}")
    if roi > ALARM_ROI:
        print("  ALARM: this is too good to be a normal soft-book edge. Check the per-year table for suspect years before believing it.")
    elif roi - 2 * se > 0 and roi >= 0.03:
        print("  Positive by more than 2 standard errors on years never used to choose anything: a REAL closing-line edge.")
        print("  Remember what it is NOT proof of: that you can get the Max price before it moves, or keep an account that lets you.")
    elif roi > 0:
        print("  Positive but within ~2 standard errors: consistent with an edge, not proof of one. Read the bucket table: real edges grow with the gap.")
    else:
        print("  Not positive on the new years. The 2022-2026 result was most likely a small-sample bounce. Time to stop chasing this one.")


# ------------------------------------------------------------- selftest ----
def selftest():
    """Fake data with KNOWN answers. No real files touched."""
    fails = []

    def check(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            fails.append(msg)

    # PSW/PSL 1.90/1.90 -> Pinnacle fair 0.50 each side.
    rows = [
        # Date,        PSW,  PSL,  MaxW, MaxL, Comment       -> what should happen at thr 0.02
        ("2015-01-05", 1.90, 1.90, 2.20, 1.95, "Completed"),   # winner side: imp .4545, edge .0455 -> bet W, profit +1.20
        ("2015-01-05", 1.90, 1.90, 1.95, 2.20, "Completed"),   # loser side edge .0455 -> bet L, profit -1
        ("2015-01-05", 1.90, 1.90, 2.05, 2.05, "Completed"),   # imp .4878, edge .0122 -> below .02, no bet either side
        ("2015-01-05", 1.90, 1.90, 2.20, 2.20, "Completed"),   # BOTH sides edge .0455 -> 2 bets: +1.20 and -1
        ("2015-01-05", 1.90, 1.90, 2.20, 1.95, "Retired"),     # would qualify but retired -> excluded
        ("2015-01-05", np.nan, np.nan, 2.20, 1.95, "Completed"),  # no Pinnacle price -> excluded
        ("2015-01-05", 1.90, 1.90, np.nan, 2.20, "Completed"),  # Max missing on W; L side qualifies -> bet L, -1
    ]
    od = pd.DataFrame(rows, columns=["Date", "PSW", "PSL", "MaxW", "MaxL", "Comment"])
    od = prep(od)
    prof = bets_at(od, THRESHOLD)
    exp = sorted([1.20, -1.0, 1.20, -1.0, -1.0])
    check(sorted(np.round(prof, 6).tolist()) == exp, f"bets & profits at thr .02 = {exp} (got {sorted(np.round(prof, 4).tolist())})")
    n, roi, se, hit = summarise(prof)
    check(n == 5 and abs(roi - (sum(exp) / 5)) < 1e-9, f"n=5, ROI = {sum(exp)/5:+.2%} (got n={n}, {roi:+.2%})")
    check(abs(hit - 0.4) < 1e-9, "hit rate 40% (2 of 5)")
    check(len(bets_at(od, 0.05)) == 0, "at thr .05 nothing qualifies (all edges .0455)")
    check(len(bets_at(od, 0.00)) == 7, "at thr .00 the .0122 row qualifies on BOTH sides -> 7 bets")
    # devig sanity on an unequal price
    od2 = prep(pd.DataFrame([("2015-01-05", 1.50, 2.80, 1.55, 2.90, "Completed")], columns=["Date", "PSW", "PSL", "MaxW", "MaxL", "Comment"]))
    fair = od2["ps_fair_w"].iloc[0]
    check(abs(fair - (1/1.5) / (1/1.5 + 1/2.8)) < 1e-12 and 0.65 < fair < 0.66, f"de-vig: PSW 1.50 / PSL 2.80 -> fair {fair:.4f} (~0.651)")
    # --sane: freak lines excluded, ordinary ones kept
    global SANE
    od3 = prep(pd.DataFrame([
        ("2015-01-05", 1.90, 1.90, 2.20, 1.95, "Completed"),   # 2.20 <= 1.25*1.90=2.375 -> kept, +1.20
        ("2015-01-05", 1.90, 1.90, 2.50, 1.95, "Completed"),   # 2.50 > 2.375 -> freak, dropped
        ("2015-01-05", 8.00, 1.08, 12.0, 1.10, "Completed"),   # 12.0 > 10 -> dropped even though ratio ok? 12/8=1.5 also >1.25 -> dropped
        ("2015-01-05", 9.00, 1.05, 9.90, 1.06, "Completed"),   # 9.90 <= 10 and 9.9/9=1.1 -> kept, edge? fair_w=(1/9)/(1/9+1/1.05)=.1045; imp .101 -> edge .0035 <.02 no bet
        ("2015-01-05", 1.90, 1.90, 1.95, 2.60, "Completed"),   # loser side 2.60 > 2.375 -> dropped
        ("2015-01-05", 1.90, 1.90, 1.95, 2.30, "Completed"),   # loser side 2.30 ok -> bet L, -1
    ], columns=["Date", "PSW", "PSL", "MaxW", "MaxL", "Comment"]))
    saved = SANE
    SANE = False
    plain = sorted(np.round(bets_at(od3, THRESHOLD), 4).tolist())
    SANE = True
    sane = sorted(np.round(bets_at(od3, THRESHOLD), 4).tolist())
    SANE = saved
    check(plain == sorted([1.2, 1.5, 11.0, -1.0, -1.0]), f"plain mode: 5 bets incl. the freak +1.5 and +11.0 payouts (got {plain})")
    check(sane == sorted([1.2, -1.0]), f"--sane: freak lines dropped, ordinary kept -> [+1.2, -1.0] (got {sane})")
    od4 = prep(pd.DataFrame([("2029-01-05", 1.90, 1.90, 2.20, 1.95, "Completed"), ("2015-01-05", 1.90, 1.90, 2.20, 1.95, "Completed")],
                            columns=["Date", "PSW", "PSL", "MaxW", "MaxL", "Comment"]))
    check(len(od4) == 1 and int(od4["year"].iloc[0]) == 2015, "typo year 2029 dropped, 2015 kept")
    print()
    if fails:
        print(f"{len(fails)} FAILURE(S)")
        sys.exit(1)
    print("ALL CHECKS PASSED.")


if __name__ == "__main__":
    if "--sane" in sys.argv:
        SANE = True
    if "--selftest" in sys.argv:
        selftest()
    else:
        run()
