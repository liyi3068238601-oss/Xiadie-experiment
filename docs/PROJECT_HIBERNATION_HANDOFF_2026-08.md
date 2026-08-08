# Xiadie Experiment 项目停工快照与恢复施工手册

> 状态：长期暂停施工时的权威交接快照
> 冻结日期：2026-08-08
> 冻结分支：`main`
> 冻结提交：`f0d82c8`（`docs(cyr3): record CYR.3 merge sha`）
> 远端：`origin/main`，仓库 `liyi3068238601-oss/Xiadie-experiment`
> 应用版本：`0.1.0`（实验版）
> 数据库最新 Schema：89
> 适用对象：未来恢复施工的维护者、Codex 会话和代码审查者

## 1. 这份文档解决什么问题

本项目将在较长时间内停止施工。恢复时不能依赖聊天记录、人的短期记忆或 README 中某个可能已经陈旧的段落。本文件冻结暂停时的代码事实、产品方向、已完成阶段、未完成工作、已知风险、恢复顺序和验证命令。

恢复施工时，先读本文件，再读准备施工阶段的设计与实施计划。若本文件与 2026-08-08 以前的路线状态描述冲突，以 Git 代码、阶段验收报告和本文件记录的冻结事实为准；历史设计仍用于理解原因，不自动代表当前实现。

本文件不是新的需求路线，也不授权扩大系统权限。它只说明暂停时项目在哪里，以及如何安全接回工作。

## 2. 一页结论

Xiadie Experiment 已从“带 Live2D 的陪伴聊天原型”迁移为“保留遐蝶身份与自然表达的本地优先、助手优先 Windows Agent”。LIFE 离线生活模拟已物理退役；Persona、用户记忆、知识治理、上下文、任务执行、日志诊断等可复用能力保留并继续发展。

暂停时已经完成：

- RETIRE.0～RETIRE.3：LIFE 运行时、UI、API、worker、adapter 和专属表退役，旧路线文档归档。
- LOG.1～LOG.5：结构化日志、trace、ToolRun、诊断 SSE、终端式可读日志和支持包基线。
- CYR.1 / CYR.1S：单一 Persona v2.3、WorldBook 低权限知识边界、模型质量记录与运行资格解耦。
- CYR.2A～CYR.2D：TaskRun/TaskNode 工作台、计划 DAG、用户编辑与锁定、聊天计划卡、来源引用、恢复面板、故障注入和全链路验收。
- CYR.3：ToolRegistry、PermissionGuard、ConfirmationRequest、首批本地工具、正式 Artifact 域和 RecoveryCheckpoint。
- Memory、CTX、KIG/PWM、CIE、CDS 等此前专项的主要生产基线仍在代码中，并受助手优先路线约束。

暂停时没有正在进行的功能代码施工。`main` 与 `origin/main` 对齐，冻结前工作区干净。下一条尚未开始的主施工线是：

```text
PLUG.0 插件协议与最小宿主
  → PLUG.1 Hook 与事件总线
  → PLUG.2 权限、隔离和插件数据边界
  → PLUG.3 插件管理界面与兼容治理
  → PLUG.4 Feeling 插件候选
  → CYR.4 Web / Research
```

恢复后不要直接从 PLUG.4 Feeling 开始，也不要直接接第三方插件。先恢复环境和门禁，修正文档漂移，完成 PLUG.0 的现状复核、设计和最小宿主。

## 3. 冻结时的 Git 与发布状态

### 3.1 Git 基线

冻结时主线：

```text
main / origin/main
└─ f0d82c8 docs(cyr3): record CYR.3 merge sha
   └─ 0bf69c3 Merge CYR.3 closure: tool registry, permissions, artifacts
```

关键阶段合并提交：

| 阶段 | 合并提交 | 结果 |
|---|---|---|
| CYR.2B | `e100182` | 合同闭合与 UX 工作台合入 `main` |
| CYR.2C | `d02f50f` | Planner、锁定、来源引用和恢复协议/UI 合入 `main` |
| CYR.2D | `606a530` | 故障注入、崩溃恢复、全链路与质量固定集合入 `main` |
| CYR.3 | `0bf69c3` | 工具、权限、确认、Artifact 和恢复检查点合入 `main` |

