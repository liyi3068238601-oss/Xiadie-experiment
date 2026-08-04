# CYR.3 收口验收报告

- 批次：CYR.3（ToolRegistry / 权限 / Artifact）
- 日期：2026-08-04
- 分支：`agent/cyr3-tools`（合入 `main` 的 merge SHA 见 git 历史）
- 前置基线：CYR.2D 收口（main `7725f7e`，merge `606a530`）；Schema 88
- Schema：89

## 交付物

| 组件 | 内容 |
|---|---|
| Schema 89 | `task_nodes.tool_ref/tool_args_json`；`permission_grants`、`confirmation_requests`、`artifacts`、`recovery_checkpoints` |
| ToolRegistry | manifest 注册/发现/轻量 schema 校验（不引入 jsonschema） |
| 首批工具 | `workspace.read_file` / `workspace.search` / `workspace.list_dir` / `document.parse` / `code.inspect` + `workspace.write_file`（S2 显式确认） |
| Executor | 节点工具绑定，ToolRun 真实证据链（queued→authorizing→running→succeeded/failed），只有证据成功才允许节点 succeed |
| 权限 | PermissionGuard 有期限可撤销 grant；只读工作区内会话隐式授权；聊天确认卡（SSE + 前端） |
| Artifact | 版本（最近 10 版）、回滚、审计软删→purge、预览、工作台产物区与 ArtifactViewer |
| RecoveryCheckpoint | 每次 ToolRun 终态记录输入证据；恢复面板"重试"接真实执行器 |

## 门禁

| 检查 | 结果 |
|---|---|
| 后端全量 pytest | 2820 passed |
| 前端 node --test | 102 passed |
| Vite 生产构建 | pass |
| Python compileall | pass |
| git diff --check | pass |

## 边界

- 不可信插件隔离（独立进程）属于 PLUG.2；本批工具均为进程内第一方。
- 外部浏览器/邮件/云盘连接属于 CYR.6；Worker 委派属于 CYR.8；打包/安装属于 CYR.9。
- 聊天直调目前只读；写入确认卡已就绪，等待聊天写意图接入。

## 遗留

- 写工具产物记录失败不阻断工具成功（留证据日志），后续可补重试补录。
- planner 质量固定集仍记"未验证"（CYR.2D 遗留，等待输出合同加固后重测）。
