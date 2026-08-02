"""Structured logging facade and stdlib logging bridge."""
from __future__ import annotations

from datetime import datetime
import logging
import os
import sys
from threading import RLock
import time
import traceback
import uuid
from typing import Any

from .buffer import BUFFER
from .context import current_context
from .redaction import redact, redact_text
from .sinks import HumanConsoleSink, RotatingJsonlSink, encode_event

_LOCK = RLock()
_CONFIGURED = False
_CONSOLE: HumanConsoleSink | None = None
_FILE: RotatingJsonlSink | None = None
_RESERVED_FIELDS = frozenset({
    "schema", "event_id", "timestamp", "epoch", "monotonic_ms", "level",
    "logger", "event", "message", "process", "pid", "thread", "environment",
    "cursor",
})


def _level_name(value: int | str) -> str:
    if isinstance(value, str):
        normalized = value.upper()
        return "WARNING" if normalized == "WARN" else normalized
    return logging.getLevelName(value) if value >= logging.DEBUG else "TRACE"


def _error(exc: BaseException | None) -> dict[str, Any] | None:
    if exc is None:
        return None
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "code": getattr(exc, "code", type(exc).__name__.upper()),
        "type": type(exc).__name__,
        "message": redact_text(str(exc), limit=500),
        "retryable": bool(getattr(exc, "retryable", False)),
        "stack": redact_text(stack, limit=12000),
    }


def log_event(logger: str, level: int | str, event: str, message: str, *,
              fields: dict[str, Any] | None = None, error: BaseException | None = None,
              process: str | None = None) -> dict[str, Any]:
    context = current_context().fields()
    payload: dict[str, Any] = {
        "schema": "operational-log-v1",
        "event_id": f"log_{uuid.uuid4().hex}",
        "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "epoch": time.time(),
        "monotonic_ms": round(time.monotonic() * 1000, 3),
        "level": _level_name(level),
        "logger": str(logger or "app"),
        "event": str(event or "log_event"),
        "message": redact_text(str(message or ""), limit=1000),
        "process": process or os.environ.get("XIADIE_PROCESS_NAME", "backend"),
        "pid": os.getpid(),
        "thread": __import__("threading").current_thread().name,
        "environment": "experiment",
        **context,
    }
    if fields:
        safe_fields = redact(fields)
        payload.update({key: value for key, value in safe_fields.items()
                        if key not in _RESERVED_FIELDS})
    error_payload = _error(error)
    if error_payload:
        payload["error"] = error_payload
    encoded = encode_event(payload)
    stored = BUFFER.append(payload, len(encoded.encode("utf-8")))
    with _LOCK:
        if _CONSOLE:
            _CONSOLE.emit(stored)
        if _FILE:
            _FILE.emit(encode_event(stored))
    return stored


class StructuredLogger:
    def __init__(self, name: str) -> None:
        self.name = name

    def debug(self, event: str, message: str, **fields: Any) -> dict[str, Any]:
        return log_event(self.name, "DEBUG", event, message, fields=fields)

    def info(self, event: str, message: str, **fields: Any) -> dict[str, Any]:
        return log_event(self.name, "INFO", event, message, fields=fields)

    def warning(self, event: str, message: str, **fields: Any) -> dict[str, Any]:
        return log_event(self.name, "WARNING", event, message, fields=fields)

    def error(self, event: str, message: str, *, error: BaseException | None = None,
              **fields: Any) -> dict[str, Any]:
        return log_event(self.name, "ERROR", event, message, fields=fields, error=error)

    def exception(self, event: str, message: str, *, error: BaseException | None = None,
                  **fields: Any) -> dict[str, Any]:
        exc = error or sys.exc_info()[1]
        return log_event(self.name, "ERROR", event, message, fields=fields, error=exc)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)


class _BridgeHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "_xiadie_structured", False):
            return
        try:
            message = record.getMessage()
            exc = record.exc_info[1] if record.exc_info else None
            log_event(record.name, record.levelno, "python_log", message, error=exc)
        except Exception:
            pass


def configure_observability(*, force: bool = False) -> None:
    global _CONFIGURED, _CONSOLE, _FILE
    with _LOCK:
        if _CONFIGURED and not force:
            return
        data_dir = os.environ.get(
            "XIADIE_DATA_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
        )
        log_root = os.environ.get("XIADIE_LOG_DIR", os.path.join(data_dir, "logs"))
        _CONSOLE = HumanConsoleSink()
        _FILE = RotatingJsonlSink(log_root)
        root = logging.getLogger()
        if not any(isinstance(handler, _BridgeHandler) for handler in root.handlers):
            root.addHandler(_BridgeHandler())
        configured_level = os.environ.get("XIADIE_LOG_LEVEL", "INFO").upper()
        root.setLevel(getattr(logging, configured_level, logging.INFO))
        _CONFIGURED = True
        log_event("observability", "INFO", "observability_started", "Structured observability started", fields={
            "log_root": log_root,
            "buffer_capacity": BUFFER.max_events,
        })
