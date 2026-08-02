# 遐蝶 Codex 项目上下文

> 助手优先路线更新（2026-08-02）：`Xiadie-experiment` 已物理移除 LIFE 生活模拟。Persona、WorldBook 和 ShortMemo 中有通用价值的部分继续保留，但 ShortMemo 迁入 Task/CTX/MEM，InnerStateProjection 删除。旧路线文档集中归档到 `docs/archive/legacy-routes/`；LOG.1～LOG.5 与 CYR.1/CYR.1S 已完成，当前推进 CYR.2 TaskRun，之后才进入 ToolRegistry 与插件宿主。

> 状态：当前执行约束  
> 适用对象：Codex、维护者和后续参与开发的协作者  
> 项目根目录：`E:\Xiadie\Xiadie-experiment`
> 当前产品基线：v0.1.0  
> 最后更新：2026-08-02

## 1. 使用方式

每次开始遐蝶开发任务前，必须先阅读本文件，再阅读任务对应的长期路线章节。

本文件负责回答：

- 遐蝶是什么。
- 当前项目已经实现了什么。
- 哪些技术和产品决策已经冻结。
- 哪些旧路线已经失效。
- Codex 每轮可以做什么、不能做什么。
- 修改完成后必须如何验证和交付。

如果用户的新指令明确改变了本文件中的决策，应先说明影响，创建或更新 ADR，再修改本文件；不得在普通功能提交中静默改变项目方向。

---

## 2. 产品定位

遐蝶是一个本地优先、常驻 Windows 桌面的助手优先 Agent。她保留稳定角色人格和自然陪伴表达，但主要职责是完成检索、分析、写作、编程、任务管理与受控工具执行，而不是模拟离线生活。

当前阶段首先保证：

- 桌宠入口自然、稳定。
- 主窗口聊天、任务、记忆和模型配置可用。
- 用户数据保存在本机并可控。
- 后续工具能力具备最小权限、确认、审计和恢复机制。

最终形态不是“拥有无限权限的全能 AI”，而是一个用户始终看得见、管得住、停得下、能追溯的桌面 Agent。

目标体验：

```text
启动应用
  → 默认只显示 Live2D 桌宠
  → 点击桌宠或托盘打开单一主窗口
  → 在主窗口聊天、管理任务和记忆、交付资料
  → Agent 形成可见计划并调用受控工具
  → 高风险动作请求用户确认
  → 展示执行过程、来源、产物和审计记录
```

---

## 3. 权威文档顺序

发生冲突时，按照以下顺序判断：

1. 用户在当前任务中的明确指令。
2. `docs/ASSISTANT_FIRST_ARCHITECTURE_AND_LIFE_RETIREMENT_PLAN.md`。
3. 当前任务对应的现行专项计划；TaskRun 以 `docs/CYR2_TASKRUN_EXECUTION_WORKBENCH_PLAN.md` 为准，日志施工以 `docs/OBSERVABILITY_AND_DIAGNOSTIC_LOGGING_PLAN.md` 为准。
4. `docs/CYRENE_STYLE_AGENT_EXPERIMENT_PLAN.md` 与 `docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md`。
5. 本文件。
6. `docs/XIADIE_LONG_TERM_ROADMAP.md`。
7. 仓库内已接受且未被助手优先路线取代的 ADR。
8. MEM、CTX、Knowledge、EAP、CDS、KIG、CIE、Persona 专项中未冲突的部分。
9. `docs/archive/legacy-routes/`、旧 LIFE/Affect/EAP 生活化段落和旧多 Agent 文档只作历史参考。

设计文档的 v0.3、v0.5、v0.6 是文档修订号，不是应用发布版本。应用版本从当前 v0.1.0 继续推进。

任务专项施工基线：

- 记忆系统最终形态与已完成阶段：`docs/MEMORY_SYSTEM_DESIGN_FOR_BEGINNERS.md`。
- 知识库优化 K.0～K.9：`docs/KNOWLEDGE_SYSTEM_OPTIMIZATION_PLAN.md`。该计划已完成并通过总验收；
  自然召回、远传策略、一次性授权、记忆隔离和生命周期均以 ADR-0036～ADR-0044 为准。
