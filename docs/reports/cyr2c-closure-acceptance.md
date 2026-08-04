# CYR.2C 收口验收报告

- 批次：CYR.2C（Agent Planner / 锁定 / 来源引用 / 恢复协议与面板）
- 日期：2026-08-04
- 合入：`agent/cyr2c-planner-locking` → `main`（merge `d02f50f`）
- 前置基线：CYR.2B 收口（main `f9bb3f0`，merge `e100182`）；Schema 87
- Schema：88

## 交付物

| 组件 | 内容 |
|---|---|
| Schema 88 | `task_nodes.user_locked / locked_reason / recovery_class`；`task_node_source_links` 表 |
| KIG 来源解析 | 新增 `memory_episode / memory_saga / memory_entity` resolver |
| task_runs | 来源链接写入与失效阻塞、锁定节点不可变校验、`validate_plan_shape`、`invalidate_source_links`、`recovery_view` |
| task_planner | 轻量 Planner（ModelRouter 结构化输出 + 程序校验 + 意图匹配） |
| API | `POST /api/task-runs/from-proposal`、`POST /api/task-runs/{run_id}/planner-proposal`、`GET /api/task-runs/{run_id}/recovery` |
| 聊天 SSE | `plan_proposal` 事件（规划意图命中、非 mock 模型、失败静默） |
| 前端 | 聊天计划卡、任务页重新生成/锁定/来源 chips/失效横幅、恢复面板（继续/重试诚实禁用/重新规划） |
| 失效钩子 | knowledge 归档/删除、memory 删除、entity 归档、episode/saga lifecycle 归档/墓碑 |

## 门禁

| 检查 | 结果 |
|---|---|
| 后端全量 pytest | 2775 passed |
| 前端 node --test | 97 passed |
| Vite 生产构建 | pass |
| Python compileall | pass |
| git diff --check | pass |

## 边界

- 不含真实工具执行与重试逻辑（CYR.3）；「重试」按钮在工具接入前诚实禁用。
- conversation 来源只记录引用，不做持久失效检测（spec §7.3）。
- 不引入外部编排运行时、第二数据库或新依赖。

## 遗留

- 真实使用观察与多模型计划质量固定集继续作为软指标。
- CYR.2D：取消竞态、进程崩溃、数据库忙、打包态恢复与全链路验收。
