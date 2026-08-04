# CYR.3 ToolRegistry / 权限 / Artifact 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立工具共享安全执行底座：ToolRegistry + 首批只读工具绑定 TaskRun 节点执行器（ToolRun 真实证据），PermissionGuard + 聊天确认 + 受限写入，Artifact 域（版本/回滚/软删/预览）与 RecoveryCheckpoint。

**Architecture:** 工具是进程内注册函数，统一经 Executor → ToolRun 包装器执行；节点声明 `tool_ref/tool_args`，只有 ToolRun `succeeded` 证据才允许节点 `succeed`；权限按 manifest 声明 × 有期限 grant 判定，缺失走聊天确认；写入生成 Artifact 版本，回滚即恢复上一版；RecoveryCheckpoint 每次 ToolRun 终态落一条。

**Tech Stack:** Python 3.12 / FastAPI / SQLite（Schema 89）/ 复用 `tool_runs.create|transition`、`knowledge_parser`、`task_run_artifact_links`；前端 React + `api.ts` / `chatSseProtocol.ts` / `ChatView`（knowledge-grant-card 模式）/ `TasksPage`。

## Global Constraints

- 工具结果只能来自真实执行包装器，模型文字不能自报成功；节点 `succeeded` 必须由 ToolRun 证据驱动。
- 默认 fail closed：未注册工具 404、缺权限拒绝、拒绝/超时确认不产生半状态。
- 只读工具工作区内会话级隐式授权；写入/工作区外必须显式确认。
- 参数先过 JSON Schema 校验；输出与错误脱敏、有界（沿用 `redact_text`）。
- 路径经规范化校验：拒绝 `..` 与符号链接逃逸；所有工具仅限 `workspace` 根内。
- Artifact 保留最近 10 版；删除走软删 → purge 审计；回滚 = 恢复上一活动版本。
- 不修改 TaskRun/TaskNode 状态机合同；不引入外部编排、第二数据库或新运行时依赖。
- CYR.2C/2D 固定集保持绿（恢复矩阵、故障注入、全链路关联）。

---

## Segment A：ToolRegistry + 只读工具 + 执行器

### Task A1: Schema 89 迁移

**Files:**
- Modify: `backend/app/db.py`（MIGRATIONS 追加 `(89, ...)`）
- Create: `backend/tests/test_task_run_schema_89.py`

**Interfaces:**
- Produces: `task_nodes.tool_ref/tool_args_json`；新表 `permission_grants`、`confirmation_requests`、`artifacts`、`recovery_checkpoints`。

- [ ] **Step 1: 写失败测试**

```python
def test_schema_89_tables_and_columns() -> None:
    conn = db.connect()
    try:
        node_cols = {r["name"] for r in conn.execute("PRAGMA table_info(task_nodes)").fetchall()}
        assert {"tool_ref", "tool_args_json"} <= node_cols
        for table in ("permission_grants", "confirmation_requests", "artifacts",
                      "recovery_checkpoints"):
            assert conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone() is not None
        assert db.get_schema_version() == 89
    finally:
        conn.close()
```

- [ ] **Step 2: 运行确认失败**（schema 88，无表/列）
- [ ] **Step 3: 追加迁移 89**（参照 spec §4.4/5.1/6.1/6.4 的列定义；`task_nodes` 用 ALTER，四张新表用 CREATE + 索引；`confirmation_requests.status` 与 `artifacts.status` 加 CHECK）
- [ ] **Step 4: 运行确认通过**（含既有 schema 87/88 测试）
- [ ] **Step 5: 提交** `feat(tools): add CYR.3 schema 89 tables`

---

### Task A2: ToolRegistry 模块

**Files:**
- Create: `backend/app/tool_registry.py`
- Create: `backend/tests/test_tool_registry.py`

**Interfaces:**
- Consumes: 无。
- Produces: `ToolManifest` dataclass；`register(manifest, handler)`、`list() -> list[dict]`、`get(id) -> ToolManifest`、`validate_input(id, args) -> dict`。

- [ ] **Step 1: 写失败测试**

