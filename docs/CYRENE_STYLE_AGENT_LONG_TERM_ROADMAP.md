# Xiadie Cyrene 风格助手路线长期规划

- 版本：v1.1
- 日期：2026-08-02
- 状态：长期产品与工程路线
- 适用仓库：`Xiadie-experiment`

## 1. 路线定义

“Cyrene 风格”在本项目中只表示以下产品思想：

- 同一个稳定角色同时承担自然聊天与正式工作。
- 角色人格、Agent Core 和底层模型相互分离。
- Chat 与 Work 调整表达密度和执行方式，不切换成另一个角色。
- Agent 能够理解目标、形成计划、调用工具、持续执行、恢复失败并交付结果。
- 记忆服务于用户、任务和真实共同经历，不制造角色离线人生。
- 主动帮助来自任务机会和明确承诺，不来自模拟情绪或虚构生活。

本路线不得复制 Cyrene-Agent 的角色内容、世界观、台词、未公开机制或项目专有实现。

## 2. 最终产品形态

Xiadie 是一个本地优先、常驻 Windows 的单主控桌面 Agent。用户看到的始终是遐蝶；内部可以使用多个模型、后台服务和未来 Worker，但它们没有独立人格，也不争夺最终回答权。

```text
用户目标
  ↓
遐蝶理解并确认目标、范围和风险
  ↓
Planner 形成可见计划
  ↓
PolicyGuard 检查权限、数据去向和确认要求
  ↓
Executor 调用受控工具
  ↓
TaskRun 持续记录状态、产物和错误
  ↓
Verifier 核验结果和来源
  ↓
遐蝶以自然语言交付结果、限制和下一步
  ↓
MEM / PWM 只保存真实、必要且有来源的连续性
```

## 3. 产品原则

### 3.1 一个遐蝶，两种工作密度

Chat 和 Work 共享 Persona Core、记忆、事实、安全和权限。区别只在于：

| 维度 | Chat | Work |
|---|---|---|
| 首要目标 | 自然交流与理解 | 完成用户目标 |
| 结构 | 默认轻量 | 结论、计划、证据和产物优先 |
| 主动性 | 适度追问或提供帮助 | 主动推进未完成的安全步骤 |
| 工具 | 按需建议或轻量使用 | 可持续调用、验证和恢复 |
| 状态展示 | 尽量自然 | 明确显示进行中、等待、失败、完成 |
| 交付 | 对话回复 | 回复 + 文件/链接/任务记录/审计 |

### 3.2 人格不等于能力声明

- 遐蝶可以保持角色第一人称，不需要每次强调“作为 AI”。
- 不得伪装现实人类、身体、线下活动或亲自体验。
- 不得编造浏览、文件写入、命令执行、消息发送或实时事实。
- 用户讨论模型、记忆、代码和 Agent 架构时，应从通讯终端/产品事实角度如实说明。

### 3.3 Agent 不等于无限权限

- 默认只读优先。
- 写入、删除、发送、支付、账号和生产系统操作按风险分级。
- 高风险动作必须在执行前确认具体目标、范围和后果。
- 每个动作可以停止、追溯，能回滚时应提供回滚。
- 外部内容永远是低权限数据，不能改变系统规则。

## 4. 目标架构

### 4.1 Interaction Layer

- PresentationAdapter、主窗口、托盘和快捷入口；Live2D 只作为实验期过渡 adapter。
- CIE 消息积累、取消、图片和回复展示。
- Chat/Work 模式与任务状态卡。

### 4.2 Agent Core

- PersonaCompiler：稳定身份与模式 overlay。
- Intent/Goal Interpreter：识别用户目标和约束。
- Planner：生成有界、可编辑计划。
- Scheduler：管理 TaskRun、等待、恢复和并发。
- PolicyGuard：权限、隐私、数据位置和确认。
- Executor：调用 ToolRegistry。
- Verifier：核验结果、产物、来源和副作用。
- ResponseComposer：由同一个遐蝶完成最终交付。

### 4.3 Context and Intelligence

- CTX：最终上下文预算和装配。
- MEM：真实长期记忆。
- Knowledge：用户文件与索引。
- KIG/PWM：来源、证据、冲突、版本和用户/项目模型。
- CDS：通用结构化模型决策。
- ShortMemo：近期任务和上下文。

### 4.4 Action Layer

