"""
test_dataset_a.py — validates the Dataset A capture layer BEFORE it
touches production, per operator directive: "I do not want Dataset A's
first validation run to occur in production."

Covers the 10 objectives, in order:
 1. eval_id creation (one per evaluation, stable, no duplicates)
 2. Lifecycle progression through all valid transitions
 3. Failure capture (rows survive every failure path)
 4. NO_PLAY does not route through failure handling
 5. Rule 28 dedup still produces a valid record (the original reason
    Dataset A exists)
 6. Moneyline compatibility (evaluation_type=MONEYLINE)
 7. Outcome linking (win_loss_alert / pending_results_json / manual_override)
 8. SQLite integrity (schema creation, inserts, updates, uniqueness, indexes)
 9. Fail-silent guarantee (DB unavailable/locked/write-failure never raises,
    never blocks the caller)
10. Historical auditability (a completed row answers what/why/what
    rule/what changed confidence/what was the result, without relying on
    reasoning text alone)

Run: pytest test_dataset_a.py -v
"""

import sqlite3
import json
import uuid as uuid_module
import pytest

import dataset_a_capture as d1


# ─────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolated SQLite DB per test — schema applied fresh, DB_PATH
    monkeypatched so no test can ever touch a real warehouse file."""
    db_path = tmp_path / "dataset_a_test.sqlite"
    schema_sql = (Path := __import__("pathlib").Path)(__file__).parent.joinpath(
        "dataset_a_schema.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_sql)
    conn.close()
    monkeypatch.setattr(d1, "DB_PATH", db_path)
    return db_path


def _row(db_path, eval_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM evaluations WHERE eval_id = ?", (eval_id,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def _lifecycle_rows(db_path, eval_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT * FROM lifecycle_log WHERE eval_id = ? ORDER BY log_id", (eval_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _start_basic(db_path, evaluation_type="PROP"):
    eid = d1.new_eval_id()
    d1.start(eid, evaluation_type, "Novak Djokovic", "Carlos Alcaraz",
             tour="ATP", tournament="Wimbledon", round_="F", surface="Grass",
             market="double_faults", line=2.5)
    return eid


# ─────────────────────────────────────────────────────────────────────
# 1. eval_id creation
# ─────────────────────────────────────────────────────────────────────

def test_eval_id_is_unique_uuid():
    ids = {d1.new_eval_id() for _ in range(500)}
    assert len(ids) == 500
    for i in ids:
        uuid_module.UUID(i)  # raises if not a valid UUID


def test_one_eval_id_per_evaluation_no_duplicate_rows(db):
    eid = _start_basic(db)
    # Calling start() again with the same eval_id must NOT create a
    # second row (ON CONFLICT DO NOTHING) — this is what "stable identity"
    # actually depends on.
    d1.start(eid, "PROP", "Novak Djokovic", "Carlos Alcaraz")
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM evaluations WHERE eval_id = ?", (eid,)).fetchone()[0]
    conn.close()
    assert count == 1


def test_eval_id_stable_through_full_lifecycle(db):
    eid = _start_basic(db)
    d1.transition(eid, "RESEARCH_COMPLETE")
    d1.transition(eid, "EVALUATION_COMPLETE", eval_confidence=0.74)
    d1.transition(eid, "COMPLIANCE_COMPLETE", compliance_category="B")
    d1.transition(eid, "SCORING_COMPLETE", final_confidence=0.71, final_grade="GREEN")
    d1.transition(eid, "POSTED", posted=1)
    row = _row(db, eid)
    assert row["eval_id"] == eid  # never changed
    assert row["lifecycle_state"] == "POSTED"


# ─────────────────────────────────────────────────────────────────────
# 2. Lifecycle progression
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    ["RESEARCH_COMPLETE", "EVALUATION_COMPLETE", "COMPLIANCE_COMPLETE",
     "SCORING_COMPLETE", "POSTED"],
])
def test_happy_path_progression(db, path):
    eid = _start_basic(db)
    prev = "RESEARCH_STARTED"
    for state in path:
        d1.transition(eid, state)
        row = _row(db, eid)
        assert row["lifecycle_state"] == state
        prev = state


def test_rejected_is_a_valid_terminal_state(db):
    eid = _start_basic(db)
    d1.terminate(eid, "GATE11_REJECTED")
    row = _row(db, eid)
    assert row["lifecycle_state"] == "REJECTED"
    assert row["termination_reason"] == "GATE11_REJECTED"


def test_failed_is_a_valid_terminal_state(db):
    eid = _start_basic(db)
    d1.terminate(eid, "RESEARCH_FAILURE", "connection reset")
    row = _row(db, eid)
    assert row["lifecycle_state"] == "FAILED"
    assert row["termination_reason"] == "RESEARCH_FAILURE"
    assert "connection reset" in (row["termination_detail"] or "")


def test_no_play_is_a_valid_terminal_state(db):
    eid = _start_basic(db, evaluation_type="MONEYLINE")
    d1.no_play(eid, "Phase 1 shows no meaningful structural edge")
    row = _row(db, eid)
    assert row["lifecycle_state"] == "NO_PLAY"
    assert row["termination_reason"] == "NO_PLAY"


def test_lifecycle_log_records_every_transition(db):
    eid = _start_basic(db)
    d1.transition(eid, "RESEARCH_COMPLETE")
    d1.transition(eid, "EVALUATION_COMPLETE")
    d1.terminate(eid, "BROKEN_EVAL")
    log = _lifecycle_rows(db, eid)
    to_states = [r["to_state"] for r in log]
    assert to_states == ["RESEARCH_STARTED", "RESEARCH_COMPLETE",
                          "EVALUATION_COMPLETE", "FAILED"]
    # from_state chain must be contiguous (proves nothing was skipped/lost)
    assert log[1]["from_state"] == "RESEARCH_STARTED"
    assert log[2]["from_state"] == "RESEARCH_COMPLETE"
    assert log[3]["from_state"] == "EVALUATION_COMPLETE"


def test_invalid_lifecycle_state_is_rejected_silently(db):
    """transition() validates against VALID_STATES before touching the DB —
    a typo'd state name must not corrupt the row or raise."""
    eid = _start_basic(db)
    d1.transition(eid, "NOT_A_REAL_STATE")
    row = _row(db, eid)
    assert row["lifecycle_state"] == "RESEARCH_STARTED"  # unchanged


