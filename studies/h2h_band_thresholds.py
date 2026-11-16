#!/usr/bin/env python3
"""
h2h_band_thresholds.py — derives real moderate/strong band cutoffs for
a new H2H signal (S3), the same way ML_S1_SURFACE_MODERATE_GAP_PP /
ML_S1_SURFACE_STRONG_GAP_PP were presumably set for S1 -- from the
actual distribution of real gaps in your own data, not a guess.

Only considers matches with a real H2H sample size >= MIN_PROPOSAL_SAMPLE
(10, matching the existing system-wide minimum-sample standard) --
anything thinner isn't a fair basis for setting a threshold on.

Reports the H2H gap (in percentage points, same units as S1's surface-
form signal, for direct comparability) at the 50th/75th/90th
percentiles of |gap| among qualifying matches -- gives you real,
evidence-based candidates for MODERATE and STRONG cutoffs instead of
picking numbers out of the air.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "warehouse" / "tennis_warehouse.sqlite"
MIN_PROPOSAL_SAMPLE = 10  # matches the real constant already in openclaw_core.py


def parse_h2h(h2h_str):
    if not h2h_str or "-" not in h2h_str:
        return None
    try:
        w, l = h2h_str.split("-")
        return int(w), int(l)
    except ValueError:
        return None


def run():
    if not DB_PATH.exists():
        print(f"FATAL: database not found at {DB_PATH}")
        return
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT h2h_at_match FROM matches WHERE h2h_at_match IS NOT NULL"
    ).fetchall()
    conn.close()

    gaps = []
    for (h2h_str,) in rows:
        parsed = parse_h2h(h2h_str)
        if not parsed:
            continue
        w, l = parsed
        total = w + l
        if total < MIN_PROPOSAL_SAMPLE:
            continue
        pct = w / total  # win pct for whichever side "w" represents
        gap_pp = abs(2 * pct - 1) * 100  # rescale to a 0-100 percentage-point gap, same units as S1
        gaps.append(gap_pp)

    if not gaps:
        print(f"No matches found with H2H sample >= {MIN_PROPOSAL_SAMPLE}. "
              f"Can't set real thresholds without real data -- either the sample "
              f"size requirement needs revisiting, or there just isn't enough "
              f"deep-H2H data on file yet.")
        return

    gaps.sort()
    n = len(gaps)

    def pct_at(p):
        idx = min(n - 1, int(p * n))
        return gaps[idx]

    print(f"{n} matches on file with H2H sample size >= {MIN_PROPOSAL_SAMPLE}.\n")
    print("Real gap distribution (percentage points, same units as S1's ML_S1_SURFACE_*_GAP_PP):")
    print(f"  median (50th pct):  {pct_at(0.50):.1f}pp")
    print(f"  75th percentile:    {pct_at(0.75):.1f}pp")
    print(f"  90th percentile:    {pct_at(0.90):.1f}pp")
    print()
    print("Suggested reading (mirrors how S1's 5pp/15pp bands likely work):")
    print(f"  MODERATE candidate (~median-ish gap): {pct_at(0.50):.0f}pp")
    print(f"  STRONG candidate (~75th-90th pct gap): {pct_at(0.75):.0f}-{pct_at(0.90):.0f}pp")
    print()
    print("These are DATA, not a final decision -- review before locking them into code.")


if __name__ == "__main__":
    run()