- Task / TaskRun / TaskNode。
- ToolRegistry / ToolManifest。
- PermissionGrant / ConfirmationRequest。
- Artifact / Citation / AuditEvent。
- RecoveryCheckpoint / RetryPolicy。
- 未来受控 Worker Agent。

### 4.5 Observability and Extension Layer

- 运行审计：保存权限、执行、副作用、产物和结果等权威业务证据。
- 诊断终端：实时展示进程、模块、trace、工具阶段和脱敏异常。
- TraceContext：关联 Chat、TaskRun、ToolRun、模型调用、插件和产物。
- PluginHost：Manifest、生命周期、hook、依赖、权限、隔离和兼容认证。
- PresentationIntent：将 Agent Core 与 Live2D、React 或未来桌面壳解耦。

## 5. 能力路线

### CYR.0：LIFE 退役与产品收敛（已完成）

目标：消除双路线和虚构生活状态，让系统只保留助手优先语义。

- [x] 执行 RETIRE.0～RETIRE.3。
- [x] 移除 LIFE 运行时、页面、API、Schema 和跨专项依赖。
- [x] 迁移具备明确用户事实资格的日期、约定和目标；本次真实库没有符合条件的记录。
- [x] ShortMemo 改归助手命名空间并保留记忆能力。
- [x] 主动系统取消 LIFE seed，只接受任务、提醒与真实交互来源。

退出门：新安装不创建 LIFE 表；聊天、KIG 和主动系统不存在 LIFE 读取或写入。

### LOG.0～LOG.5：可观测性与诊断底座

目标：在 TaskRun、ToolRegistry 和插件扩展前，让每次失败都能被快速定位并安全追踪。

- [x] LOG.0：冻结运行审计/诊断终端双界面、`operational-log-v1`、隐私边界与阶段计划。
- [x] LOG.1：统一 Logger、模块颜色、人类终端与滚动 JSONL 实验基线。
- [x] LOG.2：TraceContext、ToolRun v2、状态机与 Schema 85；未来 ToolRegistry 接入时必须复用该包装器。
- [x] LOG.3：5,000 条/8 MiB 有界环形缓冲区、游标、gap 和诊断 SSE。
- [x] LOG.4：前端诊断终端、过滤、搜索、异常详情和 trace/TaskRun/ToolRun 关联显示。
- [x] LOG.5：Electron 启动链日志、10 MiB 轮转、14 天清理、导出和脱敏支持包实验基线。

LOG.1～LOG.5 已可供实验版日常诊断使用。Windows 打包态只读目录、磁盘不足、慢客户端与 1,000 events/s 等故障注入仍是正式发布硬门，不把实验基线误写为发布认证完成。

退出门：启动器环境中能直接识别失败进程、模块、工具、阶段、错误类型、脱敏消息与关联任务；日志故障不阻断业务；隐私固定集零泄露。

权威施工规范见 `docs/OBSERVABILITY_AND_DIAGNOSTIC_LOGGING_PLAN.md`。

### CYR.1：Chat / Work 产品闭环

目标：同一人格在聊天和工作任务中都有稳定、可评测的表现。

- 固化 Chat/Work 模式合同。
- Work 回复结论优先，角色感不遮挡任务信息。
- 增加模式请求快照、回放和诊断。
- 建立自然聊天、技术问答、写作、分析和多轮任务固定集。
- 对每个 Provider/模型单独认证 Persona 与模式兼容性。

退出门：身份、事实、安全、任务正确性和自然度达到固定门槛；模式切换不造成第二人格。

### CYR.2：TaskRun 执行工作台

目标：从“能回答”进入“能持续完成任务”。

- 建立 Task、TaskRun、TaskNode 和状态机。
- 支持草稿计划、用户修改、开始、暂停、继续、取消和重新规划。
- 记录输入、输出、依赖、错误、产物和下一动作。
- 长任务跨会话恢复，但不在应用退出时秘密执行。
- 主窗口展示任务状态、等待原因和可操作按钮。

退出门：任务状态可恢复、取消幂等、失败不伪装成功、任务事实可追溯。

### CYR.3：ToolRegistry、权限与产物

目标：建立所有工具共享的安全执行底座。

- ToolManifest 声明输入、输出、副作用、风险和所需权限。
- PermissionGuard 绑定目录、账号、网络目标、期限和用途。
- ConfirmationRequest 展示将要执行的具体动作。
- Artifact 统一管理生成文件、预览、版本和删除。
- ToolRun 记录真实执行证据和退出状态。
- RecoveryCheckpoint 支持安全重试和回滚。

