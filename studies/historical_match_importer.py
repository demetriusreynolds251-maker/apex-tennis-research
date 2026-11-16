"""
historical_match_importer.py
2026-08-07 — one-time backfill of the real "ATP & WTA, 1968-2026" CSV
archive into Dataset B's `matches` table (tennis_warehouse.sqlite).

WHY THIS EXISTS: `elo_backtest.py`'s real result (AUC 0.59-0.62) was
computed against only 1,832 matches — Dataset B's `matches` table is
filled by the daily V8 collector, which has only been running a few
weeks, NOT by the ~500K-row historical archive the user downloaded.
That archive was previously used ONLY for `build_name_reference.py`'s
name lookup — never actually loaded into the real database ELO reads
from. This importer closes that gap for real.

REAL SCHEMA VARIANCE CONFIRMED THIS SESSION (from 5 actual uploaded
files, not assumed):
  - Column ORDER differs across eras (1967.csv has no `indoor` column
    and `winner_rank`/`loser_rank` sit at the end instead of right
    after winner_age) — handled automatically since this reads by
    column NAME via csv.DictReader, not position.
  - `wta_ongoing_tourneys.csv` has NO HEADER ROW AT ALL — confirmed by
    inspecting the raw file (line 1 is data, not headers). Detected
    and handled via a fallback canonical header list (the modern
    50-column shape, confirmed identical column COUNT to the headered
    files) rather than crashing or silently misreading it.
  - `surface` is empty on some real older rows (14/386 in 1967.csv) —
    stored as NULL, never guessed.
  - `tourney_date` is an 8-digit YYYYMMDD string — converted to
    YYYY-MM-DD to match the ISO-sortable format Dataset B's existing
    `year_coverage()` query already assumes (SUBSTR(match_date,1,4)).

DELIBERATELY NARROW SCOPE: only the fields elo_backtest.py/elo_ops.py
actually read (player_a, player_b, winner, surface, match_date, tour,
tournament, score) are populated with real values. Box-score fields
(aces, double faults, first-serve splits) are left NULL for
historically-imported rows rather than guessed from an uncertain
column-mapping — the CSV's real fields (w_ace, w_svpt, w_1stIn, etc.)
don't have a confirmed 1:1 mapping to the schema's
player_a_first_serve_of etc. without checking openclaw_v8_api.py's
real field definitions, which weren't available this session. ELO
doesn't need these fields at all, so leaving them NULL is honest and
zero-risk rather than a guess dressed up as data.

UPSERT SAFETY: uses INSERT OR IGNORE keyed on the same match_id
derivation the schema already documents (sorted player pair + date)
— a historical row is never allowed to overwrite a richer row the
live V8 collector already wrote (which has real box-score data this
import deliberately doesn't attempt to guess).
"""
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "data" / "warehouse" / "tennis_warehouse.sqlite"

# Confirmed real column list — the modern (50-column) shape shared by
# 2007_atp_quali.csv, 2026_atp_quali.csv, 2023_wta.csv, and matching
# wta_ongoing_tourneys.csv's real column COUNT (50). Used ONLY as a
# fallback when a file has no header row at all.
FALLBACK_HEADER = [
    "tourney_id", "tourney_name", "surface", "draw_size", "tourney_level",
    "indoor", "tourney_date", "match_num", "winner_id", "winner_seed",
    "winner_entry", "winner_name", "winner_hand", "winner_ht", "winner_ioc",
    "winner_age", "winner_rank", "winner_rank_points", "loser_id",
    "loser_seed", "loser_entry", "loser_name", "loser_hand", "loser_ht",
    "loser_ioc", "loser_age", "loser_rank", "loser_rank_points", "score",
    "best_of", "round", "minutes", "w_ace", "w_df", "w_svpt", "w_1stIn",
    "w_1stWon", "w_2ndWon", "w_SvGms", "w_bpSaved", "w_bpFaced", "l_ace",
    "l_df", "l_svpt", "l_1stIn", "l_1stWon", "l_2ndWon", "l_SvGms",
    "l_bpSaved", "l_bpFaced",
]

RETIRED_MARKERS = ("RET", "W/O", "WO", "DEF")


def _conn(db_path=None):
    path = db_path or DB_PATH
    if not path.exists():
        return None
    c = sqlite3.connect(str(path), timeout=30)
    return c


def _has_real_header(first_line: str) -> bool:
    """Real check: does the first line look like the real header row,
    or is it already data? The genuine header always starts with the
    literal string 'tourney_id' — real data rows start with a real
    tourney_id VALUE like '1967-southern-pro' or '2026-toronto', never
    the literal column name."""
    first_field = first_line.split(",", 1)[0].strip()
    return first_field == "tourney_id"


def _tour_from_filename(filename: str) -> str:
    """Same real convention already established and working in
    build_name_reference.py: '_wta' in the filename (case-insensitive)
    -> WTA, everything else -> ATP."""
    return "WTA" if "_wta" in filename.lower() else "ATP"


