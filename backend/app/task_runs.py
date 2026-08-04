"""Durable TaskRun and TaskNode aggregate writer for the CYR.2 workbench."""
from __future__ import annotations

import json
from typing import Any

from . import db, kig_sources, task_run_contract as contract
from .observability import bind_context, log_event, new_trace_id
from .observability.redaction import redact_text

RUN_TERMINAL = contract.RUN_TERMINAL
NODE_TERMINAL = contract.NODE_TERMINAL
MAX_NODES = 50
SOURCE_KINDS = {"memory_fragment", "memory_episode", "memory_saga",
                "memory_entity", "knowledge_source", "conversation"}
RECOVERY_CLASSES = {"side_effect_free", "idempotent", "side_effectful"}


class TaskRunError(ValueError):
    pass


class TaskRunConflict(TaskRunError):
    def __init__(self, code: str, *, current: dict[str, Any] | None = None,
                 run_id: str | None = None):
        spec = contract.ERROR_SPECS[code]
        super().__init__(code)
        self.code = code
        self.message = spec.message
        self.retry = spec.retry
        self.current = current
        self.run_id = run_id

    @classmethod
    def from_decision(cls, decision: contract.Decision, *, run_id: str) -> "TaskRunConflict":
        assert decision.code is not None
        error = cls(decision.code, run_id=run_id)
        error.message = decision.message or error.message
        error.retry = decision.retry or error.retry
        return error


class _MutationConflict(Exception):
    def __init__(self, conflict: TaskRunConflict):
        self.conflict = conflict


def _text(value: object, limit: int) -> str:
    return redact_text(str(value or "").strip(), limit=limit)


def _decode_run(row: Any) -> dict[str, Any]:
    return dict(row)