# ─────────────────────────────────────────────────────────────────────
# 3. Failure capture — rows survive, nothing disappears
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("reason,expected_state", [
    ("GATE11_UNVERIFIED", "FAILED"),
    ("BROKEN_EVAL", "FAILED"),
    ("COMPLIANCE_UNPARSEABLE", "FAILED"),
    ("SYSTEM_ERROR", "FAILED"),
    ("RESEARCH_FAILURE", "FAILED"),
    ("RULE28_DEDUP", "REJECTED"),
    ("GATE11_REJECTED", "REJECTED"),
    ("MANUAL_REJECT", "REJECTED"),
    ("ENGINE_DECLINED", "ENGINE_DECLINED"),  # APEX-HOTFIX-2026-09-28 FIX #1
])
def test_every_failure_reason_leaves_a_row(db, reason, expected_state):
    eid = _start_basic(db)
    d1.terminate(eid, reason, f"test detail for {reason}")
    row = _row(db, eid)
    assert row is not None, f"Row disappeared for {reason} — this is the exact bug Dataset A exists to prevent"
    assert row["lifecycle_state"] == expected_state
    assert row["termination_reason"] == reason


def test_unknown_termination_reason_falls_back_to_system_error_not_silently_dropped(db):
    eid = _start_basic(db)
    d1.terminate(eid, "TOTALLY_MADE_UP_REASON", "should not happen in practice")
    row = _row(db, eid)
    assert row is not None
    assert row["termination_reason"] == "SYSTEM_ERROR"


# APEX-HOTFIX-2026-09-28 FIX #1: ENGINE_DECLINED must land in its own
# lifecycle_state, distinct from FAILED -- an intentional, expected
# engine decline (no odds yet, research-collection-only market, etc.)
# is not a system failure and must not pollute failure-rate metrics,
# Mission Control's failed-row panel, or #alerts.

