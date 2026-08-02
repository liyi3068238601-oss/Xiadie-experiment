# Xiadie 助手优先架构与 LIFE 退役迁移计划

- 版本：v1.0
- 日期：2026-08-01
- 状态：RETIRE.0～RETIRE.3 已实施；RETIRE.4 进行前
- 适用仓库：`Xiadie-experiment`
- 取代范围：LIFE 作为现行产品能力的全部设计，以及其他专项对 LIFE 的现行依赖

## 0. 实施记录

2026-08-01 已完成：

- 删除 LIFE 运行时、CatchUp、Schedule、LifeEvent、Goal、ImportantDate、Diary、SelfTimeline、InnerStateProjection、分享适配器及专属测试。
- 删除后端 `/api/life/*`、前端生活页、导航、类型、API 和样式；ShortMemo API 迁至 `/api/assistant/*`。
- KIG 从六源收敛为 Knowledge、Memory、History、Task、Lore 五源；EAP 不再接收 LIFE seed。
- Schema 83 将 ShortMemo、Persona v2、WorldBook 设置迁至 `assistant.*`；Schema 84 在本地备份后迁移明确用户日期/目标并删除 27 个退役表。
- 真实库从 Schema 82 升级到 84：迁移前 26 个退役表共 3 行，迁移后退役表为 0；备份位于 `backend/data/backups/life-retirement-before-schema-84.json`。
- 定向后端回归已通过 API/CTX/MEM/Knowledge/EAP、KIG/PWM、Persona/WorldBook/ShortMemo 等分组；前端生产构建通过。完整 2496 项测试因单命令 120 秒时限拆分执行，长耗时 MEM/Episode/Saga 分组仍需在发布门继续完成。

## 1. 结论

Xiadie 实验版保留“遐蝶”的稳定身份、人格、表达方式和角色知识，但产品核心改为现代通用 Agent。系统可以自然聊天，并以检索、分析、写作、编程、任务管理和受控工具执行为主要职责。

`LIFE` 生活模拟不再作为可关闭的可选路线，而是从实验版中退役并最终物理移除。退役包括 LifeClock、SelfState、离线世界续演、模拟日程、遐蝶个人目标、日记、SelfTimeline、生活事件生产和请求内 InnerStateProjection。

删除 LIFE 不等于删除连续性。真实连续性由原始消息、会话摘要、长期记忆、ShortMemo、任务、重要日期和可审计工具结果共同提供。

## 2. 产品边界

### 2.1 保留

- Persona Core、Chat/Work 模式、WorldBook/Lore 和输出真实性边界。
- 原始对话、CTX 滚动摘要与跨会话历史回忆。
- MEM Fragment、Entity、Episode、Saga、Archivist、纠错与来源追踪。
- ShortMemo，但归属改为近期任务与上下文，不再归 LIFE。
- Knowledge 文档、切片、FTS、BGE-M3、授权、引用和删除生命周期。
- CDS 通用 DecisionRun、结构化判断、模型路由、校验、熔断、预算和校准。
- KIG/PWM 的来源、查询规划、多源检索、重排、证据、版本、新鲜度和用户/项目世界模型。
- CIE 的消息积累、生成取消、图片、回复展示节奏和 ContextContribution。
- EAP 的 Presence、主动候选、授权、频率、投递、反馈和可取消状态机。
- Relationship 中由真实互动支持的称呼、距离、信任和边界。
- 当轮用户状态理解和当轮表达指导。

### 2.2 删除

- `life_runtime.py`、`life_catchup.py`、`life_catchup_service.py`。
- `life_schedule.py` 及模拟日程数据和 API。
- `life_events.py` 及模拟生活事件生产链。
- `personal_goals.py` 中遐蝶自我目标语义。
- `diary.py` 中遐蝶私人生活日记语义。
- `self_timeline.py` 及 LIFE 自我时间线。
- `inner_state_projection.py`。
- 离线情绪漂移、联系需求积温和虚构跨轮心境。
- LIFE 页面、导航入口、设置、导出和诊断。
- CDS、KIG、EAP、CIE、MEM 中仅服务于 LIFE 的 decision kind、source adapter、seed 和展示字段。
- `assistant_first` / `life_companion` 双产品 Profile；迁移完成后实验版只有助手优先路线。

