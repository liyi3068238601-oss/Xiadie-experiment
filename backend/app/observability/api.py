"""Local authenticated diagnostic APIs."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import sys
import zipfile
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import db, mental_activity, tool_runs
from .buffer import BUFFER
from .logger import log_event
from .redaction import redact
from .sinks import encode_event

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _matches(event: dict[str, Any], *, level: str = "", process: str = "", logger: str = "",
             search: str = "", content_class: str = "") -> bool:
    if level and str(event.get("level", "")).upper() != level.upper():
        return False
    if process and event.get("process") != process:
        return False
    if logger and not str(event.get("logger", "")).startswith(logger):
        return False
    if content_class and event.get("content_class") != content_class:
        return False
    if search and search.casefold() not in encode_event(event).casefold():
        return False
    return True


@router.get("/status")
def diagnostic_status() -> dict[str, Any]:
    snapshot = BUFFER.snapshot(limit=1)
    return {
        "schema": "operational-log-v1",
        "stream": "sse-fetch-v1",
        "oldest_cursor": snapshot["oldest_cursor"],
        "latest_cursor": snapshot["latest_cursor"],
        "dropped": snapshot["dropped"],
        "capacity": snapshot["capacity"],
        "process": os.environ.get("XIADIE_PROCESS_NAME", "backend"),
    }


@router.get("/logs")
def diagnostic_logs(after: int = 0, limit: int = 1000, level: str = "", process: str = "",
                    logger: str = "", search: str = "", content_class: str = "") -> dict[str, Any]:
    requested_limit = max(1, min(int(limit), 5000))
    # Filtering a truncated prefix can hide a brand-new matching error when the
    # buffer is busy. Scan the complete bounded buffer, then apply the response cap.
    snapshot = BUFFER.snapshot(after=max(0, after), limit=5000)
    matched = [item for item in snapshot["items"] if _matches(
        item, level=level, process=process, logger=logger, search=search,
        content_class=content_class,
    )]
    snapshot["items"] = matched[:requested_limit]
    snapshot["privacy_notice"] = (
        "诊断事件已脱敏。带 💭 的内容是 AI 显式生成并声明为用户可见的角色表达，"
        "不是 Provider 隐藏思维链。"
    )
    return snapshot


@router.get("/logs/stream")
async def diagnostic_stream(request: Request, after: int = 0) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        snapshot = BUFFER.snapshot(after=max(0, after), limit=5000)
        if snapshot["gap"]:
            yield f"event: gap\ndata: {json.dumps({'oldest_cursor': snapshot['oldest_cursor']})}\n\n"
        for item in snapshot["items"]:
            yield f"id: {item['cursor']}\nevent: log\ndata: {encode_event(item)}\n\n"
        key, queue = BUFFER.subscribe()
        try:
            while not await request.is_disconnected():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"id: {item['cursor']}\nevent: log\ndata: {encode_event(item)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            BUFFER.unsubscribe(key)
    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@router.get("/traces/{trace_id}")
def diagnostic_trace(trace_id: str) -> dict[str, Any]:
    snapshot = BUFFER.snapshot(limit=5000)
    items = [item for item in snapshot["items"] if item.get("trace_id") == trace_id]
    if not items:
        raise HTTPException(404, {"code": "trace_not_found", "message": "诊断链不存在或已过期"})
    return {"trace_id": trace_id, "items": items, "total": len(items)}


@router.get("/tool-runs")
def diagnostic_tool_runs(limit: int = 100) -> dict[str, Any]:
    items = tool_runs.list_recent(limit)
    return {"items": items, "total": len(items), "schema": "tool-run-v2"}


@router.get("/tool-runs/{run_id}")
def diagnostic_tool_run(run_id: str) -> dict[str, Any]:
    item = tool_runs.get(run_id)
    if item is None:
        raise HTTPException(404, {"code": "tool_run_not_found", "message": "工具运行不存在"})
    snapshot = BUFFER.snapshot(limit=5000)
    item["logs"] = [event for event in snapshot["items"] if event.get("tool_run_id") == run_id]
    return item


class IngestEvent(BaseModel):
    level: str = Field(default="INFO", pattern=r"^(TRACE|DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    logger: str = Field(min_length=1, max_length=120)
    event: str = Field(min_length=1, max_length=120)
    message: str = Field(default="", max_length=2000)
    process: str = Field(default="desktop", pattern=r"^(desktop|backend|plugin)$")
    fields: dict[str, Any] = Field(default_factory=dict)


@router.post("/ingest")
def diagnostic_ingest(body: IngestEvent) -> dict[str, Any]:
    event = log_event(body.logger, body.level, body.event, body.message,
                      fields=body.fields, process=body.process)
    return {"accepted": True, "event_id": event["event_id"], "cursor": event["cursor"]}


class MentalActivityIn(BaseModel):
    session_id: str | None = None
    trace_id: str = ""
    turn_id: str = ""
    event_kind: str
    origin: str = "plugin"
    thought: str = Field(default="", max_length=240)
    mood: str = Field(default="", max_length=16)
    intensity: float | None = Field(default=None, ge=0, le=1)
    expected_reaction: str = Field(default="", max_length=120)
    reason: str = Field(default="", max_length=80)
    action_summaries: list[str] = Field(default_factory=list, max_length=10)


@router.post("/mental-activity")
def write_mental_activity(body: MentalActivityIn) -> dict[str, Any]:
    try:
        return mental_activity.record(**body.model_dump())
    except mental_activity.MentalActivityError as exc:
        raise HTTPException(400, {"code": str(exc), "message": "心理活动事件不合法"}) from exc


@router.get("/mental-activity/{session_id}")
def read_mental_activity(session_id: str, limit: int = 50) -> dict[str, Any]:
    items = mental_activity.list_session(session_id, limit)
    return {"items": items, "total": len(items), "schema": "mental-activity-log-v1"}


@router.delete("/mental-activity/{session_id}")
def delete_mental_activity(session_id: str) -> dict[str, Any]:
    return {"deleted_count": mental_activity.clear_session(session_id)}


def _log_root() -> Path:
    data_dir = Path(db.DATA_DIR)
    return Path(os.environ.get("XIADIE_LOG_DIR", str(data_dir / "logs")))


def _support_root() -> Path:
    return Path(db.DATA_DIR) / "diagnostics"


@router.post("/export")
def export_support_bundle() -> dict[str, Any]:
    root = _support_root()
    root.mkdir(parents=True, exist_ok=True)
    bundle_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + db.new_id()[:8]
    target = root / f"xiadie-support-{bundle_id}.zip"
    snapshot = BUFFER.snapshot(limit=5000)
    safe_events = []
    excluded_mental = 0
    for event in snapshot["items"]:
        if event.get("content_class") == "character_mental_activity":
            excluded_mental += 1
            safe = {key: value for key, value in event.items()
                    if key not in {"thought", "reason", "expected_reaction"}}
            safe["content_excluded"] = True
            safe_events.append(redact(safe))
        else:
            safe_events.append(redact(event))
    manifest = {
        "format": "xiadie-support-bundle-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "application": "Xiadie-Experiment",
        "schema_version": db.get_schema_version(85),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "events": len(safe_events),
        "mental_activity_bodies_excluded": excluded_mental,
        "excluded": ["credentials", "database", "chat bodies", "memory bodies", "knowledge bodies",
                     "model prompts/responses", "mental activity bodies"],
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        bundle.writestr("diagnostics/events.jsonl", "\n".join(encode_event(item) for item in safe_events))
    log_event("diagnostics.export", "INFO", "support_bundle_created", "Support bundle created",
              fields={"bundle_id": bundle_id, "size": target.stat().st_size})
    return {"bundle_id": bundle_id, "filename": target.name, "size": target.stat().st_size,
            "download_url": f"/api/diagnostics/export/{bundle_id}"}


@router.get("/export/{bundle_id}")
def download_support_bundle(bundle_id: str) -> FileResponse:
    if not bundle_id.replace("-", "").isalnum() or len(bundle_id) > 40:
        raise HTTPException(400, "诊断包 ID 无效")
    target = _support_root() / f"xiadie-support-{bundle_id}.zip"
    if not target.is_file():
        raise HTTPException(404, "诊断包不存在")
    return FileResponse(target, filename=target.name, media_type="application/zip")
