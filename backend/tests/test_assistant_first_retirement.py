"""Assistant-first retirement gates that protect retained memory capabilities."""

import os

from fastapi.testclient import TestClient

from app import db, kig_query_planner, kig_retrieval, main, short_memo


client = TestClient(main.app, headers={"X-Xiadie-Token": "test-token-with-at-least-thirty-two-bytes"})


def test_life_http_surface_is_absent_and_short_memo_has_assistant_owner():
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    assert not any(path.startswith("/api/life") for path in paths)
    assert "/api/assistant/short-memos" in paths
    assert "/api/assistant/short-memo-settings" in paths


def test_short_memo_settings_migrated_out_of_life_namespace():
    db.init_db()
    conn = db.connect()
    try:
        old_count = conn.execute(
            "SELECT COUNT(*) FROM settings WHERE key LIKE 'life.short_memo.%'"
        ).fetchone()[0]
        new_count = conn.execute(
            "SELECT COUNT(*) FROM settings WHERE key LIKE 'assistant.short_memo.%'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert old_count == 0
    assert new_count == 7
    assert short_memo.rollout_snapshot().enabled is True


def test_retired_tables_are_absent_and_recovery_backup_exists():
    db.init_db()
    conn = db.connect()
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert version == "84"
    assert not set(db.RETIRED_LIFE_TABLES) & tables
    assert {"short_memos", "short_memo_events", "reminders", "tasks"} <= tables
    assert os.path.exists(os.path.join(
        db.DATA_DIR, "backups", "life-retirement-before-schema-84.json",
    ))


def test_kig_planner_and_retrieval_expose_five_non_life_sources():
    expected = ("knowledge", "memory", "history", "task", "lore")
    assert kig_query_planner.SOURCES == expected
    assert kig_retrieval.SOURCES == expected


def test_schema_84_migrates_grounded_date_and_user_goal_before_drop(tmp_path, monkeypatch):
    isolated_path = tmp_path / "retirement.db"
    monkeypatch.setattr(db, "DB_PATH", str(isolated_path))
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    conn = db.connect()
    try:
        conn.executescript(db.SCHEMA)
        for target, sql in db.MIGRATIONS:
            if target > 83:
                break
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(target),),
            )
        conn.execute(
            "INSERT INTO important_dates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("date-1", "项目纪念日", "active", "yearly_solar", None, 8, 1,
             "Asia/Shanghai", 1.0, "natural", 1, 10.0, 10.0),
        )
        conn.execute(
            "INSERT INTO important_date_sources VALUES(?,?,?,?,?,?,?,?,?)",
            ("date-source-1", "date-1", "user_statement", "message-1", "1", "a" * 64,
             1, 10.0, None),
        )
        conn.execute(
            "INSERT INTO personal_goals VALUES(?,?,?,?,?,?,?,?,?)",
            ("goal-1", "完成迁移", "active", 2, 1.0, 1, "2026-08-05", 10.0, 10.0),
        )
        conn.execute(
            "INSERT INTO personal_goal_sources VALUES(?,?,?,?,?,?,?,?)",
            ("goal-source-1", "goal-1", "user_explicit", "message-2", "1", "b" * 64,
             1, 10.0),
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db()
    conn = db.connect()
    try:
        reminder = conn.execute(
            "SELECT * FROM reminders WHERE source_id='date-1'"
        ).fetchone()
        task = conn.execute(
            "SELECT * FROM tasks WHERE id='retired-goal:goal-1'"
        ).fetchone()
    finally:
        conn.close()
    assert reminder and reminder["title"] == "项目纪念日"
    assert task and task["status"] == "doing" and task["due_date"] == "2026-08-05"
