# CYR.2 TaskRun 执行工作台施工计划

> 状态：CYR.2A 与 CYR.2B 合同闭合批次已完成工程验证；多节点编辑、TaskRun SSE 与执行历史仍在 CYR.2B 后续
> 最后更新：2026-08-02
> 当前批次设计：[CYR.2B 合同闭合批次设计](superpowers/specs/2026-08-02-cyr2b-contract-closure-design.md)
> 适用范围：Task、TaskRun、TaskNode、恢复、任务台与执行审计
> 前置基线：CYR.1/CYR.1S、LOG.1～LOG.5
> 后续边界：ToolRegistry、PermissionGrant 与正式 Artifact 属于 CYR.3

## 1. 目标

CYR.2 要把目前的待办列表变成可持续推进、可暂停、可恢复且不会伪造结果的执行工作台。它不增加第二个对话角色，也不把“规划”变成一层新的 Persona。用户仍然只和遐蝶交互；TaskRun 是遐蝶完成较长任务时使用的产品状态与证据结构。

完成后的基本关系：

```text
Task（用户目标）
  └─ TaskRun（一次具体执行，可重新发起）
       ├─ TaskNode（有依赖、有验收条件的步骤）
       ├─ TaskRunEvent（权威状态证据）
       ├─ ToolRun（真实工具执行，CYR.3 接入）
       └─ ArtifactRef（产物引用，正式 Artifact 域由 CYR.3 提供）
```

核心承诺：

- 用户可以在真正执行前看到并修改计划。
- 开始、暂停、继续、取消和重新规划都有确定状态转换。
- 任务完成必须来自节点完成证据，失败必须保留错误状态。
- 应用重启不会秘密续跑；中断中的任务进入 `recovery_required`。
- 每个 TaskRun 都有 `trace_id`，可以与诊断日志和 ToolRun 对齐。
- TaskRun 只保存有界摘要、状态与引用，不保存完整提示词、文件正文或隐藏推理。

## 2. 非目标与阶段边界

CYR.2 不负责：

- 任意 Shell、任意文件系统写入、桌面控制或外部消息发送。
- 工具发现、Manifest、风险分级、权限授权与确认弹窗；这些属于 CYR.3。
- 正式 Artifact 存储、预览、版本和删除；CYR.2 只允许保存 `artifact_id` 引用。
- Provider 隐藏 chain-of-thought、reasoning token 或系统内部推理草稿。
- 应用退出后的后台执行，或没有用户可见停止入口的常驻 worker。
- 多 Persona、多对话主控或 Worker Agent；受控 Worker 属于更后期路线。

## 3. 领域模型

### 3.1 Task

`Task` 表示用户目标，继续兼容现有 `todo / doing / done / archived` 待办语义。一个 Task 可以有多次 TaskRun；失败或取消一次执行不等于删除目标。

迁移期继续允许旧客户端直接修改 Task 状态，但新执行链只通过 TaskRun 驱动 `doing` 与 `done`：TaskRun 开始时标为 `doing`，有完整节点证据完成时标为 `done`。

### 3.2 TaskRun

TaskRun 的正式状态：

| 状态 | 含义 | 允许的主要后继 |
|---|---|---|
| `draft` | 尚未形成可执行计划 | `planning`、`ready`、`awaiting_approval`、`cancelled` |
| `planning` | 正在建立或替换计划 | `ready`、`awaiting_approval`、`failed`、`cancelled` |
| `awaiting_approval` | 计划包含需确认内容 | `ready`、`planning`、`cancelled` |
| `ready` | 计划有效但尚未执行 | `running`、`planning`、`cancelled` |
| `running` | 可执行节点正在推进 | `paused`、`planning`、`completed`、`failed`、`cancelled`、`recovery_required` |
| `paused` | 用户主动暂停 | `running`、`planning`、`cancelled` |
| `recovery_required` | 进程中断，需要显式处理 | `running`、`paused`、`planning`、`failed`、`cancelled` |
| `failed` | 有明确失败证据 | `planning`、`ready`、`cancelled` |
| `completed` | 所有节点均有完成或跳过证据 | 终态 |
| `cancelled` | 用户或治理层取消 | 终态，重复取消幂等 |

`revision` 用于状态修订，`plan_version` 只在整份计划被替换时增加。`goal_summary`、`waiting_reason`、`next_action` 与错误消息都有长度上限并经过日志脱敏工具处理。

### 3.3 TaskNode

节点状态为 `pending / ready / running / blocked / succeeded / failed / skipped / cancelled`。

