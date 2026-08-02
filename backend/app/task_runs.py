"""Durable TaskRun and TaskNode state machine for the CYR.2 workbench."""
from __future__ import annotations

import json
from typing import Any

from . import db
from .observability import bind_context, log_event, new_trace_id
from .observability.redaction import redact_text

RUN_TERMINAL = frozenset({"completed", "cancelled"})
RUN_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"planning", "ready", "awaiting_approval", "cancelled"},
    "planning": {"ready", "awaiting_approval", "failed", "cancelled"},
    "awaiting_approval": {"ready", "planning", "cancelled"},
    "ready": {"running", "planning", "cancelled"},
    "running": {"paused", "planning", "completed", "failed", "cancelled", "recovery_required"},
    "paused": {"running", "planning", "cancelled"},
    "recovery_required": {"running", "paused", "planning", "failed", "cancelled"},
    "failed": {"planning", "ready", "cancelled"},
}
NODE_TERMINAL = frozenset({"succeeded", "failed", "skipped", "cancelled"})
MAX_NODES = 50


class TaskRunError(ValueError):
    pass


def _text(value: object, limit: int) -> str:
    return redact_text(str(value or "").strip(), limit=limit)


def _decode_run(row: Any) -> dict[str, Any]:
    return dict(row)


def _decode_node(row: Any) -> dict[str, Any]:
    item = dict(row)
    try:
        item["depends_on"] = json.loads(item.pop("depends_on_json"))
    except (TypeError, ValueError):
        item["depends_on"] = []
    return item


def _event(conn, run_id: str, event_type: str, *, node_id: str | None = None,
           from_status: str | None = None, to_status: str | None = None,
           revision: int, reason_code: str | None = None,
           metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO task_run_events(id,task_run_id,node_id,event_type,from_status,to_status,"
        "revision,reason_code,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (f"tse_{db.new_id()}", run_id, node_id, event_type, from_status, to_status,
         revision, reason_code, json.dumps(metadata or {}, ensure_ascii=False), db.now()),
    )


def _log(run: Any, event: str, message: str, *, level: str = "INFO", **fields: Any) -> None:
    with bind_context(trace_id=run["trace_id"], task_run_id=run["id"],
                      session_id=run["source_session_id"] or ""):
        log_event("task.scheduler", level, event, message, fields=fields)


def create(*, task_id: str, goal_summary: str = "", source_session_id: str | None = None,
           idempotency_key: str | None = None, trace_id: str = "") -> dict[str, Any]:
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        task = conn.execute("SELECT * FROM tasks WHERE id=? AND status!='archived'", (task_id,)).fetchone()
        if task is None:
            raise TaskRunError("task_not_found")
        selected_session_id = source_session_id or task["source_session_id"]
        if selected_session_id and conn.execute(
            "SELECT 1 FROM sessions WHERE id=?", (selected_session_id,),
        ).fetchone() is None:
            raise TaskRunError("task_session_not_found")
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM task_runs WHERE task_id=? AND idempotency_key=?",
                (task_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return get(existing["id"]) or _decode_run(existing)
        run_id = f"trn_{db.new_id()}"
        now = db.now()
        trace = trace_id or new_trace_id()
        summary = _text(goal_summary or task["title"], 500)
        conn.execute(
            "INSERT INTO task_runs(id,task_id,trace_id,source_session_id,status,goal_summary,"
            "next_action,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (run_id, task_id, trace, selected_session_id, "draft",
             summary, "制定执行计划", idempotency_key, now, now),
        )
        _event(conn, run_id, "task_run_created", to_status="draft", revision=1)
        conn.commit()
        row = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    _log(row, "task_run_created", "Task run created", status="draft", task_id=task_id)
    return get(run_id) or _decode_run(row)


def list_for_task(task_id: str) -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM task_runs WHERE task_id=? ORDER BY created_at DESC,id DESC", (task_id,),
        ).fetchall()
        return [_decode_run(row) for row in rows]
    finally:
        conn.close()


def get(run_id: str) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = _decode_run(row)
        result["nodes"] = [_decode_node(item) for item in conn.execute(
            "SELECT * FROM task_nodes WHERE task_run_id=? ORDER BY position,id", (run_id,),
        ).fetchall()]
        result["events"] = [dict(item) for item in conn.execute(
            "SELECT * FROM task_run_events WHERE task_run_id=? ORDER BY created_at,id", (run_id,),
        ).fetchall()]
        for event in result["events"]:
            try:
                event["metadata"] = json.loads(event.pop("metadata_json"))
            except (TypeError, ValueError):
                event["metadata"] = {}
        result["artifacts"] = [dict(item) for item in conn.execute(
            "SELECT * FROM task_run_artifact_links WHERE task_run_id=? ORDER BY created_at,id", (run_id,),
        ).fetchall()]
        result["tool_runs"] = [dict(item) for item in conn.execute(
            "SELECT id,trace_id,plugin_id,tool_name,status,phase,error_code,error_type,error_message,"
            "created_at,updated_at FROM tool_runs WHERE task_run_id=? ORDER BY created_at,id", (run_id,),
        ).fetchall()]
        return result
    finally:
        conn.close()


