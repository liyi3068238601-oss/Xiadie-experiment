"""CYR.3 chat ingress: run bounded read-only tools from chat intent (same wrapper)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .tool_executor import REGISTRY, _bounded_result

_READ_PATTERN = re.compile(r"(?:帮我)?读(?:一下)?\s*([^\s，。；]+)")
_SEARCH_PATTERN = re.compile(r"(?:帮我)?搜(?:索)?(?:一下)?\s*([^\s，。；在哪]+)")


def match_tool_intent(content: str) -> tuple[str, dict[str, Any]] | None:
    text = (content or "").strip()
    if not text or len(text) > 800:
        return None
    read = _READ_PATTERN.search(text)
    if read:
        path = read.group(1).strip().strip("，。；")
        if path:
            return "workspace.read_file", {"path": path}
    search = _SEARCH_PATTERN.search(text)
    if search:
        query = search.group(1).strip().strip("，。；")
        if query:
            return "workspace.search", {"query": query}
    return None


def run_readonly(content: str, *, workspace: Path) -> dict[str, Any] | None:
    intent = match_tool_intent(content)
    if intent is None:
        return None
    tool_id, args = intent
    try:
        manifest = REGISTRY.get(tool_id)
        validated = REGISTRY.validate_input(tool_id, args)
        result = REGISTRY.handler_for(tool_id)(validated, workspace=workspace)
    except Exception:  # noqa: BLE001 - 聊天直调失败静默，不打断回复
        return None
    return {
        "tool": tool_id,
        "risk_level": manifest.risk_level,
        "summary": str(_bounded_result(result).get("summary") or result)[:2000],
    }
