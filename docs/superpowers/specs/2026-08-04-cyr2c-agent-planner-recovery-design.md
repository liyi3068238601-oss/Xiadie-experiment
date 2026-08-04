# CYR.2C 单 Agent Planner 与恢复协议设计

> 状态：设计已批准（2026-08-04），书面 spec 待用户复核
> 决策日期：2026-08-04
> 适用范围：聊天驱动的候选计划生成、任务页重新生成计划、来源引用与失效、节点锁定、恢复协议与恢复面板骨架
> 前置基线：CYR.2B 收口（main `f9bb3f0`，merge `e100182`）；Schema 87
> 后续边界：真实工具执行与恢复逻辑属于 CYR.3；CYR.2D 做取消竞态、崩溃、打包态与全链路验收

## 1. 批次定义

一个批次、一份 spec、两段实施：

- 第一段（Segment 1）：Planner 生成与程序校验、聊天紧凑计划卡、任务页重新生成计划、来源引用与失效、节点锁定语义。
- 第二段（Segment 2）：恢复协议数据结构与恢复面板骨架。

## 2. 目标

1. 用户从聊天目标直接获得"先可见、可修改、可批准"的候选计划；完整编辑仍发生在任务工作台。
2. 模型输出只是提案：程序校验通过前不落库，用户编辑 + 批准是唯一晋级闸门。
3. 用户修改优先：编辑即锁定 + 显式锁定，重规划不得覆盖锁定节点。
4. 节点引用现有真实来源，来源失效时 fail closed，不把失效证据伪装成有效。
5. 冻结三类恢复语义协议，恢复面板基于现有 ToolRun 证据提供"最后证据、风险、可继续/重试/重规划"。

## 3. 非目标

- 不做工具执行、ToolRegistry、PermissionGuard、ConfirmationRequest 或正式 Artifact（CYR.3）。
- 不做 CDS Shadow/Advisory/Active 自治晋级；计划提案由用户批准直接晋级。
- 不做第二个对话角色、Worker Agent 或后台执行。
- 不保存完整提示词、记忆正文、文件正文或 Provider 隐藏推理。
- 不引入外部编排运行时或第二套状态数据库。
- 不实现 conversation 来源的持久失效检测（见 7.3 边界）。

## 4. 架构

```text
聊天 SSE（plan_proposal 事件） / 任务页"重新生成计划"
  → task_planner（ModelRouter 结构化输出 + 模型指纹）
  → 程序校验（复用 task_run_contract 内核：DAG、上限、引用完整性、锁定保持）
  → 候选计划仅存在于会话内，不落库
  → 用户确认后经既有 PUT /plan 原子写入（服务端再次校验）→ draft
  → 用户编辑/锁定/批准 → ready/running（CYR.3 接入执行器）
```

Planner 是轻量提案路径：不经过 CDS Shadow/Advisory 状态机，不新增 plan 提案表。候选计划是瞬态数据，关闭聊天即放弃；一旦进入工作台编辑器并保存，才成为 TaskRun 计划的一部分。

## 5. 数据模型与合同

### 5.1 TaskPlannerProposal（瞬态，不落库）

```text
goal_summary: str（≤200 字）
nodes[]:
  client_id: str（计划内稳定 ID）
  title: str（≤60 字）
  acceptance_criteria: str（≤300 字）
  depends_on: [client_id]（写入前验证存在且无环）
  input_refs: [{source_kind, source_id}]（见 7.1）
  output_summary: str（≤300 字）
  recovery_class: side_effect_free | idempotent | side_effectful
approval_required: bool
```

所有字段长度沿用 CYR.2B 既有上限；程序校验失败时给一次带错误摘要的自动修复重试，仍失败则 fail closed 并返回可读原因，不落库。

### 5.2 task_nodes 扩展