### 2.3 不得删除

- `messages`、`sessions` 和附件来源记录。
- `memory_fragments`、Entity、Episode、Saga 及其来源和审计。
- KnowledgeDocument、Chunk、FTS、Embedding、引用与授权记录。
- 会话摘要、历史召回、ContextPackage 诊断。
- 用户确认的重要日期、任务、提醒、约定和边界。
- Provider、模型、权限、安全、审计和工具执行事实。

## 3. 能力迁移

| 原 LIFE 能力 | 新所有者 | 新语义 |
|---|---|---|
| 用户生日、纪念日、考试、发布日 | Memory + Reminder/Task | 真实用户日期；保留来源、时区和提醒授权 |
| 用户约定与近期安排 | ShortMemo + Task | 有 TTL 的近期上下文或正式任务 |
| 项目目标与里程碑 | Task + MEM Episode/Saga | 用户项目事实，不是遐蝶自我目标 |
| 有意义的共同经历 | MEM Episode/Saga | 只来自真实对话、用户资料和已完成工具结果 |
| 主动联系 | EAP | 只由任务、提醒、承诺、重要日期、工具结果或当前会话机会触发 |
| 当前表达状态 | request-local guidance | 当轮生成、当轮失效，不跨轮模拟遐蝶心境 |
| 世界事件 | KIG/PWM | 必须有 SourceRef；只记录真实用户、项目、文档或工具事件 |
| 时间线 | MEM/PWM/Task | 用户与项目事实时间线，不是遐蝶离线人生 |

## 4. 专项新边界

### MEM

保留完整长期记忆。Episode/Saga 的“经历”统一解释为真实共同对话、用户经历、项目进展和有证据的工具结果，不表示遐蝶离线期间自行生活。

### CTX

继续拥有最终 ContextPackage 和 token 预算。允许消费 Persona、当前会话、摘要、历史、MEM、Knowledge、KIG、ShortMemo、Task、附件和治理后的第三方贡献；不再接受 LIFE、SelfTimeline 或 InnerStateProjection。

### EAP

保留 Presence、候选、授权、投递、反馈和安静时段。删除持久 Affect 生活化演进和 LIFE seed。主动候选的允许来源收敛为 `task_due`、`explicit_reminder`、`user_commitment`、`important_date`、`tool_result`、`open_thread` 和有当前轮证据的 `emotional_care`。

### CDS

保留通用决策运行时。删除 `life_schedule_*`、`life_important_date_interpretation`、`life_diary_reflection`、`life_event_meaning` 等 LIFE 专属 decision kind；后续新增 Tool/Task/Research 领域 decision kind。

### KIG/PWM

检索源从 Knowledge、Memory、History、Life、Task、Lore 六源收敛为 Knowledge、Memory、History、Task、Lore 五源，并可在 NetworkPolicy/ToolRegistry 完成后增加真实 Web/ToolRun 来源。删除 LIFE adapter；PWM 不得保存模拟心境、日程或遐蝶离线活动。

### CIE/KFC

保留消息积累、取消、图片、展示节奏和 ContextContribution。删除对 LIFE 心理状态、LifeEvent、Goal 和 SelfTimeline 的读取；ShortMemo 改由 Task/CTX 提供。

### Persona / WorldBook / ShortMemo

Persona、WorldBook 和 Chat/Work 模式保留。ShortMemo 迁出 LIFE，限定为用户安排、待办、明确承诺、当前项目状态和近期上下文。删除 InnerStateProjection。

## 5. 数据迁移原则