```python
def test_register_validate_and_reject_unknown() -> None:
    registry = ToolRegistry()
    registry.register(ToolManifest(
        id="workspace.read_file", name="读取文件", description="read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}},
                      "required": ["path"]},
        output_schema={}, side_effect=False, risk_level="S0",
        declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
    ), lambda args: {"content": "x"})
    assert registry.validate_input("workspace.read_file", {"path": "a.txt"})["path"] == "a.txt"
    with pytest.raises(ToolRegistryError):
        registry.validate_input("ghost", {})
    with pytest.raises(ToolRegistryError):
        registry.validate_input("workspace.read_file", {"path": 1})
    assert len(registry.list()) == 1
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：`ToolManifest`（frozen dataclass + `to_dict`）、`ToolRegistry`（dict 注册、内置轻量校验器：支持 `type`/`required`/`properties`/`enum`/`maxLength`/`minLength`/`maxItems`，不引入 jsonschema 依赖）、`ToolRegistryError`。
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(tools): add tool registry with manifest validation`

---

### Task A3: 首批只读工具

**Files:**
- Create: `backend/app/tool_handlers.py`（5 个 handler + `register_default_tools(registry)`）
- Create: `backend/tests/test_tool_handlers.py`

**Interfaces:**
- Consumes: `tool_registry`、`knowledge_parser`、`db`（workspace 根路径从设置取）。
- Produces: `workspace.read_file` / `workspace.search` / `workspace.list_dir` / `document.parse` / `code.inspect` 注册。

- [ ] **Step 1: 写失败测试**

```python
def test_read_file_respects_workspace_boundary(tmp_path) -> None:
    target = tmp_path / "ok.txt"
    target.write_text("hello", encoding="utf-8")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("no", encoding="utf-8")
    handler = read_file()
    assert handler({"path": "ok.txt"}, workspace=tmp_path)["content"] == "hello"
    with pytest.raises(ToolExecutionError):
        handler({"path": str(outside)}, workspace=tmp_path)  # 越界
    with pytest.raises(ToolExecutionError):
        handler({"path": "../secret.txt"}, workspace=tmp_path)  # 规范化逃逸
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：
  - `_resolve_workspace_path(workspace, raw) -> Path`：`resolve()` 后必须 `is_relative_to(workspace)`，否则抛 `ToolExecutionError`。
  - 统一签名 `handler(args, *, workspace)`：`read_file` 大小 ≤2 MiB、行数 ≤20000，输出有界；`search` `Path.rglob` + 文本匹配（大小写/正则受限）结果 ≤100 条；`list_dir` 单层元数据；`document.parse` 委托 `knowledge_parser`（有界页数）；`code.inspect` 用 `compile()`/`ast` 不执行。
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(tools): add first read-only tool handlers`

---

### Task A4: Executor 绑定节点 + ToolRun 证据链

**Files:**
- Create: `backend/app/executor.py`
- Modify: `backend/app/main.py`、`backend/app/task_runs.py`（节点解码带 tool 字段）、`backend/app/task_run_contract.py`（如需新错误码）
- Create: `backend/tests/test_executor.py`

**Interfaces:**
- Consumes: `tool_registry`、`tool_handlers.register_default_tools`、`tool_runs.create|transition`、`task_runs.transition_node`。
- Produces: `execute_node(run, node, *, session_id=None) -> dict`；`POST /api/task-runs/{run_id}/nodes/{node_id}/action` 的 `start` 走执行器。

- [ ] **Step 1: 写失败测试**

```python
def test_execute_node_only_succeeds_with_real_evidence() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="exec-1")
    planned = task_runs.replace_plan(run["id"], [{
        "client_id": "a", "title": "读取说明",
        "tool_ref": "workspace.read_file", "tool_args": {"path": "README.md"},
    }], expected_revision=run["revision"])
    started = task_runs.start(planned["id"], expected_revision=planned["revision"])
    node = started["nodes"][0]
    result = executor.execute_node(started, node, workspace=Path(repo_root))
    detail = task_runs.get(started["id"])
    assert detail["nodes"][0]["status"] == "succeeded"
    assert detail["tool_runs"][-1]["status"] == "succeeded"
    assert detail["tool_runs"][-1]["result_summary"] != {}


def test_execute_node_failure_marks_node_failed_with_evidence() -> None:
    # 工具抛 ToolExecutionError → ToolRun failed + 节点 failed + 脱敏错误
```

