"""
historical_match_enrichment.py
2026-08-07 — enriches Dataset B's `matches` table with the fields
S2, S4, and S5's real backtests need, none of which the original
historical_match_importer.py captured (it was deliberately scoped to
ELO-only fields).

Real fields added, self-healing (ALTER TABLE IF NOT EXISTS pattern,
same philosophy as _ensure_moneyline_detail_columns()):
  - round        (TEXT)  -- real CSV column, e.g. "R32", "QF", "F"
  - best_of      (INT)   -- real CSV column, 3 or 5
  - tourney_id   (TEXT)  -- real CSV column, precise event-edition key
                            (better than tournament NAME for grouping
                            "matches in the same real event")
  - set_count    (INT)   -- DERIVED from the real `score` string (not
                            best_of, which is the format not the
                            actual outcome) -- counts real completed
                            sets, excluding RET/W-O/DEF markers
  - player_a/b_svgms, _bp_faced, _bp_saved (INT) -- real box-score
    columns (w_SvGms/w_bpFaced/w_bpSaved, mirrored for l_*), needed to
    derive season hold_pct/break_pct/bp_save_pct for S5's real
    dominance_score formula (confirmed from compute_ml_dominance_score()
    this session, not guessed):
        dominance_score = 0.35*hold_pct_gap + 0.25*break_pct_gap +
                           0.15*bp_save_pct_gap + 0.25*win_pct_gap

THIS IS AN ENRICHMENT PASS, NOT A RE-IMPORT: the original 518,032
historical rows already exist. This script UPSERTs via
ON CONFLICT...DO UPDATE, filling in ONLY currently-NULL fields
(COALESCE(existing, new)) -- it can NEVER overwrite a real value
already on file, whether from the original historical import or from
the live V8 collector. Safe to run on top of the existing data,
and safe to re-run (idempotent).
"""
import csv
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "data" / "warehouse" / "tennis_warehouse.sqlite"

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
# Real set-score token: one or two digits, dash, one or two digits,
# optional parenthesized tiebreak score -- e.g. "6-4", "7-6(5)", "10-8"
SET_TOKEN = re.compile(r"^\d{1,2}-\d{1,2}(\(\d+\))?$")


def _conn():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH), timeout=30)


