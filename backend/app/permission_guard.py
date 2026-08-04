"""CYR.3 permission guard: scoped, expiring, revocable tool grants."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import db
from .tool_registry import ToolManifest


def create_grant(*, tool_id: str, target_kind: str, target: str, purpose: str = "",
                 expires_at: float | None = None, session_id: str | None = None) -> dict[str, Any]:
    if target_kind not in {"path_prefix", "domain"}:
        raise ValueError("target_kind 必须是 path_prefix 或 domain")
    conn = db.connect()
    try:
        grant_id = f"ptg_{db.new_id()}"
        conn.execute(
            "INSERT INTO permission_grants(id,tool_id,target_kind,target,purpose,expires_at,"
            "session_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (grant_id, tool_id, target_kind, target, purpose, expires_at, session_id, db.now()),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM permission_grants WHERE id=?", (grant_id,)).fetchone())
    finally:
        conn.close()


def revoke_grant(grant_id: str, reason: str) -> bool:
    conn = db.connect()
    try:
        updated = conn.execute(
            "UPDATE permission_grants SET revoked_at=?,revoked_reason=? WHERE id=? AND revoked_at IS NULL",
            (db.now(), reason, grant_id),
        ).rowcount
        conn.commit()
        return bool(updated)
    finally:
        conn.close()


def active_grant(tool_id: str, target: str) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM permission_grants WHERE tool_id=? AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?) ORDER BY created_at DESC LIMIT 1",
            (tool_id, db.now()),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    grant = dict(row)
    if grant["target_kind"] == "path_prefix":
        try:
            if not Path(target).resolve().is_relative_to(Path(grant["target"]).resolve()):
                return None
        except (OSError, ValueError):
            return None
    elif grant["target"] != target:
        return None
    return grant


def check(tool: ToolManifest, *, target: str, session_id: str | None,
          workspace: Path) -> str:
    """Return allowed | denied | needs_confirmation."""
    workspace_root = str(Path(workspace).resolve())
    try:
        inside = Path(target).resolve().is_relative_to(Path(workspace_root))
    except (OSError, ValueError):
        inside = False
    if not tool.side_effect and tool.risk_level == "S0" and inside:
        return "allowed"  # 工作区内只读：会话级隐式授权
    if active_grant(tool.id, target) is not None:
        return "allowed"
    if active_grant(tool.id, target) is None and _has_expired_or_revoked(tool.id, target):
        return "denied"
    return "needs_confirmation"


def _has_expired_or_revoked(tool_id: str, target: str) -> bool:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM permission_grants WHERE tool_id=? AND "
            "(revoked_at IS NOT NULL OR (expires_at IS NOT NULL AND expires_at <= ?)) LIMIT 1",
            (tool_id, db.now()),
        ).fetchone()
    finally:
        conn.close()
    return row is not None
