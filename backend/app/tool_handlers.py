"""CYR.3 first-party read-only tool handlers (in-process, workspace-bounded)."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Callable

from . import knowledge_parser
from .tool_registry import ToolManifest, ToolRegistry

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILE_LINES = 20_000
MAX_SEARCH_RESULTS = 100
Handler = Callable[[dict[str, Any], Any], dict[str, Any]]


class ToolExecutionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _resolve_workspace_path(workspace, raw: str) -> Path:
    root = Path(workspace).resolve()
    candidate = Path(str(raw)).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ToolExecutionError("path_outside_workspace", "路径越出工作区")
    return resolved


def read_file() -> Handler:
    def handler(args: dict[str, Any], *, workspace) -> dict[str, Any]:
        path = _resolve_workspace_path(workspace, args["path"])
        if not path.is_file():
            raise ToolExecutionError("file_not_found", "文件不存在")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ToolExecutionError("file_too_large", "文件超过 2 MiB 上限")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ToolExecutionError("file_unreadable", "文件读取失败") from exc
        lines = text.splitlines()
        if len(lines) > MAX_FILE_LINES:
            raise ToolExecutionError("file_too_long", "文件行数超过 20000 上限")
        return {"path": str(path.relative_to(Path(workspace).resolve())),
                "content": text[: 2 * MAX_FILE_BYTES]}

    return handler


def search() -> Handler:
    def handler(args: dict[str, Any], *, workspace) -> dict[str, Any]:
        root = Path(workspace).resolve()
        query = str(args["query"])
        flags = re.IGNORECASE if args.get("case_insensitive") else 0
        pattern = re.compile(re.escape(query), flags)
        matches: list[dict[str, Any]] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for index, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    matches.append({
                        "path": str(path.relative_to(root)),
                        "line": index,
                        "text": line[:300],
                    })
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        return {"query": query, "matches": matches, "truncated": True}
        return {"query": query, "matches": matches, "truncated": False}

    return handler


def list_dir() -> Handler:
    def handler(args: dict[str, Any], *, workspace) -> dict[str, Any]:
        root = Path(workspace).resolve()
        path = _resolve_workspace_path(workspace, args.get("path") or ".")
        if not path.is_dir():
            raise ToolExecutionError("dir_not_found", "目录不存在")
        items = []
        for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name)):
            stat = child.stat()
            items.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": stat.st_size if child.is_file() else None,
                "mtime": stat.st_mtime,
            })
        return {"path": str(path.relative_to(root)), "items": items}

    return handler


def document_parse() -> Handler:
    def handler(args: dict[str, Any], *, workspace) -> dict[str, Any]:
        path = _resolve_workspace_path(workspace, args["path"])
        if not path.is_file():
            raise ToolExecutionError("file_not_found", "文件不存在")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ToolExecutionError("file_too_large", "文件超过 2 MiB 上限")
        try:
            result = knowledge_parser.parse(path.read_bytes(), extension=path.suffix.lower())
        except Exception as exc:  # noqa: BLE001 - 解析失败要 fail closed
            raise ToolExecutionError("parse_failed", "文档解析失败") from exc
        return {
            "path": str(path.relative_to(Path(workspace).resolve())),
            "summary": result.get("normalized_text", "")[:2000],
            "headings": result.get("headings", [])[:50],
            "page_count": result.get("page_count"),
        }

    return handler


def code_inspect() -> Handler:
    def handler(args: dict[str, Any], *, workspace) -> dict[str, Any]:
        path = _resolve_workspace_path(workspace, args["path"])
        if not path.is_file():
            raise ToolExecutionError("file_not_found", "文件不存在")
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            return {"path": str(path.relative_to(Path(workspace).resolve())),
                    "ok": False, "error": f"syntax error at line {exc.lineno}", "symbols": []}
        symbols = sorted({node.name for node in ast.walk(tree)
                          if isinstance(node, (ast.FunctionDef, ast.ClassDef))})
        return {"path": str(path.relative_to(Path(workspace).resolve())),
                "ok": True, "symbols": symbols,
                "lines": len(source.splitlines())}

    return handler


def register_default_tools(registry: ToolRegistry) -> None:
    registry.register(ToolManifest(
        id="workspace.read_file", name="读取文件", description="读取工作区内文本文件（有界）",
        input_schema={"type": "object",
                      "properties": {"path": {"type": "string", "maxLength": 400}},
                      "required": ["path"]},
        output_schema={}, side_effect=False, risk_level="S0",
        declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
    ), read_file())
    registry.register(ToolManifest(
        id="workspace.search", name="搜索文本", description="在工作区内搜索文本",
        input_schema={"type": "object",
                      "properties": {
                          "query": {"type": "string", "minLength": 1, "maxLength": 200},
                          "case_insensitive": {"type": "boolean"},
                      },
                      "required": ["query"]},
        output_schema={}, side_effect=False, risk_level="S0",
        declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
    ), search())
    registry.register(ToolManifest(
        id="workspace.list_dir", name="列出目录", description="列出工作区内目录的单层条目",
        input_schema={"type": "object",
                      "properties": {"path": {"type": "string", "maxLength": 400}}},
        output_schema={}, side_effect=False, risk_level="S0",
        declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
    ), list_dir())
    registry.register(ToolManifest(
        id="document.parse", name="解析文档", description="解析文本/Markdown/PDF/DOCX（有界）",
        input_schema={"type": "object",
                      "properties": {"path": {"type": "string", "maxLength": 400}},
                      "required": ["path"]},
        output_schema={}, side_effect=False, risk_level="S0",
        declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
    ), document_parse())
    registry.register(ToolManifest(
        id="code.inspect", name="代码检查", description="本地语法与符号检查（不执行）",
        input_schema={"type": "object",
                      "properties": {"path": {"type": "string", "maxLength": 400}},
                      "required": ["path"]},
        output_schema={}, side_effect=False, risk_level="S0",
        declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
    ), code_inspect())
