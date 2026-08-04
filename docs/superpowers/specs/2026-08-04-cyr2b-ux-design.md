# CYR.2B-UX TaskRun 工作台设计

状态：已实施，待随真实使用补充可用性反馈。  
日期：2026-08-04  
范围：CYR.2B 的最后一个 UX 纵切；不引入 Agent Planner、ToolRegistry 或权限授予。

## 目标

把已经完成并发合同闭合的 TaskRun 变成用户能直接理解和操作的工作台：计划先可见、可改；每个步骤有依赖与验收条件；批准边界明确；历史执行可回看、可复制为新的未启动执行；状态变化不依赖通用诊断日志。

## 交互合同

1. “建立执行”只创建 `draft`，随后打开计划编辑器；不再后台写入不可见的默认单步骤计划。
2. 编辑器可增删节点、编辑标题/验收条件、选择前置依赖，并选择是否需要批准。保存仍通过现有 `PUT /plan + expected_revision` 原子替换，后端仍是 DAG、上限和 CAS 的唯一裁决者。
3. 对 `ready` 或 `running` 执行“编辑计划”会先显式请求 `replan`，然后再提交新版本；批准只绑定该 `plan_version`，绝不被解释为文件、网络、工具、账户或外发权限。
4. 节点卡片显示依赖、验收条件、失败/跳过证据；手动跳过必须写入稳定原因，且只在既有状态机允许时出现。
5. 每个 Task 显示其执行历史；终态运行可“再次执行”。再次执行复制结构化计划和批准要求，创建一个新的 TaskRun，不复制节点结果、错误或批准，也不会自动开始。

## 事件流合同

- `GET /api/task-runs/{id}/events?after=<event-id>&limit=...` 返回有界的 body-free 历史、下一游标和 `gap` 标志。
- `GET /api/task-runs/{id}/events/stream?after=<event-id>` 使用 SSE 推送 `ready`、`task_run_event`、`gap` 和心跳。事件只包含事件表的 ID、状态、revision、reason code 和有界 metadata，不包含目标摘要、计划正文、文件正文或隐藏推理。
- 游标未知时服务端明确发送 `gap`，客户端重新读取权威 `GET /api/task-runs/{id}`，不推测或重放 mutation。
- 前端使用已有 `fetch + ReadableStream + X-Xiadie-Token` 模式，而不是无法携带桌面本地令牌的 `EventSource`；事件到达后读取权威快照并刷新历史。
- 此流是 TaskRun 的业务证据流，不替代 `task.scheduler` 诊断日志，更不混入模型心理活动或通用日志终端。

## 验收与非目标

- 已有 TaskRun 领域合同、Schema 87、CAS、幂等和启动恢复语义保持不变。
- 后端单元测试覆盖游标、body-free 投影和 gap；前端源契约测试覆盖带认证流、计划编辑、批准提示、历史和跳过入口。
- CYR.2C 才处理 Agent 提案计划、恢复策略和实际工具执行；CYR.3 才处理工具权限、确认与 Artifact 正式域。
