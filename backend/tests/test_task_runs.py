from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import inspect

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


def _planned_run(*, requires_approval: bool = False, nodes: list[dict] | None = None) -> dict:
    run = task_runs.create(task_id=_task(), idempotency_key="same-request")
    return task_runs.replace_plan(run["id"], nodes or [
        {"client_id": "inspect", "title": "检查变更", "depends_on": []},
        {"client_id": "write", "title": "写发布说明", "depends_on": ["inspect"]},
    ], expected_revision=run["revision"], requires_approval=requires_approval)


def _running_run() -> dict:
    planned = _planned_run()
    return task_runs.start(planned["id"], expected_revision=planned["revision"])


BUSINESS_TABLES = (
    "tasks", "task_runs", "task_nodes", "task_run_events", "task_run_artifact_links",
)


def _business_snapshot() -> dict[str, list[tuple]]:
    conn = db.connect()
    try:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in BUSINESS_TABLES
        }
    finally:
        conn.close()


def test_schema_87_contains_taskrun_tables():
    conn = db.connect()
    try:
        assert db.get_schema_version() == 87
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
        ], expected_revision=first["revision"])


def test_event_cursor_catchup_is_body_free_and_detects_unknown_cursor():
    run = _planned_run()
    first = task_runs.list_events(run["id"])
    assert first["gap"] is False
    assert first["events"]
    assert first["cursor"] == first["events"][-1]["id"]
    assert all("metadata_json" not in event for event in first["events"])
    assert all("goal_summary" not in event and "title" not in event for event in first["events"])

    started = task_runs.start(run["id"], expected_revision=run["revision"])
    catchup = task_runs.list_events(run["id"], after=first["cursor"])
    assert catchup["gap"] is False
    assert [event["event_type"] for event in catchup["events"]] == ["task_run_started"]
    assert catchup["events"][0]["revision"] == started["revision"]
    assert task_runs.list_events(run["id"], after="missing-cursor")["gap"] is True


