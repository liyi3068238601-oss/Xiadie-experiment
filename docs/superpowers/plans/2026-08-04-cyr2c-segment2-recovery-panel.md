# CYR.2C Segment 2（恢复协议与恢复面板）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 冻结三类恢复语义（side_effect_free / idempotent / side_effectful）并交付基于 ToolRun 证据的恢复面板骨架。

**Architecture:** 后端新增纯 `recovery_policy`（风险等级 + 允许动作矩阵，无 I/O），`task_runs.recovery_view` 聚合 run/nodes/tool_runs 证据，`GET /api/task-runs/{id}/recovery` 暴露权威结果；前端 `recoveryUi.mjs` 纯辅助 + TasksPage 恢复卡片（继续/重试/重规划 + 空态 + 中断横幅）。真实工具执行与重试逻辑属于 CYR.3。

**Tech Stack:** Python 3.12 / FastAPI / SQLite（Schema 88 已含 `recovery_class`）；前端 React + 既有 `api.ts` / `TasksPage.tsx`。

## Global Constraints

- 恢复矩阵以功能 spec §9 为唯一口径：未知 `recovery_class` 或无 ToolRun 终态证据时 fail closed（只允许重新规划）。
- 面板是业务证据视图，不替代 `task.scheduler` 诊断日志，不混入模型心理活动。
- 错误脱敏：trace/错误展示沿用 ToolRun 既有字段，不新增正文落盘。
- 不实现真实工具重试（CYR.3）；「重试」按钮按矩阵显示可用性，点击给出诚实的未接入提示。
- 风险等级只用 `--ok/--warn/--danger` 色值，同时配文字，不单独依赖颜色。

---

### Task 1: recovery_policy 纯模块与矩阵

**Files:**
- Create: `backend/app/recovery_policy.py`
- Create: `backend/tests/test_recovery_policy.py`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `decide_recovery(recovery_class, *, has_terminal_evidence, retries_used) -> dict`
  - 返回：`{risk: "low"|"mid"|"high"|"none", allowed: {"continue": bool, "retry": bool, "replan": bool}, reasons: dict[str, str]}`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_recovery_policy.py`：
```python
from __future__ import annotations

from app import recovery_policy as rp


def test_side_effect_free_matrix() -> None:
    d = rp.decide_recovery("side_effect_free", has_terminal_evidence=True, retries_used=0)
    assert d["risk"] == "low"
    assert d["allowed"] == {"continue": True, "retry": True, "replan": True}


def test_idempotent_retry_bounded() -> None:
    d = rp.decide_recovery("idempotent", has_terminal_evidence=True, retries_used=3)
    assert d["allowed"]["retry"] is False
    assert "retry" in d["reasons"]


def test_side_effectful_requires_confirm_and_no_retry() -> None:
    d = rp.decide_recovery("side_effectful", has_terminal_evidence=True, retries_used=0)
    assert d["risk"] == "high"
    assert d["allowed"] == {"continue": True, "retry": False, "replan": True}
    assert "继续前需要确认" in d["reasons"]["continue"]


def test_no_evidence_fail_closed() -> None:
    for cls in (None, "side_effect_free", "idempotent", "side_effectful", "unknown"):
        d = rp.decide_recovery(cls, has_terminal_evidence=False, retries_used=0)
        assert d["allowed"] == {"continue": False, "retry": False, "replan": True}


def test_exhaustive_matrix() -> None:
    for cls in (None, "side_effect_free", "idempotent", "side_effectful", "unknown"):
        for evidence in (False, True):
            for used in (0, 1, 3, 9):
                d = rp.decide_recovery(cls, has_terminal_evidence=evidence, retries_used=used)
                assert set(d) == {"risk", "allowed", "reasons"}
                assert set(d["allowed"]) == {"continue", "retry", "replan"}
                assert d["risk"] in {"low", "mid", "high", "none"}
```

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_recovery_policy.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 recovery_policy.py**

```python
"""CYR.2C recovery protocol: pure risk/allowed-action matrix (no I/O)."""
from __future__ import annotations

from typing import Literal

RecoveryClass = Literal["side_effect_free", "idempotent", "side_effectful"]
RETRY_LIMIT = 3


