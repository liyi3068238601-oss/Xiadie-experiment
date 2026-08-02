import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import db, mental_activity, tool_runs
from app.main import app
from app.observability import bind_context, log_event
from app.observability import api as diagnostic_api
from app.observability.buffer import DiagnosticBuffer, BUFFER
from app.observability.redaction import redact

CLIENT = TestClient(
    app, headers={"X-Xiadie-Token": "test-token-with-at-least-thirty-two-bytes"},
)


def _session(session_id: str) -> None:
    conn = db.connect()
    try:
        now = db.now()
        conn.execute(
            "INSERT INTO sessions(id,title,archived,created_at,updated_at) VALUES(?,?,?,?,?)",
            (session_id, "诊断测试", 0, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def test_redaction_removes_structured_and_inline_secrets():
    value = redact({
        "api_key": "sk-super-secret-value",
        "message": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": {"password": "do-not-log"},
    })
    rendered = json.dumps(value)
    assert "sk-super" not in rendered
    assert "abcdefghijklmnopqrstuvwxyz" not in rendered
    assert "do-not-log" not in rendered
    assert rendered.count("REDACTED_SECRET") >= 3


def test_buffer_is_bounded_reports_gap_and_keeps_cursor_order():
    buffer = DiagnosticBuffer(max_events=3, max_bytes=1000)
    for index in range(5):
        buffer.append({"event_id": str(index)}, 10)
    snapshot = buffer.snapshot(after=1, limit=10)
    assert snapshot["gap"] is True
    assert [item["cursor"] for item in snapshot["items"]] == [3, 4, 5]
    assert snapshot["dropped"] == 2


def test_log_event_carries_trace_context_and_diagnostic_snapshot():
    with bind_context(trace_id="trc-test", request_id="req-test", session_id="ses-test"):
        event = log_event("test.module", "ERROR", "test_failed", "safe message",
                          fields={"phase": "executing"}, error=ValueError("bad value"))
    assert event["trace_id"] == "trc-test"
    assert event["request_id"] == "req-test"
    assert event["session_id"] == "ses-test"
    assert event["error"]["type"] == "ValueError"
    response = CLIENT.get("/api/diagnostics/logs", params={"after": event["cursor"] - 1})
    assert response.status_code == 200
    assert any(item["event_id"] == event["event_id"] for item in response.json()["items"])


def test_tool_run_v2_transitions_and_audit_detail():
    _session("tool-run-session")
    run = tool_runs.create(
        tool_name="file.read", session_id="tool-run-session", risk_level="S0",
        arguments_summary={"path": "<WORKSPACE>/README.md", "api_key": "secret"},
    )
    assert run["status"] == "queued"
    tool_runs.transition(run["id"], "authorizing", permission_grant_id="grant-local")
    tool_runs.transition(run["id"], "running")
    finished = tool_runs.transition(
        run["id"], "failed", error=FileNotFoundError("missing.md"),
        error_code="FILE_NOT_FOUND",
    )
    assert finished["status"] == "failed"
    assert finished["phase"] == "terminal"
    assert finished["error_type"] == "FileNotFoundError"
    assert finished["arguments_summary"]["api_key"] == "[REDACTED_SECRET]"
    detail = CLIENT.get(f"/api/diagnostics/tool-runs/{run['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert [event["to_status"] for event in body["events"]] == [
        "queued", "authorizing", "running", "failed",
    ]
    assert any(item.get("tool_run_id") == run["id"] for item in body["logs"])
    with pytest.raises(tool_runs.ToolRunError, match="tool_run_terminal"):
        tool_runs.transition(run["id"], "running")


def test_visible_mental_activity_is_bounded_persisted_and_logged():
    _session("mental-session")
    for index in range(55):
        mental_activity.record(
            session_id="mental-session", event_kind="bot_planning",
            thought=f"第 {index} 条显式想法", mood="专注", intensity=0.4,
            expected_reaction="用户会看到", action_summaries=["file.read"],
        )
    items = mental_activity.list_session("mental-session", 100)
    assert len(items) == 50
    assert items[0]["thought"] == "第 54 条显式想法"
    snapshot = BUFFER.snapshot(limit=5000)
    visible = next(item for item in reversed(snapshot["items"])
                   if item.get("content_class") == "character_mental_activity")
    assert visible["visibility"] == "user_visible"
    assert visible["thought"] == "第 54 条显式想法"
    response = CLIENT.get("/api/diagnostics/logs", params={
        "content_class": "character_mental_activity", "limit": 5000,
    })
    assert response.status_code == 200
    assert all(item["content_class"] == "character_mental_activity"
               for item in response.json()["items"])
    assert mental_activity.clear_session("mental-session") == 50


def test_support_bundle_excludes_mental_activity_bodies(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    event = log_event("kfc.mental", "INFO", "mental_activity_recorded", "visible", fields={
        "content_class": "character_mental_activity",
        "visibility": "user_visible",
        "thought": "不应进入支持包的内心正文",
        "reason": "不应进入支持包的原因",
    })
    response = CLIENT.post("/api/diagnostics/export")
    assert response.status_code == 200
    bundle_id = response.json()["bundle_id"]
    bundle_path = tmp_path / "diagnostics" / f"xiadie-support-{bundle_id}.zip"
    with zipfile.ZipFile(bundle_path) as bundle:
        events = bundle.read("diagnostics/events.jsonl").decode("utf-8")
        manifest = json.loads(bundle.read("manifest.json"))
    assert "不应进入支持包的内心正文" not in events
    assert "不应进入支持包的原因" not in events
    assert manifest["mental_activity_bodies_excluded"] >= 1
    assert event["event_id"] in events


def test_mental_activity_fields_obey_exact_database_bounds():
    _session("mental-bounds-session")
    mental_activity.record(
        session_id="mental-bounds-session",
        event_kind="bot_planning",
        thought="x" * 300,
        mood="m" * 30,
        expected_reaction="e" * 160,
        reason="r" * 100,
        action_summaries=["a" * 100],
    )
    item = mental_activity.list_session("mental-bounds-session", 1)[0]
    assert len(item["thought"]) == 240
    assert len(item["mood"]) == 16
    assert len(item["expected_reaction"]) == 120
    assert len(item["reason"]) == 80
    assert len(item["action_summaries"][0]) == 80
    mental_activity.clear_session("mental-bounds-session")


def test_desktop_ingest_exposes_readable_error_without_core_field_spoofing():
    response = CLIENT.post("/api/diagnostics/ingest", json={
        "level": "ERROR",
        "logger": "desktop.backend_process",
        "event": "backend_start_failed",
        "message": "Backend process failed to start",
        "process": "desktop",
        "fields": {
            "error": {"type": "SpawnError", "message": "missing executable"},
            "event_id": "spoofed-id",
            "level": "INFO",
        },
    })
    assert response.status_code == 200
    event_id = response.json()["event_id"]
    assert event_id != "spoofed-id"
    logs = CLIENT.get("/api/diagnostics/logs", params={"search": event_id}).json()["items"]
    event = next(item for item in logs if item["event_id"] == event_id)
    assert event["level"] == "ERROR"
    assert event["error"]["type"] == "SpawnError"
    assert event["error"]["message"] == "missing executable"


def test_filtered_log_query_scans_beyond_the_oldest_response_page(monkeypatch):
    busy = DiagnosticBuffer(max_events=1500, max_bytes=2 * 1024 * 1024)
    for index in range(1200):
        busy.append({
            "event_id": f"busy-{index}", "level": "INFO", "process": "backend",
            "logger": "busy.test", "message": "ordinary event",
        }, 64)
    busy.append({
        "event_id": "newest-error", "level": "ERROR", "process": "backend",
        "logger": "tool.file", "message": "needle failure",
    }, 64)
    monkeypatch.setattr(diagnostic_api, "BUFFER", busy)
    response = CLIENT.get("/api/diagnostics/logs", params={"search": "needle", "limit": 10})
    assert response.status_code == 200
    assert [item["event_id"] for item in response.json()["items"]] == ["newest-error"]
