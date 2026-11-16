"""
fix_player_ab_assignment.py
2026-08-07 — real, one-time fix for a serious bug in
historical_match_importer.py: it stored player_a = winner_name for
EVERY historical row, making "did player_a win" a rigged question
with the same answer every time for ~518K of Dataset B's ~520K rows.
This silently corrupted every AUC backtest that used "player_a won"
as its label (ELO, S1, S4 all affected -- their real results from
earlier tonight need to be re-run after this fix).

THE FIX: reassign player_a/player_b using a winner-INDEPENDENT rule
-- alphabetical order of the two names. `winner` (which names the
actual winner, independent of a/b) is never touched. All per-player
"_a"/"_b" suffixed fields (aces, double_faults, first_serve_in/of,
svgms, bp_faced, bp_saved) are swapped together with player_a/
player_b so they stay correctly attached to the right real player.

Does NOT touch `match_id` -- the schema's own derivation
(sorted(player pair) + date) is ALREADY alphabetically stable
regardless of which one was originally called "player_a", so no
primary-key collision risk and no need to delete+reinsert rows.

SAFE FOR ALL ROWS, not just historical ones: this reassigns EVERY
row (including any pre-existing live V8-collected rows) to the same
canonical "player_a alphabetically <= player_b" convention. This is
deliberate -- it doesn't matter what convention the live collector
originally used, since real facts (who won, and each player's own
stats) are fully preserved through a symmetric swap. One single
consistent convention going forward, for every row.

Confirmed via direct test before writing this: SQLite evaluates an
UPDATE's SET clause using the row's PRE-update values for every
expression (simultaneous, not sequential) -- so `SET player_a =
player_b, player_b = player_a` performs a real, correct swap in one
statement, not a corruption.
"""
from elo_ops import _conn


# Real per-player fields that must swap together with player_a/player_b
# so they stay attached to the correct real player. Checked dynamically
# against the actual table (not hardcoded blindly) so this works whether
# or not historical_match_enrichment.py's newer box-score columns exist.
CANDIDATE_PAIRED_COLUMNS = [
    "aces", "double_faults", "first_serve_in", "first_serve_of",
    "svgms", "bp_faced", "bp_saved",
]


def _existing_paired_columns(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(matches)").fetchall()}
    return [c for c in CANDIDATE_PAIRED_COLUMNS
            if f"player_a_{c}" in cols and f"player_b_{c}" in cols]


def fix_player_ab_assignment():
    """
    Real one-time migration. Returns real counts: how many rows were
    already correctly ordered (untouched) vs how many needed the swap.
    """
    conn = _conn()
    if not conn:
        return {"status": "offline", "message": "Warehouse database not accessible"}

    try:
        before_total = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE player_a IS NOT NULL AND player_b IS NOT NULL"
        ).fetchone()[0]
        needs_swap = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE player_a > player_b"
        ).fetchone()[0]

        paired = _existing_paired_columns(conn)
        set_clauses = ["player_a = player_b", "player_b = player_a"]
        for c in paired:
            set_clauses.append(f"player_a_{c} = player_b_{c}")
            set_clauses.append(f"player_b_{c} = player_a_{c}")

        sql = f"UPDATE matches SET {', '.join(set_clauses)} WHERE player_a > player_b"
        cur = conn.execute(sql)
        rows_swapped = cur.rowcount
        conn.commit()

        # Real sanity check after the fix: confirm no row is left
        # out of order, and confirm `winner` still matches one side
        # (never touched, but verifying nothing else broke it).
        still_out_of_order = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE player_a > player_b"
        ).fetchone()[0]
        winner_mismatch = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE winner IS NOT NULL "
            "AND winner != player_a AND winner != player_b"
        ).fetchone()[0]

        return {
            "status": "ok",
            "total_rows_checked": before_total,
            "rows_needed_swap": needs_swap,
            "rows_swapped": rows_swapped,
            "paired_columns_swapped": paired,
            "still_out_of_order_after_fix": still_out_of_order,
            "winner_mismatch_after_fix": winner_mismatch,
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


if __name__ == "__main__":
    print(fix_player_ab_assignment())