def decide_recovery(recovery_class: str | None, *, has_terminal_evidence: bool,
                    retries_used: int) -> dict:
    """Return authoritative recovery advice for one node/run.

    fail closed: unknown class or missing terminal ToolRun evidence only
    allows replanning.
    """
    if not has_terminal_evidence or recovery_class not in {
        "side_effect_free", "idempotent", "side_effectful",
    }:
        return {
            "risk": "none",
            "allowed": {"continue": False, "retry": False, "replan": True},
            "reasons": {
                "continue": "没有可用的工具终态证据。",
                "retry": "没有可用的工具终态证据。",
                "replan": "建议重新规划后再执行。",
            },
        }
    if recovery_class == "side_effect_free":
        return {
            "risk": "low",
            "allowed": {"continue": True, "retry": True, "replan": True},
            "reasons": {
                "continue": "最后一次工具操作无副作用，可安全继续。",
                "retry": "无副作用，可安全重试。",
                "replan": "可重新规划。",
            },
        }
    if recovery_class == "idempotent":
        retry_allowed = int(retries_used or 0) < RETRY_LIMIT
        return {
            "risk": "mid",
            "allowed": {"continue": True, "retry": retry_allowed, "replan": True},
            "reasons": {
                "continue": "幂等操作可继续，但需确认输入未变化。",
                "retry": f"重试安全；剩余 {max(0, RETRY_LIMIT - int(retries_used or 0))} 次。"
                if retry_allowed else "已达到重试上限（3 次）。",
                "replan": "可重新规划。",
            },
        }
    return {
        "risk": "high",
        "allowed": {"continue": True, "retry": False, "replan": True},
        "reasons": {
            "continue": "有副作用操作，继续前需要确认。",
            "retry": "有副作用操作不可盲目重放。",
            "replan": "建议重新规划。",
        },
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_recovery_policy.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/recovery_policy.py backend/tests/test_recovery_policy.py
git commit -m "feat(taskrun): freeze CYR.2C recovery policy matrix"
```

---

### Task 2: recovery_view 与恢复端点

**Files:**
- Modify: `backend/app/task_runs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_recovery_policy.py`

**Interfaces:**
- Consumes: `recovery_policy.decide_recovery`、`task_runs.get`。
- Produces:
  - `task_runs.recovery_view(run_id) -> dict | None`
  - `GET /api/task-runs/{run_id}/recovery`

- [ ] **Step 1: 写失败测试（追加到 test_recovery_policy.py）**

```python
def test_recovery_view_aggregates_tool_evidence() -> None:
    from app import task_runs
    run = task_runs.create(task_id=_task(), idempotency_key="rec-1")
    view = task_runs.recovery_view(run["id"])
    assert view is not None
    assert view["risk"] == "none"          # 无工具证据 -> fail closed
    assert view["allowed"] == {"continue": False, "retry": False, "replan": True}
```

> `_task` 助手可复制 `test_task_runs.py` 的 `_task`/`isolated_db` fixture 到此文件（保持测试独立）。

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_recovery_policy.py -q`
Expected: FAIL（recovery_view 不存在）。

- [ ] **Step 3: 实现**

`task_runs.py` 追加：
```python
def recovery_view(run_id: str) -> dict | None:
    """Aggregate authoritative recovery advice from run, nodes and ToolRun evidence."""
    from . import recovery_policy
    run = get(run_id)
    if run is None:
        return None
    tool_runs = run.get("tool_runs") or []
    last = tool_runs[-1] if tool_runs else None
    has_terminal = bool(last and last.get("status") in {"succeeded", "failed", "completed"})
    # 恢复语义以当前（首个）非终态节点为准；无节点则按 run 级 fail closed。
    node = next((n for n in (run.get("nodes") or [])
                 if n.get("status") not in NODE_TERMINAL), None)
    recovery_class = node.get("recovery_class") if node else None
    retries_used = _count_retries(run, last)
    advice = recovery_policy.decide_recovery(
        recovery_class, has_terminal_evidence=has_terminal, retries_used=retries_used,
    )
    return {
        "run_id": run_id,
        "status": run["status"],
        "recovery_class": recovery_class,
        "last_evidence": {
            "tool_name": last.get("tool_name") if last else None,
            "phase": last.get("phase") if last else None,
            "status": last.get("status") if last else None,
            "trace_id": last.get("trace_id") if last else None,
            "error_message": last.get("error_message") if last else None,
        } if last else None,
        "retries_used": retries_used,
        **advice,
    }


def _count_retries(run: dict, last: dict | None) -> int:
    """Bounded heuristic: tool interruption events observed for this run."""
    if not last:
        return 0
    count = 0
    for event in run.get("events") or []:
        if event.get("event_type") == "task_node_running" and event.get("reason_code") == "retry":
            count += 1
    return min(count, 9)
```

`main.py` 追加路由（任务区末尾）：
```python
@app.get("/api/task-runs/{run_id}/recovery")
def get_task_run_recovery(run_id: str) -> dict:
    result = task_runs.recovery_view(run_id)
    if result is None:
        raise HTTPException(404, "task_run_not_found")
    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_recovery_policy.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/task_runs.py backend/app/main.py backend/tests/test_recovery_policy.py
git commit -m "feat(taskrun): recovery view and endpoint"
```

---

### Task 3: 前端恢复类型与纯辅助

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/recoveryUi.mjs`
- Create: `frontend/tests/recoveryUi.test.mjs`

**Interfaces:**
- Consumes: 后端 `/recovery` 响应。
- Produces: `TaskRunRecovery` 类型、`getTaskRunRecovery(runId)`、`riskLabel/actionLabel` 纯函数。

- [ ] **Step 1: 写失败测试**

`frontend/tests/recoveryUi.test.mjs`：
```js
import { riskLabel, actionLabel, isRetryDisabled } from "../src/recoveryUi.mjs";
import test from "node:test";
import assert from "node:assert/strict";

test("risk labels map to pills", () => {
  assert.equal(riskLabel("low"), "风险 · 低");
  assert.equal(riskLabel("mid"), "风险 · 中");
  assert.equal(riskLabel("high"), "风险 · 高");
  assert.equal(riskLabel("none"), "无证据 · fail closed");
});

test("action labels stay honest before tool execution exists", () => {
  assert.equal(actionLabel("retry", false), "重试（接入工具后可用）");
  assert.equal(isRetryDisabled({ allowed: { retry: false } }), true);
});
```

- [ ] **Step 2: 运行确认失败**

Run: `frontend\node --test tests/recoveryUi.test.mjs`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现**

`frontend/src/recoveryUi.mjs`：
```js
export const riskLabel = (risk) => ({
  low: "风险 · 低", mid: "风险 · 中", high: "风险 · 高", none: "无证据 · fail closed",
}[risk] || "风险未知");
export const actionLabel = (action, retryAllowed) =>
  action === "retry" && !retryAllowed ? "重试（接入工具后可用）" : action === "retry" ? "重试" : action === "continue" ? "继续" : "重新规划";
export const isRetryDisabled = (advice) => advice?.allowed?.retry === false;
```

`api.ts` 追加：
```ts
export interface TaskRunRecovery {
  run_id: string;
  status: TaskRunStatus;
  recovery_class?: TaskNode["recovery_class"];
  last_evidence: {
    tool_name?: string | null;
    phase?: string | null;
    status?: string | null;
    trace_id?: string | null;
    error_message?: string | null;
  } | null;
  retries_used: number;
  risk: "low" | "mid" | "high" | "none";
  allowed: { continue: boolean; retry: boolean; replan: boolean };
  reasons: Record<string, string>;
}
export const getTaskRunRecovery = (runId: string) =>
  j<TaskRunRecovery>(`/api/task-runs/${encodeURIComponent(runId)}/recovery`);
```

- [ ] **Step 4: 运行确认通过**

Run: `frontend\node --test tests/recoveryUi.test.mjs` + `npm.cmd run build`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api.ts frontend/src/recoveryUi.mjs frontend/tests
git commit -m "feat(frontend): recovery types and ui helpers"
```

---

### Task 4: 恢复面板（TasksPage）

**Files:**
- Modify: `frontend/src/components/TasksPage.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/taskRunUx.test.mjs`

**Interfaces:**
- Consumes: `api.getTaskRunRecovery`、`recoveryUi` 辅助。
- Produces: run 处于 `paused/recovery_required/failed` 时显示恢复卡 + 中断横幅；「继续」走 `resume`，「重新规划」走 `editPlan`，「重试」禁用并说明。

- [ ] **Step 1: 写失败测试（追加到 taskRunUx.test.mjs）**

```js
import { recoveryCardVisible } from "../src/recoveryUi.mjs";
test("recovery card only appears for interrupted statuses", () => {
  for (const s of ["paused", "recovery_required", "failed"]) {
    assert.equal(recoveryCardVisible(s), true);
  }
  for (const s of ["draft", "ready", "running", "completed"]) {
    assert.equal(recoveryCardVisible(s), false);
  }
});
```
`recoveryUi.mjs` 追加：
```js
export const recoveryCardVisible = (status) =>
  ["paused", "recovery_required", "failed"].includes(status);
```

- [ ] **Step 2: 运行确认失败**

Run: `frontend\node --test tests/taskRunUx.test.mjs`
Expected: FAIL（recoveryCardVisible 不存在）。

- [ ] **Step 3: 实现 TasksPage**

1. 状态：`const [recovery, setRecovery] = useState<Record<string, api.TaskRunRecovery>>({});`
2. `refresh` 与 `replaceRun` 后，对非终态 run 拉取恢复：
```tsx
const loadRecovery = async (run: api.TaskRun) => {
  try { setRecovery((cur) => ({ ...cur, [run.id]: await api.getTaskRunRecovery(run.id) })); }
  catch { /* 面板是辅助视图，失败不阻塞任务列表 */ }
};
```
3. 运行面板内、节点列表之后渲染（仅当 `recoveryCardVisible(run.status)`）：
```tsx
{recoveryCardVisible(run.status) && (
  <>
    {run.status === "recovery_required" && (
      <div className="run-banner warn">
        <strong>应用中断，任务已进入保护状态，不会自动继续</strong>
      </div>
    )}
    <article className="recovery-card" data-mode={recovery[run.id]?.last_evidence ? "data" : "empty"}>
      <header>
        <div>
          <span className="page-eyebrow">恢复建议</span>
          <h2>{recovery[run.id]?.last_evidence ? "基于最后一次工具证据" : "暂无工具执行记录"}</h2>
        </div>
        <span className={`risk-pill ${recovery[run.id]?.risk || "none"}`}>
          {riskLabel(recovery[run.id]?.risk || "none")}
        </span>
      </header>
      {recovery[run.id]?.last_evidence ? (
        <div className="recovery-evidence">
          <div className="evidence-row"><span className="evidence-label">工具</span><strong>{recovery[run.id].last_evidence.tool_name}</strong></div>
          <div className="evidence-row"><span className="evidence-label">阶段</span><span>{recovery[run.id].last_evidence.phase} · {recovery[run.id].last_evidence.status}</span></div>
          {recovery[run.id].last_evidence.trace_id && (
            <div className="evidence-row"><span className="evidence-label">trace</span><code>{recovery[run.id].last_evidence.trace_id.slice(0, 8)}…</code></div>
          )}
          {recovery[run.id].last_evidence.error_message && (
            <div className="evidence-row"><span className="evidence-label">错误</span><span className="redacted">{recovery[run.id].last_evidence.error_message}</span></div>
          )}
        </div>
      ) : (
        <p className="empty-copy">当前运行没有工具执行记录；接入工具后将在这里显示恢复建议。</p>
      )}
      <div className="recovery-actions">
        <button className="primary" disabled={!recovery[run.id]?.allowed.continue}
          onClick={() => void runAction(run, "resume")}>继续</button>
        <button disabled={!recovery[run.id]?.allowed.retry || true}
          title={recovery[run.id]?.reasons?.retry || "工具执行接入后可重试"}>
          重试（接入工具后可用）</button>
        <button className="ghost" onClick={() => void editPlan(task, run)}>重新规划</button>
      </div>
    </article>
  </>
)}
```
> 「重试」按钮在 CYR.3 前恒禁用并给出诚实的提示；`runAction(run, "resume")` 与 `editPlan(task, run)` 是 TasksPage 既有函数。

`styles.css` 追加（按 UI 设计 v0.2）：
```css
.run-banner.warn{border-color:rgba(234,200,120,.32);background:rgba(234,200,120,.06);border-left:3px solid var(--warn)}
.run-banner.warn strong{color:#efd9a3}
.recovery-card{display:grid;gap:10px;margin-top:4px;padding:12px 13px;
  border:1px solid rgba(157,132,255,.18);border-left:3px solid var(--warn);
  border-radius:var(--radius-sm);background:rgba(44,28,78,.5)}
.recovery-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.recovery-card h2{margin-top:4px;font-size:12px;color:#e0dae9}
.risk-pill{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:99px;font-size:9px;border:1px solid}
.risk-pill.low{border-color:rgba(98,201,155,.3);color:#9fe0bf;background:rgba(98,201,155,.07)}
.risk-pill.mid{border-color:rgba(234,200,120,.3);color:#efd9a3;background:rgba(234,200,120,.07)}
.risk-pill.high{border-color:rgba(233,135,154,.35);color:#f0b3bf;background:rgba(233,135,154,.07)}
.risk-pill.none{border-color:rgba(255,255,255,.14);color:#8f88a0;background:rgba(255,255,255,.025)}
.recovery-evidence{display:grid;gap:6px;padding:9px 10px;border:1px solid rgba(157,132,255,.1);
  border-radius:8px;background:rgba(10,8,16,.22)}
.evidence-row{display:flex;align-items:center;gap:9px;font-size:9px}
.evidence-label{width:42px;flex:0 0 auto;color:var(--text-faint)}
.recovery-actions{display:flex;gap:7px;flex-wrap:wrap}
.recovery-actions button{padding:7px 13px;border:1px solid rgba(187,177,221,.16);border-radius:8px;color:#b8afd0;font-size:10px}
.recovery-actions .primary{color:#fff;background:linear-gradient(135deg,var(--violet),var(--indigo))}
.recovery-actions button:disabled{opacity:.45;cursor:not-allowed}
.empty-copy{color:var(--text-faint);font-size:10px;line-height:1.7}
```

- [ ] **Step 4: 运行确认通过**

Run: `frontend\node --test tests/recoveryUi.test.mjs tests/taskRunUx.test.mjs` + `npm.cmd run build`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/TasksPage.tsx frontend/src/styles.css frontend/src/recoveryUi.mjs frontend/tests
git commit -m "feat(tasks): recovery panel with evidence and honest retry state"
```

---

### Task 5: 全量门禁与文档收口

**Files:**
- Modify: `README.md`、`docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md`、`docs/CYR2_TASKRUN_EXECUTION_WORKBENCH_PLAN.md`
- Create: `docs/reports/cyr2c-closure-acceptance.md`

**Interfaces:**
- Consumes: 全部 CYR.2C 实现。
- Produces: 路线图 CYR.2C 勾选、README 状态更新、验收报告。

- [ ] **Step 1: 运行全量门禁**

```bash
cd backend && .\.venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend && node --test tests/*.test.mjs
npm.cmd run build
cd ..\backend && .\.venv\Scripts\python.exe -m compileall -q app tests
git diff --check
```
Expected: 全部通过。

- [ ] **Step 2: 更新文档**

- README「当前状态」：CYR.2C（Planner + 锁定 + 来源引用 + 恢复协议/面板）完成并入 main；下一批 CYR.2D。
- 路线图：`CYR.2C：单 Agent Planner、来源引用、恢复策略与用户锁定节点` 勾选 `[x]`；追加 closure record。
- CYR.2 施工计划：CYR.2C 条目全部勾选；状态行更新为「CYR.2C 已完成，下一批 CYR.2D」。
- 验收报告：`docs/reports/cyr2c-closure-acceptance.md`（批次、merge SHA、门禁数字、边界、遗留）。

- [ ] **Step 3: 提交**

```bash
git add README.md docs
git commit -m "docs(cyr2c): close CYR.2C and record acceptance"
```

- [ ] **Step 4: 收口合入**

按 `finishing-a-development-branch`：验证测试 → 合入 `main`（no-ff）→ 推送 → 更新验收报告 merge SHA → 删除已合并分支。
