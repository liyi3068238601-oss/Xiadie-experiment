# CYR.3 ToolRegistry / 权限 / Artifact 设计

> 状态：设计已批准（2026-08-04），书面 spec 待用户复核
> 决策日期：2026-08-04
> 适用范围：ToolRegistry 与首批只读工具、TaskRun 节点执行器、PermissionGuard 与聊天确认、受限写入工具、Artifact 域与 RecoveryCheckpoint
> 前置基线：CYR.2D 收口（main `7725f7e`，merge `606a530`）；Schema 88
> 后续边界：外部连接（CYR.6）、受控主动与 Worker（CYR.7/8）、不可信插件隔离（PLUG.2）、打包/安装（CYR.9）

## 1. 批次定义

一个批次、一份 spec、三段实施：

- 第一段（Segment A）：ToolRegistry + 首批只读工具 + TaskRun 节点执行器与 ToolRun 真实证据链。
- 第二段（Segment B）：PermissionGuard + ConfirmationRequest + 受限写入工具。
- 第三段（Segment C）：Artifact 域（版本/软删/回滚/预览）+ RecoveryCheckpoint。

## 2. 目标

1. 工具结果只能来自真实执行包装器，模型文字不能自报成功；ToolRun 记录输入有界摘要、真实结果、脱敏错误与 `trace_id`。
2. 首批只读工具绑定 TaskRun 节点：只有证据成功才允许节点 `succeed`；失败可重试，恢复面板的"重试"第一次有真实执行对象。
3. 权限按工具声明与目标绑定（路径前缀/域名）、有期限、可撤销；只读工作区内隐式授权，写入/网络必须聊天确认，拒绝 fail closed。
4. Artifact 统一管理生成文件：有界版本（最近 10 版）、审计软删、可恢复，回滚即恢复上一版本；预览覆盖可渲染格式。
5. RecoveryCheckpoint 记录每次工具执行的前置状态，支撑安全重试与回滚。

## 3. 非目标

- 不做外部编排运行时、多 Agent 黑板、第二套状态数据库或新运行时依赖。
- 不做不可信插件隔离（PLUG.2 独立进程）、外部浏览器/邮件/云盘连接（CYR.6）、Worker 委派（CYR.8）。
- 不扩大任意 Shell、桌面输入控制或任意文件系统写入；工具只通过 ToolRegistry 注册，默认 fail closed。
- 不修改 TaskRun/TaskNode 状态机合同；节点成功仍由证据驱动。

## 4. Segment A：ToolRegistry 与首批只读工具

### 4.1 ToolManifest

代码级注册（不落库），字段：

```text
id: str（如 workspace.read_file）
name / description
input_schema: JSON Schema（参数校验）
output_schema: JSON Schema（结果投影）
side_effect: bool（A 段工具均为 false）
risk_level: S0..S4（S0 只读无副作用，S4 高破坏性）
declared_permissions: [目标类型 + 目标模式]（如 {"path_prefix", "workspace/"}）
```

### 4.2 ToolRegistry

- `register(manifest, handler)` / `list()` / `get(id)` / `validate_input(id, args)`。
- 校验：manifest id 唯一、schema 合法、handler 可调用；未注册 id 一律 404。

### 4.3 首批工具（A 段）

| 工具 | 副作用 | 风险 | 边界 |
|---|---|---|---|
| `workspace.read_file` | 无 | S0 | 仅工作区内路径；大小 ≤2 MiB、行数 ≤20000，输出有界 |
| `workspace.search` | 无 | S0 | 工作区内文本搜索（大小写/正则受限），结果 ≤100 条 |
| `workspace.list_dir` | 无 | S0 | 单层列表 + 元数据，深度受限 |
| `document.parse` | 无 | S0 | 复用 `knowledge_parser`；文本/Markdown 直接解析，PDF/DOCX 有界页数 |
| `code.inspect` | 无 | S0 | 本地代码检查：语法编译、符号表、行数；不执行代码 |

所有工具在独立于模型调用的进程内函数中执行，参数先过 JSON Schema 校验。

### 4.4 TaskRun 节点执行器

- Schema 89：`task_nodes` 增加 `tool_ref TEXT`、`tool_args_json TEXT`（节点绑定工具与参数，有界）。
- 工作台"执行"按钮（原手动 `start`/`succeed` 调试入口）改为真实执行器：`executor.execute_node(run, node)`。
- 执行流：`tool_runs.create`（queued）→ 权限检查（B 段接入）→ 调用 handler → `transition` 到 `succeeded`/`failed`，写入输出摘要或脱敏错误 → 仅 succeeded 时节点进入 `succeeded`。
- ToolRun 包装器复用 `tool_runs.py` 状态机（`queued/running/succeeded/failed`），并绑定 `task_run_id`、`node_id`、`trace_id`。
- 手动"失败/跳过"入口保留为诊断用途，但成功路径必须经过真实执行。

### 4.5 聊天直调

- 聊天中"帮我读/搜/查"类指令经意图匹配触发同一 ToolRegistry 执行（受权限检查约束），结果以引用/摘要回填，不开放第二套执行路径。

