# 遐蝶 · 助手优先 Windows 桌面 Agent（实验版）

Xiadie Experiment 保留“遐蝶”的稳定身份、人格和自然表达，现阶段继续使用 Live2D 桌面入口，将主要职责收敛为现代通用 Agent：自然聊天、检索、分析、写作、编程、任务管理和受控工具执行。Live2D 是实验期过渡表现层，后期将在替代入口稳定后移除。

本仓库不再发展角色离线生活模拟。原 LIFE 生活连续性系统已完成物理退役：运行时代码、UI、API、worker、adapter 和专属数据库表已经移除，同时保留用户记忆、知识、会话连续性、任务事实和角色人格。

> 当前状态（2026-08-02）：RETIRE.0～RETIRE.3 与 LOG.1～LOG.5 实验基线已投入使用。CYR.1 已完成：单 Agent Persona v2.3 已接入，用户始终面对同一个遐蝶，不需要切换 Chat/Work；Persona 负责身份、判断与语气，WorldBook 只作为按需召回的遐蝶特殊知识库，Memory 只记录真实互动。现有 v2.2 仅作为迁移期运行回退，WorldBook 内容本阶段未改动。

Persona v2.3 只依赖资源完整性和模型基本兼容能力，不依赖逐模型“认证”才能运行。模型固定集结果仅显示为已验证/未验证并用于发布质量管理；更换模型、Provider 或接口地址不会让 Persona 回退，也不会由 Persona 强制采样参数。

## 产品方向

遐蝶始终以同一人格与用户交流，但角色感不应妨碍完成任务。

- 自然交流：自然、克制、有连续性，适度追问和主动帮助。
- 任务处理：结论优先、可验证，能持续执行并交付产物。
- Persona：保持遐蝶身份、价值判断、说话方式和事实诚实边界。
- Agent：计划、工具、权限、任务状态、恢复和审计由产品架构负责。
- Lore：按需召回的角色知识，不是现代知识白名单。
- Memory：保存真实用户事实、共同对话、项目进展和来源证据，不生成遐蝶的虚构人生。

## 核心能力

### 对话与交互

- FastAPI + SSE 流式聊天。
- 单一 Persona v2.3 根据当前请求自然调整表达；旧 `companionship` / `focused_work` 仅作为后端兼容输入。
- 消息积累窗口、活动生成取消、重新生成旧回复保护。
- 图片能力探测、大小限制、临时存储和远端逐轮授权。
- 客户端回复节奏与治理后的第三方 ContextContribution。

### 上下文与历史

- CTX ContextAssembler 统一控制最终模型请求。
- 按模型能力分配硬 token 预算。
- 当前消息和最近原文优先保护。
- 会话滚动摘要可从原消息重建。
- 跨会话历史按需召回。
- 临时聊天不进入长期记忆和跨会话召回。

### 长期记忆

- Fragment：稳定事实、偏好、边界、计划和项目状态。
- Entity：人物、项目、地点、宠物和其他真实对象。
- Episode：一段真实对话、共同项目或用户经历。
- Saga：跨较长时间的真实主题与项目演变。
- Archivist：来源保护、保留评分、归档、恢复和删除审计。
- 记忆观察器：结构化输出、逐字证据、幂等写入和有限重试。

Episode/Saga 不表示遐蝶离线期间发生的生活。没有消息、用户资料、知识来源或已完成工具结果时，不得补写经历。

### 知识库

- TXT、Markdown、PDF、DOCX 导入。
- SQLite FTS5 与本地 BGE-M3 dense embedding。
- FTS/Dense 混合召回、重排和可验证引用。
- Provider 数据位置、文档传输策略和一次性授权。
- 文档、切片、索引、引用和原文副本的完整删除生命周期。

### CDS 认知决策

CDS 提供所有领域共享的安全决策运行时：

- 有限候选 + LLM 结构化判断 + 程序验证。
- `Shadow → Advisory → Active` 晋级。
- 模型路由、隐私门、超时、重试、熔断和预算。
- DecisionRun、事件、反馈、校准和无正文诊断。

LIFE 专属日程、日记和生活事件 decision kind 已随 RETIRE.1 删除；CDS 通用核心保留，并转向 Task、Tool 和 Research 决策。

### KIG / PWM 知识治理