def test_engine_declined_is_not_classified_as_failed(db):
    eid = _start_basic(db)
    d1.terminate(eid, "ENGINE_DECLINED", "declined (Test Player): no usable odds")
    row = _row(db, eid)
    assert row is not None
    assert row["lifecycle_state"] == "ENGINE_DECLINED"
    assert row["lifecycle_state"] != "FAILED"
    assert row["termination_reason"] == "ENGINE_DECLINED"
    assert row["final_grade"] == "ENGINE_DECLINED"
    assert row["final_grade"] != "FAILED"


def test_engine_declined_termination_detail_is_preserved(db):
    eid = _start_basic(db)
    detail = "declined (Test Player): first-set research collection (no projection method yet) [added]"
    d1.terminate(eid, "ENGINE_DECLINED", detail)
    row = _row(db, eid)
    assert row["termination_detail"] == detail


def test_engine_declined_is_queryable_separately_from_real_failures(db):
    """The whole point of the fix: a query for real system failures
    must not accidentally include intentional engine declines, and
    vice versa."""
    real_failure = _start_basic(db)
    d1.terminate(real_failure, "BROKEN_EVAL", "unexpected crash")
    engine_decline = _start_basic(db)
    d1.terminate(engine_decline, "ENGINE_DECLINED", "declined: no usable odds")

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    failed_rows = conn.execute(
        "SELECT eval_id FROM evaluations WHERE lifecycle_state='FAILED'").fetchall()
    declined_rows = conn.execute(
        "SELECT eval_id FROM evaluations WHERE lifecycle_state='ENGINE_DECLINED'").fetchall()
    conn.close()

    failed_ids = {r["eval_id"] for r in failed_rows}
    declined_ids = {r["eval_id"] for r in declined_rows}
    assert real_failure in failed_ids
    assert real_failure not in declined_ids
    assert engine_decline in declined_ids
    assert engine_decline not in failed_ids


# ─────────────────────────────────────────────────────────────────────
# 4. NO_PLAY must never route through terminate()/failure handling
# ─────────────────────────────────────────────────────────────────────

def test_no_play_uses_dedicated_function_not_terminate(db):
    """Structural guarantee, not just a behavioral one: no_play() and
    terminate() are separate functions in the module, so a future edit
    to terminate()'s failure logic cannot accidentally swallow NO_PLAY."""
    assert d1.no_play is not d1.terminate
    import inspect
    terminate_src = inspect.getsource(d1.terminate)
    assert "no_play" not in terminate_src
    assert "NO_PLAY" not in terminate_src


def test_no_play_final_grade_is_not_a_failure_grade(db):
    eid = _start_basic(db, evaluation_type="MONEYLINE")
    d1.no_play(eid)
    row = _row(db, eid)
    assert row["final_grade"] != "FAILED"
    assert row["final_grade"] != "REJECTED"
    assert row["lifecycle_state"] == "NO_PLAY"


# ─────────────────────────────────────────────────────────────────────
# 5. Rule 28 behavior — THE test. Original reason Dataset A exists.
# ─────────────────────────────────────────────────────────────────────

