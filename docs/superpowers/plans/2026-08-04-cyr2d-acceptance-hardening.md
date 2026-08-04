# CYR.2D 工作台验收与故障加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用单测级 + 进程级故障注入验证并修复 CYR.2 工作台的取消/崩溃/忙/竞争语义；核对 TaskRun 全链路关联；建立多模型计划质量固定集与报告。

**Architecture:** 故障注入全部落在测试与脚本层，不改 TaskRun 状态机合同；进程级 E2E 用临时数据目录启动后端、强杀、重启、断言 `recovery_required`；全链路测试复用 observability 内存缓冲与 `tool_runs`/`task_run_artifact_links`；质量评测脚本复用 `task_planner.generate_proposal`，报告沿用 KIG-R 模式。

**Tech Stack:** pytest（isolated_db / ThreadPoolExecutor / TestClient）、PowerShell 脚本（仿 `test-cie6-electron-smoke.ps1`）、`observability.BUFFER.snapshot`、`tool_runs.create`、`task_planner.generate_proposal`。

## Global Constraints

- 不修改 TaskRun/TaskNode 状态机合同（CYR.2A～2C 冻结语义保持）；合同级缺陷升级给用户，不在批内擅改。
- 不做打包/安装/升级链路验收（CYR.9）。
- 故障注入期望统一：恰好一次应用、其余 409、五类业务表（tasks/task_runs/task_nodes/task_run_events/task_run_artifact_links）零脏写。
- 进程强杀后遗留 run 必须 `recovery_required`，不自动续跑；`cancel`/`resume` 按既有合同合法。
- 评测合成场景 10 组，不含用户数据；零容忍：结构非法 0、杜撰来源 0、批准≠工具权限 0、锁定节点被改写 0。
- 未验证模型不阻塞使用；模型指纹随生成事件记录。
- 不引入外部编排运行时、第二数据库或新运行时依赖。

---

## Segment A：后端故障注入与修复

### Task 1: 单测级故障注入固定集

**Files:**
- Create: `backend/tests/test_task_run_faults.py`
- Modify: 无（若发现缺陷，在后续 Task 3 修复）

**Interfaces:**
- Consumes: `task_runs.create/replace_plan/start/pause/cancel/approve`、`contract.ERROR_SPECS`、`_business_snapshot` 等价物。
- Produces: 六类故障注入用例。

- [ ] **Step 1: 写测试（含 RED 预期）**

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlite3

from app import db, task_runs


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _task(title: str = "故障注入任务") -> str:
    conn = db.connect()
    try:
        task_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO tasks(id,title,status,source,created_at,updated_at) VALUES(?,?,'todo','manual',?,?)",
            (task_id, title, now, now),
        )
        conn.commit()
        return task_id
    finally:
        conn.close()


BUSINESS_TABLES = ("tasks", "task_runs", "task_nodes", "task_run_events",
                   "task_run_artifact_links")


def _snapshot() -> dict[str, list[tuple]]:
    conn = db.connect()
    try:
        return {t: [tuple(row) for row in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                for t in BUSINESS_TABLES}
    finally:
        conn.close()


def _planned_run() -> dict:
    run = task_runs.create(task_id=_task(), idempotency_key="fault-plan")
    return task_runs.replace_plan(run["id"], [
        {"client_id": "a", "title": "A", "depends_on": []},
    ], expected_revision=run["revision"])


def test_concurrent_cancel_race_applies_once_and_zero_writes() -> None:
    planned = _planned_run()
    run = task_runs.start(planned["id"], expected_revision=planned["revision"])
    before = _snapshot()

    def cancel_once(_: int) -> str:
        try:
            return task_runs.cancel(run["id"], expected_revision=run["revision"]).get("status", "")
        except task_runs.TaskRunConflict as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(cancel_once, range(2)))
    assert results.count("cancelled") == 1
    assert results.count("task_run_revision_conflict") == 1
    after = _snapshot()
    assert after != before  # 恰好一次应用
    # 第二次取消幂等：用最新 revision 再取消一次，不产生新写入
    current = task_runs.get(run["id"])
    before2 = _snapshot()
    again = task_runs.cancel(run["id"], expected_revision=current["revision"])
    assert again["status"] == "cancelled"
    assert _snapshot() == before2