1. 先建立字段与数据分类清单，再执行删除迁移。
2. 用户确认的日期、任务、约定和项目事实先迁移到新所有者。
3. 模拟产生的 SelfState、生活事件、日记、日程和自我目标不迁入 MEM/PWM。
4. 无法证明来源或语义的数据不得伪装成用户记忆。
5. 删除迁移必须先生成统计清单和可选本地备份；不得静默删除用户输入。
6. 迁移完成后删除 LIFE 表、API、前端入口、worker、adapter、测试和文档现行声明。
7. 历史迁移源码可以保留在 Git 历史，不需要让新数据库继续创建已退役表。

## 6. 施工阶段

### RETIRE.0：文档与所有权冻结 `[x]`

- 改写 README、项目上下文、路线图和专项矩阵。
- 给 LIFE 及依赖 LIFE 的历史计划增加退役声明。
- 固定保留、迁移、删除清单。

### RETIRE.1：运行时断开与 API/UI 移除 `[x]`

- 删除 LIFE worker、请求装配、KIG life source、EAP life seed。
- 删除生活页面、前端 API、导航和设置。
- 删除双 Profile 回退，助手优先成为唯一运行模式。

### RETIRE.2：用户事实迁移 `[x]`

- 将用户确认的重要日期、约定、任务和项目目标迁入 Memory/Task/Reminder。
- 明确 ShortMemo 的新所有者和 TTL。
- 生成迁移报告和冲突清单。

### RETIRE.3：Schema 清理 `[x]`

- 在备份与迁移验收后删除 LIFE 专属表、索引、设置和审计对象。
- 更新全新数据库创建路径，不再创建 LIFE Schema 64～71/相关后续对象。
- 保留消息、MEM、CTX、Knowledge、CDS、KIG、CIE、EAP 通用基础设施。

### RETIRE.4：现代 Agent 能力重心 `[ ]`

- 建立 Task、ToolRegistry、PermissionGuard、Artifact 和 Recovery。
- 接入受控文件操作、Web/Research、代码执行与 MCP。
- 将主动系统改为任务、提醒和工具结果驱动。
- 完成 Chat/Work 对照评测和回归。

## 7. 验收硬门

- 普通聊天请求不读取或写入任何 LIFE 表。
- 启动和退出不运行 LifeClock、CatchUp 或生活 worker。
- Prompt 不包含模拟日程、心境、个人目标、日记或 SelfTimeline。
- KIG 不把 `life` 列为可选检索源。
- 主动候选不能由模拟心境或生活事件触发。
- 用户记忆、知识库、摘要、Episode/Saga、重要日期迁移结果和来源引用不丢失。
- 全新安装不会创建退役 LIFE 表。
- Persona 身份稳定、事实诚实、任务正确性和安全边界不得下降。

## 8. 文档解释顺序

发生冲突时按以下顺序解释：

1. 用户当前明确指令。
2. 本文件。
3. `CYRENE_STYLE_AGENT_EXPERIMENT_PLAN.md`。
4. `CODEX_PROJECT_CONTEXT.md` 与 `XIADIE_LONG_TERM_ROADMAP.md`。
5. MEM、CTX、Knowledge、EAP、CDS、KIG、CIE 和 Persona 专项中的未冲突部分。
6. LIFE v1/v2、旧 Affect/EAP 生活化段落只作为历史施工记录。

## 9. 代码拆除清单

### 9.1 后端完整删除候选

