"""
check_warehouse_coverage.py
Real diagnostic -- checks what's ACTUALLY in tennis_warehouse.sqlite
before assuming the 5 uploaded CSVs are new data. No guessing.

USAGE:
    python3 check_warehouse_coverage.py
"""
import sqlite3
import os

WAREHOUSE_PATH = "data/warehouse/tennis_warehouse.sqlite"


def run():
    if not os.path.exists(WAREHOUSE_PATH):
        print(f"ERROR: warehouse not found at {WAREHOUSE_PATH}")
        return
    conn = sqlite3.connect(WAREHOUSE_PATH)

    print("=" * 70)
    print("REAL DATE RANGE currently in the warehouse")
    print("=" * 70)
    row = conn.execute("SELECT MIN(match_date), MAX(match_date), COUNT(*) FROM matches").fetchone()
    print(f"  Earliest real match: {row[0]}")
    print(f"  Most recent real match: {row[1]}")
    print(f"  Total real rows: {row[2]}")

    print("\n" + "=" * 70)
    print("Matches in the last 30 days (checking if recent 2026 data is missing)")
    print("=" * 70)
    recent = conn.execute(
        "SELECT match_date, player_a, player_b, tournament FROM matches "
        "WHERE match_date >= '2026-07-01' ORDER BY match_date DESC LIMIT 15"
    ).fetchall()
    if recent:
        for r in recent:
            print(f"  {r[0]}  {r[1]} vs {r[2]}  ({r[3]})")
    else:
        print("  NONE FOUND after 2026-07-01 -- real gap, recent matches are missing.")

    print("\n" + "=" * 70)
    print("Checking for QUALIFYING-ROUND matches (real presence check, not a guess)")
    print("=" * 70)
    # Sackmann-format 'round' values for qualifying are typically Q1/Q2/Q3/BR
    cur = conn.execute("PRAGMA table_info(matches)")
    cols = [c[1] for c in cur.fetchall()]
    if "round" in cols:
        qual_count = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE round IN ('Q1','Q2','Q3','BR')"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        print(f"  Real qualifying-round rows on file: {qual_count} out of {total} total")
        if qual_count == 0:
            print("  ZERO qualifying matches found -- strong real evidence the bulk import")
            print("  never included qualifying-round files at all.")
    else:
        print("  No 'round' column found in matches table -- can't check this directly.")
        print(f"  Real columns present: {cols}")

    print("\n" + "=" * 70)
    print("Checking WTA coverage (2024_wta.csv may or may not already be in)")
    print("=" * 70)
    if "tour" in cols:
        wta_count = conn.execute("SELECT COUNT(*) FROM matches WHERE tour = 'WTA'").fetchone()[0]
        wta_2024 = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE tour = 'WTA' AND match_date >= '2024-01-01' AND match_date < '2025-01-01'"
        ).fetchone()[0]
        print(f"  Real WTA rows total: {wta_count}")
        print(f"  Real WTA rows dated in 2024: {wta_2024}")
    else:
        print("  No 'tour' column found -- can't check this directly.")

    conn.close()


if __name__ == "__main__":
    run()
