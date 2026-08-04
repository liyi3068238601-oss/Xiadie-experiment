# CYR.2D 全链路关联验收报告

- 日期：2026-08-04
- 范围：TaskRun ↔ 事件 ↔ 诊断日志 ↔ ToolRun ↔ ArtifactRef 关联核对
- 依据：`backend/tests/test_task_run_chain.py` 完整生命周期测试 + 前端契约断言

## 关联矩阵

| 对象 | 关联键 | 检查结果 |
|---|---|---|
| TaskRun | `trace_id` | PASS（创建时生成并贯穿全生命周期） |
| task_run_events | `task_run_id` | PASS（`task_run_completed` 等事件存在，body-free） |
| 诊断日志 | `trace_id` / logger | PASS（`task.scheduler` 日志同 trace 可读） |
| tool_runs | `task_run_id` | PASS（`tool_runs.create` 绑定 run；`GET /task-runs/{id}` 投影已含 `task_run_id`） |
| task_run_artifact_links | `task_run_id` / `node_id` | PASS（终态可追加 ArtifactRef 并回溯） |

## 完整生命周期证据

创建 → 计划替换 → 开始 → 节点 start → 节点 succeed → run `completed`，全程 `trace_id` 一致；进度与终态匹配。

## 前端契约断言

- 运行面板展示进度（`task-run-progress`）与 run id。
- 事件列表入口（`查看事件`）与恢复面板（`recoveryCardVisible`）可见。
- 断言文件：`frontend/tests/taskRunUx.test.mjs`（`CYR.2D chain acceptance keeps trace and evidence visible`）。

## 边界

- ToolRun 目前为 CYR.3 前的证据壳（无真实工具执行）；绑定与展示语义已验收。
- 本报告不涉及打包/安装链路（CYR.9）。
