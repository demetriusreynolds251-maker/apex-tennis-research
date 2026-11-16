"""
Schema migration: widen evaluations.lifecycle_state and
evaluations.termination_reason CHECK constraints to allow ENGINE_DECLINED.
SQLite cannot ALTER a CHECK constraint in place, so this rebuilds the table
(standard SQLite pattern: create new table with the new DDL, copy every row
verbatim, drop old, rename new -> old), inside a single transaction.
Run this BEFORE 4_backfill.py, and BEFORE restarting the bot.
"""
import sqlite3, os, sys, shutil, datetime

DB = "./data/warehouse/dataset_a.sqlite"
BACKUP_DIR = "./backups/2026-09-28_p0_incident"
BACKUP = os.path.join(BACKUP_DIR, "dataset_a.sqlite.pre_migration")

os.makedirs(BACKUP_DIR, exist_ok=True)
if not os.path.exists(BACKUP):
    shutil.copy2(DB, BACKUP)
    print(f"Backup created: {BACKUP}")
else:
    print(f"Backup already exists, leaving it as-is: {BACKUP}")

conn = sqlite3.connect(DB, timeout=10)
conn.execute("PRAGMA foreign_keys=OFF")

before_total = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
before_sys_err = conn.execute(
    "SELECT COUNT(*) FROM evaluations WHERE lifecycle_state='FAILED' AND termination_reason='SYSTEM_ERROR'"
).fetchone()[0]
print(f"BEFORE: total={before_total}, SYSTEM_ERROR={before_sys_err}")

cur_ddl = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='evaluations'"
).fetchone()[0]

if "ENGINE_DECLINED" in cur_ddl:
    print("ENGINE_DECLINED already present in schema -- nothing to do. Exiting.")
    sys.exit(0)

new_ddl = cur_ddl.replace(
    "'FAILED',\n                            'NO_PLAY',",
    "'FAILED',\n                            'ENGINE_DECLINED',\n                            'NO_PLAY',",
)
new_ddl = new_ddl.replace(
    "                            'SYSTEM_ERROR',\n                            'NO_PLAY'",
    "                            'SYSTEM_ERROR',\n                            'ENGINE_DECLINED',\n                            'NO_PLAY'",
)
new_ddl = new_ddl.replace("CREATE TABLE evaluations", "CREATE TABLE evaluations_new")

assert new_ddl.count("ENGINE_DECLINED") == cur_ddl.count("ENGINE_DECLINED") + 2, \
    "DDL widen produced an unexpected number of ENGINE_DECLINED occurrences -- abort, do not proceed manually"

cols = [r[1] for r in conn.execute("PRAGMA table_info(evaluations)").fetchall()]
col_list = ", ".join(cols)

# capture existing indexes on evaluations so they can be recreated after rename
idx_rows = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='evaluations' AND sql IS NOT NULL"
).fetchall()

try:
    conn.execute("BEGIN")
    conn.execute(new_ddl)
    conn.execute(f"INSERT INTO evaluations_new ({col_list}) SELECT {col_list} FROM evaluations")
    copied = conn.execute("SELECT COUNT(*) FROM evaluations_new").fetchone()[0]
    if copied != before_total:
        raise RuntimeError(f"row count mismatch after copy: {copied} != {before_total}")
    conn.execute("DROP TABLE evaluations")
    conn.execute("ALTER TABLE evaluations_new RENAME TO evaluations")
    for (idx_sql,) in idx_rows:
        conn.execute(idx_sql)
    conn.commit()
except Exception as e:
    conn.rollback()
    print(f"MIGRATION FAILED, rolled back, database unchanged: {e}")
    sys.exit(1)

after_total = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
print(f"Migration committed. Rows preserved: {after_total} (before: {before_total})")
print(f"Indexes recreated: {len(idx_rows)}")
conn.close()