- `user_locked: bool`：锁定标记。
- `locked_reason: 'edit' | 'explicit' | null`：`edit` 表示编辑自动锁定，`explicit` 表示用户显式锁定。
- `recovery_class: 'side_effect_free' | 'idempotent' | 'side_effectful' | null`：节点恢复语义；CYR.3 工具节点使用。

### 5.3 task_node_source_links（新表）

- `node_id`、`source_kind`、`source_id`、`summary`（有界摘要）、`status`（`active`/`invalidated`）、`invalidated_at`、`invalidated_reason`。
- `source_kind` 固定集：`memory_fragment` / `memory_episode` / `memory_saga` / `memory_entity` / `knowledge_source` / `conversation`。
- 计划提交（PUT /plan）时由领域层从 `input_refs` 解析并写入；来源不存在或已失效时提交被拒。

## 6. API

| 方法与路径 | 作用 |
|---|---|
| 聊天 SSE 事件 `plan_proposal` | 流式回复尾部携带完整有界提案（goal_summary、nodes[]、approval_required、`run_id: null`）；前端只渲染紧凑卡，不展开全部字段 |
| `POST /api/task-runs/from-proposal` | 把提案落为 TaskRun draft：服务端创建 Task（title=goal_summary 截断）+ TaskRun + 原子写计划，返回 `run_id`；前端跳转编辑器 |
| `POST /api/task-runs/{run_id}/planner-proposal` | 任务页"重新生成计划"：以 goal_summary + 当前计划结构为上下文生成候选（程序校验），返回候选不落库；用户确认后走既有 replan + `PUT /plan` + `expected_revision` |

- 触发规则：planner 只在聊天识别到建立/修改任务意图时调用（显式指令或意图固定集命中），不做每次回复的隐式规划。
- 计划写入仍然只有 `PUT /plan` 一个入口，服务端是 DAG、上限、引用和锁定保持的唯一裁决者；planner 生成与保存是两件事。
- 不新增 404 语义；参数错误 422，计划/状态/证据冲突沿用统一 409 `{code,message,retry,current}`。
- 事件与响应只包含计划的有界字段，不包含记忆正文、文件正文或隐藏推理。

## 7. 来源引用与失效

### 7.1 首批来源

- `memory_fragment` / `memory_episode` / `memory_saga` / `memory_entity`：引用 MEM 表主键。
- `knowledge_source`：引用 KIG SourceRef。
- `conversation`：引用对话消息 ID。

### 7.2 失效行为

- knowledge_source 删除/失效、memory 删除/归档时，通过既有来源删除路径挂失效通知（观察器模式），把相关 `task_node_source_links` 置为 `invalidated` 并记录原因。
- 含失效引用的 TaskRun：`start` 被拒、节点不能进入 `ready`，reason code `source_invalidated`；用户移除引用或重规划后可恢复。

### 7.3 边界

- conversation 引用只记录引用与摘要，不做持久失效检测；待 KIG SourceRef 统一覆盖 conversation 后再接入。此边界避免把历史清理机制扩大进本批。

## 8. 节点锁定语义

- 编辑即锁定：用户修改节点的标题、验收条件、依赖或输入引用后，`user_locked=true`、`locked_reason='edit'`。
- 显式锁定/解锁按钮：设置 `user_locked` 与 `locked_reason='explicit'`；解锁清空两者。
- 重规划约束：锁定节点的 `client_id`、标题、验收条件、`depends_on`、`input_refs` 逐字保留；候选计划中任一字段不一致则校验失败（reason `lock_violation`）。
- 锁定节点的依赖节点必须存在于候选计划中（保留或重新生成均可），否则校验失败（reason `locked_dependency_removed`）。
- planner 把锁定节点作为输入约束，程序校验是最终裁决；两条路径共用一个 `user_locked` 标记。

## 9. 恢复协议与恢复面板（Segment 2）

### 9.1 三类恢复语义

