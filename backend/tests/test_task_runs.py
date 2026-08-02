from __future__ import annotations

import pytest

from app import db, task_runs


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _task(title: str = "整理发布说明") -> str:
    conn = db.connect()
    try:
        task_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO tasks(id,title,status,source,created_at,updated_at) VALUES(?,?,'todo','manual',?,?)",
            (task_id, title, now, now),
        )
        conn.commit()
        return task_id
    finally:
        conn.close()


def _planned_run() -> dict:
    run = task_runs.create(task_id=_task(), idempotency_key="same-request")
    return task_runs.replace_plan(run["id"], [
        {"client_id": "inspect", "title": "检查变更", "depends_on": []},
        {"client_id": "write", "title": "写发布说明", "depends_on": ["inspect"]},
    ])


def test_schema_86_contains_taskrun_tables():
    conn = db.connect()
    try:
        assert db.get_schema_version() == 86
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"task_runs", "task_nodes", "task_run_events", "task_run_artifact_links"} <= tables
    finally:
        conn.close()


def test_create_is_idempotent_and_plan_rejects_cycles():
    task_id = _task()
    first = task_runs.create(task_id=task_id, idempotency_key="request-1")
    second = task_runs.create(task_id=task_id, idempotency_key="request-1")
    assert first["id"] == second["id"]
    with pytest.raises(task_runs.TaskRunError, match="task_plan_cycle"):
        task_runs.replace_plan(first["id"], [
            {"client_id": "a", "title": "A", "depends_on": ["b"]},
            {"client_id": "b", "title": "B", "depends_on": ["a"]},
        ])


def test_node_evidence_drives_progress_and_completion():
    run = _planned_run()
    assert run["status"] == "ready"
    run = task_runs.start(run["id"])
    assert run["status"] == "running"
    assert [node["status"] for node in run["nodes"]] == ["ready", "blocked"]

    first, second = run["nodes"]
    task_runs.transition_node(run["id"], first["id"], "start")
    run = task_runs.transition_node(run["id"], first["id"], "succeed", output_summary="检查通过")
    assert run["progress_current"] == 1
    assert run["nodes"][1]["status"] == "ready"

    task_runs.transition_node(run["id"], second["id"], "start")
    run = task_runs.transition_node(run["id"], second["id"], "succeed", output_summary="已生成")
    assert run["status"] == "completed"
    assert run["progress_current"] == run["progress_total"] == 2
    conn = db.connect()
    try:
        assert conn.execute("SELECT status FROM tasks WHERE id=?", (run["task_id"],)).fetchone()[0] == "done"
    finally:
        conn.close()


def test_failure_is_explicit_and_cancel_is_idempotent():
    run = task_runs.start(_planned_run()["id"])
    node = run["nodes"][0]
    task_runs.transition_node(run["id"], node["id"], "start")
    failed = task_runs.transition_node(run["id"], node["id"], "fail",
                                       error_code="fixture_failed", error_message="固定集未通过")
    assert failed["status"] == "failed"
    assert failed["error_code"] == "fixture_failed"
    replanning = task_runs.replan(run["id"])
    assert replanning["status"] == "planning"
    cancelled = task_runs.cancel(run["id"])
    again = task_runs.cancel(run["id"])
    assert cancelled["status"] == again["status"] == "cancelled"
    assert len(again["events"]) == len(cancelled["events"])


def test_restart_requires_explicit_recovery_and_does_not_resume():
    run = task_runs.start(_planned_run()["id"])
    node = run["nodes"][0]
    task_runs.transition_node(run["id"], node["id"], "start")
    assert task_runs.recover_stale_runs() == 1
    recovered = task_runs.get(run["id"])
    assert recovered is not None
    assert recovered["status"] == "recovery_required"
    assert recovered["nodes"][0]["status"] == "blocked"
    assert recovered["waiting_reason"]
    assert task_runs.recover_stale_runs() == 0


def test_pause_stops_active_node_and_resume_reopens_it():
    run = task_runs.start(_planned_run()["id"])
    node = run["nodes"][0]
    task_runs.transition_node(run["id"], node["id"], "start")
    paused = task_runs.pause(run["id"])
    assert paused["status"] == "paused"
    assert paused["nodes"][0]["status"] == "blocked"
    resumed = task_runs.resume(run["id"])
    assert resumed["status"] == "running"
    assert resumed["nodes"][0]["status"] == "ready"


def test_artifact_is_a_reference_and_toolrun_link_is_visible():
    run = _planned_run()
    linked = task_runs.link_artifact(run["id"], "artifact_future_1", label="发布说明")
    assert linked["artifacts"][0]["artifact_id"] == "artifact_future_1"
    assert linked["events"][-1]["event_type"] == "task_artifact_linked"


def test_expected_revision_rejects_stale_mutations_without_writing():
    run = _planned_run()
    before_events = len(run["events"])
    with pytest.raises(task_runs.TaskRunConflict) as captured:
        task_runs.start(run["id"], expected_revision=run["revision"] - 1)
    assert captured.value.current["revision"] == run["revision"]
    unchanged = task_runs.get(run["id"])
    assert unchanged is not None
    assert unchanged["status"] == "ready"
    assert len(unchanged["events"]) == before_events


def test_idempotent_terminal_action_accepts_stale_revision():
    run = _planned_run()
    cancelled = task_runs.cancel(run["id"], expected_revision=run["revision"])
    again = task_runs.cancel(run["id"], expected_revision=run["revision"])
    assert again["revision"] == cancelled["revision"]
    assert len(again["events"]) == len(cancelled["events"])


def test_http_contract_exposes_plan_and_actions():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = {"X-Xiadie-Token": "test-token-with-at-least-thirty-two-bytes"}
    created_task = client.post("/api/tasks", json={"title": "验证 HTTP 合同"}, headers=headers)
    assert created_task.status_code == 200
    task_id = created_task.json()["id"]
    created = client.post(f"/api/tasks/{task_id}/runs", json={}, headers=headers)
    assert created.status_code == 200
    run_id = created.json()["id"]
    planned = client.put(f"/api/task-runs/{run_id}/plan", json={"nodes": [{
        "client_id": "verify", "title": "运行固定集", "depends_on": [],
    }]}, headers=headers)
    assert planned.status_code == 200
    assert planned.json()["status"] == "ready"
    started = client.post(f"/api/task-runs/{run_id}/start", headers=headers)
    assert started.status_code == 200
    node_id = started.json()["nodes"][0]["id"]
    assert client.post(f"/api/task-runs/{run_id}/nodes/{node_id}/action",
                       json={"action": "start"}, headers=headers).status_code == 200
    completed = client.post(f"/api/task-runs/{run_id}/nodes/{node_id}/action",
                            json={"action": "succeed"}, headers=headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_http_revision_conflict_returns_current_snapshot():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = {"X-Xiadie-Token": "test-token-with-at-least-thirty-two-bytes"}
    task_id = client.post("/api/tasks", json={"title": "并发合同"}, headers=headers).json()["id"]
    run = client.post(f"/api/tasks/{task_id}/runs", json={}, headers=headers).json()
    planned = client.put(f"/api/task-runs/{run['id']}/plan", json={
        "expected_revision": run["revision"],
        "nodes": [{"client_id": "one", "title": "唯一步骤", "depends_on": []}],
    }, headers=headers).json()
    conflict = client.post(f"/api/task-runs/{run['id']}/start",
                           json={"expected_revision": run["revision"]}, headers=headers)
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["code"] == "task_run_revision_conflict"
    assert detail["current"]["revision"] == planned["revision"]
    assert detail["current"]["status"] == "ready"
