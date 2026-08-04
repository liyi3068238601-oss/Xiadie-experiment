from __future__ import annotations

import pytest

from app import db, task_runs, tool_runs
from app.observability.buffer import BUFFER


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
            (task_id, "全链路任务", now, now),
        )
        conn.commit()
        return task_id
    finally:
        conn.close()


def test_full_lifecycle_trace_correlation() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="chain-1")
    trace_id = run["trace_id"]
    assert trace_id
    planned = task_runs.replace_plan(run["id"], [
        {"client_id": "a", "title": "A", "depends_on": []},
    ], expected_revision=run["revision"])
    approved = task_runs.approve(planned["id"], expected_revision=planned["revision"]) \
        if planned["requires_approval"] else planned
    started = task_runs.start(approved["id"], expected_revision=approved["revision"])
    node = started["nodes"][0]
    succeeded = task_runs.transition_node(
        started["id"], node["id"], "start", expected_revision=started["revision"],
    )
    done = task_runs.transition_node(
        succeeded["id"], node["id"], "succeed", expected_revision=succeeded["revision"],
        output_summary="完成",
    )
    assert done["status"] == "completed"
    assert done["trace_id"] == trace_id

    tool = tool_runs.create(tool_name="workspace_search", trace_id=trace_id,
                            task_run_id=done["id"])
    linked = task_runs.link_artifact(done["id"], "art-1", expected_revision=done["revision"],
                                     node_id=node["id"], label="报告")
    detail = task_runs.get(done["id"])
    assert detail is not None
    assert detail["trace_id"] == trace_id
    assert any(event["event_type"] == "task_run_completed" for event in detail["events"])
    assert any(tool_run["id"] == tool["id"] and tool_run["task_run_id"] == done["id"]
               for tool_run in detail["tool_runs"])
    assert any(artifact["artifact_id"] == "art-1" and artifact["node_id"] == node["id"]
               for artifact in detail["artifacts"])

    # 诊断日志同 trace 可读
    snapshot = BUFFER.snapshot(limit=5000)
    log_items = [item for item in snapshot["items"]
                 if item.get("trace_id") == trace_id
                 and item.get("logger") == "task.scheduler"]
    assert log_items, "task.scheduler 日志应携带同一 trace_id"