## 5. Segment B：PermissionGuard 与 ConfirmationRequest

### 5.1 PermissionGrant

Schema 89 新表 `permission_grants`：

```text
id, tool_id, target_kind('path_prefix'|'domain'), target, purpose,
expires_at, session_id, created_at, revoked_at, revoked_reason
```

- 只读工具在工作区内：会话级隐式授权（`expires_at = 会话结束`，无需确认）。
- 写入/网络/工作区外读取：必须显式确认。

### 5.2 PermissionGuard

- `guard.check(tool, args)`：解析 manifest 声明权限 → 匹配活跃 grant → 通过/拒绝/需确认。
- 需确认时生成 `ConfirmationRequest` 并挂起执行（不落半状态），用户确认后自动重试；拒绝/超时 fail closed。

### 5.3 ConfirmationRequest 与聊天确认卡

- 新表 `confirmation_requests`：id、tool_id、目标、风险等级、用途、期限、状态（pending/confirmed/denied/expired）、`task_run_id/node_id`（可选）。
- 后端 `POST /api/tool-permissions/requests`、`POST .../requests/{id}/confirm|deny`。
- 聊天 SSE 新增 `tool_permission_request` 事件；前端复用 knowledge-grant-card 模式渲染确认卡（工具、目标、风险、用途、期限 + 确认/拒绝）。
- 前端 `api.ts` 增加对应类型与函数；`chatSseProtocol` 增加事件分支与 fixture。

### 5.4 受限写入工具（B 段）

| 工具 | 副作用 | 风险 | 边界 |
|---|---|---|---|
| `workspace.write_file` | 有 | S2 | 工作区内、显式确认；写入生成 Artifact 版本（C 段），可回滚 |

- 写工具执行前必须存在匹配 grant；写入内容有界，路径经规范化校验（拒绝 `..`/符号链接逃逸）。

## 6. Segment C：Artifact 域与 RecoveryCheckpoint

### 6.1 数据与存储

- Schema 89 新表 `artifacts`：

```text
id, task_run_id, node_id, artifact_kind('text'|'markdown'|'image'|'pdf'|'data'),
mime_type, size_bytes, sha256, version(>=1), status('active'|'soft_deleted'),
provenance_json, created_at, updated_at
```

- 存储布局：`data/artifacts/{task_run_id}/{artifact_id}/v{n}`。
- `task_run_artifact_links` 升级为指向真实 `artifacts.id`。

### 6.2 版本、回滚与删除

- 每次写入同一 `artifact_id` 生成 `version+1`；保留最近 10 版，超出按序清理物理文件（保留审计）。
- 回滚：`POST /api/artifacts/{id}/rollback` → 恢复上一活动版本为当前版本（复制/切换引用）。
- 删除：`DELETE /api/artifacts/{id}` → 软删（`status='soft_deleted'` + 审计事件）→ `POST /api/artifacts/{id}/purge` 物理清除。

### 6.3 预览

- `GET /api/artifacts/{id}/preview` 返回可渲染内容（文本/Markdown 全文、图片字节、PDF 页面计数）；前端 ArtifactViewer 组件按 kind 渲染。

### 6.4 RecoveryCheckpoint

- 每次 ToolRun 成功/失败时记录 checkpoint：输入参数摘要、输出 Artifact 引用、前置 Artifact 版本、`trace_id`。
- 重试：检查输入/前置版本未变才允许（沿用 CYR.2C 恢复矩阵）；回滚：恢复到 checkpoint 记录的前置版本。
- 存储：独立 `recovery_checkpoints` 表（Schema 89），每次 ToolRun 终态写入一条。

## 7. 门禁

- 后端全量 pytest、前端 node --test 与 Vite 生产构建、Python compileall、`git diff --check`。
- 工具执行集成测试：真实证据（不允许模型自报成功）、权限拒绝/确认流程、版本回滚与软删。
- 恢复面板"重试"接真实执行器后的回归（CYR.2C/2D 固定集保持绿）。

## 8. 实施分段

### Segment A：ToolRegistry + 只读工具 + 执行器

1. Schema 89（task_nodes.tool_ref/tool_args_json + permission_grants + confirmation_requests + artifacts）。
2. ToolRegistry 与首批 5 个只读工具。
3. Executor 绑定节点 + ToolRun 证据链；工作台"执行"接真实执行。
4. 聊天直调（只读）走同一包装器。

### Segment B：权限与确认

5. PermissionGuard + grant 生命周期。
6. ConfirmationRequest + 聊天确认卡（SSE 事件 + 前端卡片 + API）。
7. `workspace.write_file`（显式确认 + 写 Artifact 版本）。

### Segment C：Artifact 与恢复

8. Artifact 域（版本/回滚/软删/purge/预览 + ArtifactViewer）。
9. RecoveryCheckpoint + 恢复面板重试/回滚接线。
10. 收口门禁与文档更新，输出 `docs/reports/cyr3-closure-acceptance.md`。

## 9. 验收记录

- 三段各自独立验收；收口时更新 README、路线图与 CYR.2 施工计划（CYR.3 条目勾选），并输出验收报告。
