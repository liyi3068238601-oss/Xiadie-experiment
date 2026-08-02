"""Governed, explicitly user-visible character activity log."""
from __future__ import annotations

import json
from typing import Any

from . import db
from .observability import bind_context, log_event, new_trace_id
from .observability.redaction import redact_text

EVENT_KINDS = frozenset({
    "bot_planning", "reply_committed", "tool_selected", "feeling_changed",
    "feeling_decayed", "generation_interrupted", "context_recalled",
})
ORIGINS = frozenset({"explicit_model_field", "plugin", "system"})


class MentalActivityError(ValueError):
    pass


def _safe_field(value: object, limit: int) -> str:
    """Redact first, then enforce the database's exact character bound."""
    return redact_text(str(value).strip(), limit=None)[:limit]


def record(*, event_kind: str, session_id: str | None = None, trace_id: str = "",
           turn_id: str = "", origin: str = "explicit_model_field", thought: str = "",
           mood: str = "", intensity: float | None = None, expected_reaction: str = "",
           reason: str = "", action_summaries: list[str] | None = None) -> dict[str, Any]:
    if event_kind not in EVENT_KINDS:
        raise MentalActivityError("mental_activity_event_kind_invalid")
    if origin not in ORIGINS:
        raise MentalActivityError("mental_activity_origin_invalid")
    if intensity is not None and not 0 <= float(intensity) <= 1:
        raise MentalActivityError("mental_activity_intensity_invalid")
    safe_thought = _safe_field(thought, 240)
    safe_mood = _safe_field(mood, 16)
    safe_expected = _safe_field(expected_reaction, 120)
    safe_reason = _safe_field(reason, 80)
    trace = trace_id or new_trace_id()
    event_id = f"mnt_{db.new_id()}"
    now = db.now()
    actions = [_safe_field(item, 80) for item in (action_summaries or [])[:10]]
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO mental_activity_logs(id,session_id,trace_id,turn_id,event_kind,origin,"
            "visibility,thought,mood,intensity,expected_reaction,reason,action_summaries_json,"
            "retention_class,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, session_id, trace, turn_id or None, event_kind, origin, "user_visible",
             safe_thought, safe_mood, intensity, safe_expected, safe_reason,
             json.dumps(actions, ensure_ascii=False), "conversation_bounded", now),
        )
        if session_id:
            ids = conn.execute(
                "SELECT id FROM mental_activity_logs WHERE session_id=? ORDER BY created_at DESC,id DESC LIMIT -1 OFFSET 50",
                (session_id,),
            ).fetchall()
            if ids:
                conn.executemany("DELETE FROM mental_activity_logs WHERE id=?", [(row["id"],) for row in ids])
        conn.commit()
    finally:
        conn.close()
    with bind_context(trace_id=trace, session_id=session_id or ""):
        event = log_event("kfc.mental", "INFO", "mental_activity_recorded",
                          "Visible character activity recorded", fields={
                              "mental_activity_id": event_id,
                              "event_kind": event_kind,
                              "origin": origin,
                              "visibility": "user_visible",
                              "content_class": "character_mental_activity",
                              "thought": safe_thought,
                              "mood": safe_mood,
                              "intensity": intensity,
                              "expected_reaction": safe_expected,
                              "reason": safe_reason,
                              "action_summaries": actions,
                          })
    return event


def list_session(session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM mental_activity_logs WHERE session_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
            (session_id, max(1, min(int(limit), 200))),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["action_summaries"] = json.loads(item.pop("action_summaries_json") or "[]")
            result.append(item)
        return result
    finally:
        conn.close()


def clear_session(session_id: str) -> int:
    conn = db.connect()
    try:
        cursor = conn.execute("DELETE FROM mental_activity_logs WHERE session_id=?", (session_id,))
        conn.commit()
        return int(cursor.rowcount or 0)
    finally:
        conn.close()