def test_rule28_dedup_preserves_a_fully_scored_green(db):
    """Simulates the exact scenario found in the audit: a prop makes it
    all the way to SCORING_COMPLETE as a GREEN, then gets excluded by
    Rule 28 dedup (same player already on the slip) and never posts.
    Before this patch, that record vanished entirely."""
    eid = _start_basic(db)
    d1.transition(eid, "RESEARCH_COMPLETE")
    d1.transition(eid, "EVALUATION_COMPLETE", eval_confidence=0.76,
                  direction="LESS", dominance_level="HARD")
    d1.transition(eid, "COMPLIANCE_COMPLETE", compliance_category="B")
    d1.transition(eid, "SCORING_COMPLETE", final_confidence=0.74,
                  final_grade="GREEN", confidence_ledger=["no deductions"])

    row_before_dedup = _row(db, eid)
    assert row_before_dedup["final_grade"] == "GREEN"
    assert row_before_dedup["lifecycle_state"] == "SCORING_COMPLETE"

    # Rule 28 fires — same player already on today's slip
    d1.terminate(eid, "RULE28_DEDUP", "Novak Djokovic already on slip")

    row_after_dedup = _row(db, eid)
    assert row_after_dedup is not None, "GREEN pick vanished on Rule 28 exclusion — regression"
    assert row_after_dedup["lifecycle_state"] == "REJECTED"
    assert row_after_dedup["termination_reason"] == "RULE28_DEDUP"
    # Critically: the GREEN grade and full confidence ledger from BEFORE
    # the dedup must still be readable — this is what makes it useful to
    # Learning/Validation/ML later, not just a "something happened" stub.
    assert row_after_dedup["final_confidence"] == 0.74
    assert json.loads(row_after_dedup["confidence_ledger"]) == ["no deductions"]


def test_rule28_survives_both_exclusion_reasons(db):
    """rule_28_agent has two dedup branches (same player / same match) —
    both must terminate correctly."""
    eid1 = _start_basic(db)
    eid2 = d1.new_eval_id()
    d1.start(eid2, "PROP", "Carlos Alcaraz", "Novak Djokovic")  # same match, swapped

    d1.terminate(eid1, "RULE28_DEDUP", "player already on slip")
    d1.terminate(eid2, "RULE28_DEDUP", "match already on slip")

    for eid in (eid1, eid2):
        row = _row(db, eid)
        assert row["termination_reason"] == "RULE28_DEDUP"


# ─────────────────────────────────────────────────────────────────────
# 6. Moneyline compatibility
# ─────────────────────────────────────────────────────────────────────

def test_moneyline_evaluation_type(db):
    eid = _start_basic(db, evaluation_type="MONEYLINE")
    row = _row(db, eid)
    assert row["evaluation_type"] == "MONEYLINE"
    assert row["market"] is None or row["market"] == "double_faults"  # start() defaults unset


def test_moneyline_full_lifecycle_to_green(db):
    eid = d1.new_eval_id()
    d1.start(eid, "MONEYLINE", "Iga Swiatek", "Aryna Sabalenka", tour="WTA")
    d1.transition(eid, "SCORING_COMPLETE", final_confidence=0.78, final_grade="GREEN")
    d1.transition(eid, "POSTED", posted=1)
    row = _row(db, eid)
    assert row["evaluation_type"] == "MONEYLINE"
    assert row["lifecycle_state"] == "POSTED"


def test_moneyline_no_play_flow_A_and_D(db):
    """evaluate_moneyline's Flow A (no structural edge) and Flow D
    (direction disagreement) both terminate as NO_PLAY, not FAILED."""
    eid_a = d1.new_eval_id()
    d1.start(eid_a, "MONEYLINE", "Player A", "Player B")
    d1.no_play(eid_a, "Flow A — no meaningful structural edge")

    eid_d = d1.new_eval_id()
    d1.start(eid_d, "MONEYLINE", "Player C", "Player D")
    d1.no_play(eid_d, "Flow D — Phase 1/Phase 2 direction disagreement")

    for eid in (eid_a, eid_d):
        row = _row(db, eid)
        assert row["lifecycle_state"] == "NO_PLAY"
        assert row["evaluation_type"] == "MONEYLINE"


def test_prop_and_moneyline_coexist_in_same_table(db):
    eid_prop = _start_basic(db, evaluation_type="PROP")
    eid_ml = _start_basic(db, evaluation_type="MONEYLINE")
    conn = sqlite3.connect(db)
    prop_count = conn.execute(
        "SELECT COUNT(*) FROM evaluations WHERE evaluation_type='PROP'").fetchone()[0]
    ml_count = conn.execute(
        "SELECT COUNT(*) FROM evaluations WHERE evaluation_type='MONEYLINE'").fetchone()[0]
    conn.close()
    assert prop_count == 1
    assert ml_count == 1


