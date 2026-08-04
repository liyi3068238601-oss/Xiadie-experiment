"""Human console and bounded JSONL sinks."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import shutil
import sys
from threading import RLock
import time
from typing import Any
import zlib


LEVEL_COLORS = {
    "TRACE": "\x1b[90m", "DEBUG": "\x1b[36m", "INFO": "\x1b[32m",
    "WARNING": "\x1b[33m", "ERROR": "\x1b[31m", "CRITICAL": "\x1b[1;31m",
}
RESET = "\x1b[0m"
DIM = "\x1b[2m"
_LEVEL_RANK = {"TRACE": 5, "DEBUG": 10, "INFO": 20, "WARNING": 30,
               "ERROR": 40, "CRITICAL": 50}
_MODULE_COLORS = (
    "\x1b[38;5;111m", "\x1b[38;5;186m", "\x1b[38;5;114m", "\x1b[38;5;173m",
    "\x1b[38;5;140m", "\x1b[38;5;110m", "\x1b[38;5;150m", "\x1b[38;5;179m",
    "\x1b[38;5;117m", "\x1b[38;5;176m",
)


def _module_color(logger: str) -> str:
    """Stable per-module ANSI color so a logger keeps its identity across runs."""
    index = zlib.crc32(logger.encode("utf-8")) % len(_MODULE_COLORS)
    return _MODULE_COLORS[index]


def encode_event(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)


class HumanConsoleSink:
    def __init__(self, *, min_level: str = "INFO") -> None:
        self.stream = sys.stderr
        self.color = bool(getattr(self.stream, "isatty", lambda: False)())
        self.min_rank = _LEVEL_RANK.get(min_level.upper(), _LEVEL_RANK["INFO"])
        self._lock = RLock()

    def emit(self, event: dict[str, Any]) -> None:
        if self.stream is None:
            return
        level = str(event.get("level", "INFO"))
        if _LEVEL_RANK.get(level, _LEVEL_RANK["INFO"]) < self.min_rank:
            return
        timestamp = str(event.get("timestamp", ""))[11:19]
        logger = str(event.get("logger", "app"))[:24]
        trace = str(event.get("trace_id", ""))[-8:]
        if event.get("content_class") == "character_mental_activity" and event.get("thought"):
            body = f"💭 {event['thought']}"
        elif event.get("method") and event.get("path"):
            body = f"{event['method']} {event['path']}"
            if event.get("status") is not None:
                body += f" -> {event['status']}"
            if event.get("duration_ms") is not None:
                body += f" {int(event['duration_ms'])}ms"
        else:
            body = str(event.get("message", ""))
        if event.get("error"):
            error = event["error"]
            body += f" | {error.get('type', 'Error')}: {error.get('message', '')}"
        if self.color:
            trace_part = f"{DIM} [trace={trace}]{RESET}" if trace else ""
            line = (
                f"{DIM}[{timestamp}]{RESET} "
                f"{_module_color(logger)}{logger}{RESET}"
                f"{DIM} | {RESET}"
                f"{LEVEL_COLORS.get(level, '')}{level}{RESET}"
                f"{DIM} | {RESET}{body}{trace_part}"
            )
        else:
            trace_part = f" [trace={trace}]" if trace else ""
            line = f"[{timestamp}] {logger} | {level} | {body}{trace_part}"
        try:
            with self._lock:
                self.stream.write(line + "\n")
                self.stream.flush()
        except (OSError, ValueError):
            pass


class RotatingJsonlSink:
    def __init__(self, root: str, *, process_name: str = "backend", max_bytes: int = 10 * 1024 * 1024,
                 retention_days: int = 14, total_limit: int = 200 * 1024 * 1024) -> None:
        self.root = Path(root)
        self.process_name = process_name
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        self.total_limit = total_limit
        self.current_dir = self.root / process_name
        self.archive_dir = self.root / "archive"
        self.path = self.current_dir / "current.jsonl"
        self._day = datetime.now().date().isoformat()
        self._lock = RLock()
        self.failures = 0

    def emit(self, encoded: str) -> None:
        try:
            with self._lock:
                self.current_dir.mkdir(parents=True, exist_ok=True)
                incoming = len(encoded.encode("utf-8")) + 1
                size = self.path.stat().st_size if self.path.exists() else 0
                day = datetime.now().date().isoformat()
                if size and (size + incoming > self.max_bytes or day != self._day):
                    self._rotate()
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(encoded + "\n")
                self._day = day
        except OSError:
            self.failures += 1

    def _rotate(self) -> None:
        if not self.path.exists():
            return
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        target = self.archive_dir / f"{self.process_name}-{stamp}.jsonl.gz"
        with self.path.open("rb") as source, gzip.open(target, "wb") as destination:
            shutil.copyfileobj(source, destination)
        self.path.unlink(missing_ok=True)
        self._cleanup()

    def _cleanup(self) -> None:
        cutoff = time.time() - self.retention_days * 86400
        files = sorted(self.archive_dir.glob("*.jsonl.gz"), key=lambda item: item.stat().st_mtime)
        for item in list(files):
            if item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
                files.remove(item)
        total = sum(item.stat().st_size for item in files if item.exists())
        for item in files:
            if total <= self.total_limit:
                break
            size = item.stat().st_size
            item.unlink(missing_ok=True)
            total -= size
