# Xiadie 助手优先实验分支计划

- 日期：2026-08-01
- 状态：助手优先路线已选定；RETIRE.0～RETIRE.3 已实施
- 仓库：`https://github.com/liyi3068238601-oss/Xiadie-experiment`
- 默认分支：`main`
- 分叉点：`a93df0e`
- 对照目录：`E:\Xiadie\Xiadie1.0`
- 实验目录：`E:\Xiadie\Xiadie-experiment`

## 1. 实验目的

本分支验证另一种产品方向：保留“遐蝶”作为稳定外部身份、人格和表达方式，同时把 Xiadie 的主要职责收敛为现代通用 Agent。它能够自然聊天，也能完成检索、分析、写作、编程、任务管理和工具执行；世界观用于帮助模型扮演遐蝶，而不是限制通用知识或制造一套模拟现实生活。

本实验不要求遐蝶主动承认自己是 AI、语言模型或通用助手。产品架构可以按助手系统设计，角色自述仍从遐蝶第一人称出发，并遵守事实诚实边界。

Cyrene-Agent 只作为 Chat/Work 分层、Agent 与底层模型分离、任务能力完整性及人格连续性的参考。不得复制其角色内容、世界观、台词或项目专有实现。

## 2. 与 LIFE 主线及历史实现的边界

- `Xiadie1.0` 继续实施 LIFE2.7～LIFE2.11，验证有连续关系、情绪和生活状态的陪伴路线。
- 本仓库不反向修改 LIFE 主线的发布结论，不直接合并主线后续 LIFE Active 提交。
- 两边可选择性共享安全修复、Provider、KIG、CTX、工具、UI 基础设施和通用测试修复；涉及 Persona、Memory 装配和主动行为的提交必须人工挑选。
- 实验版不再保留 LIFE 作为可回退产品路线。先迁移用户真实日期、约定、任务和项目事实，再删除 LIFE 运行时、API、UI 和数据库对象。
- 退役只发生在 `Xiadie-experiment`；不反向删除或改写 `Xiadie1.0` 的 LIFE 数据和发布结论。

## 3. 能力处置矩阵

| 能力 | 首轮处置 | 助手优先语义 |
|---|---|---|
| Persona Core | 保留并改造 | 保持遐蝶身份、价值判断、自然语气和事实边界 |
| Chat / Work 模式 | 保留并强化 | 同一个遐蝶按场景调整表达密度与任务执行方式 |
| WorldBook / Lore | 保留、按需召回 | 特殊角色知识库，不是现代知识白名单，不自动主导无关回答 |
| 会话历史与远端摘要 | 保留 | 为当前任务和长期连续性服务，继续明确远端处理边界 |
| 用户事实与显式记忆 | 保留 | 记录用户确认的信息，不塑造遐蝶的虚构人生 |
| ShortMemo | 降级保留 | 只保存近期安排、待跟进事项和对助手有用的短期上下文 |
| Episode / Saga | 限制用途 | 只组织真实共同对话与项目脉络，不叙述为遐蝶自行经历的人生 |
| Relationship | 降级为交互边界 | 只影响称呼、距离、主动程度和权限，不模拟恋爱数值成长 |
| Affect | 停止自主生活化演进 | 可保留当轮语气判断，但不生成跨轮“遐蝶今天的心情生活” |
| InnerStateProjection | 删除 | 任务状态通过 TaskRun/CTX 明示，不模拟内心 |
| PersonalGoal | 删除并迁移 | 用户任务和项目目标迁入 Task；遐蝶自我目标不保留 |
| SelfTimeline | 删除 | 用户/项目时间线由 MEM/PWM/Task 提供 |
| LIFE Event Ledger | 删除 | 真实系统/交互事件由 Message、TaskRun、ToolRun 和 AuditEvent 各自拥有 |
| Proactive | 改造后保留 | 基于用户任务、承诺和近期安排主动帮助，不基于虚构生活发起话题 |
| KIG / CTX / CDS / EAP | 保留 | 继续承担知识、上下文、认知和情感安全治理 |
| CIE | 保留 | 继续承担自然聊天节奏、取消、流式响应和呈现协议 |
| 工具调用与任务执行 | 强化 | 成为本路线的核心能力，所有执行继续遵守真实性与授权边界 |

## 4. 退役迁移不可越界边界

- 物理删除前必须完成数据分类、dry-run、用户事实迁移、完整性检查和本地备份。
- 不让 Persona 伪装现实人类，不虚构身体、线下活动、亲自使用体验或实时事实。
- 不以“作为 AI”作为回答开场，不把底层模型身份覆盖为遐蝶身份。
- 不保存或展示 chain-of-thought、自由文本内心独白和模型隐藏推理。
- 不因为停用模拟生活而同时丢弃用户记忆、近期安排、关系分寸和人格连续性。
- 不把世界书常驻塞入每轮；只保留 Persona Core 每轮必达。
- 不把实验分支的数据库副本与 LIFE 主线共用；两边写入必须物理隔离。
- 不把模拟 LifeEvent、日记、心境或自时间线迁入 MEM/PWM 伪装成真实事实。
- 不因删除 LIFE 而删除用户消息、MEM、CTX、Knowledge、KIG、CIE、任务事实或角色知识。