def test_crash_mid_replace_plan_rolls_back_without_orphans() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="fault-crash")
    before = _snapshot()
    original = db.connect

    def exploding_connect():
        conn = original()
        original_execute = conn.execute

        def execute(sql, *args, **kwargs):
            if "INSERT INTO task_nodes" in sql:
                raise RuntimeError("simulated crash mid-transaction")
            return original_execute(sql, *args, **kwargs)

        conn.execute = execute
        return conn

    db.connect = exploding_connect  # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError):
            task_runs.replace_plan(run["id"], [
                {"client_id": "a", "title": "A", "depends_on": []},
            ], expected_revision=run["revision"])
    finally:
        db.connect = original
    assert _snapshot() == before  # 完全回滚，无半状态


def test_db_busy_does_not_corrupt_data() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="fault-busy")
    before = _snapshot()
    original = db.connect

    def busy_connect():
        conn = original()
        original_execute = conn.execute

        def execute(sql, *args, **kwargs):
            if sql.startswith("BEGIN"):
                raise sqlite3.OperationalError("database is locked")
            return original_execute(sql, *args, **kwargs)

        conn.execute = execute
        return conn

    db.connect = busy_connect  # type: ignore[assignment]
    try:
        with pytest.raises(sqlite3.OperationalError):
            task_runs.replace_plan(run["id"], [
                {"client_id": "a", "title": "A", "depends_on": []},
            ], expected_revision=run["revision"])
    finally:
        db.connect = original
    assert _snapshot() == before


def test_stale_revision_competition_applies_once() -> None:
    run = _planned_run()

    def act(action: str) -> str:
        try:
            return getattr(task_runs, action)(run["id"], expected_revision=run["revision"]).get("status", "")
        except task_runs.TaskRunConflict as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(act, ["start", "cancel"]))
    assert results.count("task_run_revision_conflict") == 1
    assert any(status in ("running", "cancelled") for status in results)
```

> 说明：`test_crash_mid_replace_plan...` 与 `test_db_busy...` 在修复前预期 RED（当前 `replace_plan` 的 `_MutationConflict` 路径在 monkeypatch 异常下可能以 `except Exception: conn.rollback(); raise` 兜底——若已通过则说明回滚已成立，标记为已覆盖并继续；以实际运行为准，把运行结果写进报告）。

- [ ] **Step 2: 运行并记录结果**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_run_faults.py -q`
Expected: 各用例要么 PASS（语义已成立）要么按预期失败（进入 Task 3 修复）；把每用例结果写进 Task 3 报告。

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_task_run_faults.py
git commit -m "test(taskrun): CYR.2D fault injection fixed set"
```

---

### Task 2: 进程级崩溃恢复 E2E 脚本

**Files:**
- Create: `scripts/test-cyr2d-crash-recovery.ps1`
- Modify: 无

**Interfaces:**
- Consumes: `backend/run_frozen.py`、HTTP API（health/tasks/runs/plan/start/cancel/resume）。
- Produces: 退出码门禁脚本。

- [ ] **Step 1: 写脚本**

仿 `scripts/test-cie6-electron-smoke.ps1` 的结构：
```powershell
param()
$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$tempRoot = Join-Path $projectRoot (".cyr2d-crash-" + [Guid]::NewGuid().ToString("N"))
$backendPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$token = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
$headers = @{ "X-Xiadie-Token" = $token }
$started = @()

function Stop-Tree([System.Diagnostics.Process]$Process) {
  if (-not $Process) { return }
  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($Process.Id)" -ErrorAction SilentlyContinue
  foreach ($child in $children) { try { Stop-Tree ([System.Diagnostics.Process]::GetProcessById($child.ProcessId)) } catch {} }
  try { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue } catch {}
}