> `_task`/isolated_db fixture 沿用 `test_task_runs.py`；`replace_plan` 的节点需先支持 `tool_ref/tool_args`（Task A1 列 + `_normalize_plan` 透传，参照 CYR.2C 的 input_refs 模式）。

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
  - `task_runs._normalize_plan` 解析 `tool_ref`（≤120）/`tool_args`（dict，有界 JSON）；`_decode_node` 返回两者。
  - `executor.execute_node`：
```python
def execute_node(run: dict, node: dict, *, session_id: str | None = None,
                 workspace: Path | None = None) -> dict:
    tool_ref = node.get("tool_ref")
    if not tool_ref:
        raise ToolExecutionError("node_has_no_tool", "节点未绑定工具")
    manifest = REGISTRY.get(tool_ref)
    args = REGISTRY.validate_input(tool_ref, node.get("tool_args") or {})
    tool_run = tool_runs.create(
        tool_name=tool_ref, trace_id=run["trace_id"], session_id=session_id,
        task_run_id=run["id"], risk_level=manifest.risk_level,
        arguments_summary=redact(args, limit=2000),
    )
    tool_runs.transition(tool_run["id"], "running")
    try:
        result = REGISTRY.handler_for(tool_ref)(args, workspace=workspace)
    except ToolExecutionError as exc:
        tool_runs.transition(tool_run["id"], "failed", error=exc)
        return task_runs.transition_node(
            run["id"], node["id"], "fail", expected_revision=run["revision"],
            error_code=exc.code, error_message=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - 未知异常也走证据失败
        tool_runs.transition(tool_run["id"], "failed", error=exc)
        return task_runs.transition_node(
            run["id"], node["id"], "fail", expected_revision=run["revision"],
            error_code="tool_execution_error", error_message="工具执行失败（已脱敏）",
        )
    tool_runs.transition(tool_run["id"], "succeeded",
                         result_summary=_bounded_result(result))
    return task_runs.transition_node(
        run["id"], node["id"], "succeed", expected_revision=run["revision"],
        output_summary=_bounded_result(result)["summary"],
    )
```
  - handler 签名统一 `handler(args, *, workspace=None)`；`REGISTRY.handler_for` 返回 handler。
  - `main.py`：`act_on_task_node` 的 `start` 分支改为调用 `executor.execute_node`（传入 run/node/workspace），`succeed/fail/skip` 保留为诊断入口但加日志标记。
  - `task_run_contract`：如需 `task_node_tool_not_bindable` 等错误码则加入 `ERROR_SPECS`（modify_then_retry）。
- [ ] **Step 4: 运行确认通过**（含 CYR.2C 恢复/故障固定集回归）
- [ ] **Step 5: 提交** `feat(tools): bind executor to task nodes with ToolRun evidence`

---

### Task A5: 聊天只读直调

**Files:**
- Create: `backend/app/chat_tool_ingress.py`
- Modify: `backend/app/main.py`（chat 尾部工具意图处理）
- Create: `backend/tests/test_chat_tool_ingress.py`

**Interfaces:**
- Consumes: `tool_registry`、`tool_handlers`。
- Produces: `match_tool_intent(content) -> (tool_id, args) | None`；`run_readonly(content, workspace) -> dict | None`。

- [ ] **Step 1: 写失败测试**

```python
def test_match_read_and_search_intents() -> None:
    assert match_tool_intent("帮我读一下 README.md") == ("workspace.read_file", {"path": "README.md"})
    assert match_tool_intent("搜索一下 TODO 在哪") == ("workspace.search", {"query": "TODO"})
    assert match_tool_intent("今天天气如何") is None
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：正则意图匹配（`读(一下)?\s*(\S+)` / `搜(索)?(一下)?\s*(.+)`），只允许只读工具；在 chat `gen()` 尾部（plan_proposal 逻辑旁）执行并把有界结果附加到回复（失败静默）。
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(tools): chat direct read-only tool ingress`

