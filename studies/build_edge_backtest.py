"""
build_edge_backtest.py
2026-08-15 — "Would this have made money?" test. Model probability vs the
bookmaker's closing price, on matches the model never studied.

RULE 9 STATUS: unchanged. Odds are NEVER an input to any pick here. They are
used ONLY as the report card after the model has spoken (user-approved
2026-08-15, scoreboard use only).

INPUTS
  walkforward_rows.csv         from build_walkforward_rows.py (engine_prob =
                               the current engine's P(player_a wins), built
                               from pre-match signals only)
  odds/*.xlsx                  tennis-data.co.uk yearly files (ATP + WTA).
                               Columns used: Date, Winner, Loser, Surface,
                               Series/Tier, Best of, WRank, LRank, PSW, PSL,
                               AvgW, AvgL, MaxW, MaxL, Comment.

HOW IT STAYS HONEST
  - TUNE years (2022-2023) pick the edge threshold. TEST years (>= 2024) are
    opened once and reported as-is. Never tune on the years you report.
  - The odds row must be the SAME match (both names + date in the tournament
    window). Dataset B `match_date` is the TOURNAMENT START date (Sackmann
    format, confirmed 2026-08-16: R128..F of a Slam all carry one date), while
    tennis-data carries the real match day. So the odds row may fall anywhere
    from match_date - 1 day through match_date + 16 days. Exactly ONE odds row
    with both names in that window is required; zero or several -> dropped,
    never guessed. (2026-08-16 matcher fix; the old +/-1-day rule only ever
    caught first-round matches and silently dropped most elite-player rows.)
  - Vig is removed from the book's price before comparing (both sides
    normalised to sum to 1) so "edge" means real disagreement, not the
    book's margin.
  - Payout is computed at the REAL price on that side (Pinnacle = sharp
    baseline; Max = what line shopping would have got you).
  - Retirements/walkovers are excluded (bet settlement rules differ).

OUTPUT: ROI (profit per unit staked) and hit rate, at each edge threshold,
overall and by segment (tour, surface, best-of, favourite vs underdog, model
band, signal count, series/tier). Plain verdict at the end.

USAGE (on the Mini):
    mkdir -p odds && cd odds
    for y in 2022 2023 2024 2025 2026; do
      curl -sSLo atp_$y.xlsx  http://www.tennis-data.co.uk/$y/$y.xlsx
      curl -sSLo wta_$y.xlsx  http://www.tennis-data.co.uk/${y}w/$y.xlsx
    done
    cd .. && python3 build_edge_backtest.py
"""
import os
import re
import sys
import glob
import unicodedata
import numpy as np
import pandas as pd

ROWS_CSV = "walkforward_rows.csv"
ODDS_DIR = "odds"
TUNE_YEARS = (2022, 2023)
TEST_MIN_YEAR = 2024
THRESHOLDS = [0.00, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15]
MIN_BETS_TO_TRUST = 200
# 2026-08-16 matcher fix: Dataset B match_date = tournament start; odds Date = real match day.
MATCH_WINDOW_BACK_DAYS = 1    # tolerance if a row DOES carry a real date (timezone / next-day finish)
MATCH_WINDOW_FWD_DAYS = 16    # covers a 2-week Slam; next event for the same pair is usually further out


# ---------------------------------------------------------------- names ----
from functools import lru_cache


@lru_cache(maxsize=None)
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace("-", " ").replace("'", "")
    return re.sub(r"\s+", " ", s).strip()


def parse_td_name(name: str):
    """tennis-data style 'Djokovic N.' / 'De Minaur A.' / 'Carreno Busta P.'
    -> (surname_tokens_tuple, first_initial). Initials are the tokens ending
    in '.'; surname is everything else."""
    toks = _norm(name).replace(".", ". ").split()
    initials = [t.rstrip(".") for t in toks if t.endswith(".")]
    surname = tuple(t for t in toks if not t.endswith("."))
    return surname, (initials[0][:1] if initials else "")