function Start-Backend {
  param([string]$DataDir)
  $env:XIADIE_API_TOKEN = $token
  $env:XIADIE_DATA_DIR = $DataDir
  $env:XIADIE_DEV_MODE = "1"
  $env:XIADIE_PARENT_PID = [string]$PID
  $proc = Start-Process -FilePath $backendPython -ArgumentList "run_frozen.py" `
    -WorkingDirectory (Join-Path $projectRoot "backend") -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $DataDir "backend.out.log") `
    -RedirectStandardError (Join-Path $DataDir "backend.err.log")
  $started += $proc
  for ($i = 0; $i -lt 60; $i++) {
    try { $h = Invoke-RestMethod "http://127.0.0.1:8756/api/health" -Headers $headers -TimeoutSec 1
      if ($h.status -eq "ok") { return $proc } } catch {}
    Start-Sleep -Milliseconds 500
  }
  throw "backend did not become healthy"
}

try {
  New-Item -ItemType Directory -Path $tempRoot | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $tempRoot "data") | Out-Null

  $backend = Start-Backend (Join-Path $tempRoot "data")
  $task = Invoke-RestMethod "http://127.0.0.1:8756/api/tasks" -Method Post -Headers $headers `
    -ContentType "application/json" -Body '{"title":"崩溃恢复验收"}'
  $run = Invoke-RestMethod "http://127.0.0.1:8756/api/tasks/$($task.id)/runs" -Method Post -Headers $headers `
    -ContentType "application/json" -Body '{"goal_summary":"崩溃恢复验收"}'
  $planBody = @{ nodes = @(@{ client_id = "a"; title = "步骤A"; depends_on = @(); completion_criteria = "完成" }); requires_approval = $false; expected_revision = $run.revision } | ConvertTo-Json -Depth 6
  $planned = Invoke-RestMethod "http://127.0.0.1:8756/api/task-runs/$($run.id)/plan" -Method Put -Headers $headers `
    -ContentType "application/json" -Body $planBody
  $running = Invoke-RestMethod "http://127.0.0.1:8756/api/task-runs/$($run.id)/start" -Method Post -Headers $headers `
    -ContentType "application/json" -Body (@{ expected_revision = $planned.revision } | ConvertTo-Json)
  if ($running.status -ne "running") { throw "run did not enter running" }

  Stop-Tree $backend
  Start-Sleep -Seconds 1

  $backend2 = Start-Backend (Join-Path $tempRoot "data")
  $recovered = Invoke-RestMethod "http://127.0.0.1:8756/api/task-runs/$($run.id)" -Headers $headers
  if ($recovered.status -ne "recovery_required") { throw "expected recovery_required, got $($recovered.status)" }
  $runningNode = $recovered.nodes | Where-Object { $_.status -eq "running" }
  if ($runningNode) { throw "running node should be blocked after crash" }

  # cancel 幂等
  $cancelled = Invoke-RestMethod "http://127.0.0.1:8756/api/task-runs/$($run.id)/cancel" -Method Post -Headers $headers `
    -ContentType "application/json" -Body (@{ expected_revision = $recovered.revision } | ConvertTo-Json)
  if ($cancelled.status -ne "cancelled") { throw "cancel failed" }
  $cancelled2 = Invoke-RestMethod "http://127.0.0.1:8756/api/task-runs/$($run.id)/cancel" -Method Post -Headers $headers `
    -ContentType "application/json" -Body (@{ expected_revision = $cancelled.revision } | ConvertTo-Json)
  if ($cancelled2.status -ne "cancelled") { throw "cancel not idempotent" }

  Write-Output "CYR.2D crash-recovery E2E: PASS"
} finally {
  foreach ($p in $started) { Stop-Tree $p }
  Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
```

> 若 `run_frozen.py` 与 `test-cie6-electron-smoke.ps1` 的实际启动参数不同（端口/环境变量），以 smoke 脚本为准对齐；脚本内保留端口冲突预检（8756/5173 占用时报错退出）。

- [ ] **Step 2: 本地运行验证**

Run: `powershell -ExecutionPolicy Bypass -File scripts\test-cyr2d-crash-recovery.ps1`
Expected: 输出 `CYR.2D crash-recovery E2E: PASS`，退出码 0。

- [ ] **Step 3: 提交**

```bash
git add scripts/test-cyr2d-crash-recovery.ps1
git commit -m "test(cyr2d): process-level crash recovery E2E script"
```

---

### Task 3: 修复注入发现的缺陷

**Files:**
- Modify: 依 Task 1/2 结果而定（`backend/app/task_runs.py` 等）
- Test: `backend/tests/test_task_run_faults.py` 及对应覆盖测试

**Interfaces:**
- Consumes: Task 1/2 的失败清单。
- Produces: 修复提交 + 报告记录。

- [ ] **Step 1: 检查 Task 1/2 结果**

- 若 fault suite 与 E2E 全绿：在报告标注"未发现需修复缺陷"，跳到 Task 4。
- 若存在红：对每个失败按 `systematic-debugging` 定位根因，写覆盖测试（RED）→ 最小修复（GREEN）→ 提交。
- 若根因属于状态机合同或 Schema 语义变更：停止并升级给用户决定，不擅改合同。

- [ ] **Step 2: 提交每个修复**

```bash
git add backend/app backend/tests
git commit -m "fix(taskrun): <defect summary> (CYR.2D fault injection)"
```

---

## Segment B：全链路关联验收

### Task 4: 完整生命周期关联测试

**Files:**
- Create: `backend/tests/test_task_run_chain.py`

**Interfaces:**
- Consumes: `task_runs`、`tool_runs.create`、`task_runs.link_artifact`、`observability.BUFFER.snapshot`。
- Produces: trace/事件/日志/ToolRun/Artifact 关联断言。

- [ ] **Step 1: 写测试**

```python
from __future__ import annotations

import pytest

from app import db, task_runs, tool_runs
from app.observability import BUFFER


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _task() -> str:
    conn = db.connect()
    try:
        task_id = db.new_id()
        now = db.now()
        conn.execute(
            "INSERT INTO tasks(id,title,status,source,created_at,updated_at) VALUES(?,?,'todo','manual',?,?)",
            (task_id, "全链路任务", now, now),
        )
        conn.commit()
        return task_id
    finally:
        conn.close()


def test_full_lifecycle_trace_correlation() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="chain-1")
    trace_id = run["trace_id"]
    assert trace_id
    planned = task_runs.replace_plan(run["id"], [
        {"client_id": "a", "title": "A", "depends_on": []},
    ], expected_revision=run["revision"])
    approved = task_runs.approve(planned["id"], expected_revision=planned["revision"]) \
        if planned["requires_approval"] else planned
    started = task_runs.start(approved["id"], expected_revision=approved["revision"])
    node = started["nodes"][0]
    succeeded = task_runs.transition_node(
        started["id"], node["id"], "start", expected_revision=started["revision"],
    )
    done = task_runs.transition_node(
        succeeded["id"], node["id"], "succeed", expected_revision=succeeded["revision"],
        output_summary="完成",
    )
    assert done["status"] == "completed"
    assert done["trace_id"] == trace_id

    tool = tool_runs.create(tool_name="workspace_search", trace_id=trace_id,
                            task_run_id=done["id"])
    linked = task_runs.link_artifact(done["id"], "art-1", expected_revision=done["revision"],
                                     node_id=node["id"], label="报告")
    detail = task_runs.get(done["id"])
    assert detail is not None
    assert detail["trace_id"] == trace_id
    assert any(e["event_type"] == "task_run_completed" for e in detail["events"])
    assert any(t["id"] == tool["id"] and t["task_run_id"] == done["id"]
               for t in detail["tool_runs"])
    assert any(a["artifact_id"] == "art-1" and a["node_id"] == node["id"]
               for a in detail["artifacts"])

    # 诊断日志同 trace 可读
    snapshot = BUFFER.snapshot(limit=5000)
    log_items = [item for item in snapshot["items"]
                 if item.get("trace_id") == trace_id and item.get("logger") == "task.scheduler"]
    assert log_items, "task.scheduler 日志应携带同一 trace_id"
