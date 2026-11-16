"""
Backfills the 990 historical FAILED/SYSTEM_ERROR rows that are actually
engine declines (100% confirmed match on the decline-text pattern -- see
the Phase 2 investigation report) to ENGINE_DECLINED. Only touches rows
matching BOTH the exact eval_id list AND the current-state guard, so it
is a no-op / safe to re-run if it's ever run twice.
"""
import sqlite3

DB = "./data/warehouse/dataset_a.sqlite"

# Exact 990-row candidate set (regenerate with the query below if you want
# to re-derive it fresh rather than trust this list -- both should match):
#   SELECT eval_id FROM evaluations
#   WHERE lifecycle_state='FAILED' AND termination_reason='SYSTEM_ERROR'
#     AND (termination_detail LIKE '%declined%' OR termination_detail LIKE '%ApexEngine%'
#          OR termination_detail LIKE '%engine declined%' OR termination_detail LIKE '%no result%'
#          OR termination_detail LIKE '%-> legacy%')
BACKFILL_QUERY = """
    SELECT eval_id FROM evaluations
    WHERE lifecycle_state='FAILED' AND termination_reason='SYSTEM_ERROR'
      AND (
        termination_detail LIKE '%declined%'
        OR termination_detail LIKE '%ApexEngine%'
        OR termination_detail LIKE '%engine declined%'
        OR termination_detail LIKE '%no result%'
        OR termination_detail LIKE '%-> legacy%'
      )
"""

conn = sqlite3.connect(DB, timeout=10)

# Verify schema is migrated first -- refuse to backfill into a CHECK
# constraint that would just reject every row.
ddl = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='evaluations'"
).fetchone()[0]
if "ENGINE_DECLINED" not in ddl:
    print("ABORT: schema not migrated yet -- run 1_migrate.py first.")
    raise SystemExit(1)

eval_ids = [r[0] for r in conn.execute(BACKFILL_QUERY).fetchall()]
print(f"Candidate rows: {len(eval_ids)} (expected: 990)")

conn.execute("BEGIN")
placeholders = ",".join("?" * len(eval_ids))
cur = conn.execute(
    f"""UPDATE evaluations
        SET lifecycle_state='ENGINE_DECLINED', termination_reason='ENGINE_DECLINED'
        WHERE eval_id IN ({placeholders})
          AND lifecycle_state='FAILED' AND termination_reason='SYSTEM_ERROR'""",
    eval_ids,
)
updated = cur.rowcount
conn.commit()
print(f"Rows updated: {updated}")
conn.close()