def _decode_node(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["user_locked"] = bool(item.get("user_locked"))
    try:
        item["tool_args"] = json.loads(item.pop("tool_args_json") or "{}")
    except (TypeError, ValueError):
        item["tool_args"] = {}
    try:
        item["depends_on"] = json.loads(item.pop("depends_on_json"))
    except (TypeError, ValueError):
        item["depends_on"] = []
    return item


def _decode_event(row: Any) -> dict[str, Any]:
    """Return the body-free, client-safe representation of a TaskRun event."""
    item = dict(row)
    try:
        item["metadata"] = json.loads(item.pop("metadata_json"))
    except (TypeError, ValueError):
        item["metadata"] = {}
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


def _log_conflict(error: TaskRunConflict) -> None:
    current = error.current
    if not current:
        return
    _log(current, "task_run_conflict", "Task run command rejected", level="WARNING",
         code=error.code, retry=error.retry, status=current["status"],
         revision=current["revision"])


def _raise_decision(decision: contract.Decision, run_id: str) -> None:
    if decision.outcome == "reject":
        raise _MutationConflict(TaskRunConflict.from_decision(decision, run_id=run_id))


def _finish_conflict(error: TaskRunConflict) -> None:
    if error.run_id:
        error.current = get(error.run_id)
    _log_conflict(error)
    raise error


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


def list_events(run_id: str, *, after: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Read a bounded, cursor-addressable event history without changing state.

    Event ids are opaque, so the cursor is resolved to its durable
    ``(created_at, id)`` ordering pair.  An unknown cursor is explicitly a
    gap: callers must refresh the authoritative TaskRun snapshot instead of
    guessing at a missed transition.
    """
    requested_limit = min(max(int(limit), 1), 500)
    conn = db.connect()
    try:
        if conn.execute("SELECT 1 FROM task_runs WHERE id=?", (run_id,)).fetchone() is None:
            raise TaskRunError("task_run_not_found")
        cursor = None
        if after:
            cursor = conn.execute(
                "SELECT id,created_at FROM task_run_events WHERE task_run_id=? AND id=?",
                (run_id, after),
            ).fetchone()
            if cursor is None:
                return {"events": [], "cursor": after, "gap": True}
        if cursor is None:
            rows = conn.execute(
                "SELECT * FROM task_run_events WHERE task_run_id=? ORDER BY created_at,id LIMIT ?",
                (run_id, requested_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM task_run_events WHERE task_run_id=? "
                "AND (created_at>? OR (created_at=? AND id>?)) "
                "ORDER BY created_at,id LIMIT ?",
                (run_id, cursor["created_at"], cursor["created_at"], cursor["id"], requested_limit),
            ).fetchall()
        events = [_decode_event(row) for row in rows]
        return {"events": events, "cursor": events[-1]["id"] if events else (after or None), "gap": False}
    finally:
        conn.close()


def get(run_id: str) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = _decode_run(row)
        node_rows = conn.execute(
            "SELECT * FROM task_nodes WHERE task_run_id=? ORDER BY position,id", (run_id,),
        ).fetchall()
        result["nodes"] = []
        for node_row in node_rows:
            item = _decode_node(node_row)
            item["source_links"] = [dict(link) for link in conn.execute(
                "SELECT id,source_kind,source_id,summary,status,invalidated_at,invalidated_reason "
                "FROM task_node_source_links WHERE node_id=? ORDER BY id", (node_row["id"],),
            ).fetchall()]
            result["nodes"].append(item)
        result["events"] = [_decode_event(item) for item in conn.execute(
            "SELECT * FROM task_run_events WHERE task_run_id=? ORDER BY created_at,id", (run_id,),
        ).fetchall()]
        result["artifacts"] = [dict(item) for item in conn.execute(
            "SELECT * FROM task_run_artifact_links WHERE task_run_id=? ORDER BY created_at,id", (run_id,),
        ).fetchall()]
        result["tool_runs"] = []
        for item in conn.execute(
            "SELECT id,trace_id,task_run_id,plugin_id,tool_name,status,phase,error_code,error_type,"
            "error_message,result_summary_json,created_at,updated_at FROM tool_runs "
            "WHERE task_run_id=? ORDER BY created_at,id", (run_id,),
        ).fetchall():
            decoded = dict(item)
            try:
                decoded["result_summary"] = json.loads(decoded.pop("result_summary_json") or "{}")
            except (TypeError, ValueError):
                decoded["result_summary"] = {}
            result["tool_runs"].append(decoded)
        return result
    finally:
        conn.close()


def _normalize_plan(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not nodes or len(nodes) > MAX_NODES:
        raise TaskRunConflict("task_plan_node_count_invalid")
    prepared: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(nodes):
        client_id = _text(raw.get("client_id") or f"step-{index + 1}", 80)
        title = _text(raw.get("title"), 240)
        if not client_id or not title or client_id in ids:
            raise TaskRunConflict("task_plan_node_invalid")
        dependencies = raw.get("depends_on") or []
        if not isinstance(dependencies, list) or len(dependencies) > MAX_NODES:
            raise TaskRunConflict("task_plan_dependencies_invalid")
        raw_refs = raw.get("input_refs") or []
        if not isinstance(raw_refs, list) or len(raw_refs) > 20:
            raise TaskRunConflict("task_plan_dependencies_invalid")
        refs: list[dict[str, str]] = []
        for ref in raw_refs:
            kind = _text(ref.get("source_kind") if isinstance(ref, dict) else None, 40)
            source_id = _text(ref.get("source_id") if isinstance(ref, dict) else None, 200)
            if kind not in SOURCE_KINDS or not source_id:
                raise TaskRunConflict("task_source_ref_invalid")
            refs.append({"source_kind": kind, "source_id": source_id})
        locked = bool(raw.get("user_locked"))
        locked_reason = _text(raw.get("locked_reason"), 20) or None
        if locked_reason not in (None, "edit", "explicit"):
            raise TaskRunConflict("task_plan_node_invalid")
        recovery_class = _text(raw.get("recovery_class"), 30) or None
        if recovery_class is not None and recovery_class not in RECOVERY_CLASSES:
            raise TaskRunConflict("task_plan_node_invalid")
        tool_ref = _text(raw.get("tool_ref"), 120) or None
        raw_args = raw.get("tool_args")
        tool_args: dict[str, Any] = {}
        if raw_args is not None:
            if not isinstance(raw_args, dict):
                raise TaskRunConflict("task_plan_node_invalid")
            if len(json.dumps(raw_args, ensure_ascii=False)) > 2000:
                raise TaskRunConflict("task_plan_node_invalid")
            tool_args = raw_args
        ids.add(client_id)
        prepared.append({
            "client_id": client_id,
            "title": title,
            "raw_dependencies": [_text(item, 80) for item in dependencies],
            "completion_criteria": _text(raw.get("completion_criteria"), 500),
            "input_refs": refs,
            "user_locked": locked,
            "locked_reason": locked_reason,
            "recovery_class": recovery_class,
            "tool_ref": tool_ref,
            "tool_args": tool_args,
        })
    positions = {item["client_id"]: position for position, item in enumerate(prepared)}
    normalized: list[dict[str, Any]] = []
    for item in prepared:
        dependencies = item.pop("raw_dependencies")
        if any(dep not in ids or dep == item["client_id"] for dep in dependencies):
            raise TaskRunConflict("task_plan_dependency_unknown")
        normalized.append({
            **item,
            "depends_on": sorted(set(dependencies), key=positions.__getitem__),
        })
    graph = {item["client_id"]: item["depends_on"] for item in normalized}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise TaskRunConflict("task_plan_cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return normalized


def _stored_plan(conn, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM task_nodes WHERE task_run_id=? ORDER BY position,id", (run_id,),
    ).fetchall()
    return [{
        "client_id": row["client_id"],
        "title": row["title"],
        "depends_on": json.loads(row["depends_on_json"] or "[]"),
        "completion_criteria": row["completion_criteria"],
        "input_refs": _stored_source_refs(conn, row["id"]),
        "user_locked": bool(row["user_locked"]),
        "locked_reason": row["locked_reason"],
        "recovery_class": row["recovery_class"],
        "tool_ref": row["tool_ref"],
        "tool_args": json.loads(row["tool_args_json"] or "{}"),
    } for row in rows]


def validate_plan_shape(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure plan-shape validation shared by planner and workbench (raises TaskRunConflict)."""
    return _normalize_plan(nodes)


def _resolve_source_link(conn, ref: dict[str, str]) -> tuple[str, str]:
    kind, source_id = ref["source_kind"], ref["source_id"]
    if kind == "conversation":
        return "active", ""  # 边界见 spec §7.3：只记录，不做失效检测
    kig_kind = "knowledge_document" if kind == "knowledge_source" else kind
    try:
        source_ref = kig_sources.registry.resolve(kig_kind, source_id)
    except kig_sources.SourceRefError as exc:
        if exc.code == "source_missing":
            raise TaskRunConflict("task_source_ref_unknown")
        raise TaskRunConflict("task_source_ref_invalid")
    if source_ref.status != "active":
        raise TaskRunConflict("task_source_ref_invalid")
    return "active", _source_summary(conn, kind, source_id)


def _source_summary(conn, kind: str, source_id: str) -> str:
    sqls = {
        "memory_fragment": ("SELECT content FROM memory_fragments WHERE id=?",
                            lambda row: row["content"]),
        "memory_episode": ("SELECT summary FROM memory_episodes WHERE id=?",
                           lambda row: row["summary"]),
        "memory_saga": ("SELECT summary FROM memory_sagas WHERE id=?",
                        lambda row: row["summary"]),
        "memory_entity": ("SELECT name,summary FROM memory_entities WHERE id=?",
                          lambda row: f"{row['name']}：{row['summary']}"),
        "knowledge_source": ("SELECT original_name FROM knowledge_documents WHERE id=?",
                             lambda row: row["original_name"]),
    }
    sql, extract = sqls[kind]
    row = conn.execute(sql, (source_id,)).fetchone()
    return redact_text(extract(row) if row is not None else "", limit=240)


def _stored_source_refs(conn, node_id: str) -> list[dict[str, str]]:
    return [{"source_kind": row["source_kind"], "source_id": row["source_id"]}
            for row in conn.execute(
                "SELECT source_kind,source_id FROM task_node_source_links "
                "WHERE node_id=? ORDER BY id", (node_id,),
            ).fetchall()]


def _replace_source_links(conn, run_id: str, node_id: str,
                          refs: list[dict[str, str]]) -> None:
    conn.execute("DELETE FROM task_node_source_links WHERE node_id=?", (node_id,))
    for ref in refs:
        status, summary = _resolve_source_link(conn, ref)
        conn.execute(
            "INSERT INTO task_node_source_links(id,task_run_id,node_id,source_kind,source_id,"
            "summary,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (f"tsl_{db.new_id()}", run_id, node_id, ref["source_kind"], ref["source_id"],
             summary, status, db.now()),
        )


def invalidate_source_links(source_kind: str, source_id: str, reason: str) -> int:
    conn = db.connect()
    try:
        now = db.now()
        updated = conn.execute(
            "UPDATE task_node_source_links SET status='invalidated',invalidated_at=?,"
            "invalidated_reason=? WHERE source_kind=? AND source_id=? AND status='active'",
            (now, redact_text(reason, limit=240), source_kind, source_id),
        ).rowcount
        conn.commit()
        return int(updated or 0)
    finally:
        conn.close()


def replace_plan(run_id: str, nodes: list[dict[str, Any]], *, expected_revision: int,
                 requires_approval: bool = False) -> dict[str, Any]:
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise TaskRunError("task_run_not_found")
        try:
            plan = _normalize_plan(nodes)
        except TaskRunConflict as error:
            error.run_id = run_id
            raise _MutationConflict(error) from error
        existing_nodes = conn.execute(
            "SELECT * FROM task_nodes WHERE task_run_id=? ORDER BY position", (run_id,),
        ).fetchall()
        locked_existing = {row["client_id"]: dict(row) for row in existing_nodes if row["user_locked"]}
        for item in plan:
            prev = locked_existing.get(item["client_id"])
            if prev is None:
                continue
            prev_refs = _stored_source_refs(conn, prev["id"])
            if (prev["title"] != item["title"]
                    or prev["completion_criteria"] != item["completion_criteria"]
                    or json.loads(prev["depends_on_json"] or "[]") != item["depends_on"]
                    or prev_refs != item["input_refs"]):
                raise _MutationConflict(TaskRunConflict(
                    "task_plan_locked_node_modified", run_id=run_id,
                ))
        decision = contract.decide_run(contract.RunCommandContext(
            command="replace_plan", status=run["status"], revision=run["revision"],
            expected_revision=expected_revision, plan_version=run["plan_version"],
            requires_approval=bool(run["requires_approval"]),
            approved_plan_version=run["approved_plan_version"],
            plan_matches=(
                _stored_plan(conn, run_id) == plan
                and bool(run["requires_approval"]) == bool(requires_approval)
            ),
            has_started=run["started_at"] is not None,
        ))
        if decision.outcome == "idempotent":
            conn.rollback()
            return get(run_id) or _decode_run(run)
        _raise_decision(decision, run_id)
        old_status = run["status"]
        conn.execute("DELETE FROM task_nodes WHERE task_run_id=?", (run_id,))
        now = db.now()
        for position, item in enumerate(plan):
            node_id = f"tnd_{db.new_id()}"
            conn.execute(
                "INSERT INTO task_nodes(id,task_run_id,client_id,position,title,status,depends_on_json,"
                "completion_criteria,user_locked,locked_reason,recovery_class,tool_ref,tool_args_json,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (node_id, run_id, item["client_id"], position, item["title"], "pending",
                 json.dumps(item["depends_on"], ensure_ascii=False), item["completion_criteria"],
                 int(item["user_locked"]), item["locked_reason"], item["recovery_class"],
                 item["tool_ref"], json.dumps(item["tool_args"], ensure_ascii=False), now, now),
            )
            _replace_source_links(conn, run_id, node_id, item["input_refs"])
        target = "awaiting_approval" if requires_approval else "ready"
        revision = int(run["revision"]) + 1
        plan_version = int(run["plan_version"]) + 1
        conn.execute(
            "UPDATE task_runs SET status=?,revision=?,plan_version=?,requires_approval=?,"
            "approved_plan_version=NULL,approved_at=NULL,progress_current=0,progress_total=?,"
            "current_node_id=NULL,waiting_reason=?,next_action=?,error_code=NULL,error_message=NULL,"
            "finished_at=NULL,updated_at=? WHERE id=?",
            (target, revision, plan_version, int(requires_approval), len(plan),
             "等待用户批准" if requires_approval else "",
             "批准计划" if requires_approval else "开始执行", now, run_id),
        )
        _event(conn, run_id, "task_plan_replaced", from_status=old_status, to_status=target,
               revision=revision, metadata={"plan_version": plan_version, "node_count": len(plan),
                                            "requires_approval": bool(requires_approval)})
        conn.commit()
        updated = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
    except _MutationConflict as wrapper:
        conn.rollback()
        error = wrapper.conflict
        conn.close()
        _finish_conflict(error)
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
    _log(updated, "task_plan_replaced", "Task plan replaced", status=target,
         plan_version=plan_version, node_count=len(plan), requires_approval=bool(requires_approval))
    return get(run_id) or _decode_run(updated)