# ─────────────────────────────────────────────────────────────────────
# 7. Outcome linking
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("source", [
    "win_loss_alert", "pending_results_json", "manual_override"
])
def test_outcome_recorded_from_each_source(db, source):
    eid = _start_basic(db)
    d1.transition(eid, "POSTED", posted=1)
    d1.record_outcome(eid, "HIT", source)
    row = _row(db, eid)
    assert row["outcome"] == "HIT"
    assert row["outcome_source"] == source
    assert row["lifecycle_state"] == "OUTCOME_RECORDED"
    assert row["outcome_recorded_at"] is not None


def test_manual_override_can_overwrite_automated_outcome(db):
    """Operator directive elsewhere: 'Manual overrides always win.' This
    test just confirms the write path allows a second outcome call to
    overwrite the first — Mission Control's precedence logic for WHEN to
    call this is out of scope for Dataset A itself."""
    eid = _start_basic(db)
    d1.transition(eid, "POSTED", posted=1)
    d1.record_outcome(eid, "BUST", "win_loss_alert")
    d1.record_outcome(eid, "HIT", "manual_override")
    row = _row(db, eid)
    assert row["outcome"] == "HIT"
    assert row["outcome_source"] == "manual_override"


# ─────────────────────────────────────────────────────────────────────
# 8. SQLite integrity
# ─────────────────────────────────────────────────────────────────────

def test_schema_creates_all_expected_tables(db):
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"evaluations", "slip_members", "lifecycle_log"}.issubset(tables)


def test_schema_indexes_exist(db):
    conn = sqlite3.connect(db)
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    expected = {"idx_eval_lifecycle", "idx_eval_termination", "idx_eval_grade",
                "idx_eval_player", "idx_eval_outcome", "idx_eval_type"}
    assert expected.issubset(indexes)


def test_eval_id_primary_key_uniqueness_enforced_at_db_level(db):
    eid = _start_basic(db)
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO evaluations (eval_id, created_at, evaluation_type, player, opponent) "
            "VALUES (?,?,?,?,?)", (eid, "2026-01-01", "PROP", "X", "Y"))
    conn.close()


def test_invalid_evaluation_type_rejected_by_check_constraint(db):
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO evaluations (eval_id, created_at, evaluation_type, player, opponent) "
            "VALUES (?,?,?,?,?)",
            (d1.new_eval_id(), "2026-01-01", "NOT_A_TYPE", "X", "Y"))
    conn.close()


def test_invalid_termination_reason_rejected_by_check_constraint(db):
    eid = _start_basic(db)
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE evaluations SET termination_reason = ? WHERE eval_id = ?",
            ("MADE_UP_REASON_NOT_IN_ENUM", eid))
    conn.close()


def test_slip_members_many_to_many(db):
    eid1 = _start_basic(db)
    eid2 = d1.new_eval_id()
    d1.start(eid2, "PROP", "Player X", "Player Y")
    d1.add_slip_member("slip_2026-07-11_001", eid1)
    d1.add_slip_member("slip_2026-07-11_001", eid2)
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM slip_members WHERE slip_id = ?",
        ("slip_2026-07-11_001",)).fetchone()[0]
    conn.close()
    assert count == 2


def test_json_fields_round_trip_correctly(db):
    eid = _start_basic(db)
    ledger = [{"cause": "serve_stat_gate", "delta": -0.02, "note": "sub-0.5 REQ"}]
    flags = ["feature_echo:hold_pct_cited_twice"]
    d1.transition(eid, "SCORING_COMPLETE",
                   confidence_ledger=ledger, feature_echo_flags=flags)
    row = _row(db, eid)
    assert json.loads(row["confidence_ledger"]) == ledger
    assert json.loads(row["feature_echo_flags"]) == flags


# ─────────────────────────────────────────────────────────────────────
# 9. Fail-silent guarantee — MANDATORY, per operator directive
# ─────────────────────────────────────────────────────────────────────