def _iso_date(raw: str):
    """Real YYYYMMDD -> YYYY-MM-DD. Returns None (not a guess) if the
    raw value isn't a real 8-digit date string."""
    if not raw or len(raw) != 8 or not raw.isdigit():
        return None
    try:
        d = datetime.strptime(raw, "%Y%m%d")
        return d.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _is_retired(score: str) -> int:
    """Real signal already present in the score string itself
    ('6-2 3-2 RET', 'W/O', etc.) — not a guess, a direct textual
    marker Sackmann-format data already uses consistently."""
    if not score:
        return 0
    upper = score.upper()
    return 1 if any(m in upper for m in RETIRED_MARKERS) else 0


def _match_id(player_a: str, player_b: str, match_date: str) -> str:
    """Same real derivation tennis_warehouse_schema.sql already
    documents for the matches table: sorted(player pair) + date."""
    a, b = sorted([player_a, player_b])
    return f"{a}|{b}|{match_date}"


def _iter_csv_rows(filepath: Path):
    """Yields (fieldnames, row_dict) for every real data row in one
    file, transparently handling the headerless case. Returns
    (None, None) once via a sentinel if the file has a real header
    but is missing winner_name/loser_name entirely (same skip
    condition build_name_reference.py already established)."""
    with open(filepath, newline="", encoding="utf-8", errors="replace") as f:
        first_line = f.readline()
        f.seek(0)
        if _has_real_header(first_line):
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
        else:
            reader = csv.DictReader(f, fieldnames=FALLBACK_HEADER)
            fieldnames = FALLBACK_HEADER

        if "winner_name" not in fieldnames or "loser_name" not in fieldnames:
            return  # real file, but not one this importer can use — caller counts this as skipped

        for row in reader:
            yield row


def import_historical_matches(root_folder: str, db_path=None, commit_every: int = 5000):
    """
    Real end-to-end import. Walks root_folder recursively for every
    .csv file (same real approach build_name_reference.py already
    uses), and upserts real match rows into Dataset B's `matches`
    table via INSERT OR IGNORE.

    Returns a real summary dict — every count here reflects an actual
    outcome, not an assumption: files_processed, files_skipped
    (no usable winner_name/loser_name columns), rows_read,
    rows_inserted (genuinely new), rows_ignored_duplicate (match_id
    already present — either from a prior run of this importer or
    from the live V8 collector), rows_skipped_missing_names,
    rows_skipped_bad_date.
    """
    conn = _conn(db_path)
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}

    stats = {
        "files_processed": 0, "files_skipped": 0, "rows_read": 0,
        "rows_inserted": 0, "rows_ignored_duplicate": 0,
        "rows_skipped_missing_names": 0, "rows_skipped_bad_date": 0,
    }

    try:
        csv_files = sorted(Path(root_folder).rglob("*.csv"))
        pending = 0
        for filepath in csv_files:
            tour = _tour_from_filename(filepath.name)
            saw_any_row = False
            for row in _iter_csv_rows(filepath):
                saw_any_row = True
                stats["rows_read"] += 1

                winner_name = (row.get("winner_name") or "").strip()
                loser_name = (row.get("loser_name") or "").strip()
                if not winner_name or not loser_name:
                    stats["rows_skipped_missing_names"] += 1
                    continue

                match_date = _iso_date(row.get("tourney_date", ""))
                if not match_date:
                    stats["rows_skipped_bad_date"] += 1
                    continue

                surface = (row.get("surface") or "").strip() or None
                tournament = (row.get("tourney_name") or "").strip() or None
                score = (row.get("score") or "").strip() or None
                match_id = _match_id(winner_name, loser_name, match_date)
                retired = _is_retired(score)
                now = datetime.now(timezone.utc).isoformat()

                # FIXED 2026-08-07 (real bug found + fixed this session):
                # player_a/player_b must NOT correlate with who won -- doing
                # so silently rigs any later "did player_a win" backtest
                # label. Alphabetical order is a stable, winner-independent
                # assignment. `winner` (below) still always names the real
                # winner correctly, independent of the a/b assignment.
                player_a, player_b = sorted([winner_name, loser_name])

                cur = conn.execute(
                    "INSERT OR IGNORE INTO matches "
                    "(match_id, tour, player_a, player_b, winner, surface, "
                    "tournament, match_date, score, retired, source, collected_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (match_id, tour, player_a, player_b, winner_name,
                     surface, tournament, match_date, score, retired,
                     "HISTORICAL_CSV", now)
                )
                if cur.rowcount == 1:
                    stats["rows_inserted"] += 1
                else:
                    stats["rows_ignored_duplicate"] += 1

                pending += 1
                if pending >= commit_every:
                    conn.commit()
                    pending = 0

            if saw_any_row:
                stats["files_processed"] += 1
            else:
                stats["files_skipped"] += 1

        conn.commit()
        return {"status": "ok", **stats}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e), **stats}
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 historical_match_importer.py \"<folder path>\"")
        sys.exit(1)
    result = import_historical_matches(sys.argv[1])
    print(result)