---

## Segment B：权限与确认

### Task B1: PermissionGuard + grant 生命周期

**Files:**
- Create: `backend/app/permission_guard.py`
- Create: `backend/tests/test_permission_guard.py`

**Interfaces:**
- Consumes: Schema 89 `permission_grants`。
- Produces: `create_grant(...)`、`revoke_grant(id, reason)`、`active_grant(tool_id, target)`、`check(tool, args, *, session_id, workspace) -> "allowed"|"denied"|"needs_confirmation"`。

- [ ] **Step 1: 写失败测试**：工作区内只读 S0 工具 → allowed（会话隐式）；写入工具无 grant → needs_confirmation；显式 grant 后 → allowed；revoke 后 → denied；过期 → denied。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：目标规范化与匹配（path_prefix 用 `resolve` 后前缀比较）、会话隐式规则、grant 状态（active/expired/revoked 由查询时计算）。
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(tools): permission guard with scoped grants`

---

### Task B2: ConfirmationRequest 服务与 API

**Files:**
- Create: `backend/app/confirmation.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_confirmation.py`

**Interfaces:**
- Produces: `create_request(...)`、`confirm(id, *, grant_duration_seconds)`、`deny(id)`、`pending(session_id)`；API `POST /api/tool-permissions/requests`、`POST .../requests/{id}/confirm|deny`。

- [ ] **Step 1: 写失败测试**：创建 pending；confirm 生成 grant 并把 request 置 confirmed；deny 置 denied；重复处理幂等；未知 id 404。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（复用 `task_runs` 的 conflict/404 处理模式）
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(tools): confirmation request service and api`

---

### Task B3: 聊天确认卡（SSE + 前端）

**Files:**
- Modify: `backend/app/main.py`（chat 尾部 `tool_permission_request` 事件）、`frontend/src/chatSseProtocol.ts`、`frontend/tests/fixtures/chatSseProtocol.mjs`、`frontend/src/api.ts`、`frontend/src/components/ChatView.tsx`、`frontend/src/styles.css`
- Modify: `frontend/tests/chatSseFinal.test.mjs`、`frontend/tests/taskRunUx.test.mjs`

**Interfaces:**
- Produces: SSE 事件 `tool_permission_request`；前端确认卡（knowledge-grant-card 模式）；`confirmToolPermission(id, seconds)` / `denyToolPermission(id)`。

- [ ] **Step 1: 写失败测试**：`chatSseFinal` 断言 fixture 分发新事件；`taskRunUx` 正则断言 api 含 confirm/deny 与事件名。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：协议分支 + 事件发射（生成 request 后 yield）；`ChatView` 渲染确认卡（工具、目标、风险、用途、期限 + 确认/拒绝按钮，成功后重试对应执行）；样式沿用 `.knowledge-grant-card` 变体。
- [ ] **Step 4: 运行确认通过** + `npm.cmd run build`
- [ ] **Step 5: 提交** `feat(tools): chat confirmation card for tool permissions`

---

### Task B4: 受限写入工具

**Files:**
- Modify: `backend/app/tool_handlers.py`、`backend/app/executor.py`（写工具执行前强制 `guard.check`）
- Create: `backend/tests/test_tool_handlers.py`（追加）

**Interfaces:**
- Produces: `workspace.write_file`（S2，显式确认；写内容有界；写入即创建 Artifact 版本）。