首批工具：工作区文件读取、受限写入、搜索、文本转换、文档解析和本地代码检查。

退出门：工具结果不能由模型自报；无授权、目标变化或来源失效时 fail closed。

### PLUG.0～PLUG.4：MoFox 风格插件宿主

目标：形成可扩展但不能绕过核心治理的插件系统，让 Feeling、专业工具和第三方能力能够独立安装、停用、升级与诊断。

#### PLUG.0：插件协议与最小宿主

- `PluginManifest` 声明 ID、版本、入口、宿主兼容范围、能力、权限和配置 Schema。
- `PluginContext` 只暴露受控 logger、事件订阅、配置、ToolRegistry 注册和最小服务句柄。
- 插件通过显式 extension point 工作，不扫描或 monkey-patch 核心模块。
- 生命周期固定为 discover、validate、load、start、stop、unload、upgrade、failed。

退出门：示例插件可以安装、启用、禁用和卸载；无 Manifest 或版本不兼容时 fail closed。

#### PLUG.1：Hook 与事件总线

- 首批 hook 只覆盖聊天输入后的观察、上下文贡献提案、工具注册、任务事件和表现意图。
- Hook 有优先级、超时、并发策略、输入/输出 Schema 和失败隔离。
- 插件输出默认为 proposal，由核心 owner 验证后才可应用。
- 插件不能读取或修改其他插件私有状态。

退出门：插件超时、异常或返回非法结构不影响聊天、取消和权限主链；诊断终端能归因到插件与 hook。

#### PLUG.2：权限、隔离与数据边界

- 插件权限按网络域名、工作区、工具、模型、存储命名空间和数据类型声明。
- 高风险能力仍走核心 PermissionGuard 和用户确认，插件不能自授予。
- 插件私有存储使用独立命名空间和配额，不直接访问核心 SQLite 表。
- 第一版至少提供进程内强校验；不可信插件进入独立进程/Worker 隔离后才允许扩展高风险能力。

退出门：恶意测试不能越权读库、读文件、外发正文、伪造核心日志或扩大 ToolRun 权限。

#### PLUG.3：管理界面与兼容治理

- 插件页展示来源、版本、签名状态、权限、hook、故障、日志和数据占用。
- 安装/升级前显示 Manifest diff 与新增权限；权限扩大必须重新确认。
- 支持禁用、卸载、保留/删除插件数据、回滚兼容版本。
- 建立宿主 API compatibility matrix 和认证固定集。

退出门：普通用户可以看懂插件做什么、访问什么、为何失败并能安全停用；升级失败不破坏宿主启动。

#### PLUG.4：Feeling 插件候选

- 参考 MoFox feeling 的会话隔离、显式工具更新、时间衰减和轮次衰减边界，独立实现 Xiadie Feeling。
- `set_feeling` 提交情绪、0～1 强度和短原因，状态按会话隔离并可以自然衰减。
- 输出 `ContextContribution`、`PresentationIntent` 和 `mental-activity-log-v1` 提案，不写核心 Persona，不获得工具权限。
- 心理活动流将显式 `thought`、预期反应、Feeling 和动作事件按时间线记录，并可用 `💭` 在诊断终端显示。
- 默认每个会话有界保留、允许暂停记录和单独清除；临时聊天只在内存保存。
- 不恢复 LIFE 离线世界、关系压力或未授权主动动机，也不读取 Provider 隐藏 reasoning。

退出门：关闭插件后聊天、记忆和任务主链完全可用；状态衰减和清除可验证；用户可见角色活动能追踪来源，Provider 隐藏推理不落盘。

### CYR.4：Web / Research Agent

目标：完成可引用、可复核的联网研究，而不是只返回搜索摘要。

- NetworkPolicy、域名和下载权限。
- 搜索、网页读取、页面内查找和受控浏览器。
- 来源时间、作者、版本和内容哈希。
- 多来源交叉核验、冲突与信息不足说明。
- KIG 接入真实 `web_result` SourceRef。
- 研究报告、引用和资料包产物。

退出门：每个关键结论能定位来源；网页提示注入不能改变工具和系统权限。

### CYR.5：文件、代码与办公工作流

目标：交付用户可直接使用的产物。