- SourceRef 与来源状态传播。
- Knowledge、Memory、History、Task、Lore 五源查询规划。
- 候选融合、语义重排、冲突、版本和新鲜度。
- EvidenceLink、答案支持度和引用白名单。
- 用户、项目、文档和工具事实构成的 Personal World Model。
- 实体消歧、合并、拆分和非破坏性维护。

旧 `life` 检索源与 LIFE adapter 已删除。PWM 不得保存模拟心境、虚构日程或遐蝶离线活动。

### 可观测性与诊断

现有“运行日志”是从业务表聚合出的只读审计时间线，适合回顾模型、决策、检索和上下文事件，但不是完整进程终端。LOG 路线将把它明确命名为“运行审计”，并新增独立“诊断终端”：

- 统一结构化 Logger、稳定模块名、级别、颜色和异常因果链。
- 通过 `trace_id` 关联请求、TaskRun、ToolRun、模型调用、插件和产物。
- 彩色本地终端 + 有界滚动 JSONL + 内存环形缓冲 + SSE 实时视图。
- 错误行直接显示工具、阶段、错误类型、脱敏消息和关联任务。
- 支持以 `💭` 显示插件或 Agent 显式生成、声明为用户可见的心理活动、内心独白摘要与 Feeling 状态。
- 不记录密钥、完整提示词、聊天/文件正文、记忆正文或 Provider 隐藏推理；显式角色活动使用独立协议、长度上限、会话隔离和清除规则。

详细协议、分阶段施工与验收见 [可观测性与诊断日志施工计划](docs/OBSERVABILITY_AND_DIAGNOSTIC_LOGGING_PLAN.md)。

### 主动帮助

保留 EAP 的 Presence、候选、授权、频率、安静时段、投递、反馈和取消基础设施，但重写触发来源。

允许来源：

- 用户明确设置的提醒。
- 待办或任务到期。
- 用户承诺和近期约定。
- 用户确认的重要日期。
- 工具执行完成、失败或需要用户处理。
- 尚未结束的当前会话话题。
- 有当前轮证据、用户允许的情感关心。

禁止来源：

- 遐蝶的模拟孤独、思念或联系需求。
- 离线情绪漂移。
- 模拟日记、生活事件、个人目标或日程。
- 关系数值推动的追逐、催促或情感压力。

## 已退役路线：LIFE 生活模拟

以下能力不再属于实验版目标产品：

- LifeClock 和持久 SelfState。
- 应用退出后的离线世界续演。
- 模拟精力、休息需求、活动和每日生活日程。
- 遐蝶个人目标、私人生活日记和 SelfTimeline。
- 模拟 LifeEvent 生产。
- InnerStateProjection。
- 由模拟生活驱动的主动消息。

有用户价值的内容将迁移而不是丢弃：

| 原能力 | 新归属 |
|---|---|
| 用户生日、纪念日、考试、发布日 | Memory + Reminder/Task |
| 用户约定、近期安排 | ShortMemo + Task |
| 项目目标、里程碑 | Task + MEM Episode/Saga |
| 共同经历 | MEM Episode/Saga |
| 主动提醒和结果通知 | EAP + Task/Tool |
| 用户与项目时间线 | MEM/PWM/Task |

完整迁移规范见 [助手优先架构与 LIFE 退役迁移计划](docs/ASSISTANT_FIRST_ARCHITECTURE_AND_LIFE_RETIREMENT_PLAN.md)。

## 架构

```text
Electron / PresentationAdapter（Live2D 过渡期）
        │
        ▼
React + TypeScript 主窗口
        │  本地令牌 + SSE
        ▼
FastAPI Agent Core
        ├─ Persona / Chat / Work
        ├─ CIE 交互与取消
        ├─ CTX 上下文、摘要与历史
        ├─ MEM Fragment / Entity / Episode / Saga
        ├─ Knowledge 文档、索引与授权
        ├─ CDS 结构化认知决策
        ├─ KIG / PWM 来源、证据与世界模型
        ├─ EAP 任务驱动主动帮助
        ├─ Observability / Trace / Audit / Diagnostic（LOG 路线）
        └─ Task / ToolRegistry / Permission / Artifact（后续阶段）
```

设计原则：

1. 单主控 Agent Core。
2. 人格不拥有工具权限。
3. LLM 可以提出方案，程序负责验证与执行。
4. 来源事实高于模型生成。
5. 高风险动作必须确认、可取消、可追溯。
6. 派生数据可以重建，原始用户证据不能被摘要替代。

## 专项边界