冻结文档通过独立分支 `agent/project-hibernation-handoff` 编写，避免直接改写 `main`。恢复时应先确认该交接提交是否已经合入默认分支。

### 3.2 GitHub 状态

冻结时普通 Git 远端推送凭据可用；本机 GitHub CLI `gh` 的 `liyi3068238601-oss` 登录令牌失效。该问题不影响读取本地仓库，也不代表远端仓库不可访问，但会影响通过 `gh` 创建或管理 PR。

恢复施工前执行：

```powershell
gh auth status
gh auth login -h github.com
```

不要把任何新 token 写入仓库、README、日志或支持包。

## 4. 冻结的产品方向

### 4.1 项目是什么

Xiadie 是一个本地优先、Windows 桌面优先、助手优先的单主控 Agent。模型始终直接以遐蝶身份形成判断并回应，在自然聊天、倾听、知识问答、分析、写作、任务规划和受控工具执行之间自然切换；用户不需要选择 `companionship` 或 `focused_work` 模式。

Persona 决定身份、价值判断、事实诚实、安全边界和表达方式；WorldBook 是按需召回的遐蝶特殊知识库，不是现代知识白名单，也不决定模型能否理解现代事物。Memory 保存真实用户事实与互动证据；CTX、KIG、Task 和 Tool 提供通用 Agent 能力。

### 4.2 项目不是什么

- 不再模拟遐蝶离线生活、睡眠、日程、个人目标、日记或虚构世界连续性。
- 不用模拟情绪、关系压力或虚构生活作为主动联系用户的理由。
- 不把“计划批准”解释成文件、网络、工具、账号或外部消息权限。
- 不让模型文字直接宣告工具成功；成功必须来自 ToolRun 和真实执行证据。
- 不让模型认证成为 Persona 的运行许可证。未验证模型可以运行，只显示质量未验证。
- 不在当前阶段引入多个对用户说话的 Agent 人格。未来 Worker 也只能是单主控下的内部专业执行者。
- 不允许插件直接访问核心数据库、完整文件系统、密钥或核心日志 sink。

### 4.3 Live2D 的长期定位

Live2D 是实验阶段的 PresentationAdapter，不是不可替代的 Agent Core。当前仍保留桌宠、拖拽、点击、动作和气泡入口；长期应在非 Live2D 入口、启动器和迁移门禁稳定后移除 renderer、IPC、设置和受限资产链。

当前模型只允许个人自用，禁止再分发、上传、二改或商业使用。正式对外发布前必须替换为原创或拥有明确再分发授权的资产。`frontend/public/models/` 被 Git 忽略，恢复施工不能假定克隆仓库后一定拥有模型文件。

## 5. 当前技术架构

```text
Electron 桌面壳
  ├─ 托盘、窗口、IPC、桌宠入口
  ├─ 启动本地 FastAPI 后端
  └─ 向 renderer 注入本地 API 地址与短期令牌

React + TypeScript + Vite
  ├─ ChatView：聊天、计划卡、权限确认
  ├─ TasksPage：TaskRun 工作台、恢复、Artifact
  ├─ RuntimeLogs / ToolLogs：诊断与审计视图
  └─ Memory / Knowledge / Settings 等管理页面

FastAPI + Python
  ├─ Persona / CTX / Memory / KIG / CDS / CIE
  ├─ TaskRun / Planner / Recovery
  ├─ ToolRegistry / PermissionGuard / Executor
  ├─ Artifact / Confirmation / Observability
  └─ OpenAI-compatible Provider 适配

SQLite（WAL，Schema 89）
  ├─ 会话、消息、记忆、知识、任务和配置
  ├─ TaskRun、TaskNode、事件、来源引用
  ├─ ToolRun、权限、确认、Artifact、恢复检查点
  └─ 审计与兼容迁移数据
```

冻结技术选择：

| 层 | 技术 | 不应在恢复首批改动中替换 |
|---|---|---|
| 桌面 | Electron 33 / electron-builder | 不迁移 Tauri |
| 前端 | React 18、TypeScript 5.6、Vite 5 | 不为统一语言重写 |
| 后端 | Python、FastAPI、Pydantic | 不整体改写 TypeScript |
| 存储 | SQLite WAL | 不引入第二套任务状态数据库 |
| 模型 | OpenAI-compatible Provider | Provider/模型选择不与 Persona 版本绑定 |
| 本地向量 | BGE-M3 ONNX（可选） | 缺失时必须能降级 FTS |

