from __future__ import annotations

import asyncio

from scripts.run_cyr2d_planner_quality import assess, build_report, load_scenarios, run_scenario

from app import llm


def test_run_scenario_records_unparseable_as_planner_response_invalid(monkeypatch) -> None:
    async def boom(*args, **kwargs):
        raise llm.LLMError("规划模型输出无法解析", "请调整目标后重试。")

    monkeypatch.setattr("app.task_planner.generate_proposal", boom)
    result = asyncio.run(run_scenario({"id": "x"}, "model", {"scenario_id": "s1", "goal": "g"}))
    assert result["reason"] == "planner_response_invalid"
    assert result["violations"] == ["structural_invalid"]


def test_fixture_has_ten_scenarios() -> None:
    scenarios = load_scenarios()
    assert len(scenarios) == 10
    assert len({s["scenario_id"] for s in scenarios}) == 10
    for scenario in scenarios:
        assert scenario["goal"]
        assert "expect" in scenario


def test_assess_flags_fabricated_source() -> None:
    proposal = {"goal_summary": "x", "nodes": [{
        "client_id": "a", "title": "A", "depends_on": [],
        "input_refs": [{"source_kind": "knowledge_source", "source_id": "ghost"}],
    }]}
    result = assess(proposal, {}, set())
    assert "fabricated_source" in result["violations"]


def test_assess_flags_locked_node_modified() -> None:
    scenario = {"locked_nodes": [{"client_id": "a", "title": "原标题"}]}
    proposal = {"goal_summary": "x", "nodes": [{
        "client_id": "a", "title": "被改写", "depends_on": [],
    }]}
    result = assess(proposal, scenario, set())
    assert "locked_node_modified" in result["violations"]


def test_assess_flags_approval_as_permission() -> None:
    proposal = {"goal_summary": "x", "nodes": [{
        "client_id": "a", "title": "A", "depends_on": [],
        "completion_criteria": "grant tool permission",
    }]}
    result = assess(proposal, {}, set())
    assert "approval_as_permission" in result["violations"]


def test_assess_none_is_structural_invalid() -> None:
    result = assess(None, {}, set())
    assert result["violations"] == ["structural_invalid"]
    assert result["ok"] is False


def test_build_report_zero_tolerance_summary() -> None:
    results = [
        {"scenario_id": "a", "ok": True, "violations": []},
        {"scenario_id": "b", "ok": False, "violations": ["structural_invalid"]},
    ]
    report = build_report(results, "deepseek", "deepseek-v4-pro")
    assert report["zero_tolerance"] == {
        "structural_invalid": 1, "fabricated_source": 0,
        "approval_as_permission": 0, "locked_node_modified": 0,
    }
    assert report["structural_valid_rate"] == 0.5
    assert report["verified"] is False
    assert report["protocol"] == "cyr2d-planner-quality-v1"