- 对话上下文 CTX.0～CTX.7：`docs/CONVERSATION_CONTEXT_AND_SUMMARY_PLAN.md`。该计划已完成总验收并通过独立 strict review；
  schema 45 与上下文 v1 已冻结，普通自动历史召回继续 shadow。
- 已关闭专项：`docs/archive/legacy-routes/EMOTION_RELATIONSHIP_AND_PROACTIVE_COMPANION_PLAN.md` 第 9.B 节 EAP.R0～EAP.R6。Schema 48～60 与六个 EAP 协议已通过独立 strict review 并正式冻结；不得另建重复情绪、关系或主动投递源。
- 退役专项：`docs/archive/legacy-routes/LLM_DECISION_AND_LIFE_CONTINUITY_PLAN.md`。LIFE.0～13 的历史施工和验收事实保留，但其产品结论已被助手优先退役计划取代。实验版不得新增 LIFE 写路径、运行时消费或前端入口。
- Persona/WorldBook/ShortMemo：保留通用能力；ShortMemo 迁出 LIFE，InnerStateProjection 退役。

---

## 4. 冻结的产品决策

除非用户明确批准路线调整，以下决策不得改变：

### 4.1 桌面形态

- 应用使用 Electron，不迁移到 Tauri。
- 默认启动只显示 Live2D 桌宠。
- 点击桌宠、托盘或快捷入口后打开主窗口。
- 主功能放在一个主窗口内，通过页面、面板或抽屉切换。
- 不采用启动时同时打开聊天、任务、设置等多个窗口的路线。

### 4.2 UI 方向

- 保留当前三栏主窗口的信息结构。
- 视觉保持紫蓝、深夜色、玻璃拟态、圆角和柔光方向。
- UI 语义应是“桌面伴侣”，不是工程控制台。
- 左侧承担导航和会话，中央承担主要交互，右侧承担遐蝶状态和摘要。
- 旧功能不能因为视觉改造而丢失。

### 4.3 Live2D 策略

- Live2D 是实验期过渡表现层，不再是长期不可替换的核心架构。
- 当前继续从固定内置路径加载，不扩展用户导入、模型市场或模型切换。
- Agent Core 只输出 `PresentationIntent`，由 `PresentationAdapter` 适配 React、Live2D 或未来桌面壳。
- 模型缺失或 adapter 关闭时，主窗口、托盘、聊天、任务和诊断必须独立可用。
- 先完成表现层解耦和非 Live2D 入口验收，再在实验路线后期移除 renderer、IPC、设置和资产链。
- 移除前使用的资产仍必须原创或具有明确再分发授权。

### 4.4 Agent 形态

- 当前及近期保持单主控 Agent Core。
- 先完成 ToolRegistry、权限、任务状态、产物和恢复，再拆 Worker Agent。
- 多模型路由不等于多 Agent。
- Worker 只能在统一 Scheduler、PolicyGuard 和审计体系下运行。
- 多 Agent 不得表现为多个角色争夺最终回答权。

### 4.5 助手优先与 LIFE 退役

- LIFE 不再是可切换产品 Profile；退役迁移完成后实验版只有助手优先路线。
- 不生成 LifeClock、SelfState、模拟日程、离线生活、遐蝶个人目标、日记或 SelfTimeline。
- Affect 只保留当轮用户状态理解与表达指导；Relationship 只管理真实互动支持的距离、信任和边界。
- 主动行为只由任务、提醒、承诺、重要日期、工具结果、OpenThread 或当前轮有证据的关心触发。
- 用户重要日期、约定和项目事实必须先迁移到 Memory/Task/Reminder，再删除 LIFE 数据结构。
- KIG 检索源不再包含 `life`；PWM 不得保存模拟生活或虚构心境。

### 4.6 可观测性与插件边界

