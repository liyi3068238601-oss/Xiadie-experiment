from __future__ import annotations

import hashlib
import json

import pytest

from app import db, recovery_checkpoint, task_runs


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _run() -> dict:
    conn = db.connect()
    try:
        task_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO tasks(id,title,status,source,created_at,updated_at) VALUES(?,?,'todo','manual',?,?)",
            (task_id, "恢复任务", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return task_runs.create(task_id=task_id, idempotency_key=f"cp-{db.new_id()}")


def test_record_and_latest() -> None:
    run = _run()
    checkpoint = recovery_checkpoint.record(
        task_run_id=run["id"], node_id=None, tool_run_id=None,
        input_hash=hashlib.sha256(json.dumps({"a": 1}).encode()).hexdigest(),
        trace_id=run["trace_id"],
    )
    assert checkpoint["input_hash"]
    latest = recovery_checkpoint.latest(run["id"])
    assert latest is not None
    assert latest["input_hash"] == checkpoint["input_hash"]


def test_can_retry_requires_matching_input() -> None:
    run = _run()
    digest = hashlib.sha256(json.dumps({"path": "a"}).encode()).hexdigest()
    recovery_checkpoint.record(task_run_id=run["id"], node_id=None, tool_run_id=None,
                               input_hash=digest, trace_id=run["trace_id"])
    assert recovery_checkpoint.can_retry(run["id"], {"path": "a"}) is True
    assert recovery_checkpoint.can_retry(run["id"], {"path": "b"}) is False
