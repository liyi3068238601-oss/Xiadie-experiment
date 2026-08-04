"""CYR.3 artifact domain: bounded versions, audit soft-delete, preview, purge."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from . import db

MAX_VERSIONS = 10


def _root() -> Path:
    return Path(db.DATA_DIR) / "artifacts"


def _file_path(run_id: str, artifact_id: str, version: int) -> Path:
    return _root() / run_id / artifact_id / f"v{version}"


def create_version(*, task_run_id: str, node_id: str | None, artifact_id: str,
                   kind: str, mime: str, data: bytes, workspace: Path) -> dict[str, Any]:
    if kind not in {"text", "markdown", "image", "pdf", "data"}:
        raise ValueError("artifact_kind 非法")
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT MAX(version) AS v FROM artifacts WHERE artifact_id=?", (artifact_id,),
        ).fetchone()
        version = int(row["v"] or 0) + 1
        path = _file_path(task_run_id, artifact_id, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        conn.execute(
            "INSERT INTO artifacts(id,artifact_id,task_run_id,node_id,artifact_kind,mime_type,"
            "size_bytes,sha256,version,status,provenance_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"art_{db.new_id()}", artifact_id, task_run_id, node_id, kind, mime,
             len(data), digest, version, "active", "{}", db.now(), db.now()),
        )
        # 超出最近 N 版：归档旧版（保留审计）
        stale = conn.execute(
            "SELECT id FROM artifacts WHERE artifact_id=? AND status='active' "
            "ORDER BY version DESC LIMIT -1 OFFSET ?",
            (artifact_id, MAX_VERSIONS),
        ).fetchall()
        now = db.now()
        for item in stale:
            conn.execute(
                "UPDATE artifacts SET status='archived',updated_at=? WHERE id=?",
                (now, item["id"]),
            )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM artifacts WHERE artifact_id=? AND version=?",
            (artifact_id, version),
        ).fetchone())
    finally:
        conn.close()


def get(artifact_id: str, *, version: int | None = None) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        if version is None:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id=? AND status='active' "
                "ORDER BY version DESC LIMIT 1", (artifact_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id=? AND version=?", (artifact_id, version),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def active(artifact_id: str) -> dict[str, Any] | None:
    return get(artifact_id)


def list(run_id: str) -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT artifact_id,artifact_kind,mime_type,status FROM artifacts "
            "WHERE task_run_id=? AND status='active' GROUP BY artifact_id "
            "ORDER BY MAX(version) DESC,artifact_id",
            (run_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = get(row["artifact_id"])
            if item is None:
                continue
            versions = conn.execute(
                "SELECT version,status,size_bytes,sha256 FROM artifacts "
                "WHERE artifact_id=? AND status='active' ORDER BY version DESC",
                (row["artifact_id"],),
            ).fetchall()
            item["versions"] = [dict(v) for v in versions]
            result.append(item)
        return result
    finally:
        conn.close()


def rollback(artifact_id: str) -> dict[str, Any]:
    current = active(artifact_id)
    if current is None or current["version"] <= 1:
        raise ValueError("no_previous_version")
    conn = db.connect()
    try:
        now = db.now()
        conn.execute(
            "UPDATE artifacts SET status='archived',updated_at=? WHERE artifact_id=? "
            "AND version=?", (now, artifact_id, current["version"]),
        )
        conn.commit()
    finally:
        conn.close()
    restored = active(artifact_id)
    if restored is None:
        raise ValueError("rollback_failed")
    return restored


def soft_delete(artifact_id: str) -> bool:
    conn = db.connect()
    try:
        updated = conn.execute(
            "UPDATE artifacts SET status='soft_deleted',updated_at=? "
            "WHERE artifact_id=? AND status='active'", (db.now(), artifact_id),
        ).rowcount
        conn.commit()
        return bool(updated)
    finally:
        conn.close()


def purge(artifact_id: str) -> None:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE artifact_id=? AND status='soft_deleted'",
            (artifact_id,),
        ).fetchall()
        conn.execute("DELETE FROM artifacts WHERE artifact_id=? AND status='soft_deleted'",
                     (artifact_id,))
        conn.commit()
    finally:
        conn.close()
    for row in rows:
        path = _file_path(row["task_run_id"] or "", artifact_id, row["version"])
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass


def preview(artifact_id: str) -> bytes:
    item = active(artifact_id)
    if item is None:
        raise KeyError("artifact_not_found")
    path = _file_path(item["task_run_id"] or "", artifact_id, item["version"])
    return path.read_bytes()
