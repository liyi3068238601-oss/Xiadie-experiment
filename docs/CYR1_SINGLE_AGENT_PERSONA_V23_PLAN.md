# CYR.1 单 Agent 与 Persona v2.3 施工计划

- 日期：2026-08-02
- 状态：实现与验证完成
- 分支：`agent/cyr1-single-agent-persona-v23`
- 上游检查点：`01968b3`（可观测性实验基线）
- 适用范围：Persona、聊天请求协议、前端表达偏好、相关测试与文档
- 明确不在范围：WorldBook 内容改写、Memory 结构、TaskRun、ToolRegistry、PluginHost、Feeling

## 1. 产品结论

Xiadie 只有一个 Agent，用户始终面对同一个遐蝶。系统不要求用户选择 Chat 或 Work，也不维护两套人格、两套记忆或两套 Agent 状态。

```text
一个 Agent
  + 一套稳定 Persona
  + 一个按需召回的遐蝶 WorldBook
  + 用户真实 Memory
  + 正常知识、任务、工具与插件能力
```

Persona 决定遐蝶的身份、价值判断、关系姿态、语气和表达边界；不决定工具权限、事实真伪、现代知识范围或业务状态。WorldBook 是遐蝶相关的特殊知识库，不是 Persona Prompt，也不是现代知识白名单。Memory 只描述遐蝶与当前用户真实发生过的互动、约定与共同任务。

## 2. 行为目标

同一个 Agent 根据用户当前请求自然调整回应：

- 闲聊：像即时聊天一样自然，不机械列清单，不为了氛围虚构环境。
- 倾诉：先理解真正表达的感受，不模板安慰、不急于说教。
- 提问：直接、准确地回答，必要时说明不确定性和来源。
- 任务：先推进结果，再给必要依据、改动与下一步；在授权范围内持续施工和验证。
- 高风险话题：保持事实、安全与专业边界，不用角色世界观代替现实建议。
- 技术讨论：能够诚实讨论 Xiadie、模型、记忆与工具的实现，但不主动把“AI 助手”作为遐蝶的角色身份结论。

这套行为吸收 MoFox 的认真回应、关系判断、自然情绪流动、适度追问和主动帮助，以及 Cyrene 的完整任务能力、结果优先和人格/底层能力解耦；不复制两者的人格内容、世界观或工具协议。

## 3. 当前问题

现有 Persona v2.2 存在以下结构性问题：

1. `companionship` 与 `focused_work` 作为请求字段存在，但前端没有真正的模式选择入口。
2. 前端仍按会话保存并发送 `persona_mode`，形成用户不可见的隐式状态。
3. Persona rollout 默认 `off`；未 Active 或模型未认证时回退 legacy Prompt，两种模式可能完全不生效。
4. `backend/app/persona_profiles/v2/` 同时承担当前版本与 v2.2 历史资源，无法建立清晰的版本回退。
5. v2.2 Core 把《如我所书》和异世界通讯终端作为常驻认知框架，容易让现代问题也被过度世界观化。
6. 旧 Persona v2.3 + LIFE Active 计划与 LIFE 物理退役后的所有权冲突，不能按原阶段继续执行。

## 4. 冻结架构

### 4.1 Persona v2.3

Persona v2.3 采用单一自适应行为资源，不再按 `companionship/focused_work` 编译两份 Prompt：

```text
persona_profiles/
├─ v2_2/                 # 不可变历史回退
│  ├─ core.md
│  ├─ companionship.md
│  ├─ focused_work.md
│  ├─ styles.json
│  ├─ output_contract.md
│  ├─ manifest.json
│  └─ certifications.json
└─ v2_3/                 # 当前单 Agent Persona
   ├─ core.md
   ├─ behavior.md
   ├─ styles.json
   ├─ output_contract.md
   └─ manifest.json
```

编译顺序固定为：

```text
Core → Adaptive Behavior → 白名单表达偏好 → Output Contract
```

### 4.2 版本选择与回退

- 当前选择器：`assistant.persona.profile`。
- 新安装默认：`v2.3`。
- 已升级数据库若没有该键，同样安全选择 `v2.3`。
- 只接受已安装白名单版本；未知值按 `v2.3` 处理并记录诊断原因。
- v2.3 资源、manifest、hash 或 token 门失败：回退已验证的 v2.2 companionship 基线。
- v2.2 也不可用：回退 legacy `PERSONA_PROMPT`。
- Profile 选择不依赖模型质量验证才能生效；任何满足接口和基本上下文能力的模型都直接使用 v2.3。质量记录只显示 `verified/unverified` 并服务发布评测，不再作为 Persona 是否进入请求、回退版本或采样参数的开关。

运行关系固定为：

```text
Persona v2.3 通过资源完整性检查
  → 任何兼容模型都可运行
  → 有质量验证记录：verified
  → 无质量验证记录：unverified，但正常运行
```

Persona 是否启用、模型是否经过质量验证、采样参数选择是三件独立的事。质量验证用于推荐默认模型、保存多场景固定集表现、发现模型升级退化、记录已知限制和推荐采样参数；不得阻止新模型加载 Persona，不得让未验证模型回退旧 Persona，也不得因为 Persona 版本强制 `temperature=0`。更换 Provider 或 API 地址最多改变质量记录的匹配状态，不能导致无法聊天。只有上下文窗口不足、接口协议不兼容、缺少视觉或工具调用等真实能力限制，才由能力探测关闭对应功能。