_RUN_SETTINGS: dict[str, tuple[str, str, str]] = {
    "approve": ("task_plan_approved", "", "开始执行"),
    "start": ("task_run_started", "", "执行可用步骤"),
    "pause": ("task_run_paused", "已由用户暂停", "继续或重新规划"),
    "resume": ("task_run_resumed", "", "执行可用步骤"),
    "cancel": ("task_run_cancelled", "", ""),
    "replan": ("task_replan_requested", "", "提交新计划"),
}


def approve(run_id: str, *, expected_revision: int) -> dict[str, Any]:
    return _run_command(run_id, "approve", expected_revision)


def start(run_id: str, *, expected_revision: int) -> dict[str, Any]:
    return _run_command(run_id, "start", expected_revision)


def pause(run_id: str, *, expected_revision: int) -> dict[str, Any]:
    return _run_command(run_id, "pause", expected_revision)


def resume(run_id: str, *, expected_revision: int) -> dict[str, Any]:
    return _run_command(run_id, "resume", expected_revision)


def cancel(run_id: str, *, expected_revision: int) -> dict[str, Any]:
    return _run_command(run_id, "cancel", expected_revision)


def replan(run_id: str, *, expected_revision: int) -> dict[str, Any]:
    return _run_command(run_id, "replan", expected_revision)