- “运行审计”保存授权、执行和结果等业务事实；“诊断终端”显示实时结构化运行事件，两者不得混为第二套业务状态。
- “运行审计”仍是业务表聚合视图；LOG.1～LOG.5 实验基线已另行提供统一 Logger、JSONL、TraceContext、ToolRun v2、诊断 SSE 和前端“诊断终端”。两套界面职责不同，不得用实时日志替代业务权威状态。
- 日志不得保存密钥、完整提示词、聊天/文件/记忆正文或 Provider 隐藏 chain-of-thought。插件或 Agent 通过 `mental-activity-log-v1` 显式生成并标记为 `user_visible` 的心理活动、内心独白摘要与 Feeling 状态允许本地记录和展示。
- 插件宿主必须建立在 TaskRun、ToolRegistry、PermissionGuard 和 Observability 之上；插件不能直接访问全库、全文件系统或核心日志 sink。
- Feeling 如后续实现，应作为受治理插件候选；允许维护会话隔离、可衰减的情绪状态，并将情绪、强度、短原因与显式心理活动显示在日志中，但不得恢复 LIFE 离线世界、关系压力或未授权主动动机。

---

## 5. 冻结的技术路线

| 层级 | 技术 | 长期职责 |
| --- | --- | --- |
| 桌面壳 | Electron | 窗口、托盘、IPC、安全存储、系统集成和打包。 |
| 前端 | React + TypeScript + Vite | 主窗口、桌宠渲染、状态展示和用户确认。 |
| 后端 | Python + FastAPI | Agent Core、模型接入、工具、权限、任务和知识。 |
| 本地存储 | SQLite | 会话、消息、任务、记忆、配置和审计。 |
| 模型协议 | OpenAI-compatible 基础适配 | 多供应商统一聊天和后续工具调用。 |
| 表现层 | PresentationIntent + PresentationAdapter | 隔离 Agent Core 与 React/Live2D；Live2D 仅为过渡 adapter。 |

CYR.1 产品口径只有一个 Agent：Persona 决定遐蝶的身份、价值判断和表达，WorldBook 是按需召回的遐蝶特殊知识库，Memory 是真实用户互动，底层模型、CTX、Knowledge、Task 和 Tool 共同提供普通 Agent 能力。`companionship/focused_work` 不再作为用户模式或业务状态；Persona v2.3 在同一 Prompt 内根据本轮请求自然调整表达。

不得为了统一语言而把 Python 后端整体改写为 TypeScript，也不得为了采用新框架而推倒现有前端或 Electron 壳。

---

## 6. 当前代码结构

```text
Xiadie/
├─ backend/
│  ├─ app/
│  │  ├─ main.py       # FastAPI 路由和聊天编排
│  │  ├─ db.py         # SQLite Schema 和存储基础
│  │  ├─ llm.py        # OpenAI-compatible 模型调用
│  │  ├─ memory.py     # L0/L1/L2 记忆逻辑
│  │  └─ persona.py    # 遐蝶系统提示构建
│  ├─ tests/            # 后端 API 测试
│  └─ run*.py           # 开发及冻结运行入口
├─ frontend/
│  ├─ src/
│  │  ├─ App.tsx       # 主窗口顶层组合
│  │  ├─ api.ts        # 前端 API 客户端
│  │  ├─ pet.tsx       # Live2D 桌宠页面
│  │  └─ components/   # 聊天、任务、记忆、文件、设置等页面
│  └─ public/           # 本地 Live2D 资源；受授权限制且不进入 Git
├─ desktop/
│  ├─ main.js           # Electron 生命周期、窗口、托盘和后端启动
│  ├─ preload.js        # 受控 IPC 桥接
│  └─ electron-builder.yml
├─ scripts/             # 构建和开发启动脚本
└─ docs/                # 权威上下文、长期路线、基线和 ADR
```

后续允许逐步拆分文件，但不能仅为了目录看起来漂亮而进行无行为价值的大重构。

---

## 7. 当前能力基线

### 7.1 已经真实可用

