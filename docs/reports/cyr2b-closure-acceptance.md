# CYR.2B 收口验收报告

- 批次：CYR.2B（合同闭合 + UX 工作台）
- 日期：2026-08-04
- 合入：`agent/cyr2b-contract-closure` → `main`
- 前置基线：CYR.2A（`e477bff`）、CYR.2B revision 并发合同（`abdb463` / PR #4）、合同闭合设计（`2fc0d1e` / PR #5）
- Schema：87

## 交付物

| 组件 | 提交 | 内容 |
|---|---|---|
| 合同闭合 | `dafa730` | 纯 `task_run_contract` 内核、Schema 87、API 与领域层强制 CAS、统一 409、精确语义幂等、批准边界与节点跳过证据 |
| UX 工作台 | `519f574` | 多节点计划编辑、依赖与验收条件、执行历史、再次执行、body-free 事件 SSE（游标补齐与 gap 恢复） |

## 门禁

| 检查 | 结果 |
|---|---|
| 后端全量 pytest | 2754 passed |
| TaskRun 合同/Schema/领域/HTTP/SSE 定向 | 30 passed |
| 前端 node --test | 87 passed（含 Electron 生命周期合同） |
| Python compileall | pass |
| Vite 生产构建 | pass |
| git diff --check | pass |

## 边界

- 不含 Agent Planner、来源引用、恢复策略与用户锁定节点（CYR.2C）。
- 不含 ToolRegistry、PermissionGuard、ConfirmationRequest 或正式 Artifact（CYR.3）。
- 没有引入外部编排运行时、第二套状态数据库或新运行时依赖；只吸收开源协议思想，不复制代码。

## 遗留

- 真实使用可用性反馈继续作为 CYR.2B 软指标。
- CYR.2D 仍覆盖取消竞态、崩溃、打包态与全链路工作台验收。