| recovery_class | 含义 | 允许动作 |
|---|---|---|
| `side_effect_free` | 中断无副作用，可安全重放 | continue、retry（有界）、replan |
| `idempotent` | 重试安全，但需输入不变 | continue、retry（上限 3 次）、replan |
| `side_effectful` | 中断后不可盲目重放 | continue（需确认）、replan；无证据 fail closed |

未知 recovery_class 或无 ToolRun 终态证据时 fail closed：只允许 replan，不允许继续或重试。

### 9.2 恢复面板

- 读取该 run 最近的 ToolRun 证据（`tool_runs`：阶段、状态、脱敏错误、`trace_id`），展示"最后证据、风险等级、可继续/重试/重规划"。
- 风险等级色带复用既有 UI 规范（危险/警告/成功色）；无工具执行时显示空态说明。
- 面板是业务证据视图，不替代 `task.scheduler` 诊断日志，不混入模型心理活动。

## 10. 隐私

- planner 调用只发送目标、任务上下文和（重规划时）当前计划结构；不发送记忆正文、文件正文或隐藏推理。
- 计划只保存引用与有界摘要；提案不落库，聊天关闭即失效。
- 模型指纹随生成事件记录；未认证模型仍可使用，不作为运行许可证（沿用路线图固定集原则）。

## 11. 测试与验收

### 后端

- planner 程序校验固定集：DAG 环、50 节点上限、引用完整性、锁定保持、修复重试与 fail closed。
- `task_node_source_links`：来源删除/归档置失效；含失效引用的 run 不能 start、节点不能 ready。
- 锁定：编辑即锁定、显式锁定、解锁、`lock_violation`、`locked_dependency_removed`。
- 恢复矩阵：三类语义 × 允许动作穷举；无证据 fail closed。

### 前端

- 聊天计划卡渲染、确认创建、取消；任务页重新生成入口。
- 锁定 UI：编辑自动锁定提示、显式锁定/解锁、重规划冲突提示。
- 恢复面板：最后证据、风险、可继续/重试/重规划与空态。

### 门禁

- 后端全量 pytest、前端 node --test、Vite 生产构建、Python compileall、`git diff --check` 全部通过；沿用现有非阻塞提示白名单。

## 12. UI 设计交付

- 现有 UI 设计资产（`xiadie-ui-spec.md`、`xiadie-unified-ui-prototype`）覆盖聊天、记忆、知识、设置与任务列表，**未覆盖任务工作台**（多节点计划编辑器、运行详情、恢复面板）与聊天紧凑计划卡。
- CYR.2C 新增界面：聊天紧凑计划卡、编辑器中的锁定与来源引用呈现、恢复面板。
- 是否在 Segment 1 实施前补一轮这三块界面的可视化设计（UI 设计规格 + HTML 原型，遵循 unified prototype 的组件规范），由用户决定；默认按"UI 设计与 Segment 1 并行、规格先于实现落地"推进。

## 13. 实施分段

### Segment 1：Planner 与锁定

1. `task_planner` 模块（ModelRouter 结构化输出 + 程序校验 + 修复重试）。
2. 聊天 SSE `plan_proposal` 事件与前端紧凑计划卡；`POST /api/task-runs/from-proposal` 落 draft。
3. 任务页 `POST /api/task-runs/{run_id}/planner-proposal` 重新生成入口。
4. `task_node_source_links` 表、写入与失效通知；`start`/`ready` 阻塞规则。
5. `user_locked` / `locked_reason` 字段、编辑即锁定、显式锁定/解锁、重规划保持校验。

### Segment 2：恢复协议与面板

6. `recovery_class` 字段与三类语义矩阵固定集。
7. 恢复面板骨架（ToolRun 证据 + 风险 + 继续/重试/重规划 + 空态）。

## 14. 验收记录

- Segment 1/2 各自独立验收：后端定向 + 前端源契约测试 + 全量门禁。
- 合入后更新 README、长期路线图与 CYR.2 施工计划，勾选 CYR.2C 条目。