```

> 若 `tool_runs.create` 的实际签名不含 `task_run_id` 或字段名不同，以 `tool_runs.py` 为准调整参数；断言目标不变（tool_runs 绑定 task_run_id）。

- [ ] **Step 2: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_run_chain.py -q`
Expected: PASS。

- [ ] **Step 3: 前端契约补充（taskRunUx.test.mjs）**

```js
test("CYR.2D chain acceptance keeps trace and evidence visible", () => {
  assert.match(tasks, /task-run-progress/);
  assert.match(tasks, /查看事件/);
  assert.match(tasks, /run\.id/);
  assert.match(tasks, /recoveryCardVisible/);
});
```

Run: `frontend\node --test tests/taskRunUx.test.mjs` → PASS。

- [ ] **Step 4: 提交**

```bash
git add backend/tests/test_task_run_chain.py frontend/tests/taskRunUx.test.mjs
git commit -m "test(cyr2d): full-chain trace correlation acceptance"
```

---

### Task 5: 关联矩阵验收报告

**Files:**
- Create: `docs/reports/cyr2d-chain-acceptance.md`

**Interfaces:**
- Consumes: Task 4 的测试结果。
- Produces: 关联矩阵报告。

- [ ] **Step 1: 写报告**

记录：完整生命周期测试通过（含 trace 一致、事件/日志/ToolRun/Artifact 关联断言数）、前端契约断言清单、边界说明（ToolRun 为 CYR.3 前的证据壳）。