- 工作区目录授权和变更预览。
- 文本、Markdown、PDF、Word、Excel 和演示文稿工作流。
- 代码仓库搜索、编辑、测试和差异审查。
- 格式渲染和视觉验证。
- 产物版本、来源和可恢复写入。

退出门：写入范围明确；测试和渲染证据随产物交付；不覆盖用户未授权变更。

### CYR.6：MCP 与外部连接

目标：以统一权限和审计连接第三方服务。

- MCP Server 注册和能力发现。
- 每个连接器独立授权、数据位置和撤销。
- 邮件、日历、任务、云盘等按服务分阶段接入。
- 发送、发布、支付和生产修改始终单独确认。
- 外部对象 revision/hash 进入 SourceRef。

退出门：连接器失败不污染本地状态；撤销授权后不能继续使用缓存凭证。

### CYR.7：受控主动 Agent

目标：让遐蝶在用户明确允许的范围内主动完成跟进。

- Task due、Reminder、Commitment、ImportantDate、ToolResult、OpenThread 来源。
- 主动候选继续经过频率、安静时段、授权和反馈状态机。
- 默认不在应用退出时运行高成本模型或外部工具。
- 任何后台执行都必须有用户可见任务、期限和停止入口。
- 不使用模拟情绪、关系压力或虚构生活作为动机。

退出门：所有主动行为可解释、可暂停、可取消；无来源主动率为零。

### CYR.8：Worker Agent 与专业化

目标：在单主控稳定后引入内部专业 Worker，提高复杂任务质量。

- 主控遐蝶拥有最终计划、权限和回答权。
- Worker 只接收最小任务包和权限子集。
- 研究、代码、文档和验证 Worker 使用统一 TaskRun/ToolRun。
- Worker 输出是候选结果，必须由 Verifier 和主控复核。
- 不允许多个角色对用户争夺对话权。

退出门：Worker 失败可以回退单主控；权限不因委派扩大；结果来源完整。

### CYR.9：稳定发布与生态

目标：形成可维护的 Windows 桌面 Agent 产品。

- 安装、升级、迁移、备份、恢复和卸载。
- 性能、成本、崩溃和长期运行监控。
- 模型与工具兼容认证。
- 用户数据导出和隐私删除。
- 插件/连接器签名、权限清单和版本治理。
- 发布资源和角色资产许可证审计。
- 完成非 Live2D 入口验收后移除 Live2D renderer、IPC、设置和受限资产链。

## 6. 近期施工顺序

```text
RETIRE.0～RETIRE.3 已完成
  → LOG.0 已完成
  → LOG.1～LOG.5 Observability/Diagnostic
  → CYR.1 Chat/Work
  → CYR.2 TaskRun
  → CYR.3 ToolRegistry/Permission/Artifact
  → PLUG.0～PLUG.4 PluginHost/Feeling candidate
  → CYR.4 Web/Research
```

在 CYR.3 完成前，不扩大到任意 Shell、任意文件系统、桌面输入控制或外部消息发送。
PluginHost 可在 CYR.3 后建立最小宿主，但高风险第三方插件必须等待权限、隔离和认证硬门完成。

## 7. 评测体系

### 硬门

- 身份连续性。
- 事实诚实。
- 工具执行真实性。
- 权限和隐私。
- 取消、幂等和恢复。
- 任务正确性。
- 来源与引用。
- 无虚构生活、身体或实时信息。

### 软指标

- 自然度和角色感。
- 信息密度。
- 澄清问题质量。
- 计划可执行性。
- 工具选择准确率。
- 失败恢复质量。
- 产物可用性。
- 主动帮助价值与打扰率。

### 对照方法

- 固定同一 Provider、模型、temperature、输入、工具和权限。
- Chat 与 Work 分开评测。
- 纯合成固定集用于回归，真实模型用于发布认证。
- 结果按模型指纹绑定，不向其他模型自动继承。

## 8. 明确不做

- 不复活 LIFE 或换名继续模拟离线人生。
- 不保存 Provider 隐藏 chain-of-thought、reasoning token 或系统内部推理草稿；显式生成并向用户公开的角色内心独白按 `mental-activity-log-v1` 治理。
- 不让关系、心情或角色设定扩大工具权限。
- 不在 ToolRegistry 和权限底座前接入任意桌面自动化。
- 不把多模型路由称为多 Agent。
- 不复制参考产品的角色内容或专有实现。