- `depends_on` 使用同一计划内稳定的 `client_id`，写入前验证引用存在且整个图无环。
- 只有全部依赖已 `succeeded` 或 `skipped` 的节点才能进入 `ready`。
- 只有 `ready` 节点能开始；只有 `running` 节点能成功或失败。
- 节点失败会让 TaskRun 显式进入 `failed`，不得自动改写成成功。
- 所有节点成功或跳过后，TaskRun 才自动进入 `completed`。
- 每份计划最多 50 个节点，标题、验收条件、输出摘要与错误均有界。

### 3.4 Event、ToolRun 与 ArtifactRef

`task_run_events` 是状态变化的权威业务证据；诊断日志只是定位问题的运行视图。事件不保存正文，只保存 ID、前后状态、修订号、reason code 与有界元数据。

Schema 85 已有的 `tool_runs.task_run_id` 在 CYR.2 获得真实父对象，TaskRun 详情会展示关联 ToolRun 的阶段、状态和脱敏错误。CYR.2 的 `task_run_artifact_links` 只保存外部 Artifact ID；没有正式 Artifact 时不能把引用伪装成已经生成的文件。

## 4. API 合同

| 方法与路径 | 作用 |
|---|---|
| `GET /api/tasks/{task_id}/runs` | 列出该目标的历次执行 |
| `POST /api/tasks/{task_id}/runs` | 创建幂等的 draft TaskRun |
| `GET /api/task-runs/{run_id}` | 读取节点、事件、ToolRun 与 ArtifactRef |
| `PUT /api/task-runs/{run_id}/plan` | 校验并原子替换计划 |
| `POST .../approve` | 批准待确认计划 |
| `POST .../start` | 开始 ready 执行 |
| `POST .../pause` | 暂停 running 执行；重复暂停幂等 |
| `POST .../resume` | 从 paused/recovery_required 显式继续 |
| `POST .../cancel` | 取消并终止未完成节点；重复取消幂等 |
| `POST .../replan` | 回到 planning 并停止当前 running 节点 |
| `POST .../nodes/{node_id}/action` | 受状态机约束地推进节点；未来主要由执行器调用 |
| `POST .../artifacts` | 关联未来 Artifact ID，不创建文件 |

API 使用稳定的机器错误码，例如 `task_plan_cycle`、`task_run_transition_invalid`、`task_node_transition_invalid`。不存在返回 404；缺少 revision 或格式错误返回 422；计划、状态和证据冲突返回统一 409：`detail: {code,message,retry,current}`。所有修改接口必须携带 `expected_revision`，API 请求模型和领域公共入口都不能省略；客户端只接收同 Run 且不旧于本地的 `current`，否则重新 GET，并且不自动重放 mutation。

## 5. 恢复、取消与并发

### 5.1 启动恢复

应用启动自检将所有遗留 `running` 改为 `recovery_required`，同时把当时的 running 节点改为 `blocked`，写入 `process_restarted` 事件与 WARNING 日志。系统不会自行调用 `resume`，也不会在应用关闭后继续推进。

继续之前，执行器必须重新检查：

- 上次 ToolRun 是否已形成终态证据。
- 输入来源与权限是否仍然有效。
- 目标文件或外部状态是否已经变化。
- 当前节点能否安全重试，或应重新规划。

CYR.2A 只实现“停止并等待显式恢复”；细粒度 checkpoint 和副作用重试策略与 CYR.3 工具治理一起完成。

### 5.2 幂等

- 创建 TaskRun 可使用 `(task_id, idempotency_key)` 唯一键。
- 重复取消与重复暂停返回当前状态，不重复写事件。
- 节点只能沿合法状态转换，重复成功不会制造第二份完成证据。
- ArtifactRef 在同一 TaskRun 内按 `artifact_id` 唯一。

### 5.3 并发计划

CYR.2B 合同闭合已经以 SQLite `BEGIN IMMEDIATE` 和必填 `expected_revision` 形成不可绕过的 compare-and-swap。纯合同内核穷举 Run/Node 命令矩阵，并固定“精确重放 → revision 冲突 → 状态/参数冲突 → 应用”的顺序；精确重放和所有拒绝路径均零写入。`start`/`resume`、Task 投影、节点刷新和事件同事务提交，消除了可见半状态。

## 6. 诊断与隐私

模块名固定为 `task.scheduler`。关键日志包括：

- `task_run_created`
- `task_plan_replaced`
- `task_run_started / paused / resumed / cancelled / failed / completed`
- `task_replan_requested`
- `task_node_running / succeeded / failed / skipped`
- `task_run_recovery_required`

