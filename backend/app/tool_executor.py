"""CYR.3 executor: run task nodes through registered tools with ToolRun evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import task_runs, tool_runs
from .tool_handlers import ToolExecutionError, register_default_tools
from .tool_registry import ToolRegistry, ToolRegistryError


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_default_tools(registry)
    return registry


REGISTRY = default_registry()


def default_workspace() -> Path:
    return Path(__file__).resolve().parents[2]


def _bounded_result(result: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(result, ensure_ascii=False, default=str)
    if len(encoded) <= 8000:
        return result
    return {"summary": encoded[:4000] + "…（已截断）"}


def execute_node(run: dict, node: dict, *, session_id: str | None = None,
                 workspace: Path | None = None,
                 registry: ToolRegistry | None = None) -> dict:
    reg = registry or REGISTRY
    tool_ref = node.get("tool_ref")
    if not tool_ref:
        raise ToolExecutionError("node_has_no_tool", "节点未绑定工具")
    running = task_runs.transition_node(
        run["id"], node["id"], "start", expected_revision=run["revision"],
    )
    try:
        manifest = reg.get(tool_ref)
        args = reg.validate_input(tool_ref, node.get("tool_args") or {})
    except ToolRegistryError as exc:
        tool_run = tool_runs.create(tool_name=tool_ref, trace_id=run["trace_id"],
                                    session_id=session_id, task_run_id=run["id"],
                                    risk_level="S0")
        tool_runs.transition(tool_run["id"], "denied", error=exc,
                             error_code="tool_not_found")
        return task_runs.transition_node(
            running["id"], node["id"], "fail", expected_revision=running["revision"],
            error_code="tool_not_found", error_message="工具未注册或参数无效",
        )
    tool_run = tool_runs.create(
        tool_name=tool_ref, trace_id=run["trace_id"], session_id=session_id,
        task_run_id=run["id"], risk_level=manifest.risk_level,
        arguments_summary=args,
    )
    tool_runs.transition(tool_run["id"], "authorizing")
    tool_runs.transition(tool_run["id"], "running")
    try:
        result = reg.handler_for(tool_ref)(args, workspace=workspace or default_workspace())
    except ToolExecutionError as exc:
        tool_runs.transition(tool_run["id"], "failed", error=exc, error_code=exc.code)
        return task_runs.transition_node(
            running["id"], node["id"], "fail", expected_revision=running["revision"],
            error_code=exc.code, error_message=str(exc),
        )
    except Exception:  # noqa: BLE001 - 未知异常走证据失败
        tool_runs.transition(tool_run["id"], "failed")
        return task_runs.transition_node(
            running["id"], node["id"], "fail", expected_revision=running["revision"],
            error_code="tool_execution_error", error_message="工具执行失败（已脱敏）",
        )
    bounded = _bounded_result(result)
    tool_runs.transition(tool_run["id"], "succeeded", result_summary=bounded)
    summary = str(bounded.get("summary") or bounded)[:500]
    return task_runs.transition_node(
        running["id"], node["id"], "succeed", expected_revision=running["revision"],
        output_summary=summary,
    )
