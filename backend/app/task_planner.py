"""CYR.2C lightweight Agent Planner: model proposals, program validation only."""
from __future__ import annotations

import json
import re
from typing import Any

from . import llm, task_runs
from .observability import log_event

PLANNER_MAX_TOKENS = 1_024
PLANNER_TIMEOUT_SECONDS = 30.0

_INTENT_PATTERN = re.compile(
    r"(?:帮我|请|麻烦你)?(?:把|将)?(.{0,60}?)(?:拆解|规划|计划|方案|步骤|流程|实现|落地)"
    r"|(?:列成|写成|整理成)(?:一个)?(?:步骤|计划|方案)",
)


def matches_planning_intent(content: str) -> bool:
    text = (content or "").strip()
    if not text or len(text) > 800:
        return False
    return bool(_INTENT_PATTERN.search(text))


def _locked_constraints(locked_nodes: list[dict[str, Any]]) -> str:
    if not locked_nodes:
        return "（无锁定节点）"
    lines = [
        f"- {node.get('title')} (client_id={node.get('client_id')}；标题、验收、依赖逐字保留)"
        for node in locked_nodes
    ]
    return "\n".join(lines)


def proposal_prompt(goal: str, context: str,
                    locked_nodes: list[dict[str, Any]] | None = None) -> str:
    return (
        "你是遐蝶的任务规划器。根据用户目标输出 JSON 计划提案，不要输出其他文字。\n"
        "JSON 结构：{\"goal_summary\": str(≤200字), \"requires_approval\": bool, "
        "\"nodes\": [{\"client_id\": \"step-1\", \"title\": str(≤60字), "
        "\"completion_criteria\": str(≤300字), \"depends_on\": [client_id], "
        "\"input_refs\": [{\"source_kind\": \"knowledge_source|memory_fragment|"
        "memory_episode|memory_saga|memory_entity|conversation\", \"source_id\": str}]}]}\n"
        f"用户目标：{goal}\n可用上下文（有界，不得杜撰来源 id）：{context}\n"
        f"锁定节点（必须逐字保留，不得修改、删除或改变其依赖）：\n"
        f"{_locked_constraints(locked_nodes or [])}\n"
        "约束：最多 50 个节点；client_id 唯一；depends_on 只能引用本计划内的 client_id；"
        "禁止循环依赖；没有把握的来源不要引用；计划批准不等于任何工具权限。"
    )


def parse_proposal_json(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("proposal must be an object")
    return payload


def validate_proposal(proposal: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize and validate; returns (normalized, readable_errors)."""
    errors: list[str] = []
    if not isinstance(proposal, dict):
        return {}, ["提案不是有效对象"]
    nodes = proposal.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return {}, ["提案没有步骤"]
    try:
        normalized_nodes = task_runs.validate_plan_shape(nodes)
    except task_runs.TaskRunConflict as exc:
        return {}, [exc.message]
    except Exception:  # noqa: BLE001 - planner 提案必须 fail closed
        return {}, ["提案无法解析"]
    goal = str(proposal.get("goal_summary") or "").strip()[:200]
    if not goal:
        errors.append("缺少目标摘要")
    return {
        "goal_summary": goal,
        "requires_approval": bool(proposal.get("requires_approval")),
        "nodes": normalized_nodes,
    }, errors


async def generate_proposal(*, provider: dict | None, model: str, goal: str,
                            context: str = "",
                            locked_nodes: list[dict[str, Any]] | None = None,
                            ) -> dict[str, Any]:
    if provider is None or provider.get("id") == "mock" or not provider.get("base_url"):
        raise llm.LLMError("规划模型不可用", "演示模型不执行计划生成。")
    response = await llm.complete_json(
        provider, model,
        [{"role": "user", "content": proposal_prompt(goal, context, locked_nodes)}],
        max_tokens=PLANNER_MAX_TOKENS,
        timeout_seconds=PLANNER_TIMEOUT_SECONDS,
        temperature=0.0,
        json_mode=True,
    )
    try:
        raw = parse_proposal_json(response["text"])
    except (ValueError, json.JSONDecodeError) as exc:
        log_event("task.planner", "WARNING", "planner JSON unparseable",
                  fields={"model": model, "error": str(exc)[:200]})
        raise llm.LLMError("规划模型输出无法解析", "请调整目标后重试。") from exc
    proposal, errors = validate_proposal(raw)
    if errors:
        log_event("task.planner", "WARNING", "planner proposal rejected",
                  fields={"model": model, "errors": errors[:5]})
        raise llm.LLMError("计划未通过程序校验", "；".join(errors[:5]))
    log_event("task.planner", "INFO", "planner proposal generated",
              fields={"model": model, "node_count": len(proposal["nodes"]),
                      "requires_approval": proposal["requires_approval"]})
    return proposal
