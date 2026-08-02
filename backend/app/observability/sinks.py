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


LEVEL_COLORS = {
    "TRACE": "\x1b[90m", "DEBUG": "\x1b[36m", "INFO": "\x1b[32m",
    "WARNING": "\x1b[33m", "ERROR": "\x1b[31m", "CRITICAL": "\x1b[1;31m",
}
RESET = "\x1b[0m"


def encode_event(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)


class HumanConsoleSink:
    def __init__(self) -> None:
        self.stream = sys.stderr
        self.color = bool(getattr(self.stream, "isatty", lambda: False)())
        self._lock = RLock()

    def emit(self, event: dict[str, Any]) -> None:
        if self.stream is None:
            return
        timestamp = str(event.get("timestamp", ""))[11:23]
        level = str(event.get("level", "INFO"))
        logger = str(event.get("logger", "app"))[:24].ljust(24)
        trace = str(event.get("trace_id", ""))[-8:]
        correlation = f" trace={trace}" if trace else ""
        line = f"{timestamp} {level[:3]:3} {logger}{correlation} {event.get('message', '')}"
        if event.get("error"):
            error = event["error"]
            line += f" | {error.get('type', 'Error')}: {error.get('message', '')}"
        if event.get("content_class") == "character_mental_activity" and event.get("thought"):
            line = f"{timestamp} {level[:3]:3} {logger}{correlation} 💭 {event['thought']}"
        if self.color:
            line = f"{LEVEL_COLORS.get(level, '')}{line}{RESET}"
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
