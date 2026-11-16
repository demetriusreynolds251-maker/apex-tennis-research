"""
Unit tests for reap_stale_evaluations() -- run standalone against a
disposable temp DB, never against the real dataset_a.sqlite.
"""
import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


class TestReapStaleEvaluations(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_dataset_a.sqlite")

        # Build a minimal evaluations table matching the real schema's
        # relevant columns only -- enough for the reaper's own query and
        # for transition()/terminate() to operate on.
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE evaluations (
                eval_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                evaluation_type TEXT NOT NULL,
                lifecycle_state TEXT NOT NULL DEFAULT 'RESEARCH_STARTED',
                lifecycle_updated_at TEXT,
                termination_reason TEXT,
                termination_detail TEXT,
                final_grade TEXT,
                player TEXT NOT NULL,
                opponent TEXT NOT NULL,
                market TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE lifecycle_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eval_id TEXT, from_state TEXT, to_state TEXT,
                detail TEXT, occurred_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE capture_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT, function_name TEXT, eval_id TEXT,
                error_type TEXT, error_message TEXT, args_summary TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Point a fresh import of dataset_a_capture at this temp DB.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import dataset_a_capture as d1
        importlib.reload(d1)
        d1.DB_PATH = Path(self.db_path)
        self.d1 = d1

    def _insert(self, eval_id, state, age_minutes):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO evaluations (eval_id, created_at, evaluation_type, "
            "lifecycle_state, lifecycle_updated_at, player, opponent, market) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (eval_id, ts, "PROP", state, ts, "Test Player", "Test Opp", "aces"),
        )
        conn.commit()
        conn.close()

    def test_reaps_stale_non_terminal_row(self):
        eid = str(uuid.uuid4())
        self._insert(eid, "RESEARCH_STARTED", age_minutes=60)  # older than 45min
        reaped = self.d1.reap_stale_evaluations(stale_minutes=45)
        self.assertEqual(len(reaped), 1)
        self.assertEqual(reaped[0]["eval_id"], eid)
        self.assertEqual(reaped[0]["prior_state"], "RESEARCH_STARTED")

    def test_does_not_reap_recent_row(self):
        eid = str(uuid.uuid4())
        self._insert(eid, "RESEARCH_STARTED", age_minutes=10)  # well under 45min
        reaped = self.d1.reap_stale_evaluations(stale_minutes=45)
        self.assertEqual(len(reaped), 0)

    def test_does_not_reap_terminal_row(self):
        eid = str(uuid.uuid4())
        self._insert(eid, "POSTED", age_minutes=999)  # old but already terminal
        reaped = self.d1.reap_stale_evaluations(stale_minutes=45)
        self.assertEqual(len(reaped), 0)

    def test_does_not_reap_row_at_exactly_the_boundary(self):
        eid = str(uuid.uuid4())
        self._insert(eid, "RESEARCH_STARTED", age_minutes=44)  # just under 45
        reaped = self.d1.reap_stale_evaluations(stale_minutes=45)
        self.assertEqual(len(reaped), 0)

    def test_reaped_row_actually_terminated_in_db(self):
        eid = str(uuid.uuid4())
        self._insert(eid, "EVALUATION_COMPLETE", age_minutes=90)
        self.d1.reap_stale_evaluations(stale_minutes=45)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_state, termination_reason FROM evaluations WHERE eval_id=?",
            (eid,),
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "FAILED")
        self.assertEqual(row[1], "SYSTEM_ERROR")

    def test_multiple_stale_states_all_reaped(self):
        ids = {}
        for state in self.d1.STALE_NON_TERMINAL_STATES:
            eid = str(uuid.uuid4())
            ids[eid] = state
            self._insert(eid, state, age_minutes=50)
        reaped = self.d1.reap_stale_evaluations(stale_minutes=45)
        self.assertEqual(len(reaped), len(ids))
        self.assertEqual({r["eval_id"] for r in reaped}, set(ids.keys()))

    def test_custom_threshold_respected(self):
        eid = str(uuid.uuid4())
        self._insert(eid, "RESEARCH_STARTED", age_minutes=20)
        # not stale at the 45min default
        self.assertEqual(len(self.d1.reap_stale_evaluations(stale_minutes=45)), 0)
        # but is stale at a tighter 15min threshold
        self.assertEqual(len(self.d1.reap_stale_evaluations(stale_minutes=15)), 1)

    def test_never_raises_on_missing_db(self):
        self.d1.DB_PATH = Path("/nonexistent/path/does_not_exist.sqlite")
        # @_safe's actual contract: catches and swallows the exception,
        # returning None -- the guarantee under test is "did not raise",
        # not any particular return value.
        try:
            result = self.d1.reap_stale_evaluations(stale_minutes=45)
        except Exception as e:
            self.fail(f"reap_stale_evaluations raised {e!r} instead of being caught by @_safe")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