def _run_command(run_id: str, command: contract.RunCommand, expected_revision: int) -> dict[str, Any]:
    event_type, waiting_reason, next_action = _RUN_SETTINGS[command]
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise TaskRunError("task_run_not_found")
        decision = contract.decide_run(contract.RunCommandContext(
            command=command, status=run["status"], revision=run["revision"],
            expected_revision=expected_revision, plan_version=run["plan_version"],
            requires_approval=bool(run["requires_approval"]),
            approved_plan_version=run["approved_plan_version"],
        ))
        if decision.outcome == "idempotent":
            conn.rollback()
            return get(run_id) or _decode_run(run)
        _raise_decision(decision, run_id)
        target = decision.target_status
        assert target is not None
        if command == "start" and conn.execute(
            "SELECT 1 FROM task_node_source_links WHERE task_run_id=? AND status='invalidated' "
            "LIMIT 1", (run_id,),
        ).fetchone() is not None:
            raise _MutationConflict(TaskRunConflict("task_source_invalidated", run_id=run_id))
        old = str(run["status"])
        now = db.now()
        revision = int(run["revision"]) + 1
        started = run["started_at"] or (now if target == "running" else None)
        finished = now if target in RUN_TERMINAL else None
        approved_version = run["approved_plan_version"]
        approved_at = run["approved_at"]
        if command == "approve":
            approved_version = int(run["plan_version"])
            approved_at = now
        if command == "replan":
            approved_version = None
            approved_at = None
        conn.execute(
            "UPDATE task_runs SET status=?,revision=?,waiting_reason=?,next_action=?,started_at=?,"
            "finished_at=?,approved_plan_version=?,approved_at=?,updated_at=? WHERE id=?",
            (target, revision, waiting_reason, next_action, started, finished,
             approved_version, approved_at, now, run_id),
        )
        if target == "running":
            conn.execute("UPDATE tasks SET status='doing',updated_at=? WHERE id=?", (now, run["task_id"]))
            _refresh_ready_nodes(run_id, conn)
        if target in {"paused", "planning"}:
            conn.execute(
                "UPDATE task_nodes SET status='blocked',revision=revision+1,updated_at=? "
                "WHERE task_run_id=? AND status='running'", (now, run_id),
            )
        elif target == "cancelled":
            conn.execute(
                "UPDATE task_nodes SET status='cancelled',finished_at=?,updated_at=?,revision=revision+1,"
                "skip_reason_code=NULL,skip_reason_summary=NULL WHERE task_run_id=? "
                "AND status NOT IN ('succeeded','failed','skipped','cancelled')",
                (now, now, run_id),
            )
            conn.execute(
                "UPDATE tasks SET status='todo',updated_at=? WHERE id=? AND status='doing'",
                (now, run["task_id"]),
            )
        metadata = {"plan_version": int(run["plan_version"])} if command == "approve" else None
        _event(conn, run_id, event_type, from_status=old, to_status=target,
               revision=revision, metadata=metadata)
        conn.commit()
        updated = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
    except _MutationConflict as wrapper:
        conn.rollback()
        error = wrapper.conflict
        conn.close()
        _finish_conflict(error)
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
    _log(updated, event_type, f"Task run {target}",
         level="WARNING" if target == "cancelled" else "INFO",
         from_status=old, status=target)
    return get(run_id) or _decode_run(updated)