日志必须带 `trace_id` 与 `task_run_id`，必要时带 `session_id`、节点 ID、前后状态、进度和错误码。禁止记录完整用户输入、完整计划正文、文件正文、密钥或隐藏推理。任务事件表同样保持 body-free。

## 7. 前端任务台

CYR.2A 在现有 Tasks 页面增加了最小执行卡片：

- 从 Task 建立默认单节点执行计划。
- 显示 TaskRun 状态、进度、等待原因、错误与下一动作。
- 支持批准、开始、暂停、继续、重新规划和取消。
- 展示节点，并提供人工推进按钮用于验证执行骨架。
- 重启中断时明确显示“需要恢复”，不会伪装为仍在执行。

默认单节点计划只是迁移期入口，不是最终 Planner。CYR.2B 要增加结构化计划编辑器；CYR.2C 再接入由 Agent 生成、程序验证、用户可修改的规划流。正式工具执行接入后，人工节点按钮改成诊断/开发入口，普通用户不需要手工报告工具成功。

## 8. 开源参考与采用边界

CYR.2B 参考以下开源项目的协议和交互思想，但不直接复制代码，也不把它们引入为运行时依赖：

| 项目 | 许可证 | 借鉴内容 | 当前不直接采用的原因 |
|---|---|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | checkpoint、稳定 thread/run ID、interrupt、节点边界恢复、pending writes、幂等副作用 | 遐蝶已经有 SQLite、TaskRun、ToolRun、Memory 与 Context 所有权；引入会形成第二套状态与存储抽象 |
| [Temporal Python SDK](https://github.com/temporalio/sdk-python) / [Temporal](https://github.com/temporalio/temporal) | MIT | 事件历史与 mutable state 一致性、Signal/Update/Query 分离、Update validator、取消与 heartbeat、恢复重放测试 | 需要额外服务与 worker，部署重量不适合当前本地桌面实验版 |
| [Prefect](https://github.com/PrefectHQ/prefect) | Apache-2.0 | Flow/Task 状态词汇、带类型的人机输入、暂停/恢复状态、运行历史 UI | 面向数据工作流和部署编排，直接采用会扩大产品与依赖面 |
| [LangGraph Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) | MIT | interrupt/approval 在聊天界面的展示、执行状态与消息流并置 | 当前主窗口已有稳定 React 信息架构，只参考交互，不替换前端 |
| [Temporal UI](https://github.com/temporalio/ui) | MIT | 运行摘要、事件历史、失败详情、关联 ID 与重试入口 | 面向 Temporal 服务端对象，不能直接映射遐蝶的 Task/Memory/Tool 权限语义 |
| [Xiaoda Agent](https://github.com/long-safe-accont-4567-uvwxyz-9876/xiaoda-agent) | MIT | skipped 依赖防死锁测试、并行超时与部分结果、审批作用域、fail-closed、安全拒绝审计、Self-Wake 和线性工作流 UI | 多 Agent 黑板、提示词工作流和通用自动恢复与 Xiadie 单主控 Agent、TaskRun 权威状态及副作用恢复边界不兼容；只读评估基线为 `35e42de` |

采用决策：

- 借 LangGraph：每次恢复都以稳定 `task_run_id` 和 checkpoint 边界为准；中断前的副作用必须幂等。
- 借 Temporal：命令先验证，再把事件与当前状态同事务提交；读查询不改变状态；取消是明确状态而不是成功的别名。
- 借 Prefect：等待用户时显示需要什么输入、为什么等待、从哪里继续，而不是只显示“暂停”。
- 借两类 UI：任务摘要与详细事件分层，普通用户看进度和下一动作，诊断页看 revision、trace、事件和安全错误。
- 借 Xiaoda Agent：为 `skipped` 依赖解除、超时不挂死和拒绝路径审计建立固定集；记录“审批作用域必须绑定具体对象、高风险审批故障 fail closed”为 CYR.3 硬约束，但不把计划批准解释为工具许可。
- 不采用 Xiaoda Agent 的多 Agent 共享黑板、提示词文件工作流或按错误字符串自动升级恢复；它们会形成第二事实源、绕开 TaskRun 状态证据，或在副作用未知时不安全重试。
- 不引入外部 orchestrator、云服务或第二套 checkpoint 数据库；如果未来本地任务规模、并行 worker 或跨设备执行证明现有内核不足，再以 ADR 重新评估 Temporal/LangGraph 适配器。
- 任何具体代码移植都必须单独做许可证、NOTICE 与来源审计；当前只采用通用架构思想。

## 9. 分阶段施工

### CYR.2A：持久执行骨架（本轮已完成）

- [x] Schema 86：TaskRun、TaskNode、Event、ArtifactRef。
- [x] 有向无环计划校验和 50 节点硬门。
- [x] 开始、暂停、继续、取消、重新规划、节点推进状态机。
- [x] 节点证据与 TaskRun 终态同事务提交，驱动进度、失败和 Task 完成。
- [x] 启动时进入 `recovery_required`，不秘密续跑。
- [x] `trace_id`、ToolRun 关联和 `task.scheduler` 日志。
- [x] 最小任务台状态与操作入口。
- [x] 模块固定集与前端生产构建。

### CYR.2B：计划编辑与并发合同（施工中）

- [x] `expected_revision` 可选乐观并发、409 当前快照与前端刷新恢复。
- [x] 已实现冲突无写入和暂停/取消幂等首批固定集。
- [x] API/领域层强制 CAS，纯合同内核覆盖完整 Run/Node 非法转换矩阵、精确语义幂等与统一 409。
- [x] Schema 87 保存当前计划批准资格与节点跳过证据；批准只绑定当前 `plan_version`，不等于文件、网络或工具权限。
- [x] `start`/`resume`、节点刷新、Task 投影和事件原子提交；精确重放与冲突固定集验证五类业务表零写入。
- [ ] 结构化多节点计划编辑器、依赖可视化和验收条件编辑。
- [ ] TaskRun 业务事件 SSE 状态更新。
- [ ] 列出历史执行、失败原因与再次执行入口。

### CYR.2C：Agent Planner 与恢复策略

- [ ] 单 Agent 从当前请求形成候选计划；程序校验后才落库。
- [ ] 用户修改优先，模型不得覆盖用户锁定节点。
- [ ] 节点输入/输出使用引用和有界摘要，来源失效 fail closed。
- [ ] 为无副作用、幂等和有副作用工具分别定义恢复策略。
- [ ] 恢复面板展示最后证据、风险、可继续/重试/重规划选项。

### CYR.2D：工作台验收

- [ ] 任务详情、实时状态、等待原因、下一动作和失败证据完整可读。
- [ ] 取消竞态、进程崩溃、数据库忙、重复请求和陈旧 revision 故障注入。
- [ ] 任务事件与诊断日志、ToolRun、未来 Artifact 全链路关联。
- [ ] Windows 启动器与打包态恢复测试。
- [ ] 多模型计划质量固定集；模型未验证仍可使用，不作为运行许可证。

## 10. 验收门

CYR.2 全阶段退出门：

- 状态矩阵没有绕过路径，终态不可被普通动作复活。
- 取消幂等；取消后未完成节点不再执行。
- 崩溃重启后不自动续跑，用户能看到中断原因和可选动作。
- 失败节点不会使 TaskRun 或 Task 显示完成。
- 计划依赖无环、引用完整，陈旧客户端修改能被识别。
- ToolRun 结果只能来自真实执行包装器，模型文字不能直接写成功状态。
- TaskRun、节点、事件、ToolRun 和 ArtifactRef 可由 ID 与 trace 追溯。
- 日志与支持包固定集不泄露正文、提示词、密钥或隐藏推理。
- 后端全量测试、前端测试、生产构建和启动器 smoke 全部通过。

## 11. 后续衔接

CYR.2B 合同闭合批次已在 `agent/cyr2b-contract-closure` 完成实现与本地门禁：后端全量 `2752 passed`，TaskRun 合同/Schema/领域/HTTP 定向 `234 passed`，前端 `85 passed`，Electron 生命周期 `4 passed`，Python `compileall`、Vite 生产构建与 `git diff --check` 通过。现存提示只有 Starlette/httpx 弃用、pytest cache 权限和 Live2D Classic Vite 提示。

下一步依次推进多节点计划编辑、TaskRun SSE、执行历史与再次执行，再进入 CYR.2C Planner 与恢复策略。CYR.2 全阶段完成后才进入 CYR.3：建立 ToolRegistry、PermissionGuard、ConfirmationRequest 和正式 Artifact。ToolRun 已有权威状态机，CYR.3 的工具适配器必须复用它，并把 `task_run_id` 与当前节点绑定；任何插件或工具不得直接把节点写成成功。
## CYR.2B-UX completion note (2026-08-04)

CYR.2B-UX is complete: the workbench now provides structured multi-node plan editing, dependency and completion-criteria editing, plan-approval boundary copy, node skip evidence, run history, and re-run. TaskRun business events have a body-free cursor catch-up endpoint and an authenticated SSE stream with explicit gap recovery. Agent Planner remains CYR.2C and tools/permissions remain CYR.3. Detailed contract: [CYR.2B-UX TaskRun workbench design](superpowers/specs/2026-08-04-cyr2b-ux-design.md).
