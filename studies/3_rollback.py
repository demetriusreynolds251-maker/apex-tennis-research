"""
Restores dataset_a.sqlite from the pre-migration backup. Only run this if
1_migrate.py or 4_backfill.py produced a verified-bad result -- this
discards ANY writes made to the live DB since the backup was taken,
including any real prop activity in between, so confirm that tradeoff
before running.
"""
import shutil, os, sys

DB = "./data/warehouse/dataset_a.sqlite"
BACKUP = "./backups/2026-09-28_p0_incident/dataset_a.sqlite.pre_migration"

if not os.path.exists(BACKUP):
    print("ABORT: backup file not found, nothing to roll back to.")
    sys.exit(1)

confirm = input(f"This will OVERWRITE {DB} with the pre-migration backup, "
                f"discarding any writes since. Type 'ROLLBACK' to confirm: ")
if confirm != "ROLLBACK":
    print("Not confirmed, aborting.")
    sys.exit(1)

shutil.copy2(DB, DB + ".pre_rollback_safety_copy")
shutil.copy2(BACKUP, DB)
print(f"Rolled back. Pre-rollback state saved to {DB}.pre_rollback_safety_copy")