def _refresh_ready_nodes(run_id: str, conn) -> None:
    rows = conn.execute(
        "SELECT * FROM task_nodes WHERE task_run_id=? ORDER BY position", (run_id,),
    ).fetchall()
    satisfied = {row["client_id"] for row in rows if row["status"] in {"succeeded", "skipped"}}
    now = db.now()
    for row in rows:
        if row["status"] not in {"pending", "blocked"}:
            continue
        dependencies = json.loads(row["depends_on_json"] or "[]")
        has_invalid = conn.execute(
            "SELECT 1 FROM task_node_source_links WHERE node_id=? AND status='invalidated' LIMIT 1",
            (row["id"],),
        ).fetchone() is not None
        status = ("blocked" if has_invalid
                  else "ready" if all(dependency in satisfied for dependency in dependencies)
                  else "blocked")
        conn.execute("UPDATE task_nodes SET status=?,updated_at=? WHERE id=?", (status, now, row["id"]))


def _normalize_node_evidence(action: str, *, output_summary: str, error_code: str | None,
                             error_message: str | None, reason_code: str | None,
                             reason_summary: str) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "output_summary": "",
        "error_code": None,
        "error_message": None,
        "skip_reason_code": None,
        "skip_reason_summary": None,
    }
    if action == "succeed":
        evidence["output_summary"] = _text(output_summary, 500)
    elif action == "fail":
        evidence["error_code"] = _text(error_code, 120) or None
        evidence["error_message"] = _text(error_message, 500) or None
    elif action == "skip":
        evidence["skip_reason_code"] = _text(reason_code, 120) or None
        evidence["skip_reason_summary"] = _text(reason_summary, 240) or None
        if not evidence["skip_reason_code"]:
            raise TaskRunConflict("task_node_evidence_conflict")
    return evidence


