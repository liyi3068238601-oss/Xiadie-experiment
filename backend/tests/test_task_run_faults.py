from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlite3

from app import db, task_runs


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _task(title: str = "故障注入任务") -> str:
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


BUSINESS_TABLES = ("tasks", "task_runs", "task_nodes", "task_run_events",
                   "task_run_artifact_links")


def _snapshot() -> dict[str, list[tuple]]:
    conn = db.connect()
    try:
        return {t: [tuple(row) for row in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                for t in BUSINESS_TABLES}
    finally:
        conn.close()


def _planned_run() -> dict:
    run = task_runs.create(task_id=_task(), idempotency_key="fault-plan")
    return task_runs.replace_plan(run["id"], [
        {"client_id": "a", "title": "A", "depends_on": []},
    ], expected_revision=run["revision"])


class _FaultConnection:
    """Delegate everything to a real connection, failing on a chosen SQL prefix."""

    def __init__(self, real, fail, exc=RuntimeError):
        self._real = real
        self._fail = fail
        self._exc = exc

    def execute(self, sql, *args, **kwargs):
        if self._fail(sql):
            raise self._exc("simulated fault")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_concurrent_command_race_applies_once_and_zero_writes() -> None:
    planned = _planned_run()
    run = task_runs.start(planned["id"], expected_revision=planned["revision"])

    def act(name: str) -> str:
        try:
            return getattr(task_runs, name)(run["id"], expected_revision=run["revision"]).get("status", "")
        except task_runs.TaskRunConflict as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(act, ["pause", "cancel"]))
    assert results.count("task_run_revision_conflict") == 1
    assert any(status in ("paused", "cancelled") for status in results)
    # 取消幂等：最新 revision 再取消不产生新写入
    current = task_runs.get(run["id"])
    if current["status"] != "cancelled":
        cancelled = task_runs.cancel(run["id"], expected_revision=current["revision"])
        assert cancelled["status"] == "cancelled"
        current = task_runs.get(run["id"])
    before2 = _snapshot()
    again = task_runs.cancel(run["id"], expected_revision=current["revision"])
    assert again["status"] == "cancelled"
    assert _snapshot() == before2


def test_crash_mid_replace_plan_rolls_back_without_orphans(monkeypatch) -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="fault-crash")
    before = _snapshot()
    original = db.connect

    monkeypatch.setattr(
        db, "connect",
        lambda: _FaultConnection(original(), lambda sql: "INSERT INTO task_nodes" in sql),
    )
    with pytest.raises(RuntimeError):
        task_runs.replace_plan(run["id"], [
            {"client_id": "a", "title": "A", "depends_on": []},
        ], expected_revision=run["revision"])
    assert _snapshot() == before  # 完全回滚，无半状态


def test_db_busy_does_not_corrupt_data(monkeypatch) -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="fault-busy")
    before = _snapshot()
    original = db.connect

    monkeypatch.setattr(
        db, "connect",
        lambda: _FaultConnection(original(), lambda sql: sql.startswith("BEGIN"),
                                 exc=sqlite3.OperationalError),
    )
    with pytest.raises(sqlite3.OperationalError):
        task_runs.replace_plan(run["id"], [
            {"client_id": "a", "title": "A", "depends_on": []},
        ], expected_revision=run["revision"])
    assert _snapshot() == before


def test_stale_revision_competition_applies_once() -> None:
    run = _planned_run()

    def act(action: str) -> str:
        try:
            return getattr(task_runs, action)(run["id"], expected_revision=run["revision"]).get("status", "")
        except task_runs.TaskRunConflict as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(act, ["start", "cancel"]))
    assert results.count("task_run_revision_conflict") == 1
    assert any(status in ("running", "cancelled") for status in results)