- Live2D 桌宠、托盘、右键菜单和主窗口。
- 桌宠点击、拖动、状态气泡和情绪动作。
- 会话创建、删除、自动标题和历史消息。
- SSE 流式聊天、错误卡、复制、收藏和重新生成。
- DeepSeek、OpenAI、GLM、Qwen、Kimi、OpenRouter、SiliconFlow、Ollama 和自定义 OpenAI-compatible Provider 配置。
- Mock 演示模型。
- L0/L1/L2 记忆的增删改查、启用和对话注入。
- 任务创建、状态流转、删除和从对话创建任务。
- Windows 构建脚本和 `启动遐蝶.bat` 开发入口。
- 用户明确选择的 TXT/Markdown/PDF/DOCX 可经过类型、容器、大小、配额和恶意内容校验后原子保存到应用
  数据目录；后台 worker 生成稳定 locator、contentless FTS 和本地 BGE-M3 dense 向量，支持混合召回、
  可验证对话引用、重建与可重试删除；模型失败时完整降级 FTS。
- LOG.1～LOG.5 实验诊断基线：后端与 Electron 统一结构化事件、人类终端、滚动 JSONL、TraceContext、
  5,000 条/8 MiB 内存缓冲、游标/gap/SSE、前端实时诊断终端、ToolRun v2 状态与详情、显式用户可见
  心理活动日志，以及默认排除心理活动正文和其他敏感正文的支持包。

### 7.2 只有骨架或占位

- 文件与知识已有 schema 35：在原完整闭环上增加文档远传策略和 Provider 执行位置地基；仍不会在普通陪伴对话中自动查询用户文件。扫描 PDF OCR、表格/图片
  资料解析和审计长期归档策略尚未实现。
- 运行审计已能只读聚合模型调用元数据、决策摘要、检索、上下文组装和现有 `tool_logs`；
  聊天事件可按需查看本地持久化的一轮用户输入与助手最终回复，但不展示隐藏思维链、系统提示词、密钥、知识正文或记忆正文。该视图不是诊断终端，也不能替代 CIE 固定集与专项 smoke；工具分类仍没有真实 `ToolRegistry` 调用写入。
- ToolRun v2 的 Schema、Repository、状态机和包装器已经可用，但现阶段尚无正式 ToolRegistry；未来文件、Web、代码和插件工具必须通过包装器接入，旧 `tool_logs` 仅只读兼容。
- 可观测性正式发布硬化尚未完成 Windows 打包态只读目录、磁盘不足、慢 SSE 客户端和 1,000 events/s 故障注入；实验版日常诊断不再等待这些发布门禁。
- 权限设置没有后端策略执行。
- Live2D 设置多数没有真实持久化和 IPC 行为。
- 数据导出、备份和恢复尚未实现。
- Provider 能力标签主要依赖模型名称推断。
- CTX.5 已建立本地两阶段跨会话历史召回：明确回忆可注入真实完整轮次，普通问答先 shadow；不向普通聊天展示技术来源。
- CTX.6 已增加与长期记忆独立的“参考过往聊天”开关、摘要注入开关、摘要重建/派生删除、历史索引重建和无正文高级诊断；普通聊天已移除技术性记忆/知识计数。
- CTX.7 已完成 5/20/100/500 轮合成压力、摘要六类样本、跨会话固定集和 Windows 重启/断网恢复验收；schema 45 与上下文 v1 协议冻结，普通自动召回继续 shadow。

### 7.3 当前已知优先风险

- FastAPI 已使用会话级随机令牌，并将 CORS 限制为明确的本机来源；正式安装包仍需验证后端重启链路。
- API Key 已经由 SecretStore 抽象隔离，但开发期实现仍是未加密的本地 SQLite，正式版还需 safeStorage。
- 重新生成已改为新回复成功后原子替换，并有失败保留旧回复回归测试。
- CTX.0～CTX.7 已完成实现、内部总验收与独立 strict review；审查确认 0 个未解决 P0/P1，schema 45 与上下文 v1 已正式冻结。
- EAP v0.2 已落地 Schema 48～55 和独立领域模块，但完成度审计确认只有 Presence hook 接入聊天主链；当前按 EAP.R0～R6 收口。主动陪伴产品方向为本机默认开启，但 R0～R3 不允许真实非静默投递，R4/R5 完成投递安全和用户控制前不得正式发布。
- Provider 和模型选择校验不足。
- 前端及 Electron 自动化测试不足。