| 专项 | 现行职责 | 处理结论 |
|---|---|---|
| Persona | 身份、价值观、表达和模式 | 保留 |
| MEM | Fragment、Entity、Episode、Saga、Archivist | 保留，移除虚构人生语义 |
| Knowledge | 文档、切片、索引、授权、引用 | 保留 |
| CTX | ContextPackage、预算、摘要、历史 | 保留 |
| CDS | 通用决策运行时 | 保留，删除 LIFE decision kind |
| KIG/PWM | 来源、检索、证据、冲突、用户/项目模型 | 保留，删除 LIFE source |
| CIE/KFC | 积累、取消、图片、节奏、贡献接口 | 保留，删除 LIFE 依赖 |
| EAP | Presence、候选、授权、投递、反馈 | 改为任务和提醒驱动 |
| Affect | 当轮用户状态与表达指导 | 不再跨轮模拟遐蝶心境 |
| ShortMemo | 近期任务和上下文 | 迁入 Task/CTX/MEM |
| Observability | 结构化日志、Trace、诊断终端、支持包 | LOG.1～LOG.5 实验基线可用；LOG.6 随插件宿主施工 |
| LIFE | 离线世界、日程、日记、自我时间线 | 退役并物理删除 |

## 安全与隐私

- 后端只监听本机回环地址。
- Electron 使用临时本地 API 令牌。
- CORS 只允许明确的本地开发来源。
- 密钥、提示词和敏感正文不进入普通诊断日志。
- 本地文件不会因为“本地可检索”而自动获得远传权限。
- 图片发往远端前必须绑定 Provider、模型、位置版本和本轮授权。
- Knowledge、Memory、History、Task、Tool 结果始终以低权限资料进入模型上下文。
- 不保存或展示 Provider 隐藏 chain-of-thought、reasoning token 和系统内部推理草稿；允许保存并展示通过受控字段显式生成、明确标记为 AI 角色表达的心理活动与内心独白。
- 不编造工具执行、文件修改、实时信息或现实身体活动。

## 仓库结构

```text
Xiadie-experiment/
├─ backend/          FastAPI、SQLite、Agent Core 与领域服务
├─ frontend/         React、TypeScript、Vite 主窗口
├─ desktop/          Electron、Live2D、托盘与本地进程管理
├─ docs/             权威设计、专项计划、ADR、报告和迁移规范
├─ scripts/          启动、构建和验证脚本
└─ demo/             演示资源
```

## 本地开发

### 环境

- Windows 10/11
- Python 3.10+
- Node.js 18+
- npm / pnpm（按各子项目锁文件）

### 实验版端口与身份

- 后端：`127.0.0.1:9756`
- Vite：`127.0.0.1:6173`
- AppData/日志根：`Xiadie-Experiment`
- Electron App ID：`com.xiadie.agent.experiment`

实验版不得回落正式版的 8756/5173、AppData 或单实例锁。

### 一键启动

双击：

```text
启动遐蝶.bat
```

### 分进程启动

```powershell
# 后端
cd backend
.\.venv\Scripts\python.exe run.py

# 前端
cd frontend
npm.cmd run dev

# Electron
cd desktop
npm.cmd start
```

## 测试

```powershell
# 后端
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q

# 前端
cd frontend
npm.cmd test
npm.cmd run build
```

2026-08-02 最新门禁：后端 `2510 passed`；CYR.1 相关后端 `91 passed`；前端 `80 passed`；Vite 生产构建与 Python `compileall` 通过。现存提示仅为 Starlette/httpx 弃用提醒、测试缓存目录权限提醒，以及 Live2D Classic 脚本的既有 Vite 打包提示。上一 LOG 检查点的 Electron 入口脚本与真实本机鉴权 HTTP 诊断冒烟继续有效，本轮未修改对应链路。

退役施工必须额外验证：

- 普通聊天不读取或写入 LIFE 表。
- 启动和退出不运行 LIFE worker。
- KIG 不再选择 `life` 来源。
- 主动候选不能来自模拟生活或跨轮心境。
- Memory、Knowledge、CTX、Episode/Saga 和用户日期迁移不丢失。
- 全新数据库不创建 LIFE 专属表。

## 文档入口