def _node_evidence_matches(node: Any, target: str, evidence: dict[str, Any]) -> bool:
    if node["status"] != target:
        return False
    if target == "succeeded":
        return node["output_summary"] == evidence["output_summary"]
    if target == "failed":
        return (node["error_code"] == evidence["error_code"]
                and node["error_message"] == evidence["error_message"])
    if target == "skipped":
        return (node["skip_reason_code"] == evidence["skip_reason_code"]
                and node["skip_reason_summary"] == evidence["skip_reason_summary"])
    return target == "running"


def transition_node(run_id: str, node_id: str, action: str, *, expected_revision: int,
                    output_summary: str = "", error_code: str | None = None,
                    error_message: str | None = None, reason_code: str | None = None,
                    reason_summary: str = "") -> dict[str, Any]:
    if action not in {"start", "succeed", "fail", "skip"}:
        raise TaskRunError("task_node_action_invalid")
    target = {"start": "running", "succeed": "succeeded", "fail": "failed", "skip": "skipped"}[action]
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise TaskRunError("task_run_not_found")
        node = conn.execute(
            "SELECT * FROM task_nodes WHERE id=? AND task_run_id=?", (node_id, run_id),
        ).fetchone()
        if node is None:
            raise TaskRunError("task_node_not_found")
        try:
            evidence = _normalize_node_evidence(
                action, output_summary=output_summary, error_code=error_code,
                error_message=error_message, reason_code=reason_code, reason_summary=reason_summary,
            )
        except TaskRunConflict as error:
            error.run_id = run_id
            raise _MutationConflict(error) from error
        decision = contract.decide_node(contract.NodeCommandContext(
            command=action, run_status=run["status"], node_status=node["status"],
            revision=run["revision"], expected_revision=expected_revision,
            evidence_matches=_node_evidence_matches(node, target, evidence),
        ))
        if decision.outcome == "idempotent":
            conn.rollback()
            return get(run_id) or _decode_run(run)
        _raise_decision(decision, run_id)
        old = node["status"]
        now = db.now()
        finished = now if target in NODE_TERMINAL else None
        started = node["started_at"] or (now if target == "running" else None)
        node_revision = int(node["revision"]) + 1
        conn.execute(
            "UPDATE task_nodes SET status=?,output_summary=?,error_code=?,error_message=?,"
            "skip_reason_code=?,skip_reason_summary=?,revision=?,started_at=?,finished_at=?,updated_at=? "
            "WHERE id=?",
            (target, evidence["output_summary"], evidence["error_code"], evidence["error_message"],
             evidence["skip_reason_code"] if target == "skipped" else None,
             evidence["skip_reason_summary"] if target == "skipped" else None,
             node_revision, started, finished, now, node_id),
        )
        run_revision = int(run["revision"]) + 1
        reason = evidence["skip_reason_code"] if target == "skipped" else evidence["error_code"]
        _event(conn, run_id, f"task_node_{target}", node_id=node_id, from_status=old,
               to_status=target, revision=run_revision, reason_code=reason)
        conn.execute(
            "UPDATE task_runs SET revision=?,current_node_id=?,updated_at=? WHERE id=?",
            (run_revision, None if target in NODE_TERMINAL else node_id, now, run_id),
        )
        if target in {"succeeded", "skipped"}:
            _refresh_ready_nodes(run_id, conn)
        counts = conn.execute(
            "SELECT COUNT(*) AS total,SUM(CASE WHEN status IN ('succeeded','skipped') THEN 1 ELSE 0 END) AS done "
            "FROM task_nodes WHERE task_run_id=?", (run_id,),
        ).fetchone()
        done = int(counts["done"] or 0)
        total = int(counts["total"])
        conn.execute(
            "UPDATE task_runs SET progress_current=?,progress_total=? WHERE id=?", (done, total, run_id),
        )
        final_status: str | None = None
        if target == "failed":
            final_status = "failed"
            final_revision = run_revision + 1
            conn.execute(
                "UPDATE task_runs SET status='failed',revision=?,current_node_id=NULL,error_code=?,"
                "error_message=?,waiting_reason='',next_action='重新规划或取消',finished_at=?,updated_at=? "
                "WHERE id=?",
                (final_revision, evidence["error_code"] or "task_node_failed",
                 evidence["error_message"] or "任务步骤失败", now, now, run_id),
            )
            _event(conn, run_id, "task_run_failed", from_status="running", to_status="failed",
                   revision=final_revision, reason_code=evidence["error_code"] or "task_node_failed")
            conn.execute(
                "UPDATE tasks SET status='todo',updated_at=? WHERE id=? AND status='doing'",
                (now, run["task_id"]),
            )
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
    except _MutationConflict as wrapper:
        conn.rollback()
        error = wrapper.conflict
        conn.close()
        _finish_conflict(error)
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
    current = get(run_id)
    assert current is not None
    _log(current, f"task_node_{target}", f"Task node {target}",
         level="ERROR" if final_status == "failed" else "INFO", node_id=node_id,
         node_status=target, progress_current=current["progress_current"],
         progress_total=current["progress_total"])
    return current