def db_name_matches(db_name: str, td_surname: tuple, td_initial: str) -> bool:
    """Dataset B stores full names ('Novak Djokovic', 'Alex De Minaur').
    tennis-data stores 'Djokovic N.' / 'De Minaur A.' -> (surname tokens, initial).

    2026-08-16 name fix (real misses seen after the matcher fix, ~450 rows):
      * extra surname parts on EITHER side:
          'Osorio M.'          <-> 'Maria Camila Osorio Serrano'
          'Mpetshi G.'         <-> 'Giovanni Mpetshi Perricard'
          'Riske A.'           <-> 'Alison Riske Amritraj'
          'Merida Aguilar D.'  <-> 'Daniel Merida'
      * apostrophes: 'O Connell C.' <-> "Christopher O'Connell" (compared with
        spaces removed, so 'o'+'connell' == 'oconnell')
      * the initial may match ANY given name before the surname
        ('Osorio M.' <-> 'Maria Camila Osorio Serrano', M = Maria)
    Rules kept ON PURPOSE (sibling guard): the surname must NOT start at the DB
    name's first token ('Martin A.' must not match 'Martin Damm'), and the
    initial must match some given name ('Zverev A.' must not match 'Mischa
    Zverev'; 'Cerundolo F.' must not match 'Juan Manuel Cerundolo').
    """
    toks = _norm(db_name).split()
    if len(toks) < 2 or not td_surname:
        return False
    td_join = "".join(td_surname)
    sur_start = None
    # (a) td surname (joined) equals some run of DB tokens (joined) starting at index >= 1
    for i in range(1, len(toks)):
        acc = ""
        for j in range(i, len(toks)):
            acc += toks[j]
            if acc == td_join:
                sur_start = i
                break
            if len(acc) >= len(td_join):
                break
        if sur_start is not None:
            break
    # (b) td has MORE surname tokens than DB ('Merida Aguilar D.' vs 'Daniel Merida'):
    #     DB's last token equals td's FIRST surname token; only when td has >= 2 tokens
    if sur_start is None and len(td_surname) >= 2 and toks[-1] == td_surname[0]:
        sur_start = len(toks) - 1
    if sur_start is None:
        return False
    if td_initial and not any(t.startswith(td_initial) for t in toks[:sur_start]):
        return False
    return True


# ---------------------------------------------------------------- odds ----
def load_odds():
    files = sorted(glob.glob(os.path.join(ODDS_DIR, "*.xls*")))
    if not files:
        print(f"ERROR: no odds files in ./{ODDS_DIR}/ -- see USAGE in the docstring.")
        return None
    frames = []
    for f in files:
        tour = "wta" if os.path.basename(f).lower().startswith("wta") else "atp"
        try:
            df = pd.read_excel(f)
        except Exception as e:
            print(f"  skip {f}: {e}")
            continue
        df["tour"] = tour
        df["_file"] = os.path.basename(f)
        frames.append(df)
        print(f"  loaded {os.path.basename(f)}: {len(df):,} rows")
    if not frames:
        return None
    od = pd.concat(frames, ignore_index=True)
    od.columns = [str(c).strip() for c in od.columns]
    od["Date"] = pd.to_datetime(od["Date"], errors="coerce")
    for c in ("PSW", "PSL", "AvgW", "AvgL", "MaxW", "MaxL", "WRank", "LRank", "Best of"):
        if c in od.columns:
            od[c] = pd.to_numeric(od[c], errors="coerce")
        else:
            od[c] = np.nan
    if "Series" not in od.columns:
        od["Series"] = np.nan
    if "Tier" not in od.columns:
        od["Tier"] = np.nan
    od["level"] = od["Series"].where(od["Series"].notna(), od["Tier"]).astype(str)
    od["Comment"] = od.get("Comment", pd.Series([""] * len(od))).astype(str)
    od = od[od["Date"].notna() & od["Winner"].notna() & od["Loser"].notna()].copy()
    od["w_sur"], od["w_ini"] = zip(*od["Winner"].map(parse_td_name))
    od["l_sur"], od["l_ini"] = zip(*od["Loser"].map(parse_td_name))
    return od


