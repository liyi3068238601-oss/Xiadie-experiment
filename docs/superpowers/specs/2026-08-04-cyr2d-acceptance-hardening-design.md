# CYR.2D 工作台验收与故障加固设计

> 状态：设计已批准（2026-08-04），书面 spec 待用户复核
> 决策日期：2026-08-04
> 适用范围：取消竞态、进程崩溃、数据库忙、重复请求/陈旧 revision 的故障注入与修复；TaskRun 全链路关联验收；多模型计划质量固定集
> 前置基线：CYR.2C 收口（main `48b8305`，merge `d02f50f`）；Schema 88
> 后续边界：真实工具执行与重试逻辑（CYR.3）、打包/安装/升级（CYR.9）

## 1. 批次定义

一个批次、一份 spec、三段实施：

- 第一段（Segment A）：后端故障注入与修复（单测级 + 进程级两层）。
- 第二段（Segment B）：TaskRun 全链路关联验收。
- 第三段（Segment C）：多模型计划质量固定集。

## 2. 目标

1. 四类故障（取消竞态、进程崩溃、数据库忙、重复请求/陈旧 revision）注入下，TaskRun 状态一致、取消/恢复幂等、失败不伪装成功、业务表零脏写。
2. 进程强杀后遗留执行进入 `recovery_required`，不自动续跑，可显式取消/继续。
3. 同一 `trace_id` 贯穿 TaskRun、事件、诊断日志、ToolRun 与 ArtifactRef，工作台证据展示完整可读。
4. Planner 在认证模型与常用模型固定集上跑同一组合成场景，输出"已验证/未验证"清单与零容忍门禁；未验证模型照常可用。

## 3. 非目标

- 不做打包、安装、升级、卸载链路验收（留给 CYR.9 稳定发布）。
- 不实现真实工具执行、ToolRegistry、PermissionGuard、ConfirmationRequest 或正式 Artifact（CYR.3）。
- 不修改 TaskRun/TaskNode 状态机合同（CYR.2A～CYR.2C 已冻结语义保持）；注入发现的合同级缺陷升级给用户定夺，不在批内擅改。
- 不引入外部编排运行时、第二数据库或新运行时依赖。

## 4. Segment A：后端故障注入与修复

### 4.1 单测级注入清单（pytest，确定性）

新增 `backend/tests/test_task_run_faults.py`，复用 `test_task_runs.py` 的 isolated_db / `_business_snapshot` 模式。

| 故障 | 注入方法 | 期望 |
|---|---|---|
| 取消竞态 | 并发 `approve`/`start`/`cancel`/`pause` 双请求（ThreadPoolExecutor） | 恰好一次应用，其余 409 `task_run_revision_conflict`；五类业务表零脏写 |
| 事务中途崩溃 | `replace_plan`/`transition_node` 事务内 monkeypatch 抛异常/断连接 | 回滚：nodes 与 run 一致、无孤儿 source link/artifact/事件 |
| 数据库忙 | 第二个连接 `BEGIN IMMEDIATE` 抛 `sqlite3.OperationalError`（模拟 locked） | 不产生半状态与脏写；请求以可安全重试的方式失败（具体状态码由实施测试固化） |
| 精确重放 | 相同请求重放（含相同 revision） | 幂等 200，零写入 |
| 相似不同请求 | 计划只改一个字段后提交 | 不是幂等；按合同判定（锁定/内容冲突或应用） |
| 陈旧 revision 竞争 | 不同命令携带同一旧 revision 并发 | 一次应用 + 一次 `task_run_revision_conflict` |

### 4.2 进程级 E2E（脚本，不打包）

新增 `scripts/test-cyr2d-crash-recovery.ps1`（仿 `test-cie6-electron-smoke.ps1` 风格）：

1. 以临时数据目录启动后端（`run_frozen.py`）。
2. 通过 HTTP 创建任务 → 建 run → 提交计划 → start（进入 `running`）。
3. 强杀后端进程（`Stop-Process -Force`）。
4. 重启后端，断言：遗留 run 状态为 `recovery_required`、当时 running 节点为 `blocked`、`waiting_reason` 非空。
5. 通过 HTTP 执行 `cancel`（幂等）与新建 run 的 `resume` 路径各一次，断言状态合法。
6. 清理临时数据目录与进程树。