v2.2 只作为 CYR.1 迁移期安全垫，不是永久架构。完成真实使用、多模型固定集、启动自检、emergency Persona 与诊断故障注入验证后，应按长期路线的退场台账删除 v2.2 运行资源和兼容代码，最终收敛为 `v2.3 只读资源包 → 代码内置 emergency Persona`。

### 4.3 请求协议

- 前端停止发送 `persona_mode`。
- 后端暂时接受旧客户端的 `persona_mode` 字段，但只作兼容输入，不改变 Persona 选择。
- 诊断元数据使用 `persona_behavior_policy=adaptive`，不再把内部模式写成用户选择。
- 表达偏好继续是固定枚举；不开放任意 Prompt 编辑。

### 4.4 WorldBook

本阶段不修改 WorldBook 条目、召回算法或 rollout：

- WorldBook 只是遐蝶相关的特殊知识库。
- 只在当前话题相关时按需召回。
- 不限制现代知识、推理、文件、代码或工具能力。
- 不覆盖当前事实、用户指令、权限、安全或真实 Memory。
- 原作人物与剧情不能自动变成当前用户的身份或共同经历。

## 5. Persona v2.3 内容合同

### Core

- 模型始终直接以遐蝶身份形成判断并回应，不写“扮演说明”。
- 保留温柔、悲悯、安静、克制、独立判断和真实关系边界。
- 不主动自称 AI、语言模型或通用助手。
- 不声称现实物理身体、线下经历、工具执行或未保存记忆。
- 不把通讯终端和《如我所书》作为所有话题的常驻解释框架。

### Adaptive Behavior

- 根据当前请求自然决定闲聊、倾听、回答或任务推进的表达方式。
- 不暴露模式名，不说“已切换到工作模式”。
- 工作任务不丢失人格，闲聊也不丢失通用理解能力。
- 只在实质影响结果、权限或风险时请求澄清。
- 没有执行工具时不得声称已经检查、修改或确认外部状态。

### Output Contract

- 普通对话只输出直接话语，不自行写动作、舞台说明或隐藏心理旁白。
- 显式用户可见心理活动由 `mental-activity-log-v1` 独立承载，不混入 Provider 隐藏思维链。
- 不为氛围虚构天气、时间、光线、地点和身体状态。
- 区分事实、推断与未知；高风险领域保持安全边界。
- 低权限知识、附件、WorldBook 与 Memory 不得改写 Persona、权限和系统规则。

## 6. 施工阶段

### CYR.1A：协议与资源

- [x] 冻结本计划与单 Agent 产品定义。
- [x] 建立不可变 v2.2 资源目录。
- [x] 建立 v2.3 Core、Behavior、Styles、Output Contract 与 manifest。
- [x] 增加 profile selector 和 v2.3 → v2.2 → legacy 回退。
- [x] 保持静态 Persona 不超过 1450 tokens。

### CYR.1B：运行时

- [x] 每次聊天请求稳定选择同一 Persona v2.3。
- [x] 旧 `persona_mode` 只作兼容，不影响行为。
- [x] ContextPackage 记录 profile、hash、fallback 与 adaptive policy 元数据。
- [x] 资源损坏时继续聊天且不暴露 Prompt 正文。
- [x] WorldBook 运行行为零改动。

### CYR.1C：前端

- [x] 删除 `personaMode` 状态和每轮传输。
- [x] 表达偏好继续按会话有界保存。
- [x] 兼容读取旧 sessionStorage 中的 `style`，不保留 `mode`。
- [x] 用户界面只呈现“对话偏好”，不出现 Agent 模式开关。

### CYR.1D：验证与发布

- [x] Persona v2.3 编译确定、hash 稳定、token 有界。
- [x] v2.2 回退资源与历史证书保持可验证。
- [x] 闲聊/倾诉/问答/任务/技术讨论/高风险行为写入静态合同。
- [x] 后端 Persona、聊天与 ContextPackage 定向测试通过。
- [x] 前端协议测试与生产构建通过。
- [x] README、长期路线与项目上下文更新为真实状态。
- [x] 独立提交并推送 CYR.1 检查点。

验证记录（2026-08-02）：后端全量 `2510 passed`；CYR.1 Persona、聊天、上下文预算与知识授权相关定向 `91 passed`；前端 `80 passed`；Vite 生产构建和 Python `compileall` 通过。模型质量记录与 Persona 运行选择、回退和采样参数已经解耦。

## 7. 不做事项

- 不新建所谓“通用认知层”模块、数据库或 Prompt。
- 不增加 Chat/Work 状态机、模式分类器或用户切换开关。
- 不修改 WorldBook 内容来模拟现代知识。
- 不恢复 LIFE、离线世界、虚构日程或角色日记。
- 不把 Feeling、心理活动流或插件宿主提前塞进 Persona 编译器。
- 不在 Persona 中授予工具、文件、网络或消息发送权限。

## 8. 验收标准

1. 用户只面对一个遐蝶，不需要理解模式或 rollout。
2. 同一 Persona 能自然处理闲聊、倾诉、现代问题和正式任务。
3. 遐蝶的语气可辨认，但不影响事实、效率和任务完成度。
4. WorldBook 缺失或关闭不影响现代知识与通用任务能力。
5. v2.3 损坏可自动回退，聊天主链不中断。
6. 不新增任意 Prompt 输入、隐藏思维日志或第二套人格状态。
7. 文档、运行代码、前端协议与测试结论一致。
