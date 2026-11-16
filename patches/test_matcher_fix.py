"""
test_matcher_fix.py — 2026-08-16
Fake-data test for the match_rows() fix in build_edge_backtest.py.
Run from the project folder:  python3 test_matcher_fix.py
Every case is invented; no real data is touched. Exits non-zero on any failure.

What it proves:
  1. A first-round match dated on the tournament start day still matches (as before).
  2. A LATER-ROUND match (odds row 10 days after DB match_date) NOW matches
     -- and the OLD +/-1-day matcher, reproduced here verbatim, does NOT.
  3. Same pair twice inside the window -> ambiguous -> dropped, not guessed.
  4. An odds row 20 days out (past the window) -> unmatched.
  5. Winner disagreement between DB label and odds file -> dropped.
  6. Two-token surname ('Alex De Minaur' vs 'De Minaur A.') still matches.
  7. A row where the DB DOES carry the real date one day after the odds date
     (back-tolerance) still matches.
  8. Odds side-mapping is right (player_a's Pinnacle price is PSW when a won, PSL when a lost).
"""
import sys
import numpy as np
import pandas as pd
import build_edge_backtest as B


def make_odds():
    rows = [
        # Date,        Winner,          Loser,           PSW,  PSL,  MaxW, MaxL, Round,          Comment
        ("2025-01-13", "Sinner J.",     "Jarry N.",      1.10, 7.50, 1.12, 8.00, "1st Round",    "Completed"),   # case 1: R1, day 0
        ("2025-01-23", "Sinner J.",     "Shelton B.",    1.15, 5.80, 1.17, 6.20, "Semifinals",   "Completed"),   # case 2: SF, day +10
        ("2025-02-03", "Rune H.",       "Zverev A.",     2.40, 1.60, 2.55, 1.65, "1st Round",    "Completed"),   # case 3a: pair meets
        ("2025-02-12", "Zverev A.",     "Rune H.",       1.55, 2.50, 1.60, 2.60, "Quarterfinals","Completed"),   # case 3b: ...twice in window
        ("2025-03-25", "Alcaraz C.",    "Fritz T.",      1.30, 3.60, 1.33, 3.80, "Semifinals",   "Completed"),   # case 4: +20d, past window
        ("2025-04-07", "Ruud C.",       "Paul T.",       1.70, 2.20, 1.75, 2.30, "2nd Round",    "Completed"),   # case 5: odds says Ruud, DB says Paul
        ("2025-05-05", "De Minaur A.",  "Navone M.",     1.25, 4.10, 1.28, 4.30, "1st Round",    "Completed"),   # case 6: 2-token surname
        ("2025-06-09", "Medvedev D.",   "Tiafoe F.",     1.45, 2.80, 1.48, 2.95, "1st Round",    "Completed"),   # case 7: DB date = 06-10 (real, +1)
    ]
    od = pd.DataFrame(rows, columns=["Date", "Winner", "Loser", "PSW", "PSL", "MaxW", "MaxL", "Round", "Comment"])
    od["Date"] = pd.to_datetime(od["Date"])
    for c in ("AvgW", "AvgL", "WRank", "LRank", "Best of"):
        od[c] = np.nan
    od["tour"] = "atp"
    od["level"] = "ATP250"
    od["w_sur"], od["w_ini"] = zip(*od["Winner"].map(B.parse_td_name))
    od["l_sur"], od["l_ini"] = zip(*od["Loser"].map(B.parse_td_name))
    return od


