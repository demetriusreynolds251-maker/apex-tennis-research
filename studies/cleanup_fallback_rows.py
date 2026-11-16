#!/usr/bin/env python3
"""
CLEANUP_FALLBACK_ROWS.PY — deletes all existing FALLBACK_PARTIAL rows
from player_year_stats before the corrected backfill runs.

Why a full delete-and-rebuild rather than surgical row-by-row fixes:
per the scope analysis, all 225 FALLBACK_PARTIAL rows carry the same
unvalidated risk (191 confirmed duplicated, 34 unconfirmed but
identical exposure) -- none of them were written with the year
validation the fix now requires, so none can be trusted as-is. The
AGGREGATE rows (1,091) and the entire matches table (1,677 rows) are
confirmed clean and untouched by this script.

USAGE:
    python3 cleanup_fallback_rows.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "warehouse" / "tennis_warehouse.sqlite"


def main():
    if not DB_PATH.exists():
        print(f"No warehouse found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)

    before_total = conn.execute("SELECT COUNT(*) FROM player_year_stats").fetchone()[0]
    before_fallback = conn.execute(
        "SELECT COUNT(*) FROM player_year_stats WHERE data_source='FALLBACK_PARTIAL'").fetchone()[0]
    before_aggregate = conn.execute(
        "SELECT COUNT(*) FROM player_year_stats WHERE data_source='AGGREGATE'").fetchone()[0]

    print(f"Before cleanup:")
    print(f"  Total player_year_stats rows: {before_total}")
    print(f"  AGGREGATE (untouched):        {before_aggregate}")
    print(f"  FALLBACK_PARTIAL (deleting):  {before_fallback}")

    conn.execute("DELETE FROM player_year_stats WHERE data_source='FALLBACK_PARTIAL'")
    conn.commit()

    after_total = conn.execute("SELECT COUNT(*) FROM player_year_stats").fetchone()[0]
    conn.close()

    print()
    print(f"After cleanup:")
    print(f"  Total player_year_stats rows: {after_total}")
    print(f"  (should equal the AGGREGATE count above -- {before_aggregate})")
    print()
    print("matches table (1,677 rows) and AGGREGATE rows were never touched -- confirmed clean.")
    print()
    print("Next: re-run the corrected backfill to regenerate valid fallback rows:")
    print("    python3 tennis_warehouse_collector.py --backfill")


if __name__ == "__main__":
    main()

# © 2026 Demetrius Reynolds — Project Apex Intelligence™. All rights reserved.