def _validate_plan(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not nodes or len(nodes) > MAX_NODES:
        raise TaskRunError("task_plan_node_count_invalid")
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(nodes):
        client_id = _text(raw.get("client_id") or f"step-{index + 1}", 80)
        title = _text(raw.get("title"), 240)
        if not client_id or not title or client_id in ids:
            raise TaskRunError("task_plan_node_invalid")
        ids.add(client_id)
        dependencies = raw.get("depends_on") or []
        if not isinstance(dependencies, list) or len(dependencies) > MAX_NODES:
            raise TaskRunError("task_plan_dependencies_invalid")
        normalized.append({"client_id": client_id, "title": title,
                           "depends_on": [_text(item, 80) for item in dependencies],
                           "completion_criteria": _text(raw.get("completion_criteria"), 500)})
    graph = {item["client_id"]: item["depends_on"] for item in normalized}
    if any(dep not in ids or dep == node for node, deps in graph.items() for dep in deps):
        raise TaskRunError("task_plan_dependency_unknown")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            raise TaskRunError("task_plan_cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
    return normalized


def replace_plan(run_id: str, nodes: list[dict[str, Any]], *, requires_approval: bool = False) -> dict[str, Any]:
    plan = _validate_plan(nodes)
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise TaskRunError("task_run_not_found")
        if run["status"] not in {"draft", "planning", "paused", "recovery_required", "failed"}:
            raise TaskRunError("task_plan_replace_not_allowed")
        old_status = run["status"]
        conn.execute("DELETE FROM task_nodes WHERE task_run_id=?", (run_id,))
        now = db.now()
        for position, item in enumerate(plan):
            conn.execute(
                "INSERT INTO task_nodes(id,task_run_id,client_id,position,title,status,depends_on_json,"
                "completion_criteria,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (f"tnd_{db.new_id()}", run_id, item["client_id"], position, item["title"], "pending",
                 json.dumps(item["depends_on"], ensure_ascii=False), item["completion_criteria"], now, now),
            )
        target = "awaiting_approval" if requires_approval else "ready"
        revision = int(run["revision"]) + 1
        plan_version = int(run["plan_version"]) + 1
        conn.execute(
            "UPDATE task_runs SET status=?,revision=?,plan_version=?,progress_current=0,"
            "progress_total=?,current_node_id=NULL,waiting_reason=?,next_action=?,error_code=NULL,"
            "error_message=NULL,finished_at=NULL,updated_at=? WHERE id=?",
            (target, revision, plan_version, len(plan), "等待用户批准" if requires_approval else "",
             "批准计划" if requires_approval else "开始执行", now, run_id),
        )
        _event(conn, run_id, "task_plan_replaced", from_status=old_status, to_status=target,
               revision=revision, metadata={"plan_version": plan_version, "node_count": len(plan)})
        conn.commit()
        updated = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    _log(updated, "task_plan_replaced", "Task plan replaced", status=target,
         plan_version=plan_version, node_count=len(plan))
    return get(run_id) or _decode_run(updated)


def approve(run_id: str) -> dict[str, Any]:
    return transition(run_id, "ready", event_type="task_plan_approved", next_action="开始执行")


def start(run_id: str) -> dict[str, Any]:
    result = transition(run_id, "running", event_type="task_run_started", next_action="执行可用步骤")
    _refresh_ready_nodes(run_id)
    return get(run_id) or result


def pause(run_id: str) -> dict[str, Any]:
    current = get(run_id)
    if current and current["status"] == "paused":
        return current
    return transition(run_id, "paused", event_type="task_run_paused", waiting_reason="已由用户暂停",
                      next_action="继续或重新规划")


def resume(run_id: str) -> dict[str, Any]:
    result = transition(run_id, "running", event_type="task_run_resumed", next_action="执行可用步骤")
    _refresh_ready_nodes(run_id)
    return get(run_id) or result


def cancel(run_id: str) -> dict[str, Any]:
    current = get(run_id)
    if current and current["status"] == "cancelled":
        return current
    return transition(run_id, "cancelled", event_type="task_run_cancelled", next_action="")


def replan(run_id: str) -> dict[str, Any]:
    return transition(run_id, "planning", event_type="task_replan_requested", next_action="提交新计划")


def transition(run_id: str, target: str, *, event_type: str, waiting_reason: str = "",
               next_action: str = "", error_code: str | None = None,
               error_message: str | None = None) -> dict[str, Any]:
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise TaskRunError("task_run_not_found")
        old = str(run["status"])
        if target not in RUN_TRANSITIONS.get(old, set()):
            raise TaskRunError("task_run_transition_invalid")
        now = db.now()
        if target == "completed":
            incomplete = conn.execute(
                "SELECT COUNT(*) FROM task_nodes WHERE task_run_id=? "
                "AND status NOT IN ('succeeded','skipped')", (run_id,),
            ).fetchone()[0]
            if incomplete:
                raise TaskRunError("task_run_completion_evidence_missing")
        revision = int(run["revision"]) + 1
        started = run["started_at"] or (now if target == "running" else None)
        finished = now if target in RUN_TERMINAL or target == "failed" else None
        conn.execute(
            "UPDATE task_runs SET status=?,revision=?,waiting_reason=?,next_action=?,error_code=?,"
            "error_message=?,started_at=?,finished_at=?,updated_at=? WHERE id=?",
            (target, revision, _text(waiting_reason, 240), _text(next_action, 240), error_code,
             _text(error_message, 500) or None, started, finished, now, run_id),
        )
        if target == "running":
            conn.execute("UPDATE tasks SET status='doing',updated_at=? WHERE id=?", (now, run["task_id"]))
        elif target == "completed":
            conn.execute("UPDATE tasks SET status='done',updated_at=? WHERE id=?", (now, run["task_id"]))
        if target in {"paused", "planning"}:
            conn.execute(
                "UPDATE task_nodes SET status='blocked',revision=revision+1,updated_at=? "
                "WHERE task_run_id=? AND status='running'", (now, run_id),
            )
        elif target == "cancelled":
            conn.execute(
                "UPDATE task_nodes SET status='cancelled',finished_at=?,updated_at=?,revision=revision+1 "
                "WHERE task_run_id=? AND status NOT IN ('succeeded','failed','skipped','cancelled')",
                (now, now, run_id),
            )
        _event(conn, run_id, event_type, from_status=old, to_status=target, revision=revision,
               reason_code=error_code)
        conn.commit()
        updated = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    _log(updated, event_type, f"Task run {target}",
         level="ERROR" if target == "failed" else "WARNING" if target in {"cancelled", "recovery_required"} else "INFO",
         from_status=old, status=target, error_code=error_code)
    return get(run_id) or _decode_run(updated)


def _refresh_ready_nodes(run_id: str, conn=None) -> None:
    owns = conn is None
    conn = conn or db.connect()
    try:
        rows = conn.execute("SELECT * FROM task_nodes WHERE task_run_id=? ORDER BY position", (run_id,)).fetchall()
        succeeded = {row["client_id"] for row in rows if row["status"] in {"succeeded", "skipped"}}
        now = db.now()
        for row in rows:
            if row["status"] not in {"pending", "blocked"}:
                continue
            deps = json.loads(row["depends_on_json"] or "[]")
            status = "ready" if all(dep in succeeded for dep in deps) else "blocked"
            conn.execute("UPDATE task_nodes SET status=?,updated_at=? WHERE id=?", (status, now, row["id"]))
        if owns:
            conn.commit()
    finally:
        if owns:
            conn.close()


def transition_node(run_id: str, node_id: str, action: str, *, output_summary: str = "",
                    error_code: str | None = None, error_message: str | None = None) -> dict[str, Any]:
    targets = {"start": "running", "succeed": "succeeded", "fail": "failed", "skip": "skipped"}
    if action not in targets:
        raise TaskRunError("task_node_action_invalid")
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        node = conn.execute("SELECT * FROM task_nodes WHERE id=? AND task_run_id=?", (node_id, run_id)).fetchone()
        if run is None or node is None:
            raise TaskRunError("task_node_not_found")
        if run["status"] != "running":
            raise TaskRunError("task_run_not_running")
        old = node["status"]
        target = targets[action]
        allowed = ((action == "start" and old == "ready") or
                   (action in {"succeed", "fail"} and old == "running") or
                   (action == "skip" and old in {"ready", "blocked", "pending"}))
        if not allowed:
            raise TaskRunError("task_node_transition_invalid")
        now = db.now()
        finished = now if target in NODE_TERMINAL else None
        started = node["started_at"] or (now if target == "running" else None)
        node_revision = int(node["revision"]) + 1
        conn.execute(
            "UPDATE task_nodes SET status=?,output_summary=?,error_code=?,error_message=?,revision=?,"
            "started_at=?,finished_at=?,updated_at=? WHERE id=?",
            (target, _text(output_summary, 500), error_code, _text(error_message, 500) or None,
             node_revision, started, finished, now, node_id),
        )
        run_revision = int(run["revision"]) + 1
        _event(conn, run_id, f"task_node_{target}", node_id=node_id, from_status=old,
               to_status=target, revision=run_revision, reason_code=error_code)
        conn.execute("UPDATE task_runs SET revision=?,current_node_id=?,updated_at=? WHERE id=?",
                     (run_revision, None if target in NODE_TERMINAL else node_id, now, run_id))
        if target in {"succeeded", "skipped"}:
            _refresh_ready_nodes(run_id, conn)
        counts = conn.execute(
            "SELECT COUNT(*) AS total,SUM(CASE WHEN status IN ('succeeded','skipped') THEN 1 ELSE 0 END) AS done "
            "FROM task_nodes WHERE task_run_id=?", (run_id,),
        ).fetchone()
        done = int(counts["done"] or 0)
        total = int(counts["total"])
        conn.execute("UPDATE task_runs SET progress_current=?,progress_total=? WHERE id=?",
                     (done, total, run_id))
        final_status: str | None = None
        if target == "failed":
            final_status = "failed"
            final_revision = run_revision + 1
            conn.execute(
                "UPDATE task_runs SET status='failed',revision=?,current_node_id=NULL,error_code=?,"
                "error_message=?,waiting_reason='',next_action='重新规划或取消',finished_at=?,updated_at=? WHERE id=?",
                (final_revision, error_code or "task_node_failed",
                 _text(error_message, 500) or "任务步骤失败", now, now, run_id),
            )
            _event(conn, run_id, "task_run_failed", from_status="running", to_status="failed",
                   revision=final_revision, reason_code=error_code or "task_node_failed")
        elif total and done == total:
            final_status = "completed"
            final_revision = run_revision + 1
            conn.execute(
                "UPDATE task_runs SET status='completed',revision=?,current_node_id=NULL,waiting_reason='',"
                "next_action='',finished_at=?,updated_at=? WHERE id=?", (final_revision, now, now, run_id),
            )
            conn.execute("UPDATE tasks SET status='done',updated_at=? WHERE id=?", (now, run["task_id"]))
            _event(conn, run_id, "task_run_completed", from_status="running", to_status="completed",
                   revision=final_revision)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    current = get(run_id)
    assert current is not None
    _log(current, f"task_node_{target}", f"Task node {target}",
         level="ERROR" if final_status == "failed" else "INFO", node_id=node_id,
         node_status=target, progress_current=current["progress_current"], progress_total=current["progress_total"])
    return current


def link_artifact(run_id: str, artifact_id: str, *, node_id: str | None = None, label: str = "") -> dict[str, Any]:
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise TaskRunError("task_run_not_found")
        if node_id and conn.execute("SELECT 1 FROM task_nodes WHERE id=? AND task_run_id=?", (node_id, run_id)).fetchone() is None:
            raise TaskRunError("task_node_not_found")
        link_id = f"tal_{db.new_id()}"
        conn.execute(
            "INSERT INTO task_run_artifact_links(id,task_run_id,node_id,artifact_id,label,created_at) VALUES(?,?,?,?,?,?)",
            (link_id, run_id, node_id, _text(artifact_id, 120), _text(label, 120), db.now()),
        )
        revision = int(run["revision"]) + 1
        conn.execute("UPDATE task_runs SET revision=?,updated_at=? WHERE id=?", (revision, db.now(), run_id))
        _event(conn, run_id, "task_artifact_linked", node_id=node_id, revision=revision,
               metadata={"artifact_id": _text(artifact_id, 120)})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get(run_id) or {}


def recover_stale_runs() -> int:
    """Stop implicit continuation: interrupted running work requires an explicit resume."""
    conn = db.connect()
    changed: list[dict[str, Any]] = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT * FROM task_runs WHERE status='running'").fetchall()
        now = db.now()
        for run in rows:
            revision = int(run["revision"]) + 1
            conn.execute(
                "UPDATE task_runs SET status='recovery_required',revision=?,waiting_reason=?,next_action=?,"
                "current_node_id=NULL,updated_at=? WHERE id=?",
                (revision, "应用重启中断了执行", "检查状态后继续、重新规划或取消", now, run["id"]),
            )
            conn.execute("UPDATE task_nodes SET status='blocked',revision=revision+1,updated_at=? "
                         "WHERE task_run_id=? AND status='running'", (now, run["id"]))
            _event(conn, run["id"], "task_run_recovery_required", from_status="running",
                   to_status="recovery_required", revision=revision, reason_code="process_restarted")
            changed.append(dict(run))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    for run in changed:
        _log(run, "task_run_recovery_required", "Interrupted task requires explicit recovery",
             level="WARNING", from_status="running", status="recovery_required",
             reason_code="process_restarted")
    return len(changed)
