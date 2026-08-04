from __future__ import annotations

from pathlib import Path

import pytest

from app import db, task_runs
from app.tool_executor import execute_node


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _task() -> str:
    conn = db.connect()
    try:
        task_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO tasks(id,title,status,source,created_at,updated_at) VALUES(?,?,'todo','manual',?,?)",
            (task_id, "工具执行任务", now, now),
        )
        conn.commit()
        return task_id
    finally:
        conn.close()


def _repo() -> Path:
    return Path(__file__).resolve().parents[2]


def _started_run(tool_args: dict) -> dict:
    run = task_runs.create(task_id=_task(), idempotency_key="exec-1")
    planned = task_runs.replace_plan(run["id"], [{
        "client_id": "a", "title": "读取说明",
        "tool_ref": "workspace.read_file", "tool_args": tool_args,
    }], expected_revision=run["revision"])
    return task_runs.start(planned["id"], expected_revision=planned["revision"])


def test_execute_node_only_succeeds_with_real_evidence() -> None:
    started = _started_run({"path": "README.md"})
    node = started["nodes"][0]
    execute_node(started, node, workspace=_repo())
    detail = task_runs.get(started["id"])
    assert detail["nodes"][0]["status"] == "succeeded"
    assert detail["tool_runs"][-1]["status"] == "succeeded"
    assert detail["tool_runs"][-1]["result_summary"] != {}


def test_execute_node_failure_marks_node_failed_with_evidence() -> None:
    started = _started_run({"path": "no_such_file_xyz.txt"})
    node = started["nodes"][0]
    execute_node(started, node, workspace=_repo())
    detail = task_runs.get(started["id"])
    assert detail["nodes"][0]["status"] == "failed"
    assert detail["tool_runs"][-1]["status"] == "failed"
    assert detail["tool_runs"][-1]["error_code"] == "file_not_found"