脚本退出码即门禁结果，纳入 CYR.2D 验收命令。

### 4.3 修复与升级规则

- 注入发现的缺陷在批内修复，每个修复带覆盖测试（TDD）。
- 若缺陷根因需要改状态机合同或 Schema 语义，停止并升级给用户决定，不擅改冻结合同。

## 5. Segment B：全链路关联验收

### 5.1 关联矩阵

| 对象 | 关联键 | 校验 |
|---|---|---|
| TaskRun | `trace_id` | 创建时生成并贯穿 |
| task_run_events | `task_run_id` | 每次状态变化都有事件，body-free |
| 诊断日志 | `trace_id` / `task_run_id` | `task.scheduler` 日志同 trace |
| tool_runs | `task_run_id` | 同一 run 的工具执行可回溯 |
| task_run_artifact_links | `task_run_id` / `node_id` | 终态可追加 ArtifactRef |

### 5.2 验收方法

- 单测：一次完整生命周期（创建 → 计划 → 批准 → 开始 → 节点完成 → 完成）后，断言 run/events/log 的 `trace_id` 一致、tool_runs 绑定 `task_run_id`、artifact 链接可回溯、进度与终态匹配。
- 前端契约：工作台运行面板展示 run id/trace、事件列表 body-free、节点证据与恢复面板（CYR.2C 已实现）——验收其完整呈现，不改结构。
- 输出：验收报告记录关联矩阵与检查结果。

## 6. Segment C：多模型计划质量固定集

### 6.1 模型固定集

- 必跑（认证）：`deepseek` / `deepseek-v4-pro`、`deepseek` / `deepseek-v4-flash`。
- 常用（按可用配置）：`deepseek-chat`、`qwen-plus`、`glm-4-flash`；配置缺失时记录 `unavailable` 不判失败。

### 6.2 合成场景

10 组纯合成场景（不含用户数据），覆盖：多步骤 DAG、依赖链、来源引用（真实 seed 的 knowledge_source/memory_fragment）、锁定节点保留、需批准边界、拒绝无把握来源、循环依赖纠正、节点数上限、重复 client_id、目标摘要缺失。

### 6.3 零容忍指标

| 指标 | 分母 | 门槛 |
|---|---:|---:|
| 结构非法提案（无法落库） | 10 | 0 |
| 杜撰来源引用（来源不存在） | 10 | 0 |
| 批准被解释为工具权限 | 10 | 0 |
| 锁定节点被改写 | 10 | 0 |

软指标：计划合理率（固定规则复核，记录不设硬门槛）。

### 6.4 报告与资格

- 沿用 KIG-R 报告模式：`docs/reports/cyr2d-planner-quality-{provider}-{model}.json/.md` 或合并报告，记录每模型"已验证/未验证"。
- 未验证模型不阻塞使用；模型指纹随生成事件记录（沿用路线图固定集原则）。

## 7. 门禁

- 后端全量 pytest。
- 前端 node --test 与 Vite 生产构建。
- Python compileall、`git diff --check`。
- `scripts/test-cyr2d-crash-recovery.ps1` 进程级 E2E。

## 8. 实施分段

### Segment A：故障注入与修复

1. 单测级注入固定集（`test_task_run_faults.py`）。
2. 进程级 E2E 脚本（`scripts/test-cyr2d-crash-recovery.ps1`）。
3. 修复注入发现的缺陷（TDD），并升级合同级问题。

### Segment B：全链路关联验收

4. 完整生命周期关联测试与前端契约验收。
5. 输出关联矩阵报告。

### Segment C：多模型计划质量固定集

6. 评测脚本（复用 `task_planner.generate_proposal`，合成场景 seed）。
7. 跑固定集、生成报告与"已验证/未验证"清单。

## 9. 验收记录

- 三段各自独立验收；收口时更新 README、路线图与 CYR.2 施工计划，勾选 CYR.2D 条目并输出 `docs/reports/cyr2d-closure-acceptance.md`。