def link_artifact(run_id: str, artifact_id: str, *, expected_revision: int,
                  node_id: str | None = None, label: str = "") -> dict[str, Any]:
    requested = contract.ArtifactLink(_text(artifact_id, 120), node_id, _text(label, 120))
    if not requested.artifact_id:
        raise TaskRunError("task_artifact_id_invalid")
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise TaskRunError("task_run_not_found")
        if node_id and conn.execute(
            "SELECT 1 FROM task_nodes WHERE id=? AND task_run_id=?", (node_id, run_id),
        ).fetchone() is None:
            raise TaskRunError("task_node_not_found")
        row = conn.execute(
            "SELECT * FROM task_run_artifact_links WHERE task_run_id=? AND artifact_id=?",
            (run_id, requested.artifact_id),
        ).fetchone()
        existing = None if row is None else contract.ArtifactLink(
            row["artifact_id"], row["node_id"], row["label"],
        )
        decision = contract.decide_artifact(contract.ArtifactCommandContext(
            run_status=run["status"], revision=run["revision"],
            expected_revision=expected_revision, requested=requested, existing=existing,
        ))
        if decision.outcome == "idempotent":
            conn.rollback()
            return get(run_id) or _decode_run(run)
        _raise_decision(decision, run_id)
        conn.execute(
            "INSERT INTO task_run_artifact_links(id,task_run_id,node_id,artifact_id,label,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (f"tal_{db.new_id()}", run_id, node_id, requested.artifact_id,
             requested.label, db.now()),
        )
        revision = int(run["revision"]) + 1
        conn.execute(
            "UPDATE task_runs SET revision=?,updated_at=? WHERE id=?", (revision, db.now(), run_id),
        )
        _event(conn, run_id, "task_artifact_linked", node_id=node_id, revision=revision,
               metadata={"artifact_id": requested.artifact_id})
        conn.commit()
    except _MutationConflict as wrapper:
        conn.rollback()
        error = wrapper.conflict
        conn.close()
        _finish_conflict(error)
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
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
            conn.execute(
                "UPDATE task_nodes SET status='blocked',revision=revision+1,updated_at=? "
                "WHERE task_run_id=? AND status='running'", (now, run["id"]),
            )
            conn.execute(
                "UPDATE tasks SET status='todo',updated_at=? WHERE id=? AND status='doing'",
                (now, run["task_id"]),
            )
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


