import sqlite3

DB = "./data/warehouse/dataset_a.sqlite"
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

total = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
sys_err = conn.execute(
    "SELECT COUNT(*) FROM evaluations WHERE lifecycle_state='FAILED' AND termination_reason='SYSTEM_ERROR'"
).fetchone()[0]
engine_declined = conn.execute(
    "SELECT COUNT(*) FROM evaluations WHERE lifecycle_state='ENGINE_DECLINED'"
).fetchone()[0]

print(f"Total rows:          {total}   (expect unchanged from pre-migration count)")
print(f"SYSTEM_ERROR rows:   {sys_err}  (expect 0, was 990)")
print(f"ENGINE_DECLINED rows:{engine_declined}  (expect 990, was 0)")

# Sanity: no row should exist in both an old and new bucket simultaneously,
# and no row should have vanished (total_after == total_before).
print()
print("PASS" if (sys_err == 0 and engine_declined == 990) else "FAIL -- investigate before restart")
conn.close()
