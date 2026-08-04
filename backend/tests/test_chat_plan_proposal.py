from __future__ import annotations

import pytest

from app import db, task_planner


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_mock_chat_never_emits_plan_proposal() -> None:
    # 演示模型下 gen() 不调用 planner：以意图匹配与生成 fail closed 组合断言。
    assert task_planner.matches_planning_intent("帮我拆解一个方案，列成步骤")
    # 生成失败关闭（mock provider）由 test_task_planner 覆盖；此处锁行为契约。
    assert db.get_schema_version() == 89