def recovery_view(run_id: str) -> dict | None:
    """Aggregate authoritative recovery advice from run, nodes and ToolRun evidence."""
    from . import recovery_policy
    run = get(run_id)
    if run is None:
        return None
    tool_runs = run.get("tool_runs") or []
    last = tool_runs[-1] if tool_runs else None
    has_terminal = bool(last and last.get("status") in {"succeeded", "failed", "completed"})
    node = next((n for n in (run.get("nodes") or [])
                 if n.get("status") not in NODE_TERMINAL), None)
    recovery_class = node.get("recovery_class") if node else None
    advice = recovery_policy.decide_recovery(
        recovery_class, has_terminal_evidence=has_terminal,
        retries_used=_count_retries(run, last),
    )
    from . import recovery_checkpoint
    return {
        "run_id": run_id,
        "status": run["status"],
        "recovery_class": recovery_class,
        "last_evidence": {
            "tool_name": last.get("tool_name") if last else None,
            "phase": last.get("phase") if last else None,
            "status": last.get("status") if last else None,
            "trace_id": last.get("trace_id") if last else None,
            "error_message": last.get("error_message") if last else None,
        } if last else None,
        "retries_used": _count_retries(run, last),
        "last_checkpoint": recovery_checkpoint.latest(run_id),
        **advice,
    }


def _count_retries(run: dict, last: dict | None) -> int:
    """Bounded heuristic: tool interruption events observed for this run."""
    if not last:
        return 0
    count = 0
    for event in run.get("events") or []:
        if event.get("event_type") == "task_node_running" and event.get("reason_code") == "retry":
            count += 1
    return min(count, 9)