| 文件 | 当前职责 | 处理 |
|---|---|---|
| `life_runtime.py` | LifeClock、SelfState、lease、时间推进 | 删除 |
| `life_catchup.py` | 离线 catch-up 计算与候选 | 删除 |
| `life_catchup_service.py` | 启动/退出 lease 与 heartbeat | 删除 |
| `life_schedule.py` | 粗/细日程和改期 | 删除 |
| `life_events.py` | LifeEvent 账本、revision、source、audit | 删除 |
| `life_decisions.py` | LIFE decision kind 注册 | 删除 |
| `life_quality.py` / `life2_evaluation.py` | LIFE 专用评测 | 历史报告保留，运行代码删除 |
| `life_retention.py` | LIFE 保留策略 | 删除 |
| `life_sharing.py` | LIFE 分享与主动种子 | 删除 |
| `personal_goals.py` | 遐蝶个人目标 | 删除；用户任务迁移后由 Task 取代 |
| `diary.py` | 遐蝶生活日记 | 删除 |
| `self_timeline.py` | LIFE 自我时间线 | 删除 |
| `inner_state_projection.py` | 请求内模拟内心投影 | 删除 |
| `proactive/life_adapter.py` | LIFE → EAP seed | 删除 |

`important_dates.py` 不直接原样保留。先将用户确认的日期迁入 Reminder/Task/Memory，再删除 LIFE 版本及其 API。

### 9.2 后端需要改写的共享文件

| 文件/范围 | 改写要求 |
|---|---|
| `main.py` | 删除 LIFE import、lifespan worker、聊天投影、自时间线注入、全部 `/api/life/*` 路由、导出和诊断 |
| `db.py` | 增加退役迁移；全新建库不再创建 LIFE 表；ShortMemo 设置键迁名 |
| `context_assembler.py` | 不接受 LIFE/SelfTimeline/InnerState 组件或元数据 |
| `kig_pipeline.py` / `kig_retrieval.py` | 删除 `life` source；更新五源规划与证据白名单 |
| `kig_sources.py` / `kig_integrations.py` | 删除 LifeEvent/SelfTimeline adapter 与 dependency |
| `kig_evidence.py` | 删除 `life_event` 引用类型；保留 message/memory/tool/lore/knowledge |
| `specialty_contracts.py` | 删除 LIFE owner、adapter 和 decision kind 合同 |
| `proactive/*` | 删除 LIFE seed；新增任务、提醒、承诺、工具结果来源 |
| `persona_v2.py` | 删除 projection 参数和渲染器；保留 Persona/模式/认证 |
| `short_memo.py` | 设置键从 `life.short_memo.*` 迁到 `assistant.short_memo.*`；语义限定为用户任务与近期上下文 |
| `pwm.py` / KIG-P | 禁止模拟生活、心境、日程和遐蝶离线活动进入 PWM |
| `archivist*` / Episode/Saga | 保留；将“经历”文案限定为真实对话、用户经历、项目和工具结果 |

### 9.3 前端删除与改写

删除：

- `frontend/src/components/LifePage.tsx`。
- `App.tsx` 中 `LifePage` import、`life` 导航和渲染分支。
- `store.ts` 中 `life` view。
- `Icon.tsx` 中仅用于生活页的 icon（若无其他用途）。
- `api.ts` 中 LifeSchedule、LifeSettings、LifeState、LifeDiary、LifeGoal、LIFE diagnostics/export/rebuild API。
- `styles.css` 中 `.life-*` 页面样式。

迁移：

- ShortMemo 管理进入 Task/Memory 的近期事项区域。
- 用户重要日期进入 Reminder/Task 页面。
- 任务状态、工具结果和主动跟进入 TaskRun 工作台。
- Episode/Saga 中的“生活时间线”文案改为“来源时间线”或“项目时间线”。

## 10. 数据库对象与处置

### 10.1 删除表

完成 RETIRE.2 用户事实迁移后删除：

```text
life_events
life_event_revisions
life_event_sources
life_event_audit_events
life_runtime_state
life_runtime_lease
life_runtime_events
life_exit_snapshots
life_catchup_requests
life_catchup_candidates
life_schedules
life_schedule_segments
life_schedule_replacements
life_event_candidates
personal_goals
personal_goal_sources
personal_goal_events
important_dates
important_date_sources
important_date_events
continuity_threads
diary_entries
diary_entry_revisions
diary_entry_sources
self_timeline_entries
```