def match_rows(rows: pd.DataFrame, od: pd.DataFrame) -> pd.DataFrame:
    """Join model rows to odds rows on (tournament date window, both names).

    2026-08-16 matcher fix. For each model row, candidate odds rows are those
    dated from match_date - MATCH_WINDOW_BACK_DAYS through
    match_date + MATCH_WINDOW_FWD_DAYS whose Winner/Loser names both match the
    row's two players. Exactly one candidate -> matched. Zero -> unmatched.
    Two or more (same pair met twice inside the window) -> ambiguous; dropped,
    never guessed. The winner-agreement cross-check at the end is unchanged.

    Candidates are found through a surname index (not by scanning every odds
    row per model row) so the wider window stays fast on 60K rows.
    """
    # --- fast lookup structures (plain python lists; no per-candidate .iloc) ---
    od_day = (od["Date"].dt.normalize().values.astype("datetime64[D]").astype("int64"))
    w_sur, w_ini = list(od["w_sur"]), list(od["w_ini"])
    l_sur, l_ini = list(od["l_sur"]), list(od["l_ini"])
    # Index each odds row under every surname token AND the joined surname, so
    # the relaxed name rule (extra parts / apostrophes) still finds its candidates.
    by_sur = {}
    for i in range(len(od)):
        for sur in (w_sur[i], l_sur[i]):
            for t in sur:
                by_sur.setdefault(t, []).append(i)
            by_sur.setdefault("".join(sur), []).append(i)
    # each bucket sorted by day so the date window is a bisect, not a scan
    import bisect
    for k, lst in by_sur.items():
        lst.sort(key=lambda i: od_day[i])
    by_sur_days = {k: [int(od_day[i]) for i in lst] for k, lst in by_sur.items()}

    def surname_keys(db_name):
        """Lookup keys for a DB full name: every token after the first, plus every
        joined run of tokens starting after the first ('oconnell', 'riskeamritraj')."""
        toks = _norm(db_name).split()
        keys = set()
        for i in range(1, len(toks)):
            acc = ""
            for j in range(i, len(toks)):
                acc += toks[j]
                keys.add(acc)
        return keys

    out = []
    unmatched = 0
    ambiguous = 0
    day_gaps = []
    for r in rows.itertuples(index=False):
        d0 = pd.Timestamp(r.match_date).normalize()
        d0_i = int(np.datetime64(d0, "D").astype("int64"))
        lo, hi = d0_i - MATCH_WINDOW_BACK_DAYS, d0_i + MATCH_WINDOW_FWD_DAYS
        # candidates: any odds row where player_a's surname appears (as winner or loser)
        cand = set()
        for k in surname_keys(r.player_a):
            lst = by_sur.get(k)
            if not lst:
                continue
            days = by_sur_days[k]
            a, b = bisect.bisect_left(days, lo), bisect.bisect_right(days, hi)
            cand.update(lst[a:b])
        hits = []
        for i in cand:
            a_is_w = db_name_matches(r.player_a, w_sur[i], w_ini[i]) and db_name_matches(r.player_b, l_sur[i], l_ini[i])
            a_is_l = db_name_matches(r.player_a, l_sur[i], l_ini[i]) and db_name_matches(r.player_b, w_sur[i], w_ini[i])
            if a_is_w or a_is_l:
                hits.append((i, a_is_w))
        if not hits:
            unmatched += 1
            continue
        if len(hits) > 1:
            # same two players inside the window more than once (e.g. final one week, early round the next) -- skip, don't guess
            ambiguous += 1
            continue
        i, a_is_w = hits[0]
        o = od.iloc[i]
        day_gaps.append(int(od_day[i] - d0_i))
        # side mapping: 'W' columns are the winner's, 'L' the loser's
        def side(colw, coll):
            return (o[colw], o[coll]) if a_is_w else (o[coll], o[colw])
        ps_a, ps_b = side("PSW", "PSL")
        avg_a, avg_b = side("AvgW", "AvgL")
        max_a, max_b = side("MaxW", "MaxL")
        rank_a, rank_b = side("WRank", "LRank")
        # sanity: odds file's winner must agree with our label
        odds_says_a_won = 1 if a_is_w else 0
        out.append({
            **r._asdict(),
            "tour": o["tour"], "level": o["level"], "best_of": o["Best of"], "comment": o["Comment"],
            "odds_round": o["Round"] if "Round" in od.columns else "",
            "ps_a": ps_a, "ps_b": ps_b, "avg_a": avg_a, "avg_b": avg_b, "max_a": max_a, "max_b": max_b,
            "rank_a": rank_a, "rank_b": rank_b, "odds_label_a_won": odds_says_a_won, "_odds_idx": i,
        })
    m = pd.DataFrame(out)
    # diagnostic: which odds-file matches did NOT get a model row? (names the matcher may be missing)
    used = set(m["_odds_idx"]) if "_odds_idx" in m.columns else set()
    print(f"\n  Matched {len(m):,} of {len(rows):,} model rows to an odds row "
          f"({unmatched:,} no match, {ambiguous:,} ambiguous -- both dropped, never guessed).")
    print(f"  Window used: match_date -{MATCH_WINDOW_BACK_DAYS}d .. +{MATCH_WINDOW_FWD_DAYS}d (2026-08-16 fix; was +/-1d).")
    if len(m):
        # proof the fix took: matched odds rows should now spread over the tournament, not sit at day 0/1
        gaps = pd.Series(day_gaps).value_counts().sort_index()
        print("  Days from DB match_date (tournament start) to the matched odds row:")
        print("    " + ", ".join(f"{int(k):+d}d: {int(v):,}" for k, v in gaps.items()))
        if "odds_round" in m.columns:
            rc = m["odds_round"].astype(str).value_counts()
            print("  Matched rows by odds-file round: " + ", ".join(f"{k} ({v:,})" for k, v in rc.items()))
        # coverage from the odds side: main-tour matches in the odds files that never found a model row
        od_years = od[od["Date"].dt.year >= int(rows["year"].min())]
        missing = od_years[~od_years.index.isin(used)]
        print(f"  Odds-file coverage: {len(od_years) - len(missing):,} of {len(od_years):,} main-tour odds rows found a model row; {len(missing):,} did not.")
        if len(missing):
            names = pd.concat([missing["Winner"], missing["Loser"]]).value_counts().head(25)
            print("  Most frequent player names in UNMATCHED odds rows (fix these in the matcher if they look like plain misses):")
            print("    " + ", ".join(f"{n} ({c})" for n, c in names.items()))
        disagree = int((m["odds_label_a_won"] != m["label_a_won"]).sum())
        print(f"  Winner-label agreement check: {len(m) - disagree:,} agree, {disagree:,} disagree (disagreements dropped).")
        m = m[m["odds_label_a_won"] == m["label_a_won"]].copy()
    return m