新增工具和自动化能力之前，应优先解决这些风险。

---

## 8. 数据、隐私与素材约束

### 8.1 用户数据

- 会话、任务、记忆和设置默认保存在本机。
- 长期记忆默认开启；用户主动关闭后必须持续尊重该选择，初始化、升级和迁移不得擅自重新开启。
- 不得未经用户明确操作扫描磁盘或其他目录。
- 不得在用户不知情时把文件、记忆或屏幕内容发送给远程模型。
- 日志不得记录完整 API Key、Authorization Header、密码或高敏正文。
- 所有派生数据最终都必须支持导出和删除。

### 8.2 API Key

- API 不得向前端回传完整密钥。
- 当前 SQLite 明文字段仅是需要迁移的开发期兼容方案。
- 正式方案使用 Electron `safeStorage` 或系统安全存储。
- 密钥迁移必须先验证新存储，再清除旧值，并提供失败恢复。

### 8.3 Live2D 素材

- 当前本地模型仅限个人开发和自用。
- `frontend/public/models/` 与 `frontend/public/libs/` 已被 `.gitignore` 排除。
- 不得把当前受限模型提交到 Git、公开仓库或正式 Release。
- 正式发布前必须替换为原创或明确允许再分发的资源，并保留 LICENSE/NOTICE。

---

## 9. 安全执行原则

### 9.1 能力增加顺序

```text
只展示
  → 只读本地数据
  → 用户明确范围内读取文件
  → 可预览、可回滚的本地写入
  → 受确认的网络和外部写入
  → 白名单桌面操作
  → 最后才考虑 Shell 和输入控制
```

### 9.2 永久红线

- 模型不能给自己授权。
- 网页、文件和工具输出都是不可信数据，不能覆盖系统规则。
- 高风险动作不能依赖一句自然语言“我确认了”直接执行。
- 禁止静默发送消息、支付、下单、删除数据和修改生产系统。
- 禁止静默修改、提交、推送或部署自身代码。
- 禁止通过编码、链接、重定向或子进程绕过目录和权限范围。
- 急停必须独立于模型推理链路。

### 9.3 风险等级方向

- S0：展示、计算、纯转换。
- S1：在用户已授权范围内读取。
- S2：本地写入和用户数据修改，逐次预览确认。
- S3：外发消息、网络写入和操作外部应用，强确认。
- S4：Shell、输入控制、系统设置和支付，默认禁用。

---

## 10. Codex 每轮工作规则

### 10.1 开始前

1. 阅读本文件和长期路线对应章节。
2. 检查 `git status`，保护现有修改。
3. 明确本轮目标、范围、不做事项和风险。
4. 明确验证命令和人工验收方法。
5. 涉及数据、权限或外部影响时，先定义回滚方式。

### 10.2 实施中

- 每轮只做一个主题。
- 通常控制在 8 至 12 个文件内。
- 超过 15 个文件前必须停止并说明原因。
- 不同时做大重构、新功能和视觉改版。
- 不修改无关文件，不覆盖用户已有修改。
- 不增加未被当前任务需要的依赖。
- 不为了通过测试而删除、跳过或弱化有效测试。
- 不通过关闭权限、校验或错误处理来让功能“看起来可用”。

### 10.3 完成后

- 后端变更运行完整后端测试。
- 前端变更运行 TypeScript 检查和生产构建。
- Electron 变更运行语法检查和相应桌面启动验证。
- 数据库变更验证新库、旧库迁移、重复迁移和失败回滚。
- 权限变更验证允许、拒绝、取消、超时和越权。
- 文件变更验证路径逃逸、大小、编码、并发修改和失败恢复。
- 输出修改文件、行为变化、验证结果、风险和下一步。
- 形成单一目的提交并推送；不得把受限素材、密钥、数据库和构建产物提交。

---

## 11. 验证命令基线

### 11.1 后端