同时删除只引用这些表的索引、触发器、设置、decision runs 派生诊断和 dependency 边。

### 10.2 保留并迁名

```text
short_memos
short_memo_events
```

ShortMemo 数据表可以保留，但设置键必须迁移：

| 旧键 | 新键 |
|---|---|
| `life.short_memo.enabled` | `assistant.short_memo.enabled` |
| `life.short_memo.rollout_mode` | `assistant.short_memo.rollout_mode` |
| `life.short_memo.rollout_epoch` | `assistant.short_memo.rollout_epoch` |
| `life.short_memo.remote_extraction_enabled` | `assistant.short_memo.remote_extraction_enabled` |
| `life.short_memo.default_ttl_seconds` | `assistant.short_memo.default_ttl_seconds` |
| `life.short_memo.max_active` | `assistant.short_memo.max_active` |
| `life.short_memo.max_recall` | `assistant.short_memo.max_recall` |

设置迁移采用 copy-if-absent → 校验 → 删除旧键，不覆盖用户已经写入的新键。

### 10.3 绝对保留表域

- Session / Message / Attachment。
- MEM Fragment / Entity / Episode / Saga / Archivist / Recall / Conflict。
- CTX Summary / History / Budget / Diagnostics。
- Knowledge Document / Chunk / FTS / Embedding / Grant / Citation。
- CDS DecisionRun 通用表、模型认证、熔断与校准。
- KIG SourceRef/Evidence/PWM 中非 LIFE 且来源仍有效的数据。
- CIE ingress、vision 和 contributor 治理对象。
- EAP 通用候选、投递、反馈和设置，但删除 LIFE 来源记录。

## 11. 数据分类与迁移算法

### 11.1 ImportantDate

每条日期先分类：

1. 有用户消息或用户编辑来源，且描述用户/共同项目的真实日期：迁移。
2. 仅由 LIFE 模型、模拟日记或遐蝶个人目标产生：删除。
3. 来源缺失、语义含混或同时包含用户与模拟内容：进入人工确认清单，不自动迁移。

迁移结果必须保存原 ID、revision、source locator、timezone、recurrence 和迁移批次 ID。

### 11.2 PersonalGoal

- `owner=user` 或有明确用户目标证据：转换为 Task 草稿，默认不自动开始。
- `owner=shared` 且有项目/约定来源：转换为 Task 或 MEM 项目状态候选。
- `owner=persona`、模拟生活或无用户来源：删除。

### 11.3 LifeEvent / Diary / SelfTimeline

- 不把模拟 LifeEvent、日记和 SelfTimeline 直接迁入 MEM/PWM。
- 如果某条仅是 message、tool_run、正式 Memory 的重复派生，删除派生项，保留权威来源。
- 如果含有用户后来手工补充且其他系统没有保存的事实，进入人工确认清单。
- 禁止把模型生成摘要当成迁移事实来源。

### 11.4 ShortMemo

保留条件：内容属于用户安排、待办、明确承诺、项目状态或近期上下文，并且来源仍有效。模拟心境、遐蝶日程、自我目标和生活感想全部删除。

## 12. 分 PR 施工卡

### PR-R0：文档与基线

- 本文件、Cyrene 长期路线、README 和专项边界更新。
- 记录 LIFE 表行数、设置、API、文件、测试和前端入口。
- 不删除代码或数据。

验收：文档链接通过；冲突搜索没有把 LIFE 描述为现行产品能力。

### PR-R1：运行时和上下文断开

- 从 lifespan 删除 LIFE service。
- 从聊天路径删除 InnerState/SelfTimeline/LifeEvent/PersonalGoal。
- 从 KIG 删除 life source。
- 从 EAP 删除 life adapter 和 seed。
- 删除双 Profile，助手优先成为唯一模式。