# ------------------------------------------------------------ betting ----
def devig(o_a, o_b):
    """Book's implied P(a) with the margin removed. Returns NaN if either side missing."""
    with np.errstate(divide="ignore", invalid="ignore"):
        ia, ib = 1.0 / o_a, 1.0 / o_b
        return ia / (ia + ib)


def simulate(df: pd.DataFrame, thr: float, price_col_a: str, price_col_b: str, implied_col: str):
    """Flat 1-unit stake on whichever side the model likes MORE than the book,
    if the disagreement exceeds thr. Returns (n_bets, hits, profit)."""
    p = df["engine_prob"].values
    q = df[implied_col].values
    y = df["label_a_won"].values
    oa = df[price_col_a].values
    ob = df[price_col_b].values
    edge_a = p - q
    edge_b = (1 - p) - (1 - q)
    bet_a = (edge_a > thr) & np.isfinite(oa)
    bet_b = (edge_b > thr) & np.isfinite(ob) & ~bet_a
    profit = 0.0
    hits = 0
    n = int(bet_a.sum() + bet_b.sum())
    if n == 0:
        return 0, 0, 0.0
    # side a
    oa_c = np.nan_to_num(oa, nan=1.0)   # non-bet rows contribute 0 either way
    ob_c = np.nan_to_num(ob, nan=1.0)
    win_a = bet_a & (y == 1)
    profit += float(((oa_c - 1.0) * win_a).sum()) - float((bet_a & (y == 0)).sum())
    hits += int(win_a.sum())
    # side b
    win_b = bet_b & (y == 0)
    profit += float(((ob_c - 1.0) * win_b).sum()) - float((bet_b & (y == 1)).sum())
    hits += int(win_b.sum())
    return n, hits, profit


