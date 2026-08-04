"""CYR.3 recovery checkpoints: per-ToolRun input evidence for safe retry."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import db


def record(*, task_run_id: str, node_id: str | None, tool_run_id: str | None,
           input_hash: str, trace_id: str,
           artifact_before: dict[str, Any] | None = None) -> dict[str, Any]:
    conn = db.connect()
    try:
        checkpoint_id = f"chk_{db.new_id()}"
        conn.execute(
            "INSERT INTO recovery_checkpoints(id,task_run_id,node_id,tool_run_id,input_hash,"
            "artifact_before_json,trace_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (checkpoint_id, task_run_id, node_id, tool_run_id, input_hash,
             json.dumps(artifact_before or {}, ensure_ascii=False), trace_id, db.now()),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM recovery_checkpoints WHERE id=?", (checkpoint_id,),
        ).fetchone())
    finally:
        conn.close()


def latest(run_id: str) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM recovery_checkpoints WHERE task_run_id=? "
            "ORDER BY created_at DESC,id DESC LIMIT 1", (run_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def can_retry(run_id: str, tool_args: dict[str, Any]) -> bool:
    checkpoint = latest(run_id)
    if checkpoint is None:
        return False
    digest = hashlib.sha256(
        json.dumps(tool_args, ensure_ascii=False, sort_keys=True).encode(),
    ).hexdigest()
    return digest == checkpoint["input_hash"]
