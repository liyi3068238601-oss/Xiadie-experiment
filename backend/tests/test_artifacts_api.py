from __future__ import annotations

import base64

import pytest

from app import artifacts, db, task_runs


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _run() -> str:
    conn = db.connect()
    try:
        task_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO tasks(id,title,status,source,created_at,updated_at) VALUES(?,?,'todo','manual',?,?)",
            (task_id, "产物API", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return task_runs.create(task_id=task_id, idempotency_key=f"api-{db.new_id()}")["id"]


def test_http_artifact_lifecycle() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    headers = {"X-Xiadie-Token": "test-token-with-at-least-thirty-two-bytes"}
    run_id = _run()
    created = client.post("/api/artifacts", json={
        "task_run_id": run_id, "artifact_kind": "text", "mime_type": "text/plain",
        "data_b64": base64.b64encode(b"hello artifact").decode(),
    }, headers=headers)
    assert created.status_code == 200, created.text
    artifact_id = created.json()["artifact_id"]
    assert created.json()["version"] == 1
    preview = client.get(f"/api/artifacts/{artifact_id}/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.content == b"hello artifact"
    rolled = client.post(f"/api/artifacts/{artifact_id}/rollback", json={}, headers=headers)
    assert rolled.status_code == 409  # 只有一版不可回滚
    deleted = client.delete(f"/api/artifacts/{artifact_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/artifacts/{artifact_id}/preview", headers=headers).status_code == 404