## 6. 运行、端口和数据位置

### 6.1 实验版端口

当前代码权威端口：

- FastAPI：`127.0.0.1:9756`
- Vite：`127.0.0.1:6173`
- Electron App ID：`com.xiadie.agent.experiment`
- 实验版数据/日志身份：`Xiadie-Experiment`

`desktop/main.js`、`backend/run.py`、`backend/run_frozen.py` 和 `scripts/start-dev.ps1` 已一致使用 9756/6173。本次停工交接已把 `BUILD-WINDOWS.md` 中遗留的 8756 和旧 AppData 文案改为实验版配置；但安装包仍未按 CYR.3 / Schema 89 重新实测，重新发布前必须以构建产物验证文档结论。

### 6.2 开发数据

开发启动脚本将 `XIADIE_DATA_DIR` 指向仓库内的 `backend/data`。Electron 安装版将数据写入用户可写的 AppData 目录，不写入只读安装目录。具体目录由 Electron 启动时注入，恢复施工不要硬编码用户主目录。

任何涉及 Schema、退役旧表、记忆迁移、Artifact 或隐私删除的施工，必须先备份实际 SQLite 数据、WAL/SHM 文件和必要的本地资源，再启动新代码触发迁移。

### 6.3 本地 API 安全

Electron 为本地 API 注入 `XIADIE_API_TOKEN`；前端通过 `X-Xiadie-Token` 访问受保护端点。SSE 需要认证头，因此 TaskRun 和聊天流使用 `fetch + ReadableStream`，不能无条件替换为无法附带请求头的原生 `EventSource`。

密钥由受控存储接口管理。日志、TaskRun 事件和支持包不得包含 API key、完整 Prompt、聊天附件正文、记忆正文、知识正文或 Provider 隐藏推理。

## 7. 已完成能力的真实状态

### 7.1 Persona v2.3 与模型兼容

已完成：

- 单一 Persona v2.3 默认运行。
- Persona 资源 manifest、hash、token 门和启动自检。
- v2.3 资源异常时的回退链；长期目标是正式只读 Persona 资源包加代码内置 emergency Persona。
- 模型质量评测与运行资格解耦：有记录显示“已验证”，无记录显示“未验证”但可正常运行。
- 采样参数选择与 Persona 版本选择解耦。

迁移遗留：Persona v2.2 仍是安全垫，不应永久保留。删除之前必须满足真实使用、多模型固定集、资源损坏回退、诊断日志、旧客户端兼容和历史认证数据退场门禁。最终只保留正式 v2.3 与极短代码内置 emergency Persona；v2.2 的 manifest/hash/认证报告进入归档。

### 7.2 Memory、CTX、KIG/PWM

保留的是用户真实证据与通用认知能力，而不是 LIFE 模拟状态。

当前包括：

- Fragment、Entity、Episode、Saga 等记忆与来源链。
- 会话摘要、上下文预算、跨会话历史召回、贡献者协议和诊断。
- 知识文件导入、解析、稳定 locator、FTS、本地 BGE-M3 dense 向量、混合检索、引用和生命周期治理。
- KIG 来源治理、查询规划、重排、证据、冲突/版本/新鲜度和 PWM。
- 模型不可用或本地向量缺失时的有界程序降级。

仍需长期退场治理：旧 `memory_candidates` 兜底、兼容候选 API、独立 ShortMemo、旧摘要字段、Memory Shadow 开关、旧 Lore 桥、内建 Affect/Relationship 和旧主动陪伴适配。退场必须迁移用户真实数据、对账、备份、回滚和验证，不能因为删除旧实现而删除真实记忆。

### 7.3 CIE / KFC 交互能力

已保留并重构了 KFC 风格中适合 Xiadie 的交互能力：流式对话、取消、中断隔离、图片能力探测、上下文贡献、回复分段与节奏、附件治理和桌面交付。没有采用 QQ 的 `do_nothing/pass_and_wait` 语义；Xiadie 当前默认是直接对用户回应的桌面 Agent。