def _ensure_columns(conn):
    """Self-healing column add -- checks what already exists first,
    only adds what's missing, same pattern as
    _ensure_moneyline_detail_columns()."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(matches)").fetchall()}
    new_cols = {
        "round": "TEXT", "best_of": "INTEGER", "tourney_id": "TEXT",
        "player_a_svgms": "INTEGER", "player_a_bp_faced": "INTEGER", "player_a_bp_saved": "INTEGER",
        "player_b_svgms": "INTEGER", "player_b_bp_faced": "INTEGER", "player_b_bp_saved": "INTEGER",
        # Added 2026-08-07: player_a/b_aces and _double_faults already
        # existed in the ORIGINAL schema (for live V8 collection) but
        # were never populated for historical rows -- a real gap, same
        # category as svgms/bp_faced/bp_saved above, closed the same
        # way. Real CSV source columns (w_ace/l_ace, w_df/l_df) were
        # already being read into FALLBACK_HEADER, just never used.
        "player_a_aces": "INTEGER", "player_a_double_faults": "INTEGER",
        "player_b_aces": "INTEGER", "player_b_double_faults": "INTEGER",
    }
    for col, coltype in new_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {coltype}")
    conn.commit()


def _has_real_header(first_line: str) -> bool:
    return first_line.split(",", 1)[0].strip() == "tourney_id"


def _tour_from_filename(filename: str) -> str:
    return "WTA" if "_wta" in filename.lower() else "ATP"


def _iso_date(raw: str):
    if not raw or len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _real_set_count(score: str):
    """Counts real completed sets by parsing the actual score string.
    Returns None if the score is empty/unparseable rather than
    guessing. A retired/walkover match still counts the real completed
    sets before the stoppage -- e.g. '6-2 3-2 RET' is a real 2-set
    match, not a 3-set one, since only 2 sets have real scores."""
    if not score:
        return None
    tokens = score.strip().split()
    real_sets = [t for t in tokens if SET_TOKEN.match(t)]
    return len(real_sets) if real_sets else None


def _int_or_none(raw):
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return None


def _match_id(player_a: str, player_b: str, match_date: str) -> str:
    a, b = sorted([player_a, player_b])
    return f"{a}|{b}|{match_date}"


def _iter_csv_rows(filepath: Path):
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
            return
        for row in reader:
            yield row


def enrich_historical_matches(root_folder: str, commit_every: int = 5000):
    """
    Real end-to-end enrichment. Walks the same real archive the
    original importer used, but this time extracts round/best_of/
    tourney_id/box-score fields and set_count (derived from score),
    then UPSERTs with COALESCE so only currently-NULL fields ever get
    filled -- a real value already on file (historical OR live V8)
    is never touched.
    """
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}

    stats = {
        "files_processed": 0, "files_skipped": 0, "rows_read": 0,
        "rows_upserted": 0, "rows_skipped_missing_names": 0,
        "rows_skipped_bad_date": 0, "rows_with_set_count": 0,
        "rows_with_box_score": 0, "rows_with_aces": 0,
    }

    try:
        _ensure_columns(conn)
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
                tourney_id = (row.get("tourney_id") or "").strip() or None
                score = (row.get("score") or "").strip() or None
                round_ = (row.get("round") or "").strip() or None
                best_of = _int_or_none(row.get("best_of"))
                set_count = _real_set_count(score)
                match_id = _match_id(winner_name, loser_name, match_date)

                # FIXED 2026-08-07 (real bug found + fixed this session):
                # player_a/player_b must be winner-INDEPENDENT (alphabetical),
                # matching the corrected historical_match_importer.py. Box
                # score fields are attached based on which real name -- not
                # which a/b slot -- actually produced them.
                player_a, player_b = sorted([winner_name, loser_name])
                winner_is_a = (winner_name == player_a)
                pa_svgms = _int_or_none(row.get("w_SvGms") if winner_is_a else row.get("l_SvGms"))
                pa_bp_faced = _int_or_none(row.get("w_bpFaced") if winner_is_a else row.get("l_bpFaced"))
                pa_bp_saved = _int_or_none(row.get("w_bpSaved") if winner_is_a else row.get("l_bpSaved"))
                pb_svgms = _int_or_none(row.get("l_SvGms") if winner_is_a else row.get("w_SvGms"))
                pb_bp_faced = _int_or_none(row.get("l_bpFaced") if winner_is_a else row.get("w_bpFaced"))
                pb_bp_saved = _int_or_none(row.get("l_bpSaved") if winner_is_a else row.get("w_bpSaved"))
                # Same winner/loser-aware derivation for aces + double faults --
                # real gap closed 2026-08-07, same pattern as the box-score fields above.
                pa_aces = _int_or_none(row.get("w_ace") if winner_is_a else row.get("l_ace"))
                pa_df = _int_or_none(row.get("w_df") if winner_is_a else row.get("l_df"))
                pb_aces = _int_or_none(row.get("l_ace") if winner_is_a else row.get("w_ace"))
                pb_df = _int_or_none(row.get("l_df") if winner_is_a else row.get("w_df"))

                if set_count is not None:
                    stats["rows_with_set_count"] += 1
                if pa_svgms is not None and pb_svgms is not None:
                    stats["rows_with_box_score"] += 1
                if pa_aces is not None and pb_aces is not None:
                    stats["rows_with_aces"] += 1

                now = datetime.now(timezone.utc).isoformat()
                cur = conn.execute(
                    "INSERT INTO matches "
                    "(match_id, tour, player_a, player_b, winner, surface, "
                    "tournament, match_date, score, source, collected_at, "
                    "round, best_of, tourney_id, set_count, "
                    "player_a_svgms, player_a_bp_faced, player_a_bp_saved, "
                    "player_b_svgms, player_b_bp_faced, player_b_bp_saved, "
                    "player_a_aces, player_a_double_faults, "
                    "player_b_aces, player_b_double_faults) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(match_id) DO UPDATE SET "
                    "round = COALESCE(matches.round, excluded.round), "
                    "best_of = COALESCE(matches.best_of, excluded.best_of), "
                    "tourney_id = COALESCE(matches.tourney_id, excluded.tourney_id), "
                    "set_count = COALESCE(matches.set_count, excluded.set_count), "
                    "player_a_svgms = COALESCE(matches.player_a_svgms, excluded.player_a_svgms), "
                    "player_a_bp_faced = COALESCE(matches.player_a_bp_faced, excluded.player_a_bp_faced), "
                    "player_a_bp_saved = COALESCE(matches.player_a_bp_saved, excluded.player_a_bp_saved), "
                    "player_b_svgms = COALESCE(matches.player_b_svgms, excluded.player_b_svgms), "
                    "player_b_bp_faced = COALESCE(matches.player_b_bp_faced, excluded.player_b_bp_faced), "
                    "player_b_bp_saved = COALESCE(matches.player_b_bp_saved, excluded.player_b_bp_saved), "
                    "player_a_aces = COALESCE(matches.player_a_aces, excluded.player_a_aces), "
                    "player_a_double_faults = COALESCE(matches.player_a_double_faults, excluded.player_a_double_faults), "
                    "player_b_aces = COALESCE(matches.player_b_aces, excluded.player_b_aces), "
                    "player_b_double_faults = COALESCE(matches.player_b_double_faults, excluded.player_b_double_faults)",
                    (match_id, tour, player_a, player_b, winner_name, surface,
                     tournament, match_date, score, "HISTORICAL_CSV", now,
                     round_, best_of, tourney_id, set_count,
                     pa_svgms, pa_bp_faced, pa_bp_saved,
                     pb_svgms, pb_bp_faced, pb_bp_saved,
                     pa_aces, pa_df, pb_aces, pb_df)
                )
                stats["rows_upserted"] += cur.rowcount

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
        print("Usage: python3 historical_match_enrichment.py \"<folder path>\"")
        sys.exit(1)
    result = enrich_historical_matches(sys.argv[1])
    print(result)
