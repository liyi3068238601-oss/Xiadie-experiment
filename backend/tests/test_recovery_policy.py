from __future__ import annotations

import pytest

from app import db
from app import recovery_policy as rp


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _task(title: str = "恢复测试任务") -> str:
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


def test_recovery_view_aggregates_tool_evidence() -> None:
    from app import task_runs
    run = task_runs.create(task_id=_task(), idempotency_key="rec-1")
    view = task_runs.recovery_view(run["id"])
    assert view is not None
    assert view["risk"] == "none"  # 无工具证据 -> fail closed
    assert view["allowed"] == {"continue": False, "retry": False, "replan": True}


def test_side_effect_free_matrix() -> None:
    decision = rp.decide_recovery("side_effect_free", has_terminal_evidence=True, retries_used=0)
    assert decision["risk"] == "low"
    assert decision["allowed"] == {"continue": True, "retry": True, "replan": True}


def test_idempotent_retry_bounded() -> None:
    decision = rp.decide_recovery("idempotent", has_terminal_evidence=True, retries_used=3)
    assert decision["allowed"]["retry"] is False
    assert "retry" in decision["reasons"]


def test_side_effectful_requires_confirm_and_no_retry() -> None:
    decision = rp.decide_recovery("side_effectful", has_terminal_evidence=True, retries_used=0)
    assert decision["risk"] == "high"
    assert decision["allowed"] == {"continue": True, "retry": False, "replan": True}
    assert "继续前需要确认" in decision["reasons"]["continue"]


def test_no_evidence_fail_closed() -> None:
    for cls in (None, "side_effect_free", "idempotent", "side_effectful", "unknown"):
        decision = rp.decide_recovery(cls, has_terminal_evidence=False, retries_used=0)
        assert decision["allowed"] == {"continue": False, "retry": False, "replan": True}


def test_exhaustive_matrix() -> None:
    for cls in (None, "side_effect_free", "idempotent", "side_effectful", "unknown"):
        for evidence in (False, True):
            for used in (0, 1, 3, 9):
                decision = rp.decide_recovery(cls, has_terminal_evidence=evidence, retries_used=used)
                assert set(decision) == {"risk", "allowed", "reasons"}
                assert set(decision["allowed"]) == {"continue", "retry", "replan"}
                assert decision["risk"] in {"low", "mid", "high", "none"}
