from __future__ import annotations

import pytest

from app import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_schema_88_adds_lock_recovery_columns() -> None:
    conn = db.connect()
    try:
        cols = _columns(conn, "task_nodes")
        assert {"user_locked", "locked_reason", "recovery_class"} <= cols
        links = _columns(conn, "task_node_source_links")
        assert {"node_id", "source_kind", "source_id", "summary", "status",
                "invalidated_at", "invalidated_reason"} <= links
        assert db.get_schema_version() == 89
    finally:
        conn.close()