心理活动、内心独白和 Feeling 只允许通过显式、用户可见、可清除的 `mental-activity-log-v1` 或未来插件提案记录；不得读取或保存 Provider 隐藏 chain-of-thought。

### 7.4 可观测性与日志

已完成：

- 后端和 Electron 统一结构化日志。
- 人类可读、带模块颜色的 MoFox 风格控制台行。
- `trace_id` 贯穿请求、TaskRun、ToolRun、模型和 Artifact。
- 有界内存缓冲、滚动 JSONL、诊断 SSE、gap 恢复和支持包。
- 日志可显示哪个工具、哪个阶段失败，以及脱敏错误类型和消息。
- TaskRun 业务事件与诊断日志分离：前者是权威状态证据，后者用于定位问题。

发布级负载、磁盘不足、慢客户端和长期保留策略仍需要后续发布门禁；日常实验不应为了这些门禁阻塞正常诊断。

### 7.5 CYR.2 TaskRun 工作台

CYR.2A～CYR.2D 已合入 `main`。

领域能力：

- `Task` 表示用户目标；`TaskRun` 表示一次具体执行；`TaskNode` 表示带依赖和验收条件的步骤。
- 计划是最多 50 节点的 DAG，写入前验证节点、依赖和环。
- `expected_revision` 和 SQLite `BEGIN IMMEDIATE` 构成不可绕过的 CAS。
- 支持 draft、planning、awaiting_approval、ready、running、paused、recovery_required、completed、failed、cancelled。
- 节点证据驱动进度、失败和完成；模型不能直接把节点写成成功。
- 应用崩溃后的 running 进入 `recovery_required`，不会秘密续跑。
- TaskRun 业务事件使用持久游标和 body-free SSE；游标缺口后读取权威快照。

用户界面：

- 结构化多节点编辑器、依赖和验收条件编辑。
- 聊天规划意图产生紧凑 `plan_proposal` 卡；进入工作台后创建草稿，不自动开始。
- 用户编辑节点会形成锁定，Planner 重新生成时必须保留锁定节点。
- 节点来源 chip、来源失效横幅和 fail-closed 阻塞。
- 执行历史、失败证据、再次执行、跳过理由和事件时间线。
- 恢复面板显示最后 ToolRun 证据、风险分类和继续/重试/重新规划入口。
- 计划批准只绑定当前 `plan_version`，不授予工具权限。

验收：CYR.2C 报告记录 2775 条后端、97 条前端；CYR.2D 报告记录 2788 条后端、98 条前端，以及进程级崩溃恢复 E2E 通过。它们是历史验收快照，恢复后必须重新运行当前测试，不能当作新环境证明。

### 7.6 CYR.3 工具、权限、确认与 Artifact

Schema 89 已完成：

- `task_nodes.tool_ref/tool_args_json`
- `permission_grants`
- `confirmation_requests`
- `artifacts`
- `recovery_checkpoints`

当前首批工具：

- `workspace.read_file`
- `workspace.search`
- `workspace.list_dir`
- `document.parse`
- `code.inspect`
- `workspace.write_file`（S2，需要显式确认）

这些工具在进程内运行，通过统一 executor 写 ToolRun 证据，并可绑定 TaskRun 节点。只读工作区能力可在严格范围内获得隐式授权；写入必须经过范围化、带期限、可撤销的 PermissionGrant 和具体 ConfirmationRequest。没有任意 Shell、任意文件系统、桌面输入控制、外部消息发送或通用网络访问。

Artifact 支持版本、最近 10 版保留、预览、回滚、审计软删除和 purge；Task 工作台提供产物区域。RecoveryCheckpoint 保存 ToolRun 输入证据，使恢复面板的“重试”连接真实执行器。

CYR.3 历史验收报告记录 2820 条后端测试、102 条前端测试、Vite 构建、compileall 和 diff check 通过。恢复后仍需重新验证。

## 8. 暂停时正在做什么

功能施工在 CYR.3 收口后停止，没有处于“写了一半”的 PLUG 或 CYR.4 代码。暂停断点是路线决策而不是未提交实现：