| 文档 | 用途 |
|---|---|
| [助手优先架构与 LIFE 退役迁移计划](docs/ASSISTANT_FIRST_ARCHITECTURE_AND_LIFE_RETIREMENT_PLAN.md) | 助手优先产品与退役迁移规范 |
| [可观测性与诊断日志施工计划](docs/OBSERVABILITY_AND_DIAGNOSTIC_LOGGING_PLAN.md) | Logger、Trace、ToolRun、诊断终端与支持包施工规范 |
| [CYR.1 单 Agent 与 Persona v2.3 施工计划](docs/CYR1_SINGLE_AGENT_PERSONA_V23_PLAN.md) | 单一遐蝶 Agent、自动表达策略、Persona 版本回退与 WorldBook 边界 |
| [Cyrene 风格实验计划](docs/CYRENE_STYLE_AGENT_EXPERIMENT_PLAN.md) | 单 Agent 行为质量与能力分层实验路线 |
| [Cyrene 风格助手长期规划](docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md) | Task、Tool、Research、MCP 与 Worker 长期路线 |
| [项目上下文](docs/CODEX_PROJECT_CONTEXT.md) | 开发与治理约束 |
| [专项所有权矩阵](docs/SPECIALTY_OWNERSHIP_AND_CONTRACT_MATRIX.md) | 各领域唯一写入者和接口 |
| [长期路线图](docs/XIADIE_LONG_TERM_ROADMAP.md) | 后续 Task/Tool/Agent 路线 |
| [记忆系统](docs/MEMORY_SYSTEM_DESIGN_FOR_BEGINNERS.md) | MEM 设计与来源边界 |
| [上下文系统](docs/CONVERSATION_CONTEXT_AND_SUMMARY_PLAN.md) | CTX 预算、摘要和历史 |
| [知识治理与 PWM](docs/XIADIE_KNOWLEDGE_INTELLIGENCE_GOVERNANCE_AND_WORLD_MODEL_PLAN.md) | KIG/PWM 设计 |
| [KFC/CIE 交互增强](docs/KFC_COMPANION_INTERACTION_ENHANCEMENT_PLAN.md) | 聊天交互、取消、图片和贡献接口 |
| [退役路线文档归档](docs/archive/legacy-routes/README.md) | LIFE、LIFE v2 与旧生活化 Affect/EAP 历史路线 |

历史 LIFE、旧 Affect/EAP、早期 jiwen 融合和 LIFE v2 路线文档已集中到 `docs/archive/legacy-routes/`。历史 ADR 与阶段报告继续按原编号保留审计证据；其中与现行规范冲突的产品结论已经失效。

长期路线末尾维护统一的“临时兼容与退场台账”，覆盖 Persona v2.2、旧记忆候选/兼容 API、ShortMemo、旧摘要字段、内建 Affect/Relationship、旧 Lore 桥、主动陪伴适配、日志协议与 Live2D。它们只能在数据迁移、真实使用、兼容窗口、诊断和回滚门槛全部满足后删除；保留用户真实记忆不等于永久保留旧记忆实现。

## 路线图

1. `[x]` RETIRE.0：文档、所有权和迁移边界冻结。
2. `[x]` RETIRE.1：删除 LIFE 运行时、API、UI、adapter 和双 Profile。
3. `[x]` RETIRE.2：迁移用户日期、约定、任务和 ShortMemo 设置。
4. `[x]` RETIRE.3：Schema 84 备份并删除 LIFE 专属表。
5. `[x]` LOG.0：可观测性、诊断日志、隐私和 ToolRun v2 协议冻结。
6. `[x]` LOG.1～LOG.5 实验基线：统一 Logger、TraceContext、实时诊断终端、Electron 日志和支持包；发布级故障注入与负载硬化继续保留为门禁。
7. `[-]` CYR.1～CYR.3：单 Agent Persona v2.3、TaskRun、ToolRegistry、权限、产物和恢复；CYR.1 已完成。
8. `[ ]` PLUG.0～PLUG.4：MoFox 风格插件宿主、Manifest、生命周期、权限和隔离；Feeling 作为插件候选。
9. `[ ]` Web/Research、文件与代码工具、MCP 接入。
10. `[ ]` PresentationAdapter 解耦并在替代入口稳定后移除 Live2D。
11. `[ ]` 单 Agent 多场景行为评测和产品冻结。

## 许可证

项目代码遵循仓库 [LICENSE](LICENSE)。第三方模型、Live2D、字体、KFC 参考包和其他资产分别受其原许可证约束；源码级复用前必须确认兼容性和再分发权。
