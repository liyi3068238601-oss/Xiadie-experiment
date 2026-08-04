from __future__ import annotations

import asyncio

import pytest

from app import llm, task_planner


def test_intent_fixed_set() -> None:
    assert task_planner.matches_planning_intent("帮我拆解知识库检索改进方案，列成步骤")
    assert task_planner.matches_planning_intent("写一个实现计划，拆成依赖步骤")
    assert not task_planner.matches_planning_intent("今天天气怎么样")


def test_parse_and_validate_proposal() -> None:
    text = ('{"goal_summary":"改进检索","requires_approval":true,'
            '"nodes":[{"client_id":"a","title":"梳理流程","depends_on":[],'
            '"completion_criteria":"输出清单","input_refs":['
            '{"source_kind":"knowledge_source","source_id":"kd-1"}]}]}')
    proposal = task_planner.parse_proposal_json(text)
    validated, errors = task_planner.validate_proposal(proposal)
    assert not errors
    assert validated["nodes"][0]["title"] == "梳理流程"


def test_validate_rejects_cycle_with_readable_errors() -> None:
    _, errors = task_planner.validate_proposal({
        "goal_summary": "x",
        "nodes": [
            {"client_id": "a", "title": "A", "depends_on": ["b"]},
            {"client_id": "b", "title": "B", "depends_on": ["a"]},
        ],
    })
    assert errors


def test_generate_with_mock_provider_fails_closed() -> None:
    with pytest.raises(llm.LLMError):
        asyncio.run(task_planner.generate_proposal(
            provider=None, model="xiadie-mock", goal="做个计划",
        ))