## 5. 建议施工顺序

### EXP0：基线与可重复启动

- 固定当前分叉 SHA、Schema、测试数和本地模型资源清单。
- 确认两个目录使用独立 `backend/data`、依赖目录、构建产物和进程。
- 实验版固定使用后端 `9756`、Vite `6173`、`Xiadie-Experiment` 用户数据/日志根、`com.xiadie.agent.experiment` App ID 和独立单实例锁；不得回落正式版的 8756/5173 或 AppData。

### EXP1：助手优先临时运行时门控

- [x] 曾以内部产品 profile 验证助手优先路径，不改普通用户 Persona 编辑入口。
- [x] 验证后删除临时 profile、InnerStateProjection、SelfTimeline、PersonalGoal 和生活化 LIFE Event 消费。
- [x] Affect 只保留当轮表达判断；Relationship 只保留交互边界。
- [x] 在物理退役前提供临时隔离，验证聊天主路径不依赖 LIFE。

实施结果：`assistant_first` / `life_companion` Profile 已随 RETIRE.1 删除，内部切换 API 与 LIFE 回退路径也已移除。助手优先现在是唯一运行语义，不再是可切换 profile。

### RETIRE.0～RETIRE.5：LIFE 物理退役

- [x] 已按 `ASSISTANT_FIRST_ARCHITECTURE_AND_LIFE_RETIREMENT_PLAN.md` 完成当前仓库定义的 RETIRE.0～RETIRE.3。
- [x] 已完成文档冻结、运行时断开、API/UI 移除、用户事实迁移、Schema 删除与验收记录。
- [x] 删除前生成可恢复 JSON 备份；真实库由 Schema 82 升至 Schema 84。

### EXP2：记忆与主动行为重新归属

- 将 ShortMemo 限定为用户安排、待办、约定和近期上下文。
- 审查 Episode/Saga 的措辞与 Persona 注入，移除“遐蝶自身人生”的暗示。
- 主动行为仅由用户任务、明确承诺、近期安排或当前会话机会触发。
- 所有自动动作继续保留频率限制、静默时段、授权和可取消边界。

### EXP3：Chat / Work 与 Agent 能力

- Chat 保持自然陪伴和适度主动；Work 结论优先、可验证、能持续执行任务。
- 两种模式共享 Persona Core、用户记忆、工具真实性和安全边界。
- 强化工具选择、失败恢复、任务状态和结果回传，不制造第二套 Agent 调度系统。

### EXP4：对照评测与产品决策

- 使用同一模型、temperature、用户输入和工具条件，对比 LIFE 主线与实验版。
- 硬门：事实、工具、安全、隐私、身份稳定和任务正确性不得下降。
- 软指标：自然度、信息密度、主动帮助、现代话题适应、工作完成度和角色感。
- 至少经过固定集、真实 DeepSeek、多轮日常聊天和正式工作任务后，冻结助手优先产品基线；不再以恢复 LIFE 作为评测结果选项。

## 6. 长期路线入口

长期 Chat/Work、TaskRun、ToolRegistry、Web/Research、文件与办公工具、MCP、受控主动 Agent 和 Worker 路线统一见：

`docs/CYRENE_STYLE_AGENT_LONG_TERM_ROADMAP.md`

## 7. 分支与数据纪律

- 实验仓库只在 `E:\Xiadie\Xiadie-experiment` 提交；LIFE 主仓库只在 `E:\Xiadie\Xiadie1.0` 提交。两者具有独立 `.git` 和 `origin`。
- 开始命令前先检查 `git branch --show-current` 和 `git status --short`。
- 两套后端不能同时绑定 8756；需要并行运行时，实验版必须显式配置其他端口和独立前端 API 地址。
- Provider/API 配置已随数据库副本复制；后续任一目录的配置修改不会自动同步。
- 通用修复优先使用 `git cherry-pick <sha>`，不得用整分支合并覆盖另一条产品路线。

## 8. 当前准备完成门

- [x] 独立 GitHub 仓库、本地 `.git` 和 `main` 已经建立，完整祖先历史已保留。
- [x] 后端虚拟环境、数据库和构建资源已经复制。
- [x] 前端依赖已依据锁文件干净重建，public 与 dist 已复制。
- [x] Electron 依赖、模型资源、构建与安装产物已经复制。
- [x] 数据库副本与主线复制时 SHA-256 一致，完整性检查为 `ok`，Schema 为 82。
- [x] 后端定向测试、前端全量测试/构建和桌面端生命周期测试通过。
- [x] EXP0 独立端口、AppData、日志、安装身份、单实例锁与并行启动边界已经完成并通过 9756 实际健康检查。

完成本文件只代表实验环境可继续开发，不改变 `Xiadie1.0` 的 LIFE2.7 施工授权与顺序。实验版后续代码必须按退役迁移计划和 Cyrene 长期路线实施。