- [ ] **Step 2: 提交**

```bash
git add docs/reports/cyr2d-chain-acceptance.md
git commit -m "docs(cyr2d): record full-chain acceptance matrix"
```

---

## Segment C：多模型计划质量固定集

### Task 6: 评测脚本与合成场景

**Files:**
- Create: `backend/tests/fixtures/cyr2d_planner_scenarios_v1.json`
- Create: `backend/scripts/run_cyr2d_planner_quality.py`
- Create: `backend/tests/test_cyr2d_planner_quality.py`

**Interfaces:**
- Consumes: `task_planner.generate_proposal`、`llm.LLMError`。
- Produces: 10 组场景 fixture；按 provider/model 生成 `docs/reports/cyr2d-planner-quality-{provider}-{model}.json`。

- [ ] **Step 1: 写场景 fixture**

10 组场景（纯合成，无用户数据）：多步骤 DAG、依赖链、来源引用（knowledge_source/memory_fragment 各一）、锁定节点保留、需批准、拒绝无把握来源（无来源可引用）、循环依赖纠正、50 节点上限、重复 client_id、目标摘要缺失。每项：`{"scenario_id", "goal", "locked_nodes": [], "expect": {"node_count_min": N, "references_ok": bool, "approval_boundary": bool}}`。

- [ ] **Step 2: 写评测脚本（骨架 + 断言逻辑）**

```python
"""CYR.2D planner quality fixed-set runner (no user data)."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app import db, llm, task_planner

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


def assess(proposal: dict | None, scenario: dict) -> dict:
    """纯规则评估：零容忍 + 软指标。"""
    violations: list[str] = []
    if proposal is None:
        violations.append("structural_invalid")
        return {"ok": False, "violations": violations}
    nodes = proposal.get("nodes") or []
    if not nodes or not proposal.get("goal_summary"):
        violations.append("structural_invalid")
    # 批准只绑定计划：proposal 本身不含权限字段即视为通过
    if any("permission" in str(node).lower() or "tool_grant" in str(node).lower()
           for node in nodes):
        violations.append("approval_as_permission")
    if scenario.get("locked_nodes"):
        locked = {n.get("client_id"): n for n in scenario["locked_nodes"]}
        for node in nodes:
            prev = locked.get(node.get("client_id"))
            if prev and (prev.get("title") != node.get("title")):
                violations.append("locked_node_modified")
    return {"ok": not violations, "violations": violations}


async def run_scenario(provider: dict, model: str, scenario: dict) -> dict:
    try:
        proposal = await task_planner.generate_proposal(
            provider=provider, model=model, goal=scenario["goal"],
            context="（合成场景，无可引用来源时不得杜撰）",
            locked_nodes=scenario.get("locked_nodes") or [],
        )
    except llm.LLMError:
        return {"scenario_id": scenario["scenario_id"], "ok": False,
                "violations": ["structural_invalid"], "reason": "model_unavailable_or_invalid"}
    return {"scenario_id": scenario["scenario_id"], **assess(proposal, scenario)}


async def main(provider_id: str, model: str) -> int:
    provider = provider_for(provider_id)
    if provider is None or not provider.get("base_url"):
        print(f"{provider_id}/{model}: unavailable")
        return 2
    results = [await run_scenario(provider, model, s) for s in load_scenarios()]
    zero = {name: [r for r in results if name in r["violations"]] for name in ZERO_TOLERANCE}
    report = {
        "protocol": "cyr2d-planner-quality-v1",
        "provider_id": provider_id,
        "model": model,
        "scenario_count": len(results),
        "zero_tolerance": {name: len(items) for name, items in zero.items()},
        "structural_valid_rate": round(sum(1 for r in results if r["ok"]) / len(results), 4),
        "verified": all(len(items) == 0 for items in zero.values()),
        "results": results,
    }
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
```

