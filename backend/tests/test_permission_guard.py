from __future__ import annotations

from pathlib import Path

import pytest

from app import db
from app.permission_guard import active_grant, check, create_grant, revoke_grant
from app.tool_registry import ToolManifest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


READ_TOOL = ToolManifest(
    id="workspace.read_file", name="read", description="",
    input_schema={}, output_schema={}, side_effect=False, risk_level="S0",
    declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
)
WRITE_TOOL = ToolManifest(
    id="workspace.write_file", name="write", description="",
    input_schema={}, output_schema={}, side_effect=True, risk_level="S2",
    declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
)


def _target(tmp_path: Path, name: str = "a.txt") -> str:
    return str((tmp_path / name).resolve())


def test_read_within_workspace_is_implicitly_allowed(tmp_path) -> None:
    assert check(READ_TOOL, target=_target(tmp_path), session_id="s1",
                 workspace=tmp_path) == "allowed"


def test_write_without_grant_needs_confirmation(tmp_path) -> None:
    assert check(WRITE_TOOL, target=_target(tmp_path), session_id="s1",
                 workspace=tmp_path) == "needs_confirmation"


def test_write_with_grant_allowed_then_revoke_denied(tmp_path) -> None:
    target = _target(tmp_path)
    grant = create_grant(tool_id="workspace.write_file", target_kind="path_prefix",
                         target=str(tmp_path.resolve()), purpose="写测试文件",
                         session_id="s1")
    assert check(WRITE_TOOL, target=target, session_id="s1",
                 workspace=tmp_path) == "allowed"
    assert revoke_grant(grant["id"], "不再需要") is True
    assert active_grant(WRITE_TOOL.id, target) is None
    assert check(WRITE_TOOL, target=target, session_id="s1",
                 workspace=tmp_path) == "denied"


def test_expired_grant_is_denied(tmp_path) -> None:
    target = _target(tmp_path)
    create_grant(tool_id="workspace.write_file", target_kind="path_prefix",
                 target=str(tmp_path.resolve()), purpose="x",
                 session_id="s1", expires_at=db.now() - 10)
    assert check(WRITE_TOOL, target=target, session_id="s1",
                 workspace=tmp_path) == "denied"
