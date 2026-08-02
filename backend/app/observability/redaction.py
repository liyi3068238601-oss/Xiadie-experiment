"""Fail-safe structured redaction for local diagnostics."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

SECRET_KEYS = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|passwd|secret|access[_-]?token|refresh[_-]?token|credential)",
    re.IGNORECASE,
)
SECRET_VALUES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
)
MAX_STRING = 2000
MAX_DEPTH = 6
MAX_ITEMS = 100


def _home() -> str:
    return os.path.expanduser("~")


def redact_text(value: str, *, limit: int | None = MAX_STRING) -> str:
    result = str(value)
    home = _home()
    if home and home != "~":
        result = re.sub(re.escape(home), "<USER_HOME>", result, flags=re.IGNORECASE)
    for pattern in SECRET_VALUES:
        result = pattern.sub("[REDACTED_SECRET]", result)
    if limit is not None and len(result) > limit:
        result = result[:limit] + f"…[truncated:{len(result) - limit}]"
    return result


def redact(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if SECRET_KEYS.search(key):
        return "[REDACTED_SECRET]"
    if depth >= MAX_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item_value, key=str(item_key), depth=depth + 1)
            for index, (item_key, item_value) in enumerate(value.items())
            if index < MAX_ITEMS
        }
    if isinstance(value, Sequence):
        return [redact(item, depth=depth + 1) for item in list(value)[:MAX_ITEMS]]
    return redact_text(repr(value), limit=500)