def report_thresholds(df, label, price_a, price_b, implied):
    print(f"\n  {label}  (flat 1u stakes)")
    print(f"    {'edge >':>7s} {'bets':>7s} {'hit%':>7s} {'ROI':>8s}")
    best = None
    for thr in THRESHOLDS:
        n, h, pr = simulate(df, thr, price_a, price_b, implied)
        roi = pr / n if n else float("nan")
        flag = "" if n >= MIN_BETS_TO_TRUST else "  (thin)"
        print(f"    {thr:>7.2f} {n:>7,d} {h/n if n else float('nan'):>7.1%} {roi:>+8.2%}{flag}")
        if n >= MIN_BETS_TO_TRUST and (best is None or roi > best[1]):
            best = (thr, roi, n)
    return best


def report_segments(df, thr, price_a, price_b, implied):
    conf = np.maximum(df["engine_prob"], 1 - df["engine_prob"])
    df = df.assign(
        band=pd.cut(conf, [0, 0.55, 0.65, 0.75, 0.85, 1.01], labels=["<55", "55-65", "65-75", "75-85", "85+"], right=False),
        fav_or_dog=np.where(
            (df["engine_prob"] > df[implied]) == (df[implied] >= 0.5), "model backs FAVOURITE", "model backs UNDERDOG"),
    )
    segs = [("tour", "tour"), ("surface", "surface"), ("best_of", "best_of"), ("level", "level"),
            ("model band", "band"), ("signals", "n_signals_included"), ("side", "fav_or_dog")]
    for title, col in segs:
        print(f"\n    by {title}:")
        for val, g in df.groupby(col, observed=True):
            n, h, pr = simulate(g, thr, price_a, price_b, implied)
            if n == 0:
                continue
            flag = "" if n >= MIN_BETS_TO_TRUST else "  (thin)"
            print(f"      {str(val):24s} {n:>6,d} bets  {h/n:>6.1%} hit  ROI {pr/n:>+7.2%}{flag}")


