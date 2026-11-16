#!/usr/bin/env python3
"""
ADD_SEED_PLAYERS.PY — expands an already-populated player_seed_list
table with new names, without touching or duplicating what's already
there.

Why this exists: the collector's own seed-loading logic
(_load_seed_players in tennis_warehouse_collector.py) only reads the
starter JSON file when player_seed_list is EMPTY -- correct for a
first run, but it means a bigger name list uploaded after the first
backfill already ran won't get picked up automatically. This script
is the honest fix: INSERT OR IGNORE per name, so already-present
players are left untouched and only genuinely new names get added.

USAGE:
    python3 add_seed_players.py player_seed_list_full.json
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "data" / "warehouse" / "tennis_warehouse.sqlite"


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 add_seed_players.py <seed_file.json>")
        sys.exit(1)

    seed_file = Path(sys.argv[1])
    if not seed_file.exists():
        print(f"File not found: {seed_file}")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"Warehouse database not found at {DB_PATH} -- run the "
              f"collector at least once first (python3 "
              f"tennis_warehouse_collector.py --backfill) so the schema "
              f"exists before adding more seed players.")
        sys.exit(1)

    data = json.loads(seed_file.read_text())
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(DB_PATH)
    before = conn.execute("SELECT COUNT(*) FROM player_seed_list").fetchone()[0]

    added = 0
    for tour_key, tour_label in (("atp", "ATP"), ("wta", "WTA")):
        for entry in data.get(tour_key, []):
            name = entry.get("name") if isinstance(entry, dict) else entry
            if not name:
                continue
            cur = conn.execute("""
                INSERT OR IGNORE INTO player_seed_list (player, tour, ranking_at_seed, source, added_at)
                VALUES (?,?,?,?,?)
            """, (name, tour_label, entry.get("rank") if isinstance(entry, dict) else None,
                  "MANUAL_SEED", now))
            if cur.rowcount > 0:
                added += 1
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM player_seed_list").fetchone()[0]
    conn.close()

    print(f"Seed list before: {before} players")
    print(f"New names added:  {added}")
    print(f"Already present (skipped, not duplicated): {(len(data.get('atp', [])) + len(data.get('wta', []))) - added}")
    print(f"Seed list after:  {after} players")
    print()
    print("Next: run the collector again to actually fetch data for the new names:")
    print("    python3 tennis_warehouse_collector.py --backfill")


if __name__ == "__main__":
    main()

# © 2026 Demetrius Reynolds — Project Apex Intelligence™. All rights reserved.