def make_rows():
    # DB rows: match_date = tournament start (Sackmann), except case 7 which carries a real date.
    rows = [
        # case, match_date,   player_a,          player_b,           label_a_won
        (1, "2025-01-13", "Jannik Sinner",   "Nicolas Jarry",     1),
        (2, "2025-01-13", "Ben Shelton",     "Jannik Sinner",     0),   # a lost -> a's price must be PSL side
        (3, "2025-02-03", "Holger Rune",     "Alexander Zverev",  1),
        (4, "2025-03-05", "Carlos Alcaraz",  "Taylor Fritz",      1),
        (5, "2025-04-07", "Casper Ruud",     "Tommy Paul",        0),   # DB says Paul won; odds says Ruud -> drop
        (6, "2025-05-05", "Alex De Minaur",  "Mariano Navone",    1),
        (7, "2025-06-10", "Daniil Medvedev", "Frances Tiafoe",    1),
    ]
    df = pd.DataFrame(rows, columns=["case", "match_date", "player_a", "player_b", "label_a_won"])
    df["year"] = 2025
    df["engine_prob"] = 0.6
    df["n_signals_included"] = 2
    df["surface"] = "Hard"
    return df


def old_match_rows(rows, od):
    """The pre-fix matcher, reproduced verbatim from the 2026-08-15 file (date +/-1 day)."""
    by_date = {}
    for i, d in enumerate(od["Date"].dt.normalize()):
        by_date.setdefault(d, []).append(i)
    matched_cases = []
    for r in rows.itertuples(index=False):
        d0 = pd.Timestamp(r.match_date).normalize()
        cands = []
        for delta in (0, 1, -1):
            cands.extend(by_date.get(d0 + pd.Timedelta(days=delta), []))
        hits = []
        for i in cands:
            o = od.iloc[i]
            a_is_w = B.db_name_matches(r.player_a, o["w_sur"], o["w_ini"]) and B.db_name_matches(r.player_b, o["l_sur"], o["l_ini"])
            a_is_l = B.db_name_matches(r.player_a, o["l_sur"], o["l_ini"]) and B.db_name_matches(r.player_b, o["w_sur"], o["w_ini"])
            if a_is_w or a_is_l:
                hits.append(i)
        if len(hits) == 1:
            matched_cases.append(r.case)
    return set(matched_cases)


def main():
    od, rows = make_odds(), make_rows()
    fails = []

    def check(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            fails.append(msg)

    print("NEW matcher:")
    m = B.match_rows(rows, od)
    got = set(m["case"]) if len(m) else set()
    check(1 in got, "case 1: first-round match on tournament start day matches")
    check(2 in got, "case 2: semifinal 10 days after tournament start NOW matches")
    check(3 not in got, "case 3: same pair twice inside window -> ambiguous -> dropped")
    check(4 not in got, "case 4: odds row 20 days out (past window) -> unmatched")
    check(5 not in got, "case 5: winner disagreement -> dropped by cross-check")
    check(6 in got, "case 6: two-token surname (De Minaur) matches")
    check(7 in got, "case 7: DB real date one day AFTER odds date (back tolerance) matches")
    if 2 in got:
        r2 = m[m["case"] == 2].iloc[0]
        check(abs(r2["ps_a"] - 5.80) < 1e-9 and abs(r2["ps_b"] - 1.15) < 1e-9,
              "case 2: side mapping -- Shelton (player_a, lost) gets PSL=5.80, Sinner gets PSW=1.15")
    if 1 in got:
        r1 = m[m["case"] == 1].iloc[0]
        check(abs(r1["ps_a"] - 1.10) < 1e-9, "case 1: side mapping -- Sinner (player_a, won) gets PSW=1.10")

    print("\nOLD matcher (+/-1 day), same fake data:")
    old = old_match_rows(rows, od)
    print(f"  old matcher matched cases: {sorted(old)}")
    check(2 not in old, "OLD matcher MISSES the semifinal (case 2) -- this is the flaw being fixed")
    check(1 in old and 6 in old, "OLD matcher still finds the round-1 matches (cases 1, 6) -- so old results were R1-heavy, not empty")

    print()
    if fails:
        print(f"{len(fails)} FAILURE(S):")
        for f in fails:
            print("  - " + f)
        sys.exit(1)
    print("ALL CHECKS PASSED.")


if __name__ == "__main__":
    main()
