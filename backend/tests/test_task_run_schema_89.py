from __future__ import annotations

import pytest

from app import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_schema_89_tables_and_columns() -> None:
    conn = db.connect()
    try:
        node_cols = {r["name"] for r in conn.execute("PRAGMA table_info(task_nodes)").fetchall()}
        assert {"tool_ref", "tool_args_json"} <= node_cols
        for table in ("permission_grants", "confirmation_requests", "artifacts",
                      "recovery_checkpoints"):
            assert conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone() is not None
        artifact_cols = {r["name"] for r in conn.execute("PRAGMA table_info(artifacts)").fetchall()}
        assert {"artifact_id", "version", "status", "sha256", "purged_at"} <= artifact_cols
        grant_cols = {r["name"] for r in conn.execute("PRAGMA table_info(permission_grants)").fetchall()}
        assert {"tool_id", "target_kind", "target", "expires_at", "revoked_at"} <= grant_cols
        assert db.get_schema_version() == 89
    finally:
        conn.close()