def test_start_never_raises_when_db_path_is_unwritable(monkeypatch, tmp_path):
    bad_path = tmp_path / "nonexistent_dir" / "readonly" / "dataset_a.sqlite"
    monkeypatch.setattr(d1, "DB_PATH", bad_path)
    # Make the parent chain impossible to create by pointing at a file
    # where a directory is expected
    blocker = tmp_path / "nonexistent_dir"
    blocker.write_text("I am a file, not a directory")
    eid = d1.new_eval_id()
    result = d1.start(eid, "PROP", "X", "Y")  # must not raise
    assert result is None  # _safe swallows and returns None on failure


def test_transition_never_raises_on_locked_database(db, monkeypatch):
    """Simulates 'database is locked' by holding an exclusive lock on a
    separate connection while a transition() call is attempted."""
    eid = _start_basic(db)
    blocker_conn = sqlite3.connect(db, timeout=0.1)
    blocker_conn.execute("BEGIN EXCLUSIVE")
    try:
        result = d1.transition(eid, "RESEARCH_COMPLETE")  # must not raise
        assert result is None
    finally:
        blocker_conn.rollback()
        blocker_conn.close()


def test_terminate_never_raises_when_connect_itself_fails(db, monkeypatch):
    def _broken_connect():
        raise sqlite3.OperationalError("simulated disk error")
    monkeypatch.setattr(d1, "_connect", _broken_connect)
    eid = "fake-eval-id-connect-never-succeeded"
    result = d1.terminate(eid, "SYSTEM_ERROR")  # must not raise
    assert result is None


def test_no_play_never_raises_on_write_failure(db, monkeypatch):
    def _broken_connect():
        raise OSError("simulated write failure")
    monkeypatch.setattr(d1, "_connect", _broken_connect)
    result = d1.no_play("some-eval-id")  # must not raise
    assert result is None


def test_record_outcome_never_raises_on_corrupt_db_file(tmp_path, monkeypatch):
    corrupt_db = tmp_path / "corrupt.sqlite"
    corrupt_db.write_bytes(b"this is not a valid sqlite file at all")
    monkeypatch.setattr(d1, "DB_PATH", corrupt_db)
    result = d1.record_outcome("some-eval-id", "HIT", "win_loss_alert")  # must not raise
    assert result is None


def test_all_public_functions_are_wrapped_in_safe_decorator():
    """Structural guarantee: every public capture function must go through
    _safe. Enumerated explicitly so a future function added without the
    decorator fails this test rather than shipping unguarded."""
    public_fns = [d1.new_eval_id, d1.start, d1.transition, d1.terminate,
                  d1.no_play, d1.add_slip_member, d1.record_outcome,
                  d1.record_validation]
    for fn in public_fns:
        # _safe-wrapped functions are closures named 'wrapper'
        assert fn.__name__ == "wrapper" or fn.__wrapped__.__name__ != fn.__name__, \
            f"{fn} does not appear to be wrapped by _safe"


# ─────────────────────────────────────────────────────────────────────
# 10. Historical auditability
# ─────────────────────────────────────────────────────────────────────

def test_completed_row_answers_what_why_rule_confidence_result_without_reasoning_text(db):
    """The core promise of the structured-fields requirement: every
    question below must be answerable by reading dedicated columns, with
    reasoning_text left NULL, proving no field silently depends on it."""
    eid = _start_basic(db)
    d1.transition(eid, "RESEARCH_COMPLETE")
    d1.transition(eid, "EVALUATION_COMPLETE",
                   direction="LESS", dominance_level="HARD",
                   eval_confidence=0.79, req_count=4)
    d1.transition(eid, "COMPLIANCE_COMPLETE",
                   compliance_category="B", compliance_cost=0.0)
    d1.transition(eid, "SCORING_COMPLETE",
                   final_confidence=0.77, final_grade="GREEN",
                   confidence_ledger=[{"cause": "compliance_B_note", "delta": 0}],
                   ledger_empty_flag=0)
    d1.transition(eid, "POSTED", posted=1)
    d1.record_outcome(eid, "HIT", "win_loss_alert")

    row = _row(db, eid)
    assert row["reasoning_text"] is None  # deliberately never set in this test

    # What happened?
    assert row["lifecycle_state"] == "OUTCOME_RECORDED"
    assert row["final_grade"] == "GREEN"
    # Why did it happen? (structured, not reasoning text)
    assert row["dominance_level"] == "HARD"
    assert row["direction"] == "LESS"
    # What rule fired?
    assert row["compliance_category"] == "B"
    # What changed confidence?
    ledger = json.loads(row["confidence_ledger"])
    assert ledger[0]["cause"] == "compliance_B_note"
    assert row["eval_confidence"] == 0.79
    assert row["final_confidence"] == 0.77
    # What was the final result?
    assert row["outcome"] == "HIT"


