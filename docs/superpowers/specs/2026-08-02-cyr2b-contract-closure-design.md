# CYR.2B 合同闭合批次设计

> 状态：已实现、通过本地工程门禁并随 CYR.2B UX 工作台于 2026-08-04 合入 `main` 收口
> 决策日期：2026-08-02
> 适用范围：TaskRun 并发合同、状态矩阵、幂等、计划批准边界、节点跳过证据
> 前置基线：CYR.2A `e477bff`；CYR.2B revision 并发合同 `abdb463` / PR #4
> 后续批次：多节点计划编辑器、TaskRun SSE、执行历史与再次执行、CYR.2C Planner

## 1. 当前施工痕迹

> 以下列表保留设计冻结时的基线记录；实际实施结果见 1.1。

截至本设计冻结时，仓库的实际落点为：

- `main` 位于 `3a6642a`，已合入 RETIRE.0～RETIRE.3、LOG.1～LOG.5、CYR.1/CYR.1S。
- CYR.2A 位于 `agent/cyr2-taskrun-foundation` 的 `e477bff`，完成 Schema 86、TaskRun/TaskNode/Event/ArtifactRef、DAG 校验、执行状态机、启动恢复和最小任务台。
- CYR.2B 首批位于 `agent/cyr2b-concurrency-contract` 的 `abdb463`，完成可选 `expected_revision`、陈旧 revision 的 409 当前快照、前端冲突刷新和暂停/取消幂等固定集。
- GitHub PR #4 当前从 `agent/cyr2b-concurrency-contract` 指向 `agent/cyr2-taskrun-foundation`；两层尚未进入 `main`。
- 2026-08-02 本机复核结果：后端全量 `2529 passed`，TaskRun 定向 `11 passed`，前端 `83 passed`，Electron 生命周期合同 `4 passed`，Vite 生产构建、Python `compileall` 与 `git diff --check` 通过。
- 已知非阻塞提示仍为 Starlette/httpx 弃用提醒、pytest 缓存目录权限提醒和 Live2D Classic 脚本的既有 Vite 打包提示。
- 设计冻结后补充只读评估 [Xiaoda Agent](https://github.com/long-safe-accont-4567-uvwxyz-9876/xiaoda-agent)（用户提供的 `nahida-agent` 地址当前重定向到该仓库；MIT；评估基线 `35e42de`）。本批只吸收其测试和边界思想，不复制代码、不引入依赖。

下一批实施前先闭合合入链：CYR.2A 进入 `main`，再让 PR #4 基于并进入更新后的 `main`；之后从新 `main` 建立独立合同闭合分支。改变 PR 目标与实际合并仍属于外部操作，实施时单独征得用户确认。

### 1.1 实际实施记录

- 既定合入链已通过 PR #5 进入 `main`；本批从 `main@f3437a30231015274e64be3c6b22c1ef8c0b00a0` 建立 `agent/cyr2b-contract-closure`。
- 实现与设计一致：新增纯 `task_run_contract`，升级 Schema 87，API 与领域公共入口强制 CAS，统一 409，闭合 `start`/`resume` 事务，并完成批准、skip 和 ArtifactRef 证据规则。
- 前端仅做合同适配：接收同 Run 且不旧的冲突快照，无效快照 GET 回退，不自动重放 mutation，并显示计划批准权限边界；没有增加 skip 控件、多节点编辑器、轮询或 SSE。
- 没有引入外部编排器、第二数据库、Xiaoda Agent 代码或新运行时依赖，也没有扩大 CYR.3 权限范围。
- 2026-08-02 本地最终门禁：后端全量 `2752 passed`；合同/Schema 87/领域/HTTP 定向 `234 passed`；前端 `85 passed`；Electron 生命周期 `4 passed`；Vite build、Python `compileall` 与 `git diff --check` 通过。
- 首轮全量后端曾因 CDS.9 已提交报告仍记 Schema 86 而出现 `1 failed, 2747 passed`；重新生成 CDS.9/CDS.10 schema 报告后，受影响固定集与全量后端均通过。提交前复核又补齐不存在对象优先返回 404、未知节点动作 422、无关证据字段清空，以及“不同命令竞争产生一次应用和一次 revision 409”的固定集；现存非阻塞提示仍为 Starlette/httpx 弃用、pytest cache 权限及 Live2D Classic Vite 提示。
- 实现提交为 `dafa730`（`feat(taskrun): close CYR.2B mutation contracts`）；本记录随后以独立文档提交补记该 SHA。
- UX 工作台提交 `519f574`（`feat(taskrun): complete CYR.2B UX workbench`）补齐多节点计划编辑、执行历史/再次执行与 body-free 事件 SSE；CYR.2B 于 2026-08-04 合入 `main` 收口，验收记录见 `docs/reports/cyr2b-closure-acceptance.md`。

## 2. 批次目标与非目标

### 2.1 目标

本批只完成 CYR.2B 的领域与 HTTP 合同闭合：

1. 所有外部 TaskRun 修改命令必须提供 `expected_revision`。
2. API 与 TaskRun 领域服务两层都不能绕过 CAS。
3. Run/Node 的每个状态与命令组合都有唯一、可测试的结论。
4. 精确重复命令可安全重放；相似但不同的命令不得伪装成幂等。
5. 所有领域冲突使用统一结构化 409 响应且零写入。
6. `awaiting_approval` 只表示批准当前计划，不授予工具、文件、网络或外部操作权限。
7. 冻结高风险执行 fail closed 的跨阶段约束；审批基础设施故障不能把计划批准升级成执行许可。
8. 节点跳过成为带稳定原因的显式证据。
9. 修复 Run 进入 `running` 与节点刷新之间的事务缝隙。

### 2.2 非目标

本批明确不实现：

- 结构化多节点计划编辑器或依赖可视化；
- TaskRun SSE、轮询或实时状态 UI；
- 执行历史详情、再次执行入口；
- Agent Planner、用户锁定节点和来源引用；
- ToolRegistry、PermissionGuard、ConfirmationRequest 或正式 Artifact；
- 事件溯源重构、外部编排器或第二套状态数据库。

现有前端只做新合同所需的最小适配，不扩展产品功能面。

## 3. 架构

本批采用四层边界：

```text
FastAPI 请求合同
  → TaskRun 领域事务服务
      ├─ 纯合同内核（无 I/O）
      └─ SQLite Schema 86 → 87（唯一持久化）
```

### 3.1 纯合同内核

新增无数据库和框架依赖的 `task_run_contract` 模块。它只回答：

- 当前 Run/Node 状态能否接受命令；
- 请求属于执行、精确语义幂等还是拒绝；
- revision 是否匹配；
- 拒绝时使用的稳定 `code`、静态 `message` 与 `retry`；
- 成功命令的目标状态和领域应用指令。

合同内核不读取 SQLite、不写事件、不记录日志、不认识 HTTP。未来 Planner 和工具执行器必须复用这一合同，不能建立旁路状态机。

### 3.2 领域事务服务

`task_runs.py` 继续是 TaskRun 聚合的唯一写入者，负责：

- 开启 `BEGIN IMMEDIATE`；
- 读取权威 Run、Node、计划或 ArtifactRef 快照；
- 对输入做与持久化一致的规范化；
- 调用合同内核；
- 在同一事务提交 Run、Node、Task 投影和业务事件；
- 提交后读取完整聚合并记录无正文诊断日志。

`start`/`resume` 与 `ready/blocked` 节点刷新必须进入同一事务。任何中间异常整笔回滚，客户端不能看到 Run 已为 `running`、节点却尚未刷新的半完成状态。

### 3.3 API 与系统内部路径

- 创建 TaskRun 不需要 revision。
- 替换计划、Run action、Node action 和 ArtifactRef 关联都必须提供 `expected_revision`。
- FastAPI 请求模型将字段设为必填；缺失或格式错误返回标准 422。
- 领域层公共修改函数同样要求 revision，防止 Python 内部调用绕过。
- 启动恢复、节点证据触发 Run 自动完成等系统内部变化走明确命名的私有/系统事务路径，不伪造客户端 revision。
- HTTP 错误序列化留在 API 适配层；领域内核只返回类型化决策或领域冲突。

## 4. 状态与命令合同

### 4.1 Run 命令

| 命令 | 可执行状态 | 精确语义幂等 | 主要拒绝条件 |
|---|---|---|---|
| `replace_plan` | `draft/planning/paused/recovery_required/failed` | 当前仍为 `ready/awaiting_approval`，规范化计划与批准要求完全相同，且尚未开始执行 | 执行中、终态、计划内容不同 |
| `approve` | `awaiting_approval` | 当前 `plan_version` 已被明确批准 | 无需批准、计划已换版、终态 |
| `start` | `ready` | 已为 `running` | 未批准、暂停/恢复态、终态 |
| `pause` | `running` | 已为 `paused` | `recovery_required` 已停止，不能伪装成暂停 |
| `resume` | `paused/recovery_required` | 已为 `running` | 草稿、待批准、失败、终态 |
| `replan` | 除终态外的非 `planning` 状态 | 已为 `planning` | `completed/cancelled` |
| `cancel` | 除 `completed/cancelled` 外所有状态 | 已为 `cancelled` | `completed` 不可改写 |
| `link_artifact` | 所有状态 | 相同 `artifact_id/node_id/label` 已存在 | 相同 `artifact_id` 的关联参数不同 |

ArtifactRef 是追加证据，不是执行状态。Run 完成、失败或取消后仍可关联真实晚到产物；该命令只推进 revision、写关联事件，不改变或复活 Run。

### 4.2 Node 命令

- `start`：只允许 `ready → running`；已为 `running` 且目标节点相同可精确幂等。
- `succeed`：只允许 `running → succeeded`；已成功时，仅规范化 `output_summary` 完全相同才幂等。
- `fail`：只允许 `running → failed`；已失败时，仅 `error_code/error_message` 完全相同才幂等。
- `skip`：只允许 `ready/blocked → skipped`；必须提供稳定 `reason_code`，可附有界原因摘要；已跳过时，仅原因完全相同才幂等。
- `pending` 是尚未刷新出的内部中间态，不接受客户端动作。
- 节点终态不能互相改写。
- 精确重放判定先于 Run 必须为 `running` 的检查。因此最后节点已使 Run 自动完成后，响应丢失的相同请求仍可获得幂等 200。
- skipped 解除下游依赖，但事件和投影始终保留 `skipped`，不得转写成成功证据。

### 4.3 幂等顺序

在读取同一事务内的权威事实后，判定顺序固定为：

1. 精确语义重放；
2. revision 冲突；
3. 状态或参数冲突；
4. 应用命令。

精确幂等返回 `200 + 当前完整快照`，revision、业务事件和持久事实均不变化。只有请求表达的完整目标事实已经存在才成立；状态名称相同但计划版本、节点证据或 ArtifactRef 参数不同，仍返回 409。

## 5. Schema 87

Schema 87 只增加无法可靠从当前快照推导的批准资格与节点跳过证据。

### 5.1 `task_runs`

- `requires_approval INTEGER NOT NULL DEFAULT 0`：当前计划是否要求批准；
- `approved_plan_version INTEGER`：明确批准的计划版本；
- `approved_at REAL`：批准时间。

替换计划原子重置批准字段。`start` 的硬门为：当前计划无需批准，或 `approved_plan_version == plan_version`。计划批准不包含任何工具、目录、网络目标、账号、权限范围或风险确认。

### 5.2 `task_nodes`

- `skip_reason_code TEXT`：跳过时必填的稳定机器原因；
- `skip_reason_summary TEXT`：最多 240 字的可读摘要。

非 skipped 节点不得持有跳过原因。事件只需记录稳定 reason code；可读摘要作为有界业务状态保存，不进入普通诊断字段。

### 5.3 迁移

- 新数据库直接创建 Schema 87。
- Schema 86 升级时根据最近一轮 `task_plan_replaced` 与同一 `plan_version` 的 `task_plan_approved` 事件回填批准字段。
- 若现存 Run 为 `awaiting_approval`，迁移后保留等待状态并令 `approved_plan_version = NULL`。
- 若现存 Run 已越过批准门且最近一次替换事件明确 `requires_approval = true`，只有同版本批准事件存在时才回填批准；否则迁移整笔中止并报告稳定迁移错误，不静默改写正在执行或已经终结的历史事实。
- 旧事件没有 `requires_approval` 元数据时，只能根据当前 `awaiting_approval` 状态证明“仍待批准”；不能据此推断其他 Run 曾要求或已经获得批准。
- 不删除、不重建既有 TaskRun、TaskNode、Event 或 ArtifactRef。
- 升级数据库与全新数据库必须通过同一 Schema 固定集。

## 6. 输入规范化与计划相等

文本输入继续使用现有有界裁剪和脱敏规则。依赖必须：

- 只引用同一计划稳定 `client_id`；
- 去重；
- 按目标节点在计划中的位置形成稳定顺序；
- 继续满足完整引用和无环校验。

计划精确相等必须同时匹配：

- 节点数量和顺序；
- 每个节点的 `client_id`、标题、依赖和验收条件；
- `requires_approval`。

任一项不同都不是重放，必须按 revision 和状态合同处理。

## 7. 统一错误合同

所有 TaskRun 领域 409 返回：

```json
{
  "detail": {
    "code": "task_run_revision_conflict",
    "message": "任务已在其他位置更新，请查看最新状态后重试。",
    "retry": "refresh_then_user_retry",
    "current": {}
  }
}
```

### 7.1 字段规则

- `code`：稳定机器错误码；
- `message`：静态、有界、可直接显示的中文文案；
- `retry`：固定机器枚举；
- `current`：Run 存在时，尽量返回与 `GET /api/task-runs/{id}` 同形的完整聚合快照。

`retry` 只允许：

- `refresh_then_user_retry`：接受最新快照后由用户重新触发，客户端不得自动重放；
- `modify_then_retry`：计划、节点证据或 ArtifactRef 参数需要修改；
- `not_retryable`：终态或不可逆边界禁止命令。

### 7.2 稳定错误码

本批至少冻结以下分类；更细的具体码可以增加，但不能让客户端依赖中文消息：

- `task_run_revision_conflict`：revision 陈旧，`refresh_then_user_retry`；
- `task_run_transition_invalid`：Run 状态不接受命令，按是否终态使用 `refresh_then_user_retry` 或 `not_retryable`；
- `task_node_transition_invalid`：Node 状态不接受命令，按是否终态使用 `refresh_then_user_retry` 或 `not_retryable`；
- `task_plan_replace_not_allowed`：当前 Run 不允许替换计划，`not_retryable` 或先显式 replan；
- `task_plan_content_conflict`：精确重放参数与当前计划不同，`modify_then_retry`；
- `task_node_evidence_conflict`：终态节点的输出或原因与重放请求不同，`modify_then_retry`；
- `task_artifact_link_conflict`：同一 Artifact ID 的 node/label 不一致，`modify_then_retry`；
- `task_plan_approval_required`：当前 `plan_version` 未获计划批准，`not_retryable`，客户端应展示批准动作而非自动重试。

纯计划校验错误继续使用既有稳定码（例如 `task_plan_cycle`、未知依赖和节点数量越界），但也必须套用统一结构化 409 外壳并使用 `modify_then_retry`。

### 7.3 HTTP 边界

- 对象不存在保持 404；
- 缺少 revision 或字段格式错误保持 422；
- revision、状态、节点证据和参数冲突统一使用结构化 409；
- 所有 409 路径必须回滚，Run、Node、Task、Event 与 ArtifactRef 零写入；
- `message` 不能作为客户端控制流依据。

## 8. 事件与隐私

- `task_plan_replaced` 记录 `plan_version/node_count/requires_approval`。
- `task_plan_approved` 记录被批准的 `plan_version`，不记录权限或工具语义。
- `task_node_skipped` 记录稳定 `reason_code`，不把可读原因正文写入诊断日志。
- `task_artifact_linked` 记录受限 Artifact ID 与关联节点，不保存文件正文。
- 所有冲突日志保持 body-free，只记录错误码、revision、状态、Run/Node ID 与 trace。
- 不记录完整计划正文、用户输入、文件正文、提示词、密钥或隐藏推理。

## 9. 前端最小适配

- `replaceTaskRunPlan`、Run action 和 Node action 的 TypeScript 签名把 revision 改为必填。
- 统一解析 `{code,message,retry,current}`。
- 仅当 `current.id` 与本地 Run 一致且 `current.revision >= local.revision` 时接收冲突快照；否则重新 GET。
- 409 后显示静态建议，但不得自动重复修改命令。
- 精确幂等 200 按普通成功处理。
- `awaiting_approval` 附明确文案：“这里只批准计划，不会授予文件、网络或工具权限。”
- 本批不增加跳过按钮、多节点编辑器、自动轮询或 SSE。

## 10. 开源参考补充：Xiaoda Agent

用户提供的 `nahida-agent` 地址当前重定向至 [Xiaoda Agent](https://github.com/long-safe-accont-4567-uvwxyz-9876/xiaoda-agent)。本次以 MIT 仓库 `main@35e42de` 为只读评估基线，检查了任务图、并行超时、恢复编排、Self-Wake、共享黑板、审批/权限、工作流 API/UI 及相关测试。结论是采用协议与固定集思想，不复制实现。

| 观察 | 决策 | 落点 |
|---|---|---|
| DAG 将 `skipped` 依赖视为已解除，并用回归测试防止下游永久等待 | 本批采用 | 保持 `skipped` 为独立证据，同时验证下游能刷新为 `ready`；加入超时型死锁固定集 |
| 并行任务设置整体期限，超时后取消未完成分支并保留已完成结果 | 只采用“必须有界、不得挂死”的原则 | CYR.2B 增加状态刷新/事务故障注入；真正并行执行与部分结果策略留到 CYR.2C/CYR.3，不在本批创造 worker |
| 审批结果区分一次、工具级、具体命令级和拒绝，且命令批准绑定工具；高风险审批器故障 fail closed，拒绝路径也审计 | 记录为 CYR.3 硬约束 | 进一步证明计划批准不能充当工具许可；CYR.3 另行设计 `ConfirmationRequest`、作用域、过期、撤销和拒绝证据 |
| `DISCUSS/PLAN/INTERACTIVE/AUTO/CUSTOM` 等模式把“规划能力”和“执行权限”分开 | 采用边界，不采用现成枚举 | 本批只冻结计划批准边界；是否需要同名模式由 CYR.3 设计决定，不能由 TaskRun 状态隐式推导权限 |
| Self-Wake 用 `pending/due/fired`、完成/事件/计时触发和过期清理代替无界轮询 | 延后 | 可作为后续提醒与后台基础设施参考；TaskRun 恢复仍坚持启动时进入 `recovery_required`、不自动续跑 |
| 工作流编辑器提供线性节点链、资源选择和提示词预览 | 只借交互启发 | 后续 CYR.2B 多节点编辑器必须编辑真实 DAG、依赖与验收条件；不得把 Markdown 提示词文件当作 TaskRun 权威状态 |
| 共享黑板以 TTL KV 或独立 SQLite 表跨 Agent 交换临时结果 | 当前拒绝 | Xiadie 现阶段是单主控 Agent；TaskRun/Event/ArtifactRef、CTX/MEM/KIG 已有明确所有权，新增黑板会形成第二事实源 |
| 通用六级自动恢复根据错误字符串选择重试、降级、重配置、重启 | 当前拒绝 | TaskRun 恢复必须基于工具副作用、持久证据和显式策略；不能仅凭错误文本自动重试或重启 |

这份参考不改变本批范围、Schema 87 或合入顺序。若未来移植具体代码，必须单独进行许可证、NOTICE、来源与安全审计；当前文档不构成代码采用决定。

## 11. 测试设计

### 11.1 纯合同内核

- 穷举所有 Run 状态 × Run 命令；
- 穷举所有 Node 状态 × Node 命令；
- 每格断言 `apply/idempotent/reject`、目标状态、错误码和 retry；
- 验证精确重放先于 revision 冲突；
- 验证参数不同不能伪装成幂等。

### 11.2 领域事务

- 两个客户端持同一 revision，恰好一个成功，另一个 409；
- 所有拒绝路径对 Run、Node、Task、Event 和 ArtifactRef 零写入；
- `start/resume + ready/blocked 刷新` 故障注入后整笔回滚；
- 计划换版清除旧批准，批准只绑定当前 `plan_version`；
- blocked 节点带原因跳过后解除下游依赖，但不产生成功证据；同时用有界超时固定集证明不会因 `skipped` 依赖进入永久等待；
- 最后节点命令响应丢失后可以精确重放；
- completed/failed/cancelled 后可追加晚到 ArtifactRef，且终态不变；
- Schema 86 → 87 与新库 Schema 一致。

### 11.3 HTTP

- 每个修改端点缺 revision 均为 422；
- revision、状态、节点和参数冲突均使用统一 409 结构；
- 不存在对象保持 404；
- 幂等重放为 200、revision 不变、事件数不变。

### 11.4 前端

- 所有修改调用都携带当前可见 revision；
- 409 接受较新快照，拒绝较旧或错误 Run 快照；
- 冲突不会自动重放；
- 批准文案明确权限边界。

### 11.5 工程门禁

- 后端全量与 TaskRun 定向测试；
- 前端全量测试与生产构建；
- Python `compileall`；
- Electron 生命周期合同；
- Schema 升级/新库固定集；
- `git diff --check`。

## 12. 完成定义

本批只有在以下条件全部满足时才可标记完成：

- 没有外部 TaskRun 修改入口可以省略 CAS；
- 领域层公共入口不能绕过 revision；
- 状态矩阵不存在未定义或绕过路径；
- 终态不能被执行命令复活；
- 精确重放全部安全且零写入，相似但不同的命令明确冲突；
- 计划批准与工具授权在 Schema、API、文案和测试上分离；
- 高风险执行的审批或权限基础设施故障必须 fail closed，并保留拒绝证据；本批以边界测试冻结要求，正式执行门在 CYR.3 实现；
- 启动/继续与节点刷新没有跨事务半状态；
- 全部工程门禁通过；
- README 与 CYR.2 权威计划记录真实测试数字和施工痕迹；
- 本批形成独立提交/PR，后续多节点编辑器从其合入后的 `main` 开始；
- 不把 CYR.2B 或 CYR.2 全阶段误标为完成。

## 13. 后续顺序

合同闭合并合入后，CYR.2B 后续按独立纵切推进：

1. 结构化多节点计划编辑器与本地冲突草稿恢复；
2. TaskRun 业务事件 SSE、游标、重连与快照补偿；
3. 历史执行、失败证据与再次执行入口；
4. CYR.2C Agent Planner、用户锁定节点和恢复策略。

CYR.3 的 ToolRegistry、PermissionGuard、ConfirmationRequest 与正式 Artifact 仍在 CYR.2 既定边界之后；计划批准永远不能被解释为这些权限的替代品。