def run():
    if not os.path.exists(ROWS_CSV):
        print(f"ERROR: {ROWS_CSV} not found. Run build_walkforward_rows.py first.")
        return
    rows = pd.read_csv(ROWS_CSV)
    rows["year"] = rows["year"].astype(int)
    rows["engine_prob"] = pd.to_numeric(rows["engine_prob"], errors="coerce")
    rows = rows[rows["engine_prob"].notna() & (rows["year"] >= TUNE_YEARS[0])].copy()
    print("=" * 72)
    print("LOADING ODDS (tennis-data.co.uk) — scoreboard use only, never a pick input")
    print("=" * 72)
    od = load_odds()
    if od is None:
        return
    print(f"\n  Model rows {TUNE_YEARS[0]}+: {len(rows):,}")
    m = match_rows(rows, od)
    if m.empty:
        print("  Nothing matched -- check name formats / dates.")
        return

    # exclude retirements / walkovers; require Pinnacle price
    before = len(m)
    m = m[~m["comment"].str.contains("Retired|Walkover", case=False, na=False)]
    print(f"  Dropped {before - len(m):,} retirements/walkovers.")
    m["ps_imp_a"] = devig(m["ps_a"].values, m["ps_b"].values)
    m["avg_imp_a"] = devig(m["avg_a"].values, m["avg_b"].values)
    has_ps = m["ps_imp_a"].notna()
    print(f"  Rows with a Pinnacle price: {int(has_ps.sum()):,}   with an Average price: {int(m['avg_imp_a'].notna().sum()):,}")

    tune = m[(m["year"] >= TUNE_YEARS[0]) & (m["year"] <= TUNE_YEARS[1]) & has_ps]
    test = m[(m["year"] >= TEST_MIN_YEAR) & has_ps]
    print(f"\n  TUNE ({TUNE_YEARS[0]}-{TUNE_YEARS[1]}): {len(tune):,} matches   TEST (>= {TEST_MIN_YEAR}): {len(test):,} matches")

    # baseline: how good is the book itself, and the model, on the same matches?
    print("\n" + "=" * 72)
    print("BASELINES ON THE TEST YEARS (same matches)")
    print("=" * 72)
    y = test["label_a_won"].values
    for name, p in (("Pinnacle (de-vigged)", test["ps_imp_a"].values), ("Current engine", test["engine_prob"].values)):
        acc = float(((p > 0.5).astype(int) == y).mean())
        ll = float(-np.mean(y * np.log(np.clip(p, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1))))
        print(f"  {name:22s} accuracy {acc:.1%}   log loss {ll:.4f}")
    # blind strategy controls
    for name, thr in (("Bet EVERY match on the model's side (edge > 0)", 0.0),):
        n, h, pr = simulate(test, thr, "ps_a", "ps_b", "ps_imp_a")
        print(f"  Control: {name}: {n:,} bets, ROI {pr/n:+.2%}")

    print("\n" + "=" * 72)
    print(f"TUNE YEARS {TUNE_YEARS[0]}-{TUNE_YEARS[1]} — pick the edge threshold here")
    print("=" * 72)
    best_ps = report_thresholds(tune, "vs Pinnacle closing price", "ps_a", "ps_b", "ps_imp_a")
    best_max = report_thresholds(tune, "vs Pinnacle price, paid at MAX odds (line shopping)", "max_a", "max_b", "ps_imp_a")
    chosen = best_ps[0] if best_ps else 0.05
    print(f"\n  Chosen threshold (best ROI on TUNE with >= {MIN_BETS_TO_TRUST} bets): edge > {chosen:.2f}")

    print("\n" + "=" * 72)
    print(f"TEST YEARS >= {TEST_MIN_YEAR} — opened once, threshold fixed at {chosen:.2f}")
    print("=" * 72)
    report_thresholds(test, "vs Pinnacle closing price (all thresholds shown for context)", "ps_a", "ps_b", "ps_imp_a")
    report_thresholds(test, "paid at MAX odds (line shopping)", "max_a", "max_b", "ps_imp_a")
    n, h, pr = simulate(test, chosen, "ps_a", "ps_b", "ps_imp_a")
    n2, h2, pr2 = simulate(test, chosen, "max_a", "max_b", "ps_imp_a")
    print(f"\n  AT THE CHOSEN THRESHOLD ({chosen:.2f}):")
    print(f"    Pinnacle price:  {n:,} bets, {h/n if n else 0:.1%} hit, ROI {pr/n if n else 0:+.2%}")
    print(f"    Max price:       {n2:,} bets, {h2/n2 if n2 else 0:.1%} hit, ROI {pr2/n2 if n2 else 0:+.2%}")
    print("\n  Where the profit lives / dies (TEST, chosen threshold, Pinnacle price):")
    report_segments(test, chosen, "ps_a", "ps_b", "ps_imp_a")

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    roi = pr / n if n else float("nan")
    if n < MIN_BETS_TO_TRUST:
        print(f"  Too few bets ({n}) on the test years to say anything.")
    elif roi > 0.02:
        print(f"  Betting only when the model beats Pinnacle by >{chosen:.0%}, {TEST_MIN_YEAR}-2026 would have returned {roi:+.1%}")
        print(f"  on {n:,} bets ({h/n:.1%} hit rate). That is a REAL edge on years the model never studied.")
        print("  Next: check the segment table -- keep the pockets that pay, drop the ones that don't; then re-run with the upgraded ELO.")
    elif roi > -0.02:
        print(f"  Roughly break-even ({roi:+.1%}) against Pinnacle -- the model is about as sharp as the book, no better.")
        print("  Look at the segments: an edge may exist in pockets even when the total is flat. Then improve the ingredients (ELO upgrades).")
    else:
        print(f"  Negative ({roi:+.1%}) against Pinnacle: the current signals do NOT beat the closing price as-is.")
        print("  This is the honest starting line. The ingredient upgrades (margin-of-victory ELO, surface, level, rank) are what to test next,")
        print("  each judged by whether it moves THIS number on THESE years.")


if __name__ == "__main__":
    run()
