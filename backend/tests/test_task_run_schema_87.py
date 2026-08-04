from __future__ import annotations

import json
import sqlite3

import pytest

from app import db


TASKRUN_TABLES = (
    "task_runs", "task_nodes", "task_run_events", "task_run_artifact_links",
)


@pytest.fixture
def schema86_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "schema86.db"))
    migrations = db.MIGRATIONS
    monkeypatch.setattr(db, "MIGRATIONS", [item for item in migrations if item[0] <= 86])
    db.init_db()
    monkeypatch.setattr(db, "MIGRATIONS", migrations)
    assert db.get_schema_version() == 86
    return tmp_path / "schema86.db"


def _insert_task_run(conn, *, run_id: str, status: str, plan_version: int = 1) -> None:
    now = db.now()
    task_id = f"task-{run_id}"
    conn.execute(
        "INSERT INTO tasks(id,title,status,source,created_at,updated_at) "
        "VALUES(?,?,'todo','manual',?,?)",
        (task_id, run_id, now, now),
    )
    conn.execute(
        "INSERT INTO task_runs(id,task_id,trace_id,status,revision,plan_version,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (run_id, task_id, f"trace-{run_id}", status, 3, plan_version, now, now),
    )


def _event(conn, run_id: str, event_type: str, *, plan_version: int,
           requires_approval=None, created_at: float = 1.0) -> None:
    metadata = {"plan_version": plan_version}
    if requires_approval is not None:
        metadata["requires_approval"] = requires_approval
    conn.execute(
        "INSERT INTO task_run_events(id,task_run_id,event_type,revision,metadata_json,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (f"event-{run_id}-{event_type}-{created_at}", run_id, event_type, 2,
         json.dumps(metadata), created_at),
    )


def _columns(conn, table: str) -> dict[str, tuple]:
    return {
        row["name"]: (row["type"], row["notnull"], row["dflt_value"], row["pk"])
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def test_schema_87_new_database_has_approval_and_skip_evidence():
    assert db.get_schema_version() == 87
    conn = db.connect()
    try:
        run_columns = _columns(conn, "task_runs")
        node_columns = _columns(conn, "task_nodes")
        assert run_columns["requires_approval"] == ("INTEGER", 1, "0", 0)
        assert run_columns["approved_plan_version"] == ("INTEGER", 0, None, 0)
        assert run_columns["approved_at"] == ("REAL", 0, None, 0)
        assert node_columns["skip_reason_code"] == ("TEXT", 0, None, 0)
        assert node_columns["skip_reason_summary"] == ("TEXT", 0, None, 0)
    finally:
        conn.close()


def test_schema_86_upgrade_preserves_waiting_approval(schema86_db):
    conn = db.connect()
    try:
        _insert_task_run(conn, run_id="waiting", status="awaiting_approval")
        _event(conn, "waiting", "task_plan_replaced", plan_version=1, requires_approval=True)
        conn.commit()
    finally:
        conn.close()

    db.init_db()
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM task_runs WHERE id='waiting'").fetchone()
        assert row["status"] == "awaiting_approval"
        assert row["requires_approval"] == 1
        assert row["approved_plan_version"] is None
        assert row["approved_at"] is None
    finally:
        conn.close()


def test_schema_86_upgrade_backfills_only_same_version_approval(schema86_db):
    conn = db.connect()
    try:
        _insert_task_run(conn, run_id="approved", status="ready", plan_version=2)
        _event(conn, "approved", "task_plan_replaced", plan_version=2,
               requires_approval=True, created_at=2.0)
        _event(conn, "approved", "task_plan_approved", plan_version=2, created_at=3.0)
        conn.commit()
    finally:
        conn.close()

    db.init_db()
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM task_runs WHERE id='approved'").fetchone()
        assert row["requires_approval"] == 1
        assert row["approved_plan_version"] == 2
        assert row["approved_at"] == 3.0
    finally:
        conn.close()


def test_schema_86_upgrade_does_not_infer_approval_from_legacy_events(schema86_db):
    conn = db.connect()
    try:
        _insert_task_run(conn, run_id="legacy", status="running")
        _event(conn, "legacy", "task_plan_replaced", plan_version=1)
        conn.commit()
    finally:
        conn.close()

    db.init_db()
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM task_runs WHERE id='legacy'").fetchone()
        assert row["requires_approval"] == 0
        assert row["approved_plan_version"] is None
        assert row["approved_at"] is None
    finally:
        conn.close()


def test_schema_86_upgrade_rejects_missing_explicit_approval_atomically(schema86_db):
    conn = db.connect()
    try:
        _insert_task_run(conn, run_id="unsafe", status="running", plan_version=4)
        _event(conn, "unsafe", "task_plan_replaced", plan_version=4,
               requires_approval=True, created_at=4.0)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(db.SchemaMigrationError, match="schema_87_task_plan_approval_evidence_missing"):
        db.init_db()

    conn = db.connect()
    try:
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        assert version == "86"
        assert "requires_approval" not in _columns(conn, "task_runs")
        assert "skip_reason_code" not in _columns(conn, "task_nodes")
        assert conn.execute("SELECT status FROM task_runs WHERE id='unsafe'").fetchone()[0] == "running"
    finally:
        conn.close()


def test_new_and_upgraded_schema_87_have_matching_taskrun_shapes(schema86_db, tmp_path, monkeypatch):
    db.init_db()
    upgraded = db.connect()
    try:
        upgraded_shapes = {table: _columns(upgraded, table) for table in TASKRUN_TABLES}
        upgraded_indexes = {
            row["name"] for row in upgraded.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name IN "
                "('task_runs','task_nodes','task_run_events','task_run_artifact_links')"
            )
        }
    finally:
        upgraded.close()

    fresh_root = tmp_path / "fresh"
    monkeypatch.setattr(db, "DATA_DIR", str(fresh_root))
    monkeypatch.setattr(db, "DB_PATH", str(fresh_root / "fresh.db"))
    db.init_db()
    fresh = db.connect()
    try:
        assert {table: _columns(fresh, table) for table in TASKRUN_TABLES} == upgraded_shapes
        assert {
            row["name"] for row in fresh.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name IN "
                "('task_runs','task_nodes','task_run_events','task_run_artifact_links')"
            )
        } == upgraded_indexes
    finally:
        fresh.close()


def test_schema_87_init_is_idempotent():
    db.init_db()
    db.init_db()
    assert db.get_schema_version() == 87
