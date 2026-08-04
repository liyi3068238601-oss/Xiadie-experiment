from __future__ import annotations

from pathlib import Path

import pytest

from app import confirmation, db, permission_guard, task_runs
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


def _session() -> str:
    conn = db.connect()
    try:
        session_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO sessions(id,created_at,updated_at) VALUES(?,?,?)",
            (session_id, now, now),
        )
        conn.commit()
        return session_id
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


def _write_started(tmp_path, content: str = "x") -> dict:
    run = task_runs.create(task_id=_task(), idempotency_key="exec-write")
    planned = task_runs.replace_plan(run["id"], [{
        "client_id": "a", "title": "写文件",
        "tool_ref": "workspace.write_file",
        "tool_args": {"path": "out.txt", "content": content},
    }], expected_revision=run["revision"])
    return task_runs.start(planned["id"], expected_revision=planned["revision"])


def test_write_without_grant_waits_for_confirmation(tmp_path) -> None:
    started = _write_started(tmp_path)
    node = started["nodes"][0]
    session_id = _session()
    result = execute_node(started, node, session_id=session_id, workspace=tmp_path)
    assert result["nodes"][0]["status"] == "running"  # 等待确认，不推进
    assert len(confirmation.pending(session_id)) == 1
    assert not (tmp_path / "out.txt").exists()


def test_write_with_grant_succeeds(tmp_path) -> None:
    session_id = _session()
    permission_guard.create_grant(
        tool_id="workspace.write_file", target_kind="path_prefix",
        target=str(tmp_path.resolve()), purpose="写测试", session_id=session_id,
    )
    started = _write_started(tmp_path)
    node = started["nodes"][0]
    result = execute_node(started, node, session_id=session_id, workspace=tmp_path)
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "x"
    assert result["nodes"][0]["status"] == "succeeded"