1. CYR.3 安全工具底座已经建立。
2. 下一步准备在这个底座上设计并实现 MoFox 风格插件宿主。
3. Feeling 被确定为插件候选，不写回核心 Persona，不恢复 LIFE。
4. CYR.4 Web/Research 排在插件宿主之后，目标是有来源、可复核的联网研究。
5. Planner 多模型结构输出稳定性仍是横向质量问题，但不是模型运行许可证。

因此恢复时不需要找“隐藏的半成品分支”。应从 `main` 最新状态新建独立工作分支，先做恢复审计，再进入 PLUG.0。

## 9. 已知问题和风险登记

### P0：恢复施工前必须处理

1. **先备份数据再运行迁移。** 长期暂停后依赖、Python、SQLite 或迁移代码可能变化；不要用唯一真实用户数据库做首次启动实验。
2. **恢复 GitHub 认证。** `gh` 令牌在冻结时失效；普通 push 是否仍可用必须现场验证。
3. **确认私有/忽略资源。** Live2D 模型和可选 BGE-M3 大模型不一定存在于新克隆中。
4. **继续清理历史文档漂移。** 本次已校正 README 路线图和 Windows 打包指南；`CODEX_PROJECT_CONTEXT.md` 与部分 CYR.2 阶段文档仍可能残留“下一步 CYR.2C/CYR.3”的时代口径。阶段文档可作为历史记录，但权威上下文必须与顶部状态和验收报告一致。
5. **重新跑完整门禁。** 历史 pass 不是长期暂停后的环境证明。

### P1：下一阶段应优先解决

1. **Planner 输出结构稳定性。** CYR.2D 的真实 DeepSeek 固定集记录：v4-pro 结构合法率 0.30、v4-flash 0.40、deepseek-chat 0.90，三者均标记为未验证。主要失败是 JSON 不可解析或空响应。来源杜撰、批准越权和锁定改写三项零容忍未出现违规。推荐收紧 JSON 单对象合同、禁止 Markdown 围栏，并增加一次受限结构修复；之后重新跑同一固定集。
2. **真实使用观察不足。** Persona、Planner、恢复面板、权限确认和 Artifact 虽有固定集，但长时间真实使用反馈仍是软指标。
3. **Windows 安装包未按 CYR.3 基线重新验收。** CYR.2D 已明确把打包/安装/升级链路交给 CYR.9；本次只校正了 `BUILD-WINDOWS.md` 的静态配置说明，没有证明安装、升级、卸载和资源完整性门禁已通过。
4. **插件边界尚未实现。** 当前工具都是第一方进程内能力，不等于安全的第三方插件系统。

### P2：长期治理事项

- Persona v2.2 与旧模型质量记录退场。
- 旧记忆候选、ShortMemo、摘要字段、Shadow 开关和 Lore 桥退场。
- 内建 Affect/Relationship 向受治理 Feeling 插件迁移；迁移真实用户事实，不迁移虚构心境。
- 非 Live2D 入口稳定后移除受限模型和 PresentationAdapter 旧链路。
- 用户数据导出、完整备份/恢复和隐私删除闭环。
- Provider 能力探测取代主要依赖模型名称的推断。
- 正式发行前完成代码签名、依赖许可证、角色资产授权和安装升级验证。

## 10. 恢复施工的正确顺序

### R0：只读恢复审计

恢复第一天先不改代码：

```powershell
git status -sb
git remote -v
git fetch --all --prune
git log --oneline --decorate -20
gh auth status
```

然后确认：

- 本文件所在提交已合入默认分支。
- 没有他人尚未合并的恢复分支或 PR。
- `main` 与远端默认分支的关系清楚。
- Python、Node、npm、PowerShell 和 Git 版本仍满足项目要求。
- 用户数据库和必要资源已经备份。

### R1：恢复依赖与门禁