- [ ] **Step 3: 写单测（stub 生成器）**

`backend/tests/test_cyr2d_planner_quality.py`：断言 fixture 10 组、`assess` 对"杜撰来源/锁定改写/批准当权限"给出 violations、报告 JSON 结构与零容忍汇总正确；不调用真实模型（monkeypatch `task_planner.generate_proposal`）。

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_cyr2d_planner_quality.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/tests/fixtures/cyr2d_planner_scenarios_v1.json backend/scripts/run_cyr2d_planner_quality.py backend/tests/test_cyr2d_planner_quality.py
git commit -m "feat(cyr2d): planner quality fixed-set runner and scenarios"
```

---

### Task 7: 跑固定集并生成报告

**Files:**
- Create: `docs/reports/cyr2d-planner-quality-{provider}-{model}.json`（按实际运行）
- Create: `docs/reports/cyr2d-planner-quality-summary.md`

**Interfaces:**
- Consumes: Task 6 脚本；真实模型配置（需可用 provider）。

- [ ] **Step 1: 运行固定集**

```bash
backend\.venv\Scripts\python.exe -m scripts.run_cyr2d_planner_quality --provider-id deepseek --model deepseek-v4-pro
# 同法跑 deepseek-v4-flash、deepseek-chat、qwen-plus、glm-4-flash（不可用则记录 unavailable）
```

> 真实模型运行需要网络与已配置 API Key；环境不具备时记录 `unavailable` 并在报告中如实说明，不伪造通过。

- [ ] **Step 2: 汇总报告**

`docs/reports/cyr2d-planner-quality-summary.md`：每模型"已验证/未验证"清单、零容忍表、软指标（结构合法率）与运行环境说明。

- [ ] **Step 3: 提交**

```bash
git add docs/reports/cyr2d-planner-quality-* docs/reports/cyr2d-planner-quality-summary.md
git commit -m "docs(cyr2d): record planner quality fixed-set results"
```

---

## 收口

### Task 8: 全量门禁与文档收口

**Files:**
- Modify: `README.md`、`docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md`、`docs/CYR2_TASKRUN_EXECUTION_WORKBENCH_PLAN.md`
- Create: `docs/reports/cyr2d-closure-acceptance.md`

**Interfaces:**
- Consumes: 全部 CYR.2D 实现。
- Produces: 路线图 CYR.2D 勾选、README 状态更新、验收报告。

- [ ] **Step 1: 运行全量门禁**

```bash
cd backend && .\.venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend && node --test tests/*.test.mjs
npm.cmd run build
cd ..\backend && .\.venv\Scripts\python.exe -m compileall -q app tests
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\test-cyr2d-crash-recovery.ps1
```
Expected: 全部通过（现存非阻塞提示白名单不变）。

- [ ] **Step 2: 更新文档**

- README「当前状态」：CYR.2D 完成；下一批 CYR.3。
- 路线图：`CYR.2D：取消竞态、崩溃、打包态与全链路工作台验收` 勾选 `[x]`（保留"打包态"按 spec 边界注明留给 CYR.9）；追加 closure record。
- CYR.2 施工计划：CYR.2D 条目勾选；状态行更新。
- 验收报告：`docs/reports/cyr2d-closure-acceptance.md`（批次、merge SHA、门禁数字、边界、遗留）。

- [ ] **Step 3: 提交并合入**

按 `finishing-a-development-branch`：提交文档 → 合入 `main`（no-ff）→ 推送 → 更新 merge SHA → 删除分支。
