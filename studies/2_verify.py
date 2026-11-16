import sqlite3

DB = "./data/warehouse/dataset_a.sqlite"
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

ddl = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='evaluations'"
).fetchone()[0]

ok = ddl.count("ENGINE_DECLINED") == 2  # one in lifecycle_state clause, one in termination_reason clause
print(f"ENGINE_DECLINED present in both CHECK clauses: {ok} (found {ddl.count('ENGINE_DECLINED')}x)")

# Prove the constraint actually accepts an ENGINE_DECLINED row (rolled back, never committed)
try:
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO evaluations (eval_id, created_at, evaluation_type, lifecycle_state, "
        "termination_reason, player, opponent) VALUES "
        "('__verify_test__', datetime('now'), 'PROP', 'ENGINE_DECLINED', 'ENGINE_DECLINED', 'x', 'y')"
    )
    print("INSERT with ENGINE_DECLINED succeeded (constraint accepts it).")
except Exception as e:
    print(f"INSERT with ENGINE_DECLINED FAILED -- migration did not take: {e}")
finally:
    conn.execute("ROLLBACK")  # never actually commit this test row

conn.close()
