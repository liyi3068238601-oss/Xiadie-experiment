from __future__ import annotations

import pytest

from app import confirmation, db, permission_guard


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_create_confirm_creates_grant() -> None:
    request = confirmation.create_request(
        session_id="s1", tool_id="workspace.write_file", target="C:/ws/a.txt",
        risk_level="S2", purpose="写文件", grant_duration_seconds=3600,
    )
    assert request["status"] == "pending"
    decided = confirmation.confirm(request["id"], grant_duration_seconds=3600)
    assert decided["status"] == "confirmed"
    assert decided["confirmed_grant_id"]
    assert permission_guard.active_grant("workspace.write_file", "C:/ws/a.txt") is not None


def test_deny_then_idempotent() -> None:
    request = confirmation.create_request(
        session_id="s1", tool_id="workspace.write_file", target="C:/ws/b.txt",
    )
    denied = confirmation.deny(request["id"])
    assert denied["status"] == "denied"
    again = confirmation.confirm(request["id"], grant_duration_seconds=3600)
    assert again["status"] == "denied"  # 幂等：已决策不翻转


def test_pending_scoped_to_session() -> None:
    confirmation.create_request(session_id="s1", tool_id="t", target="x")
    confirmation.create_request(session_id="s2", tool_id="t", target="y")
    assert len(confirmation.pending("s1")) == 1
    assert confirmation.pending("s2")[0]["target"] == "y"


def test_get_missing_returns_none() -> None:
    assert confirmation.get("missing") is None


def test_http_confirm_deny_flow() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    headers = {"X-Xiadie-Token": "test-token-with-at-least-thirty-two-bytes"}
    created = client.post("/api/tool-permissions/requests", json={
        "tool_id": "workspace.write_file", "target": "C:/ws/a.txt",
        "purpose": "写文件", "grant_duration_seconds": 3600,
        "session_id": "s-http",
    }, headers=headers)
    assert created.status_code == 200
    request_id = created.json()["id"]
    denied = client.post(f"/api/tool-permissions/requests/{request_id}/deny",
                         json={}, headers=headers)
    assert denied.status_code == 200
    assert denied.json()["status"] == "denied"
    missing = client.post("/api/tool-permissions/requests/nope/confirm",
                          json={}, headers=headers)
    assert missing.status_code == 404