- [ ] **Step 1: 写失败测试**：无 grant 时 executor 拒绝且 ToolRun `denied`、节点不推进；有 grant 时写入成功并生成 Artifact 版本（C 段表）。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：`executor` 在执行前调 `permission_guard.check`；`denied` → `tool_runs.transition(..., "denied", cancellation_reason=...)`；`needs_confirmation` → 创建 `ConfirmationRequest` 并返回挂起状态（节点保持 `running` 或回退 `ready`——以测试固化：选"保持 running + waiting_reason=待确认权限"）。
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(tools): restricted write tool with explicit confirmation`

---

## Segment C：Artifact 与恢复

### Task C1: Artifact 服务

**Files:**
- Create: `backend/app/artifacts.py`
- Create: `backend/tests/test_artifacts.py`

**Interfaces:**
- Produces: `create_version(task_run_id, node_id, artifact_id, kind, data, mime) -> dict`、`list(run_id)`、`get(id)`、`rollback(id)`、`soft_delete(id)`、`purge(id)`、`preview(id)`。

- [ ] **Step 1: 写失败测试**：版本递增且保留最近 10 版；rollback 恢复上一活动版本；soft_delete 后 list 不可见但审计可查；purge 物理删除；preview 按 kind 返回。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：存储 `data/artifacts/{run_id}/{artifact_id}/v{n}`；软删状态 + `purged_at`；回滚用引用切换（当前活动版本指针字段 `active_version`）。
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(artifacts): versioned artifact domain with rollback and audit delete`

---

### Task C2: Artifact API 与前端预览

**Files:**
- Modify: `backend/app/main.py`、`frontend/src/api.ts`、`frontend/src/components/TasksPage.tsx`、`frontend/src/components/ArtifactViewer.tsx`（新建）、`frontend/src/styles.css`
- Create: `backend/tests/test_artifacts_api.py`、`frontend/tests/artifactUi.test.mjs`

**Interfaces:**
- Produces: `GET/POST /api/artifacts`、`POST /api/artifacts/{id}/rollback`、`DELETE /api/artifacts/{id}`、`POST /api/artifacts/{id}/purge`、`GET /api/artifacts/{id}/preview`；前端 ArtifactViewer + 运行面板产物列表（含 `task_run_artifact_links`）。

- [ ] **Step 1: 写失败测试**：API happy/404/409 路径；`artifactUi` 纯函数（kind→渲染标签、版本排序）。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（路由复用 `_task_run_call` 模式；前端 viewer 按 kind 渲染文本/图片/PDF 元数据）
- [ ] **Step 4: 运行确认通过** + build
- [ ] **Step 5: 提交** `feat(artifacts): artifact api and frontend viewer`

---

### Task C3: RecoveryCheckpoint 与恢复接线

**Files:**
- Create: `backend/app/recovery_checkpoint.py`
- Modify: `backend/app/executor.py`（ToolRun 终态写 checkpoint）、`backend/app/task_runs.py`（`recovery_view` 暴露 checkpoint）、`frontend/src/components/TasksPage.tsx`（重试按钮接真实执行）
- Create: `backend/tests/test_recovery_checkpoint.py`

**Interfaces:**
- Produces: `record(run, node, tool_run, artifact_before)`；`latest(run_id)`；`can_retry(run_id) -> bool`（复用 `recovery_policy`）。

- [ ] **Step 1: 写失败测试**：succeeded 与 failed 都写 checkpoint（含前置 Artifact 版本）；重试仅在输入/前置版本未变时允许；回滚恢复到 checkpoint 记录版本。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：checkpoint 表写入；`recovery_view` 返回 `last_checkpoint`；前端"重试"按钮在 `allowed.retry && can_retry` 时启用，点击走 `POST /api/task-runs/{id}/nodes/{node_id}/action start`（真实执行器重跑）。
- [ ] **Step 4: 运行确认通过**（CYR.2C/2D 恢复固定集保持绿）
- [ ] **Step 5: 提交** `feat(tools): recovery checkpoints and real retry wiring`

---

## 收口

### Task C4: 全量门禁与文档收口

**Files:**
- Modify: `README.md`、`docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md`、`docs/CYR2_TASKRUN_EXECUTION_WORKBENCH_PLAN.md`
- Create: `docs/reports/cyr3-closure-acceptance.md`

- [ ] **Step 1: 全量门禁**：后端全量 pytest、前端 node --test + build、compileall、`git diff --check`。
- [ ] **Step 2: 更新文档**：README 当前状态（CYR.3 完成，下一批 PLUG.0/CYR.4）；路线图 CYR.3 勾选并追加 closure record；施工计划更新。
- [ ] **Step 3: 提交并合入**：按 `finishing-a-development-branch` 合入 `main`（no-ff）→ 推送 → 更新 merge SHA → 删除分支。
