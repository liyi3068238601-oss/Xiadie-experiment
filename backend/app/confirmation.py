"""CYR.3 confirmation requests: pending -> confirmed (grant) | denied."""
from __future__ import annotations

from typing import Any

from . import db, permission_guard


def create_request(*, session_id: str | None, tool_id: str, target: str,
                   risk_level: str = "S2", purpose: str = "",
                   grant_duration_seconds: int | None = None,
                   task_run_id: str | None = None,
                   node_id: str | None = None) -> dict[str, Any]:
    conn = db.connect()
    try:
        request_id = f"cnf_{db.new_id()}"
        conn.execute(
            "INSERT INTO confirmation_requests(id,session_id,tool_id,target,risk_level,purpose,"
            "grant_duration_seconds,status,task_run_id,node_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, session_id, tool_id, target, risk_level, purpose,
             grant_duration_seconds, "pending", task_run_id, node_id, db.now()),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM confirmation_requests WHERE id=?", (request_id,),
        ).fetchone())
    finally:
        conn.close()


def get(request_id: str) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM confirmation_requests WHERE id=?", (request_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def pending(session_id: str | None) -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM confirmation_requests WHERE status='pending' AND session_id=? "
            "ORDER BY created_at,id", (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def confirm(request_id: str, *, grant_duration_seconds: int | None) -> dict[str, Any]:
    request = get(request_id)
    if request is None:
        raise KeyError("confirmation_request_not_found")
    if request["status"] != "pending":
        return request  # 幂等
    duration = int(grant_duration_seconds or request["grant_duration_seconds"] or 3600)
    grant = permission_guard.create_grant(
        tool_id=request["tool_id"], target_kind="path_prefix",
        target=request["target"], purpose=request["purpose"],
        expires_at=db.now() + duration, session_id=request["session_id"],
    )
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE confirmation_requests SET status='confirmed',decided_at=?,confirmed_grant_id=? "
            "WHERE id=?",
            (db.now(), grant["id"], request_id),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM confirmation_requests WHERE id=?", (request_id,),
        ).fetchone())
    finally:
        conn.close()


def deny(request_id: str) -> dict[str, Any]:
    request = get(request_id)
    if request is None:
        raise KeyError("confirmation_request_not_found")
    if request["status"] != "pending":
        return request  # 幂等
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE confirmation_requests SET status='denied',decided_at=? WHERE id=?",
            (db.now(), request_id),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM confirmation_requests WHERE id=?", (request_id,),
        ).fetchone())
    finally:
        conn.close()
