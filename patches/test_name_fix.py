"""
test_name_fix.py — 2026-08-16
Tests db_name_matches() after the name fix in build_edge_backtest.py, using the
REAL Dataset B spellings pulled from the Mini on 2026-08-16 (nothing else real).
Run from the project folder:  python3 test_name_fix.py   -> ALL CHECKS PASSED
Also proves the OLD rule (DB name must END with the odds surname) missed these.

Sections:
  MUST MATCH  — the misses seen in the unmatched-name list, and normal names
  MUST NOT    — sibling / first-name-as-surname traps that must keep failing
  END-TO-END  — full match_rows() on a mini odds file with these names
"""
import sys
import numpy as np
import pandas as pd
import build_edge_backtest as B


def old_rule(db_name, td_surname, td_initial):
    """The pre-fix rule, verbatim: DB name ends with td surname; first token starts with initial."""
    toks = B._norm(db_name).split()
    if not toks or not td_surname:
        return False
    n = len(td_surname)
    if tuple(toks[-n:]) != td_surname:
        return False
    if td_initial and not toks[0].startswith(td_initial):
        return False
    return True


def m(db, td):
    sur, ini = B.parse_td_name(td)
    return B.db_name_matches(db, sur, ini)


def old(db, td):
    sur, ini = B.parse_td_name(td)
    return old_rule(db, sur, ini)


fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


print("MUST MATCH (new rule):")
must = [
    ("Maria Camila Osorio Serrano", "Osorio M.",         "extra surname part + initial = 1st given name"),
    ("Giovanni Mpetshi Perricard",  "Mpetshi G.",        "extra surname part (Perricard)"),
    ("Alison Riske Amritraj",       "Riske A.",          "extra surname part (Amritraj)"),
    ("Daniel Merida",               "Merida Aguilar D.", "odds has MORE surname tokens than DB"),
    ("Daniel Merida Aguilar",       "Merida Aguilar D.", "same player, other DB spelling"),
    ("Christopher O'Connell",       "O Connell C.",      "apostrophe: 'o'+'connell' == 'oconnell'"),
    ("Novak Djokovic",              "Djokovic N.",       "plain name still works"),
    ("Alex De Minaur",              "De Minaur A.",      "two-token surname still works"),
    ("Pablo Carreno Busta",         "Carreno Busta P.",  "two-token surname still works"),
    ("Martin Damm",                 "Damm M.",           "surname at index 1, initial matches"),
    ("Juan Sebastian Osorio",       "Osorio J.",         "different Osorio, initial J = Juan"),
]
for db, td, why in must:
    check(m(db, td), f"'{td}' <-> '{db}'  ({why})")

print("\nMUST NOT MATCH (sibling / trap guards kept):")
must_not = [
    ("Mischa Zverev",          "Zverev A.",     "sibling: A(lexander) vs Mischa"),
    ("Juan Manuel Cerundolo",  "Cerundolo F.",  "sibling: F(rancisco) vs Juan Manuel"),
    ("Martin Damm",            "Martin A.",     "first name used as surname -> refuse"),
    ("Pedro Martin",           "Martinez P.",   "'martin' != 'martinez' (no prefix matching)"),
    ("Camila Osorio",          "Osorio M.",     "known remaining miss: DB spelling has no 'Maria' -> refuse rather than guess"),
    ("Tomas Barrios Vera",     "Barrios M.",    "known remaining miss: DB has no 'Marcelo' -> refuse rather than guess"),
    ("Sinner",                 "Sinner J.",     "single-token DB name -> refuse"),
]
for db, td, why in must_not:
    check(not m(db, td), f"'{td}' -/-> '{db}'  ({why})")

print("\nOLD RULE on the same misses (proves what was broken):")
for db, td, _ in [x for x in must[:6] if x[0] != "Daniel Merida Aguilar"]:
    check(not old(db, td), f"old rule MISSED '{td}' <-> '{db}'")
check(old("Daniel Merida Aguilar", "Merida Aguilar D."), "old rule DID match the 'Daniel Merida Aguilar' spelling (only 'Daniel Merida' was missed)")

print("\nEND-TO-END through match_rows():")
od = pd.DataFrame([
    ("2025-03-03", "Osorio M.",     "Riske A.",       1.60, 2.30, 1.65, 2.40, "1st Round"),
    ("2025-03-05", "O Connell C.",  "Mpetshi G.",     2.10, 1.75, 2.20, 1.80, "2nd Round"),
    ("2025-03-04", "Merida Aguilar D.", "Djokovic N.", 6.00, 1.12, 6.50, 1.14, "1st Round"),
], columns=["Date", "Winner", "Loser", "PSW", "PSL", "MaxW", "MaxL", "Round"])
od["Date"] = pd.to_datetime(od["Date"])
for c in ("AvgW", "AvgL", "WRank", "LRank", "Best of"):
    od[c] = np.nan
od["tour"] = "atp"; od["level"] = "x"; od["Comment"] = "Completed"
od["w_sur"], od["w_ini"] = zip(*od["Winner"].map(B.parse_td_name))
od["l_sur"], od["l_ini"] = zip(*od["Loser"].map(B.parse_td_name))
rows = pd.DataFrame([
    (1, "2025-03-03", "Alison Riske Amritraj", "Maria Camila Osorio Serrano", 0),
    (2, "2025-03-03", "Giovanni Mpetshi Perricard", "Christopher O'Connell", 0),
    (3, "2025-03-03", "Daniel Merida", "Novak Djokovic", 1),
], columns=["case", "match_date", "player_a", "player_b", "label_a_won"])
rows["year"] = 2025; rows["engine_prob"] = 0.5; rows["n_signals_included"] = 1; rows["surface"] = "Hard"
mm = B.match_rows(rows, od)
got = set(mm["case"]) if len(mm) else set()
check(got == {1, 2, 3}, f"all three name-fix cases matched end-to-end (got {sorted(got)})")
if 1 in got:
    r = mm[mm["case"] == 1].iloc[0]
    check(abs(r["ps_a"] - 2.30) < 1e-9, "case 1 side mapping: Riske (player_a, lost) gets PSL=2.30")

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASSED.")