def test_http_event_catchup_endpoint_exposes_cursor_and_body_free_events():
    client, headers = _http_client()
    run = _http_run(client, headers)
    response = client.get(f"/api/task-runs/{run['id']}/events", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["gap"] is False
    assert payload["cursor"] == payload["events"][-1]["id"]
    assert all("metadata_json" not in event for event in payload["events"])
    assert client.get(f"/api/task-runs/{run['id']}/events?after=bad", headers=headers).json()["gap"] is True


def test_node_evidence_drives_progress_and_completion():
    run = _planned_run()
    assert run["status"] == "ready"
    run = task_runs.start(run["id"], expected_revision=run["revision"])
    assert run["status"] == "running"
    assert [node["status"] for node in run["nodes"]] == ["ready", "blocked"]

    first, second = run["nodes"]
    task_runs.transition_node(run["id"], first["id"], "start", expected_revision=run["revision"])
    run = task_runs.transition_node(run["id"], first["id"], "succeed", output_summary="检查通过", expected_revision=task_runs.get(run["id"])["revision"])
    assert run["progress_current"] == 1
    assert run["nodes"][1]["status"] == "ready"

    task_runs.transition_node(run["id"], second["id"], "start", expected_revision=run["revision"])
    run = task_runs.transition_node(run["id"], second["id"], "succeed", output_summary="已生成", expected_revision=task_runs.get(run["id"])["revision"])
    assert run["status"] == "completed"
    assert run["progress_current"] == run["progress_total"] == 2
    conn = db.connect()
    try:
        assert conn.execute("SELECT status FROM tasks WHERE id=?", (run["task_id"],)).fetchone()[0] == "done"
    finally:
        conn.close()


def test_failure_is_explicit_and_cancel_is_idempotent():
    run = _running_run()
    node = run["nodes"][0]
    task_runs.transition_node(run["id"], node["id"], "start", expected_revision=run["revision"])
    failed = task_runs.transition_node(run["id"], node["id"], "fail",
                                       error_code="fixture_failed", error_message="固定集未通过",
                                       expected_revision=task_runs.get(run["id"])["revision"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "fixture_failed"
    replanning = task_runs.replan(run["id"], expected_revision=failed["revision"])
    assert replanning["status"] == "planning"
    cancelled = task_runs.cancel(run["id"], expected_revision=replanning["revision"])
    again = task_runs.cancel(run["id"], expected_revision=replanning["revision"])
    assert cancelled["status"] == again["status"] == "cancelled"
    assert len(again["events"]) == len(cancelled["events"])


def test_restart_requires_explicit_recovery_and_does_not_resume():
    run = _running_run()
    node = run["nodes"][0]
    task_runs.transition_node(run["id"], node["id"], "start", expected_revision=run["revision"])
    assert task_runs.recover_stale_runs() == 1
    recovered = task_runs.get(run["id"])
    assert recovered is not None
    assert recovered["status"] == "recovery_required"
    assert recovered["nodes"][0]["status"] == "blocked"
    assert recovered["waiting_reason"]
    assert task_runs.recover_stale_runs() == 0


def test_pause_stops_active_node_and_resume_reopens_it():
    run = _running_run()
    node = run["nodes"][0]
    task_runs.transition_node(run["id"], node["id"], "start", expected_revision=run["revision"])
    paused = task_runs.pause(run["id"], expected_revision=task_runs.get(run["id"])["revision"])
    assert paused["status"] == "paused"
    assert paused["nodes"][0]["status"] == "blocked"
    resumed = task_runs.resume(run["id"], expected_revision=paused["revision"])
    assert resumed["status"] == "running"
    assert resumed["nodes"][0]["status"] == "ready"


def test_artifact_is_a_reference_and_toolrun_link_is_visible():
    run = _planned_run()
    linked = task_runs.link_artifact(run["id"], "artifact_future_1", label="发布说明", expected_revision=run["revision"])
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


def test_public_mutations_require_expected_revision():
    operations = (
        task_runs.replace_plan, task_runs.approve, task_runs.start, task_runs.pause,
        task_runs.resume, task_runs.cancel, task_runs.replan, task_runs.transition_node,
        task_runs.link_artifact,
    )
    for operation in operations:
        parameter = inspect.signature(operation).parameters["expected_revision"]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_plan_normalization_makes_dependency_order_and_duplicates_idempotent():
    run = task_runs.create(task_id=_task())
    first = task_runs.replace_plan(run["id"], [
        {"client_id": "a", "title": "A", "depends_on": []},
        {"client_id": "b", "title": "B", "depends_on": []},
        {"client_id": "c", "title": "C", "depends_on": ["b", "a", "b"]},
    ], expected_revision=run["revision"])
    before = _business_snapshot()
    replay = task_runs.replace_plan(run["id"], [
        {"client_id": "a", "title": "A", "depends_on": []},
        {"client_id": "b", "title": "B", "depends_on": []},
        {"client_id": "c", "title": "C", "depends_on": ["a", "b"]},
    ], expected_revision=run["revision"])
    assert replay["revision"] == first["revision"]
    assert replay["nodes"][2]["depends_on"] == ["a", "b"]
    assert _business_snapshot() == before


def test_plan_content_conflict_is_zero_write():
    run = _planned_run()
    before = _business_snapshot()
    with pytest.raises(task_runs.TaskRunConflict) as captured:
        task_runs.replace_plan(run["id"], [
            {"client_id": "inspect", "title": "改过的步骤", "depends_on": []},
        ], expected_revision=run["revision"])
    assert captured.value.code == "task_plan_content_conflict"
    assert captured.value.current["id"] == run["id"]
    assert _business_snapshot() == before


def test_start_and_resume_rollback_run_node_task_and_event_on_refresh_failure(monkeypatch):
    planned = _planned_run()
    before_start = _business_snapshot()

    def fail_refresh(run_id, conn):
        raise RuntimeError("refresh_failed")

    original_refresh = task_runs._refresh_ready_nodes
    monkeypatch.setattr(task_runs, "_refresh_ready_nodes", fail_refresh)
    with pytest.raises(RuntimeError, match="refresh_failed"):
        task_runs.start(planned["id"], expected_revision=planned["revision"])
    assert _business_snapshot() == before_start

    monkeypatch.setattr(task_runs, "_refresh_ready_nodes", original_refresh)
    running = task_runs.start(planned["id"], expected_revision=planned["revision"])
    paused = task_runs.pause(running["id"], expected_revision=running["revision"])
    before_resume = _business_snapshot()
    monkeypatch.setattr(task_runs, "_refresh_ready_nodes", fail_refresh)
    with pytest.raises(RuntimeError, match="refresh_failed"):
        task_runs.resume(paused["id"], expected_revision=paused["revision"])
    assert _business_snapshot() == before_resume


def test_two_clients_with_same_revision_apply_only_once():
    run = _planned_run()

    def mutate(command):
        try:
            return command, "ok", getattr(task_runs, command)(
                run["id"], expected_revision=run["revision"],
            )
        except task_runs.TaskRunConflict as error:
            return command, error.code, error.current

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(mutate, ("start", "cancel")))
    assert sorted(item[1] for item in outcomes) == ["ok", "task_run_revision_conflict"]
    current = task_runs.get(run["id"])
    assert current is not None
    assert current["status"] in {"running", "cancelled"}
    applied = [
        event for event in current["events"]
        if event["event_type"] in {"task_run_started", "task_run_cancelled"}
    ]
    assert len(applied) == 1


def test_exact_concurrent_replay_writes_one_event():
    run = _planned_run()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(
            lambda _: task_runs.start(run["id"], expected_revision=run["revision"]),
            range(2),
        ))
    assert [outcome["status"] for outcome in outcomes] == ["running", "running"]
    current = task_runs.get(run["id"])
    assert current is not None
    assert [event["event_type"] for event in current["events"]].count("task_run_started") == 1


def test_terminal_node_replay_is_zero_write_and_different_evidence_conflicts():
    run = _running_run()
    node = run["nodes"][0]
    running = task_runs.transition_node(
        run["id"], node["id"], "start", expected_revision=run["revision"],
    )
    succeeded = task_runs.transition_node(
        run["id"], node["id"], "succeed", output_summary="检查通过",
        expected_revision=running["revision"],
    )
    before = _business_snapshot()
    replay = task_runs.transition_node(
        run["id"], node["id"], "succeed", output_summary="检查通过",
        expected_revision=running["revision"],
    )
    assert replay["revision"] == succeeded["revision"]
    assert _business_snapshot() == before
    with pytest.raises(task_runs.TaskRunConflict) as captured:
        task_runs.transition_node(
            run["id"], node["id"], "succeed", output_summary="不同证据",
            expected_revision=succeeded["revision"],
        )
    assert captured.value.code == "task_node_evidence_conflict"
    assert _business_snapshot() == before


def test_last_node_completion_can_replay_with_pre_completion_revision():
    run = _planned_run(nodes=[{"client_id": "one", "title": "唯一节点", "depends_on": []}])
    running = task_runs.start(run["id"], expected_revision=run["revision"])
    node = running["nodes"][0]
    started = task_runs.transition_node(
        run["id"], node["id"], "start", expected_revision=running["revision"],
    )
    completed = task_runs.transition_node(
        run["id"], node["id"], "succeed", output_summary="完成",
        expected_revision=started["revision"],
    )
    assert completed["status"] == "completed"
    before = _business_snapshot()
    replay = task_runs.transition_node(
        run["id"], node["id"], "succeed", output_summary="完成",
        expected_revision=started["revision"],
    )
    assert replay["status"] == "completed"
    assert replay["revision"] == completed["revision"]
    assert _business_snapshot() == before


def test_node_evidence_normalization_ignores_fields_unrelated_to_action():
    run = _running_run()
    node = run["nodes"][0]
    started = task_runs.transition_node(
        run["id"], node["id"], "start", output_summary="ignored",
        error_code="ignored", error_message="ignored", reason_code="ignored",
        reason_summary="ignored", expected_revision=run["revision"],
    )
    current_node = started["nodes"][0]
    assert current_node["output_summary"] == ""
    assert current_node["error_code"] is None
    assert current_node["error_message"] is None
    assert current_node["skip_reason_code"] is None
    assert current_node["skip_reason_summary"] is None

    succeeded = task_runs.transition_node(
        run["id"], node["id"], "succeed", output_summary="完成",
        error_code="ignored", error_message="ignored", reason_code="ignored",
        reason_summary="ignored", expected_revision=started["revision"],
    )
    current_node = succeeded["nodes"][0]
    assert current_node["output_summary"] == "完成"
    assert current_node["error_code"] is None
    assert current_node["error_message"] is None
    assert current_node["skip_reason_code"] is None
    assert current_node["skip_reason_summary"] is None


def test_not_found_precedes_plan_and_node_evidence_validation():
    invalid_plan = [{"client_id": "a", "title": "A", "depends_on": ["missing"]}]
    with pytest.raises(task_runs.TaskRunError, match="task_run_not_found"):
        task_runs.replace_plan(
            "missing-run", invalid_plan, expected_revision=1,
        )
    with pytest.raises(task_runs.TaskRunError, match="task_run_not_found"):
        task_runs.transition_node(
            "missing-run", "missing-node", "skip", expected_revision=1,
        )

    run = _running_run()
    with pytest.raises(task_runs.TaskRunError, match="task_node_not_found"):
        task_runs.transition_node(
            run["id"], "missing-node", "skip", expected_revision=run["revision"],
        )


def test_skip_unblocks_dependents_and_preserves_reason_evidence():
    run = _running_run()
    first = run["nodes"][0]
    skipped = task_runs.transition_node(
        run["id"], first["id"], "skip", reason_code="not_needed",
        reason_summary="本次发布不需要", expected_revision=run["revision"],
    )
    assert skipped["nodes"][0]["status"] == "skipped"
    assert skipped["nodes"][0]["skip_reason_code"] == "not_needed"
    assert skipped["nodes"][0]["skip_reason_summary"] == "本次发布不需要"
    assert skipped["nodes"][1]["status"] == "ready"


def test_plan_replacement_clears_approval_and_start_fails_closed():
    waiting = _planned_run(requires_approval=True)
    approved = task_runs.approve(waiting["id"], expected_revision=waiting["revision"])
    assert approved["approved_plan_version"] == approved["plan_version"]
    replanning = task_runs.replan(approved["id"], expected_revision=approved["revision"])
    replaced = task_runs.replace_plan(
        replanning["id"], [{"client_id": "new", "title": "新计划", "depends_on": []}],
        expected_revision=replanning["revision"], requires_approval=True,
    )
    assert replaced["approved_plan_version"] is None
    assert replaced["status"] == "awaiting_approval"

    conn = db.connect()
    try:
        conn.execute(
            "UPDATE task_runs SET status='ready' WHERE id=?", (replaced["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    before = _business_snapshot()
    with pytest.raises(task_runs.TaskRunConflict) as captured:
        task_runs.start(replaced["id"], expected_revision=replaced["revision"])
    assert captured.value.code == "task_plan_approval_required"
    assert _business_snapshot() == before


def test_artifact_links_allow_terminal_append_and_exact_replay():
    run = _planned_run()
    cancelled = task_runs.cancel(run["id"], expected_revision=run["revision"])
    linked = task_runs.link_artifact(
        run["id"], "artifact-1", label="报告", expected_revision=cancelled["revision"],
    )
    assert linked["status"] == "cancelled"
    before = _business_snapshot()
    replay = task_runs.link_artifact(
        run["id"], "artifact-1", label="报告", expected_revision=cancelled["revision"],
    )
    assert replay["revision"] == linked["revision"]
    assert _business_snapshot() == before
    with pytest.raises(task_runs.TaskRunConflict) as captured:
        task_runs.link_artifact(
            run["id"], "artifact-1", label="其他", expected_revision=linked["revision"],
        )
    assert captured.value.code == "task_artifact_link_conflict"
    assert _business_snapshot() == before


def _http_client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app), {"X-Xiadie-Token": "test-token-with-at-least-thirty-two-bytes"}


def _http_run(client, headers, *, requires_approval: bool = False) -> dict:
    task_id = client.post("/api/tasks", json={"title": "HTTP 固定集"}, headers=headers).json()["id"]
    created = client.post(f"/api/tasks/{task_id}/runs", json={}, headers=headers).json()
    response = client.put(f"/api/task-runs/{created['id']}/plan", json={
        "expected_revision": created["revision"],
        "requires_approval": requires_approval,
        "nodes": [{"client_id": "one", "title": "唯一步骤", "depends_on": []}],
    }, headers=headers)
    assert response.status_code == 200
    return response.json()


def test_http_mutations_require_revision_and_leave_database_unchanged():
    client, headers = _http_client()
    run = _http_run(client, headers)
    node_id = run["nodes"][0]["id"]
    requests = (
        ("PUT", f"/api/task-runs/{run['id']}/plan", {
            "nodes": [{"client_id": "one", "title": "唯一步骤", "depends_on": []}],
        }),
        *(('POST', f"/api/task-runs/{run['id']}/{action}", {})
          for action in ("approve", "start", "pause", "resume", "cancel", "replan")),
        ("POST", f"/api/task-runs/{run['id']}/nodes/{node_id}/action", {"action": "start"}),
        ("POST", f"/api/task-runs/{run['id']}/artifacts", {"artifact_id": "artifact-1"}),
    )
    for method, path, body in requests:
        before = _business_snapshot()
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 422, (method, path, response.text)
        assert _business_snapshot() == before


def test_http_unknown_node_action_is_validation_error_and_zero_write():
    client, headers = _http_client()
    run = _http_run(client, headers)
    before = _business_snapshot()
    response = client.post(
        f"/api/task-runs/{run['id']}/nodes/{run['nodes'][0]['id']}/action",
        json={"action": "unknown", "expected_revision": run["revision"]},
        headers=headers,
    )
    assert response.status_code == 422
    assert _business_snapshot() == before


def test_http_all_conflicts_have_stable_shape_and_full_current_snapshot():
    client, headers = _http_client()
    run = _http_run(client, headers)
    before = _business_snapshot()
    conflict = client.put(f"/api/task-runs/{run['id']}/plan", json={
        "expected_revision": run["revision"],
        "nodes": [{"client_id": "different", "title": "不同计划", "depends_on": []}],
    }, headers=headers)
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert set(detail) == {"code", "message", "retry", "current"}
    assert detail["code"] == "task_plan_content_conflict"
    assert detail["retry"] == "modify_then_retry"
    assert detail["message"] == task_runs.contract.ERROR_SPECS[detail["code"]].message
    assert detail["current"] == client.get(
        f"/api/task-runs/{run['id']}", headers=headers,
    ).json()
    assert _business_snapshot() == before


def test_http_exact_replay_returns_200_without_writes():
    client, headers = _http_client()
    run = _http_run(client, headers)
    started = client.post(
        f"/api/task-runs/{run['id']}/start",
        json={"expected_revision": run["revision"]}, headers=headers,
    )
    assert started.status_code == 200
    before = _business_snapshot()
    replay = client.post(
        f"/api/task-runs/{run['id']}/start",
        json={"expected_revision": run["revision"]}, headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json()["revision"] == started.json()["revision"]
    assert _business_snapshot() == before


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
    planned = client.put(f"/api/task-runs/{run_id}/plan", json={
        "expected_revision": created.json()["revision"],
        "nodes": [{
            "client_id": "verify", "title": "运行固定集", "depends_on": [],
        }],
    }, headers=headers)
    assert planned.status_code == 200
    assert planned.json()["status"] == "ready"
    started = client.post(
        f"/api/task-runs/{run_id}/start",
        json={"expected_revision": planned.json()["revision"]}, headers=headers,
    )
    assert started.status_code == 200
    node_id = started.json()["nodes"][0]["id"]
    node_started = client.post(
        f"/api/task-runs/{run_id}/nodes/{node_id}/action",
        json={"action": "start", "expected_revision": started.json()["revision"]},
        headers=headers,
    )
    assert node_started.status_code == 200
    completed = client.post(f"/api/task-runs/{run_id}/nodes/{node_id}/action",
                            json={"action": "succeed",
                                  "expected_revision": node_started.json()["revision"]}, headers=headers)
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
