#!/usr/bin/env python3
"""
WAREHOUSE_REPORT.PY — First Real Warehouse Report
Run this on the Mac Mini, from the project root. Prints all 9
requested sections using real queries against the actual
tennis_warehouse.sqlite -- no estimates, no mock data.

USAGE:
    python3 warehouse_report.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "warehouse" / "tennis_warehouse.sqlite"


def q(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def main():
    if not DB_PATH.exists():
        print(f"No warehouse found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("FIRST REAL WAREHOUSE REPORT")
    print("=" * 70)

    # 1. Rows by table
    print("\n1. ROWS BY TABLE")
    tables = ["matches", "player_year_stats", "players", "rankings_snapshot",
              "tournaments", "collector_runs", "player_seed_list"]
    total = 0
    for t in tables:
        try:
            n = q(conn, f"SELECT COUNT(*) as n FROM {t}")[0]["n"]
        except sqlite3.OperationalError:
            n = 0
        total += n
        print(f"   {t:20s} {n}")
    print(f"   {'TOTAL':20s} {total}")

    # 2. ATP vs WTA coverage
    print("\n2. ATP vs WTA COVERAGE")
    for t in ("players", "matches", "player_year_stats"):
        rows = q(conn, f"SELECT tour, COUNT(*) as n FROM {t} GROUP BY tour")
        print(f"   {t}: " + ", ".join(f"{r['tour']}={r['n']}" for r in rows))

    # 3. Rows by year
    print("\n3. ROWS BY YEAR (player_year_stats)")
    rows = q(conn, "SELECT year, COUNT(*) as n, COUNT(DISTINCT player) as players "
                    "FROM player_year_stats GROUP BY year ORDER BY year")
    for r in rows:
        print(f"   {r['year']}: {r['n']} rows, {r['players']} players")

    # 4. Feature population rates
    print("\n4. FEATURE POPULATION RATES (player_year_stats)")
    pys_total = q(conn, "SELECT COUNT(*) as n FROM player_year_stats")[0]["n"]
    for feature in ("hold_pct", "break_pct", "avg_aces", "first_serve_pct", "bp_save_pct"):
        populated = q(conn, f"SELECT COUNT(*) as n FROM player_year_stats WHERE {feature} IS NOT NULL")[0]["n"]
        pct = round(100 * populated / pys_total, 1) if pys_total else 0
        print(f"   {feature:18s} {populated}/{pys_total} ({pct}%)")

    # 5. FULL_AGGREGATE vs FALLBACK_PARTIAL
    print("\n5. DATA SOURCE QUALITY")
    rows = q(conn, "SELECT data_source, COUNT(*) as n FROM player_year_stats GROUP BY data_source")
    for r in rows:
        pct = round(100 * r["n"] / pys_total, 1) if pys_total else 0
        print(f"   {r['data_source']}: {r['n']} ({pct}%)")

    # 6. Missing value rates
    print("\n6. MISSING VALUE RATES")
    matches_total = q(conn, "SELECT COUNT(*) as n FROM matches")[0]["n"]
    missing_winner = q(conn, "SELECT COUNT(*) as n FROM matches WHERE winner IS NULL")[0]["n"]
    missing_surface = q(conn, "SELECT COUNT(*) as n FROM matches WHERE surface IS NULL")[0]["n"]
    print(f"   Matches missing winner:  {missing_winner}/{matches_total}")
    print(f"   Matches missing surface: {missing_surface}/{matches_total}")

    # 7. Data quality summary
    print("\n7. DATA QUALITY SUMMARY")
    dupes = q(conn, """
        SELECT player_a, player_b, match_date, COUNT(*) as n FROM matches
        GROUP BY player_a, player_b, match_date HAVING COUNT(*) > 1
    """)
    print(f"   Near-duplicate match groups: {len(dupes)}")
    fallback_pct = round(100 * (q(conn, "SELECT COUNT(*) as n FROM player_year_stats WHERE data_source='FALLBACK_PARTIAL'")[0]["n"]) / pys_total, 1) if pys_total else 0
    print(f"   Fallback-partial rate: {fallback_pct}%")

    # 8. Current Warehouse Health assessment
    print("\n8. WAREHOUSE HEALTH (component view, not a single hidden score)")
    last_run = q(conn, "SELECT status, finished_at FROM collector_runs ORDER BY finished_at DESC LIMIT 1")
    if last_run:
        print(f"   Last run status: {last_run[0]['status']} at {last_run[0]['finished_at']}")
    resolved = q(conn, "SELECT COUNT(*) as n FROM players")[0]["n"]
    seeded = q(conn, "SELECT COUNT(*) as n FROM player_seed_list")[0]["n"]
    print(f"   Seed resolution rate: {resolved}/{seeded}")

    # 9. Training readiness
    print("\n9. TRAINING READINESS (raw counts only, per approved tiers)")
    print(f"   player_year_stats rows: {pys_total} (tier thresholds apply per-market in Dataset A's ML Readiness, not directly here)")
    print(f"   matches rows: {matches_total}")

    conn.close()
    print("\n" + "=" * 70)
    print("Paste this full output back and I'll build the rest of Warehouse")
    print("Command Center against these real numbers.")


if __name__ == "__main__":
    main()

# © 2026 Demetrius Reynolds — Project Apex Intelligence™. All rights reserved.
