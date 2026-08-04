# CYR.2D 收口验收报告

- 批次：CYR.2D（工作台验收与故障加固）
- 日期：2026-08-04
- 合入：`agent/cyr2d-acceptance` → `main`（merge `606a530`）
- 前置基线：CYR.2C 收口（main `48b8305`，merge `d02f50f`）；Schema 88

## 交付物

| 组件 | 内容 |
|---|---|
| 单测级故障注入 | `test_task_run_faults.py`：并发命令竞争（一次应用 + 一次 409）、事务中途崩溃回滚、数据库忙零脏写、陈旧 revision 竞争、取消幂等 |
| 进程级 E2E | `scripts/test-cyr2d-crash-recovery.ps1`：启动 → running → 强杀 → 重启 → `recovery_required` → 取消幂等 |
| 全链路关联 | `test_task_run_chain.py`：trace 贯穿 run/事件/日志/ToolRun/Artifact；顺带修复 `GET /task-runs/{id}` 的 tool_runs 投影缺 `task_run_id` |
| 质量固定集 | 10 组合成场景 + `run_cyr2d_planner_quality.py` + 三份模型报告与汇总；顺带修复 `task_planner.log_event` 缺 message 的潜伏 bug |

## 门禁

| 检查 | 结果 |
|---|---|
| 后端全量 pytest | 2788 passed |
| 前端 node --test | 98 passed |
| Vite 生产构建 | pass |
| Python compileall | pass |
| git diff --check | pass |
| 崩溃恢复 E2E 脚本 | PASS |

## 质量固定集结论

deepseek-v4-pro（结构合法率 0.30）、deepseek-v4-flash（0.40）、deepseek-chat（0.90）当前均记"未验证"：失败模式为输出 JSON 不可解析/空响应；杜撰来源、批准当权限、锁定被改写三项零容忍全 0。未验证不阻塞使用；改进方向（收紧输出合同/修复重试）记录在 `cyr2d-planner-quality-summary.md`。

## 边界

- 打包/安装/升级链路验收留给 CYR.9（本批明确不打包）。
- 真实工具执行与重试逻辑属于 CYR.3。
- 未修改 TaskRun 状态机合同；合同级问题未发现。

## 遗留

- planner 多模型结构合法性未达零容忍，等待输出合同与解析加固后重测。
- 真实使用观察继续作为软指标。