不要盲目升级所有依赖。先按锁文件和现有要求恢复可运行环境，验证当前基线；升级依赖应独立提交。

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m compileall app tests
```

前端：

```powershell
cd frontend
npm.cmd install
npm.cmd test
npm.cmd run build
```

桌面与专项 smoke：

```powershell
cd desktop
npm.cmd install

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-cie6-electron-smoke.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-cyr2d-crash-recovery.ps1
```

若完整测试失败，先判断是环境漂移、依赖升级、资源缺失还是代码回归；不要在同一提交里顺手升级框架并修改业务合同。

### R2：文档一致性清理

在新功能施工前，更新：

- 复核 README 顶部状态和路线图；本次停工交接已把 CYR.2C/CYR.3 旧状态改为完成。
- `docs/CODEX_PROJECT_CONTEXT.md` 的当前阶段与“骨架/占位”描述。
- `docs/CYR2_TASKRUN_EXECUTION_WORKBENCH_PLAN.md` 中已完成项和过期“下一步”。
- 复核 `BUILD-WINDOWS.md`；本次已校正实验版端口与 AppData，并明确 CYR.3 后尚未完成 Windows 发布验收。

保留旧验收报告和历史设计，不重写历史；只给它们增加已完成/已取代标记或从当前入口移除误导性链接。

### R3：Planner 质量加固

建议在 PLUG.0 前用一个小批次处理 Planner 输出合同：

1. 冻结现有 `cyr2d-planner-quality-v1` 场景，不改分母来美化结果。
2. 收紧结构化输出提示和解析边界。
3. 只允许一次、无外部副作用的结构修复。
4. 保持锁定节点、来源和批准边界零容忍。
5. 对可用模型重新生成报告；仍未通过时继续标为未验证，但不阻止运行。

### R4：正式进入 PLUG.0

PLUG.0 首批只做最小宿主：

- `PluginManifest`：ID、版本、入口、宿主兼容范围、能力、权限和配置 Schema。
- `PluginContext`：受控 logger、配置、事件订阅、ToolRegistry 注册和最小服务句柄。
- 生命周期：discover、validate、load、start、stop、unload、upgrade、failed。
- 显式 extension point；禁止扫描 monkey-patch 核心模块。
- 非法 manifest、版本不兼容、启动异常全部 fail closed，但不影响核心聊天启动。
- 示例插件必须能安装、启用、禁用和卸载；此时先不要实现 Feeling 业务。

PLUG.0 需要先写功能 spec 和 UI 设计，再写实施计划；沿用 CYR.2C 的“先设计界面再实施”经验。随后按 PLUG.1～PLUG.3 完成事件、隔离、权限和管理 UI，最后才让 Feeling 作为 PLUG.4 候选进入。

### R5：CYR.4 Web / Research

插件宿主安全基线稳定后，再实现 NetworkPolicy、域名/下载授权、网页读取、来源时间与 hash、多来源交叉验证、KIG `web_result` SourceRef 和研究报告 Artifact。网页内容必须作为不可信数据处理，不能借提示注入改变工具或系统权限。

## 11. 恢复后的第一个 PR 应该是什么

推荐第一个 PR 只做“恢复基线与文档一致性”，范围：

- 重新跑并记录完整门禁。
- 修正 README、CODEX_PROJECT_CONTEXT、CYR.2 和 BUILD-WINDOWS 的陈旧状态。
- 不改 Schema、不改 Persona、不改 TaskRun 状态机、不引入插件代码。
- 输出一份新的恢复验收报告，记录环境版本、测试数量、警告和资源缺口。

第二个 PR 再处理 Planner 输出合同或 PLUG.0 设计。这样可以把“项目因长期暂停产生的环境漂移”与“新功能行为变化”分开审查。

## 12. 施工时不可跨越的边界

- 不恢复 LIFE 表、API、worker、日程、日记、模拟生活或离线世界。
- 不把 Persona 拆成聊天/工作两个用户模式。
- 不因更换模型、Provider 或 API 地址而回退 Persona 或阻止聊天。
- 不把 WorldBook 变成现代知识白名单。
- 不自动重放发生 409 的 TaskRun mutation；用户查看新状态后决定是否重试。
- 不让 Planner 覆盖用户锁定节点、伪造来源或把计划批准当权限。
- 不让工具绕过 ToolRegistry、PermissionGuard、ConfirmationRequest、ToolRun 和 Artifact。
- 不让插件直接读核心 SQLite、全文件系统、密钥或其他插件私有状态。
- 不记录 Provider 隐藏推理；心理活动只能是显式生成、用户可见、可清除的协议内容。
- 不在应用退出后秘密执行高成本模型或外部工具。
- 不把测试固定集的“未验证”误写成运行许可证，也不把一次通过写成永久认证。

## 13. 关键代码导航

| 领域 | 入口 |
|---|---|
| FastAPI 编排 | `backend/app/main.py` |
| Schema 与迁移 | `backend/app/db.py` |
| Persona | `backend/app/persona.py`、`persona_v2.py`、`persona_output_guard.py` |
| 模型适配 | `backend/app/llm.py` |
| 上下文 | `context_assembler.py`、`context_budget.py`、`conversation_summaries.py` |
| Memory | `memory.py`、`memory_observer_service.py`、`episodes.py`、`sagas.py` |
| KIG/PWM | `kig_pipeline.py`、`kig_retrieval.py`、`kig_evidence.py`、`pwm.py` |
| TaskRun | `task_runs.py`、`task_run_contract.py` |
| Planner | `task_planner.py` |
| 工具 | `tool_registry.py`、`tool_handlers.py`、`tool_executor.py`、`tool_runs.py` |
| 权限与确认 | `permission_guard.py`、`confirmation.py` |
| Artifact | `artifacts.py` |
| 恢复 | `recovery_policy.py`、`recovery_checkpoint.py` |
| 日志 | `backend/app/observability/`、`runtime_logs.py` |
| 聊天 UI | `frontend/src/components/ChatView.tsx` |
| 任务工作台 | `frontend/src/components/TasksPage.tsx` |
| Artifact UI | `frontend/src/components/ArtifactViewer.tsx` |
| API 客户端 | `frontend/src/api.ts` |
| Electron | `desktop/main.js`、`desktop/preload.js` |
| 开发启动 | `scripts/start-dev.ps1`、`启动遐蝶.bat` |

`main.py`、`TasksPage.tsx` 和 `ChatView.tsx` 已经较大。恢复施工时可做围绕新功能的定向拆分，但不要为了目录美观进行大规模无行为重构。

## 14. 权威文档导航

恢复顺序：

1. 本文件：暂停快照和恢复顺序。
2. `README.md` 顶部当前状态。
3. `docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md`：长期路线和不可跨越边界。
4. 对应阶段验收：`docs/reports/cyr2c-closure-acceptance.md`、`cyr2d-closure-acceptance.md`、`cyr3-closure-acceptance.md`。
5. 对应 spec/plan：`docs/superpowers/specs/` 与 `docs/superpowers/plans/`。
6. 领域文档：Memory、CTX、KIG、CIE、Observability、Persona、TaskRun。
7. `docs/archive/legacy-routes/`：只作历史证据，产品结论不再生效。

恢复前重点阅读：

- `docs/superpowers/specs/2026-08-04-cyr3-tool-permission-artifact-design.md`
- `docs/superpowers/plans/2026-08-04-cyr3-tool-permission-artifact.md`
- `docs/reports/cyr3-closure-acceptance.md`
- `docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md` 的 PLUG.0～PLUG.4 与 CYR.4 章节
- `NOTICE.md` 与 `BUILD-WINDOWS.md`

## 15. 完成恢复的判定标准

只有同时满足以下条件，才算“已经恢复施工”，而不是“代码能打开”：

- 主线、远端、分支和 PR 状态清楚，没有覆盖他人修改。
- 真实用户数据已有可恢复备份，测试使用隔离数据库。
- 后端完整测试、前端测试、生产构建、compileall 通过或失败原因已形成独立阻塞记录。
- Electron smoke 和 CYR.2D 崩溃恢复脚本在当前 Windows 环境有结果。
- Persona v2.3 启动自检、emergency 回退、Provider 配置和本地 API token 正常。
- README 与权威上下文不再把当前阶段写成 CYR.2C 或 CYR.3。
- Live2D/BGE-M3 等忽略资源的存在性和许可边界已经确认。
- 第一个新功能分支从更新后的 `main` 创建，范围明确。
- 新施工仍遵守单 Agent、LIFE 退役、权限独立、证据驱动和 body-free 诊断边界。

达到这些条件后，项目应从 PLUG.0 的设计复核开始，而不是从旧会话中猜测下一步。
