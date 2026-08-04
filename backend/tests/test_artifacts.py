from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app import artifacts, db, task_runs


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _file(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _run() -> str:
    conn = db.connect()
    try:
        task_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO tasks(id,title,status,source,created_at,updated_at) VALUES(?,?,'todo','manual',?,?)",
            (task_id, "产物任务", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return task_runs.create(task_id=task_id, idempotency_key=f"art-{db.new_id()}")["id"]


def test_versions_bounded_and_latest_selected() -> None:
    run_id = _run()
    for index in range(1, 13):
        artifacts.create_version(
            task_run_id=run_id, node_id=None, artifact_id="art-1",
            kind="text", mime="text/plain",
            data=f"v{index}".encode(), workspace=Path(db.DATA_DIR),
        )
    listing = artifacts.list(run_id)
    assert len(listing) == 1
    assert listing[0]["version"] == 12  # 最新活动版本
    assert len(listing[0]["versions"]) == 10  # 只保留最近 10 版


def test_rollback_restores_previous_version() -> None:
    run_id = _run()
    artifacts.create_version(task_run_id=run_id, node_id=None, artifact_id="art-1",
                             kind="text", mime="text/plain", data=b"one",
                             workspace=Path(db.DATA_DIR))
    artifacts.create_version(task_run_id=run_id, node_id=None, artifact_id="art-1",
                             kind="text", mime="text/plain", data=b"two",
                             workspace=Path(db.DATA_DIR))
    assert artifacts.active("art-1")["version"] == 2
    rolled = artifacts.rollback("art-1")
    assert rolled["version"] == 1
    assert artifacts.preview("art-1") == b"one"


def test_soft_delete_then_purge() -> None:
    run_id = _run()
    artifacts.create_version(task_run_id=run_id, node_id=None, artifact_id="art-1",
                             kind="text", mime="text/plain", data=b"x",
                             workspace=Path(db.DATA_DIR))
    assert artifacts.soft_delete("art-1") is True
    assert artifacts.list(run_id) == []
    artifacts.purge("art-1")
    assert artifacts.get("art-1") is None