回滚点：PR-R0 commit。此阶段不改 Schema，可直接回滚代码。

### PR-R2：前端和 API 移除

- 删除生活页面、导航、类型、API 和样式。
- 删除 `/api/life/*`；ShortMemo 迁到新 `/api/assistant/short-memos` 或 `/api/tasks/short-memos`。
- 更新设置、导出和诊断。

回滚点：PR-R1 commit。数据库仍未物理删除。

### PR-R3：目标能力地基与用户事实迁移

- 先建立 Reminder/Task 最小数据合同。
- 生成 migration dry-run 报告。
- 迁移确认日期、用户目标、约定和 ShortMemo 设置。
- 模糊项只列清单，不自动写入。

回滚：按 migration_batch_id 删除新派生项；旧 LIFE 表尚未删除。

### PR-R4：Schema 物理清理

- 创建本地数据库备份和完整性检查。
- 删除 LIFE 表、索引、设置、adapter dependency 和孤立派生对象。
- 改写全新建库路径。
- 更新 schema version、导出和恢复说明。

回滚：仅通过备份恢复；不得依赖 down migration 猜测重建已删正文。

### PR-R5：测试、文档和发布收口

- 删除 LIFE 专用测试和 fixture。
- 把有通用价值的测试迁入 MEM/Task/EAP/KIG/CIE。
- 全量后端、前端、Electron、安装和升级测试。
- 独立 Review；0 个未解决 P0/P1。

## 13. 测试迁移

删除的 LIFE 专用测试包括 `test_life0_baseline.py`、`test_life1_decision_contracts.py`、`test_life2_event_ledger.py`、`test_life3_runtime.py`、`test_life4_catchup.py`、`test_life5_schedule.py`、`test_life6_goals.py`、`test_life7_important_dates.py`、`test_life8_diary.py`、`test_life9_self_timeline.py`、`test_life10_quality_gate.py`、`test_life11_sharing.py`、`test_life12_api.py`、`test_life13_acceptance.py`、`test_proactive_life_adapter.py` 和 `test_life2_5_inner_state_projection.py`。

不得简单丢弃以下通用保障，必须迁移测试：

- 用户日期来源、时区、重复和删除 → Reminder/Task 测试。
- 用户目标 revision、状态机和来源 → Task 测试。
- ShortMemo TTL、敏感值和来源 → Assistant ShortMemo 测试。
- Episode/Saga 来源保护 → MEM 测试。
- 主动频率、安静时段、投递幂等和反馈 → EAP 测试。
- SourceRef 失效和证据 → KIG 测试。

## 14. 每阶段验证命令

```powershell
# 文档冲突和残留引用
Get-ChildItem docs -File -Filter *.md |
  Select-String -Pattern 'LIFE|life_event|SelfTimeline|InnerStateProjection'

# 后端定向测试
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_api.py tests\test_product_profile.py -q

# 全量后端
.\.venv\Scripts\python.exe -m pytest tests -q

# 前端
cd ..\frontend
npm.cmd test
npm.cmd run build

# Electron
cd ..\desktop
npm.cmd test
```

PR-R4 额外执行：

- 旧数据库升级测试。
- 全新数据库 Schema 清单测试。
- SQLite `PRAGMA integrity_check`。
- 迁移前后保留域行数与来源抽样。
- Windows frozen backend 和安装升级 smoke。

## 15. 施工纪律

- 严格按 R0 → R1 → R2 → R3 → R4 → R5 顺序。
- 未完成 Reminder/Task 目标结构前，不删除用户 ImportantDate/Goal。
- 未生成本地备份、dry-run 和人工确认清单前，不执行物理 DROP TABLE。
- 每个 PR 只占用自己的 Schema、API 和所有权范围。
- 每阶段更新本文件勾选状态、测试结果、commit 和下一阶段入口。
- 任何实现若需要恢复 LIFE 才能工作，应改写该实现，不得把 LIFE 重新设为依赖。