```powershell
cd E:\Xiadie\Xiadie\backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

当前已知基线：469 项测试通过（CTX.4 统一 ContextAssembler 与摘要注入，schema 43）。

### 11.2 前端

```powershell
cd E:\Xiadie\Xiadie\frontend
npm.cmd run build
```

### 11.3 Electron

```powershell
cd E:\Xiadie\Xiadie\desktop
node --check main.js
node --check preload.js
```

涉及窗口、托盘、IPC、后端拉起或打包资源时，仅做语法检查不够，还必须实际启动验证。

### 11.4 开发启动

依赖安装完成后，可以双击仓库根目录的 `启动遐蝶.bat`。

---

## 12. Git 与版本纪律

- 主分支为 `main`。
- 每个提交只表达一个目的。
- 提交前运行 `git diff --check` 和对应验证。
- 不使用破坏性 reset 覆盖未知修改。
- 不提交 `.env`、数据库、虚拟环境、node_modules、构建产物和受限模型。
- 小任务完成后提交并推送；小版本完成后更新 README、状态、CHANGELOG 和路线，再创建标签。
- 数据库 Schema、应用版本、安装器版本和迁移版本必须逐步统一。

---

## 13. 当前近期顺序

本节保留项目早期 v0.1 治理顺序作为历史约束；其中多项已经完成。当前具体施工顺序以用户当轮指令及对应专项
计划为准。知识库 K.0～K.9 已完成；后续扩展必须另立阶段并继续沿用该计划的 review 与验收规则。

严格按以下顺序推进：

1. 创建本文件，固化项目上下文。
2. 创建 `docs/BASELINE_STATUS.md`，记录可复现运行基线。
3. 创建 `docs/PR_CHECKLIST.md` 和 ADR 模板。
4. 设计并实现 Electron 到 FastAPI 的本地访问令牌。
5. 收紧 CORS 和健康接口暴露。
6. 建立 SecretStore 接口和 safeStorage 迁移方案。
7. 修复重新生成失败丢失旧回复。
8. 增加 Provider/Model 严格校验和统一错误结构。
9. 建立上下文预算和长会话摘要。
10. 完成 v0.1.1/v0.1.2 回归和版本收尾。

完成这些事项前，不开始文件写入、浏览器操作、外部消息、桌面自动化或多 Agent。

---

## 14. 当前专项入口

当前产品与施工入口按顺序为：

1. `docs/ASSISTANT_FIRST_ARCHITECTURE_AND_LIFE_RETIREMENT_PLAN.md`
2. `docs/OBSERVABILITY_AND_DIAGNOSTIC_LOGGING_PLAN.md`
3. `docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md`
4. `docs/CYRENE_STYLE_AGENT_EXPERIMENT_PLAN.md`
5. `docs/SPECIALTY_OWNERSHIP_AND_CONTRACT_MATRIX.md`

历史上知识库 F.1～F.8、K.0～K.9、CTX.0～CTX.7、EAP.R0～R6、CDS.0～13、LIFE.0～13、KIG.0～15、CIE.0～6 与 LIFE2.0～6 均已完成各自施工。其 Schema、测试和 Review 事实继续有效，但产品方向已改变：LIFE 退役，Persona/WorldBook/ShortMemo 拆分保留，其他专项按助手优先矩阵重新接线。

RETIRE.0～RETIRE.3 已于 2026-08-01 完成，现有数据库已经备份、迁移并删除 LIFE 表。LOG.0 已于 2026-08-02 冻结；当前固定施工顺序为 `LOG.1 → LOG.2 → LOG.3/4/5 → CYR.1 → CYR.2 → CYR.3 → PLUG.0`。未完成 ToolRegistry、权限、产物和恢复前不得开放任意 Shell、任意文件系统、桌面输入控制或外部消息发送。

EAP 的最终授权复核、恢复保护窗、at-most-once 投递与外部渠道硬门继续有效；KIG 的 SourceRef、证据、版本/新鲜度与 PWM 可重建原则继续有效；CIE 的取消、图片授权与 ContextContribution 治理继续有效。LIFE adapter、life source、InnerStateProjection 和生活化主动 seed 不再受“冻结兼容”保护，应按退役计划删除。