def test_full_lifecycle_log_is_a_complete_audit_trail(db):
    eid = _start_basic(db)
    d1.transition(eid, "RESEARCH_COMPLETE")
    d1.transition(eid, "EVALUATION_COMPLETE")
    d1.transition(eid, "COMPLIANCE_COMPLETE")
    d1.transition(eid, "SCORING_COMPLETE")
    d1.transition(eid, "POSTED")
    d1.record_outcome(eid, "HIT", "win_loss_alert")

    log = _lifecycle_rows(db, eid)
    # Every entry has a timestamp — proves WHEN, not just WHAT
    assert all(r["logged_at"] for r in log)
    # Chain is unbroken start-to-finish
    assert log[0]["from_state"] is None  # birth
    assert log[0]["to_state"] == "RESEARCH_STARTED"
    assert log[-1]["to_state"] == "OUTCOME_RECORDED"


# ─────────────────────────────────────────────────────────────────────
# 11. Agent Heartbeat (Mission Control Priority 1)
# ─────────────────────────────────────────────────────────────────────

def test_heartbeat_creates_one_row_per_agent(db):
    d1.heartbeat("research", "WORKING", current_task="Novak Djokovic")
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, current_task FROM agent_heartbeat WHERE agent_name='research'"
    ).fetchone()
    conn.close()
    assert row == ("WORKING", "Novak Djokovic")


def test_heartbeat_upserts_not_duplicates(db):
    d1.heartbeat("research", "WORKING", current_task="Player A")
    d1.heartbeat("research", "IDLE", current_task=None)
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM agent_heartbeat WHERE agent_name='research'"
    ).fetchone()[0]
    status = conn.execute(
        "SELECT status FROM agent_heartbeat WHERE agent_name='research'"
    ).fetchone()[0]
    conn.close()
    assert count == 1
    assert status == "IDLE"


def test_heartbeat_success_and_failure_counts_increment(db):
    d1.heartbeat("evaluation", "WORKING", increment_success=True)
    d1.heartbeat("evaluation", "WORKING", increment_success=True)
    d1.heartbeat("evaluation", "FAILED", increment_failure=True)
    conn = sqlite3.connect(db)
    succ, fail = conn.execute(
        "SELECT success_count, failure_count FROM agent_heartbeat WHERE agent_name='evaluation'"
    ).fetchone()
    conn.close()
    assert succ == 2
    assert fail == 1


def test_heartbeat_invalid_agent_name_rejected_silently(db):
    d1.heartbeat("not_a_real_agent", "WORKING")
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM agent_heartbeat").fetchone()[0]
    conn.close()
    assert count == 0


def test_heartbeat_invalid_status_rejected_silently(db):
    d1.heartbeat("research", "NOT_A_REAL_STATUS")
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM agent_heartbeat").fetchone()[0]
    conn.close()
    assert count == 0


def test_heartbeat_never_raises_on_connection_failure(monkeypatch):
    def _broken_connect():
        raise sqlite3.OperationalError("simulated failure")
    monkeypatch.setattr(d1, "_connect", _broken_connect)
    result = d1.heartbeat("research", "WORKING")  # must not raise
    assert result is None


def test_all_eight_agents_can_report_independently(db):
    for agent in sorted(d1.VALID_AGENTS):
        d1.heartbeat(agent, "IDLE")
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM agent_heartbeat").fetchone()[0]
    conn.close()
    assert count == 8


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))

# © 2026 Demetrius Reynolds — Project Apex Intelligence™. All rights reserved.
