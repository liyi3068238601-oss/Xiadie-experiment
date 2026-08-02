"""Authoritative ToolRun v2 repository and instrumentation."""
from __future__ import annotations

from contextlib import contextmanager
import json
import time
from typing import Any, Iterator

from . import db
from .observability import bind_context, get_logger, new_trace_id
from .observability.redaction import redact, redact_text

logger = get_logger("tool.registry")

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "denied", "timed_out"})
TRANSITIONS = {
    "queued": {"authorizing", "cancelled", "denied"},
    "authorizing": {"running", "cancelled", "denied"},
    "running": {"succeeded", "failed", "cancelled", "timed_out"},
}
PHASE_BY_STATUS = {
    "queued": "queued", "authorizing": "authorizing", "running": "executing",
    "succeeded": "terminal", "failed": "terminal", "cancelled": "terminal",
    "denied": "terminal", "timed_out": "terminal",
}


class ToolRunError(ValueError):
    pass


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("arguments_summary_json", "result_summary_json", "artifact_ids_json"):
        raw = item.pop(key, "{}" if key != "artifact_ids_json" else "[]")
        try:
            item[key.removesuffix("_json")] = json.loads(raw)
        except (TypeError, ValueError):
            item[key.removesuffix("_json")] = {} if key != "artifact_ids_json" else []
    return item


def create(*, tool_name: str, trace_id: str = "", session_id: str | None = None,
           task_run_id: str | None = None, plugin_id: str | None = None,
           tool_version: str = "1", risk_level: str = "S0",
           arguments_summary: dict[str, Any] | None = None,
           idempotency_key: str | None = None) -> dict[str, Any]:
    run_id = f"tlr_{db.new_id()}"
    trace = trace_id or new_trace_id()
    now = db.now()
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO tool_runs(id,trace_id,session_id,task_run_id,plugin_id,tool_name,"
            "tool_version,risk_level,status,phase,queued_at,arguments_summary_json,"
            "idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, trace, session_id, task_run_id, plugin_id, tool_name, tool_version,
             risk_level, "queued", "queued", now,
             json.dumps(redact(arguments_summary or {}), ensure_ascii=False),
             idempotency_key, now, now),
        )
        _insert_event(conn, run_id, "tool_run_created", None, "queued", "queued", 1)
        conn.commit()
        row = conn.execute("SELECT * FROM tool_runs WHERE id=?", (run_id,)).fetchone()
    finally:
        conn.close()
    with bind_context(trace_id=trace, tool_run_id=run_id, session_id=session_id or "",
                      task_run_id=task_run_id or "", plugin_id=plugin_id or ""):
        logger.info("tool_run_queued", "Tool queued", tool_run_id=run_id,
                    tool_name=tool_name, status="queued", phase="queued", risk_level=risk_level)
    return _decode(row)


def transition(run_id: str, status: str, *, permission_grant_id: str | None = None,
               result_summary: dict[str, Any] | None = None,
               artifact_ids: list[str] | None = None, error: BaseException | None = None,
               error_code: str | None = None, cancellation_reason: str | None = None) -> dict[str, Any]:
    if status not in PHASE_BY_STATUS:
        raise ToolRunError("tool_run_status_invalid")
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM tool_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ToolRunError("tool_run_not_found")
        old = str(row["status"])
        if old in TERMINAL:
            raise ToolRunError("tool_run_terminal")
        if status not in TRANSITIONS.get(old, set()):
            raise ToolRunError("tool_run_transition_invalid")
        now = db.now()
        started = row["started_at"]
        finished = now if status in TERMINAL else None
        if status == "running" and started is None:
            started = now
        duration = round((finished - started) * 1000) if finished and started else None
        phase = PHASE_BY_STATUS[status]
        exc_type = type(error).__name__ if error else None
        exc_message = redact_text(str(error), limit=500) if error else None
        code = error_code or (getattr(error, "code", None) if error else None)
        conn.execute(
            "UPDATE tool_runs SET status=?,phase=?,permission_grant_id=COALESCE(?,permission_grant_id),"
            "started_at=?,finished_at=?,duration_ms=?,result_summary_json=?,artifact_ids_json=?,"
            "error_code=?,error_type=?,error_message=?,cancellation_reason=?,updated_at=? WHERE id=?",
            (status, phase, permission_grant_id, started, finished, duration,
             json.dumps(redact(result_summary or {}), ensure_ascii=False),
             json.dumps(artifact_ids or [], ensure_ascii=False), code, exc_type, exc_message,
             cancellation_reason, now, run_id),
        )
        _insert_event(conn, run_id, f"tool_run_{status}", old, status, phase,
                      int(row["attempt"]), error_code=code)
        conn.commit()
        updated = conn.execute("SELECT * FROM tool_runs WHERE id=?", (run_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    level = "ERROR" if status in {"failed", "timed_out"} else "WARNING" if status in {"denied", "cancelled"} else "INFO"
    with bind_context(trace_id=updated["trace_id"], tool_run_id=run_id,
                      session_id=updated["session_id"] or "", task_run_id=updated["task_run_id"] or "",
                      plugin_id=updated["plugin_id"] or ""):
        from .observability import log_event
        log_event(f"tool.{updated['tool_name']}", level, f"tool_run_{status}",
                  f"Tool {status}", error=error, fields={
                      "tool_name": updated["tool_name"], "status": status, "phase": phase,
                      "duration_ms": duration, "error_code": code,
                  })
    return _decode(updated)


def get(run_id: str) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM tool_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = _decode(row)
        result["events"] = [dict(item) for item in conn.execute(
            "SELECT * FROM tool_run_events WHERE tool_run_id=? ORDER BY created_at,id", (run_id,),
        ).fetchall()]
        return result
    finally:
        conn.close()


def list_recent(limit: int = 100) -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM tool_runs ORDER BY created_at DESC,id DESC LIMIT ?",
                            (max(1, min(int(limit), 500)),)).fetchall()
        return [_decode(row) for row in rows]
    finally:
        conn.close()


def _insert_event(conn, run_id: str, event_type: str, from_status: str | None,
                  to_status: str, phase: str, attempt: int, *, error_code: str | None = None) -> None:
    conn.execute(
        "INSERT INTO tool_run_events(id,tool_run_id,event_type,from_status,to_status,phase,attempt,error_code,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (f"tre_{db.new_id()}", run_id, event_type, from_status, to_status, phase, attempt,
         error_code, db.now()),
    )


@contextmanager
def instrument(*, tool_name: str, session_id: str | None = None,
               task_run_id: str | None = None, plugin_id: str | None = None,
               risk_level: str = "S0", arguments_summary: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    run = create(tool_name=tool_name, session_id=session_id, task_run_id=task_run_id,
                 plugin_id=plugin_id, risk_level=risk_level, arguments_summary=arguments_summary)
    transition(run["id"], "authorizing")
    running = transition(run["id"], "running")
    try:
        with bind_context(trace_id=running["trace_id"], tool_run_id=running["id"],
                          session_id=session_id or "", task_run_id=task_run_id or "",
                          plugin_id=plugin_id or ""):
            yield running
    except BaseException as exc:
        transition(run["id"], "failed", error=exc)
        raise
    else:
        transition(run["id"], "succeeded")
