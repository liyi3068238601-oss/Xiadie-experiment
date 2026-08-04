"""CYR.2D planner quality fixed-set runner (no user data)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, llm, task_planner, task_runs

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cyr2d_planner_scenarios_v1.json"
REPORT_DIR = Path(__file__).resolve().parents[2] / "docs" / "reports"
ZERO_TOLERANCE = ("structural_invalid", "fabricated_source", "approval_as_permission",
                  "locked_node_modified")


def load_scenarios() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def provider_for(provider_id: str) -> dict | None:
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM providers WHERE id=?", (provider_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def assess(proposal: dict | None, scenario: dict, valid_source_ids: set[str]) -> dict:
    """纯规则评估：零容忍 + 软指标。"""
    violations: list[str] = []
    if proposal is None:
        return {"ok": False, "violations": ["structural_invalid"]}
    nodes = proposal.get("nodes") or []
    if not nodes or not proposal.get("goal_summary"):
        violations.append("structural_invalid")
    try:
        task_runs.validate_plan_shape(nodes)
    except Exception:  # noqa: BLE001 - 提案必须可落库
        violations.append("structural_invalid")
    if any("permission" in str(node).lower() or "tool_grant" in str(node).lower()
           for node in nodes):
        violations.append("approval_as_permission")
    refs = [ref for node in nodes for ref in (node.get("input_refs") or [])]
    if any(ref.get("source_id") not in valid_source_ids for ref in refs):
        violations.append("fabricated_source")
    locked = {node.get("client_id"): node for node in scenario.get("locked_nodes") or []}
    for node in nodes:
        prev = locked.get(node.get("client_id"))
        if prev and prev.get("title") != node.get("title"):
            violations.append("locked_node_modified")
    return {"ok": not violations, "violations": violations}


async def run_scenario(provider: dict, model: str, scenario: dict) -> dict:
    valid_ids = set(scenario.get("valid_source_ids") or [])
    try:
        proposal = await task_planner.generate_proposal(
            provider=provider, model=model, goal=scenario["goal"],
            context="（合成场景，来源仅限 valid_source_ids；没有把握的来源不得引用）",
            locked_nodes=scenario.get("locked_nodes") or [],
        )
    except llm.LLMError as exc:
        return {"scenario_id": scenario["scenario_id"], "ok": False,
                "violations": ["structural_invalid"],
                "reason": exc.code or "planner_response_invalid"}
    return {"scenario_id": scenario["scenario_id"], **assess(proposal, scenario, valid_ids)}


def build_report(results: list[dict], provider_id: str, model: str) -> dict:
    zero = {name: [r for r in results if name in r["violations"]] for name in ZERO_TOLERANCE}
    return {
        "protocol": "cyr2d-planner-quality-v1",
        "provider_id": provider_id,
        "model": model,
        "scenario_count": len(results),
        "zero_tolerance": {name: len(items) for name, items in zero.items()},
        "structural_valid_rate": round(sum(1 for r in results if r["ok"]) / len(results), 4)
        if results else 0.0,
        "verified": all(len(items) == 0 for items in zero.values()),
        "results": results,
    }


async def main(provider_id: str, model: str) -> int:
    provider = provider_for(provider_id)
    if provider is None or not provider.get("base_url") or not provider.get("api_key"):
        print(f"{provider_id}/{model}: unavailable")
        return 2
    results = [await run_scenario(provider, model, scenario)
               for scenario in load_scenarios()]
    report = build_report(results, provider_id, model)
    path = REPORT_DIR / f"cyr2d-planner-quality-{provider_id}-{model}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("model", "zero_tolerance", "verified")},
                     ensure_ascii=False))
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.provider_id, args.model)))
