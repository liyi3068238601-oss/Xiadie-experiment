# Xiadie 可观测性与诊断日志施工计划

- 版本：v1.1
- 日期：2026-08-02
- 状态：LOG.1～LOG.5 实验基线已于 2026-08-02 投入使用；发布级硬化继续跟踪
- 适用仓库：`Xiadie-experiment`
- 适用范围：Python 后端、React 前端、Electron 启动器、未来 ToolRegistry、TaskRun、Worker 与插件系统
- 参考项目：Neo-MoFox、Neo-MoFox-Launcher、`tt-P607/kokoro_flow_chatter`、`tt-P607/feeling`（只参考产品行为与信息架构，不复制 AGPL 源码）

## 1. 决策摘要

Xiadie 建立一套统一的结构化可观测性底座，并提供两个职责明确的用户界面：

1. **运行审计**：回答“系统做过什么、是否获得授权、结果是什么”，以数据库中的领域事实为准。
2. **诊断终端**：回答“刚才哪里出错、哪个模块或工具失败、异常是什么”，以实时结构化日志为准。

诊断终端同时允许显示由插件或 Agent Core **显式生成并声明为用户可见**的心理活动、内心独白摘要和 Feeling 状态。这类内容属于产品生成的角色活动日志，不是 Provider 的隐藏推理，也不得从隐藏 reasoning token、系统提示词或运行时堆栈反推产生。

所有运行事件先形成统一 `OperationalLogEvent`，再按策略分发到彩色终端、滚动 JSONL 文件、内存环形缓冲区与实时 SSE。ToolRun、TaskRun、PermissionGrant 等权威状态仍由各领域数据库所有者维护，日志不得成为业务真相的第二写入源。

施工顺序固定为：

```text
LOG.0 文档与协议冻结（本文件）
  → LOG.1 统一 Logger、终端格式与 JSONL
  → LOG.2 TraceContext 与 ToolRun v2
  → LOG.3 环形缓冲区与 SSE
  → LOG.4 前端诊断终端
  → LOG.5 Electron 启动链、导出与支持包
  → LOG.6 插件日志契约
```

LOG.1～LOG.5 是 CYR.2 TaskRun 与 CYR.3 ToolRegistry 的前置可观测性底座；LOG.6 与插件宿主共同落地。

## 2. 背景与问题

### 2.1 当前实现

现有 `backend/app/runtime_logs.py` 从模型调用、决策、检索、上下文装配和 `tool_logs` 等业务表拼装只读时间线。前端 `ToolLogsPage.tsx` 每 5 秒轮询一次，支持分类、状态、搜索和元数据展开。

这套实现适合回顾业务事件，但不适合作为开发者诊断终端：

- `tool_logs` 只有 `tool`、`risk_level`、`status`、`summary` 和 `created_at` 等摘要字段。
- 当前生产链没有完整、统一的 ToolRun 写入与阶段转换。
- 缺少 `trace_id`、任务、会话、插件、工具调用和父子操作关联。
- 缺少排队、授权、执行、重试、结束等阶段以及耗时。
- 缺少异常类型、错误码、脱敏消息和堆栈引用。
- 前端轮询无法连续呈现启动错误、子进程输出和短时事件。
- 多个模块使用各自的输出方式，格式、模块名、颜色和上下文不一致。

### 2.2 目标体验

开发者打开“诊断终端”后，应能直接看到类似下面的事件链：

```text
14:08:21.117 INF task.scheduler     trace=8c31 task=tsk_42  TaskRun started
14:08:21.164 DBG tool.registry      trace=8c31 tool=file.read Tool resolved
14:08:21.171 INF permission.guard   trace=8c31 tool=file.read Allowed scope=workspace
14:08:21.206 ERR tool.file.read     trace=8c31 run=tlr_91    FileNotFoundError: docs/a.md
14:08:21.209 INF task.scheduler     trace=8c31 task=tsk_42  Waiting for user action
```

用户不需要阅读 Python 堆栈才能知道：失败的是 `file.read`，错误发生在执行阶段，关联任务为 `tsk_42`，系统没有把失败伪装成成功。

### 2.3 参考边界

Neo-MoFox 的模块颜色、Rich 终端表达、异常可见性与事件广播，以及 Neo-MoFox-Launcher 的 PTY 终端、搜索、复制、清屏、导出、自动滚动和分实例标签页，构成本计划的交互参考。

上述参考仓库采用 AGPL。Xiadie 只吸收可独立实现的产品原则、字段需求和交互模式，不复制源码、样式资源或专有实现。

## 3. 目标与非目标

### 3.1 目标

- 一眼识别时间、级别、模块、动作、状态与错误。
- 从一次用户请求追踪到 TaskRun、ToolRun、模型调用和产物。
- 后端、Electron、工具和未来插件使用同一事件语义。
- 终端输出适合人读，JSONL 适合机器筛选和支持包分析。
- 日志实时可见，不依赖高频数据库轮询。
- 异常信息足以定位代码，同时默认保护用户正文、密钥和隐藏推理。
- 日志不可用时不阻断聊天、任务取消或权限拒绝。
- 支持 Windows 启动器环境下的进程边界、启动失败和崩溃诊断。
- 允许以 `💭`、情绪、预期反应和决策动作展示显式生成的角色活动流。

### 3.2 非目标

- 不记录或展示 Provider 隐藏 chain-of-thought、reasoning token 或系统内部推理草稿；这不禁止模型通过已声明字段显式生成、允许用户查看的角色内心独白。
- 不把所有请求参数、文件正文和模型提示词原样落盘。
- 不用日志重建数据库业务状态。
- 不在本阶段接入云端日志平台或默认上传诊断数据。
- 不把诊断终端设计成普通用户必须理解的主交互界面。
- 不在 LOG 阶段开放任意 Shell、文件写入或外部消息权限。
- 不实现 MoFox 的 QQ 特有 `do_nothing` / `pass_and_wait` 行为。

## 4. 术语与所有权

| 术语 | 定义 | 唯一所有者 |
|---|---|---|
| OperationalLogEvent | 某一时刻发生的结构化诊断事件 | Observability |
| AuditEvent | 对授权、执行、副作用和结果的持久业务证据 | 对应领域；ToolRegistry 管 ToolRun |
| TraceContext | 一次因果链的关联标识与最小上下文 | Observability 规范，各领域传播 |
| TaskRun | 一项持续任务的权威状态 | Task |
| ToolRun | 一次真实工具调用的权威状态与证据 | ToolRegistry |
| DiagnosticTerminal | 实时查看 OperationalLogEvent 的开发者界面 | Observability UI |
| SupportBundle | 用户主动导出的脱敏诊断包 | Observability / Electron |

关键规则：

- Logger 可以描述领域对象，但不得修改其权威状态。
- 领域服务先提交权威状态，再发出相应日志；若日志写入失败，业务事务仍按原结果完成。
- `OperationalLogEvent` 可按保留期删除；ToolRun 等审计事实按各自生命周期处理。
- 任何“成功”日志必须来自实际返回值或已提交事务，不能来自模型自述。

## 5. 总体架构

```text
Python / Electron / Tool / Plugin
               │
               ▼
       Structured Logger API
               │
       Redaction + Normalization
               │
     ┌─────────┼───────────┬──────────────┐
     ▼         ▼           ▼              ▼
Human Console  JSONL     Ring Buffer   Audit Adapter
ANSI/Rich      Rotation  bounded RAM   domain-owned DB
                           │
                           ▼
                        SSE API
                           │
                           ▼
                    DiagnosticTerminal
```

### 5.1 分层原则

1. **采集层**：统一 API、级别、模块名、事件名和异常捕获。
2. **规范层**：补齐时间、进程、trace、环境和 schema version。
3. **脱敏层**：按字段类型与显式敏感标记处理。
4. **分发层**：不同 sink 独立失败、独立背压。
5. **查询层**：环形缓冲、文件读取和权威审计查询互不混淆。
6. **展示层**：终端与审计时间线使用同一关联 ID，但呈现目的不同。

## 6. `operational-log-v1` 协议

### 6.1 必填字段

```json
{
  "schema": "operational-log-v1",
  "event_id": "log_01J...",
  "timestamp": "2026-08-02T14:08:21.206+08:00",
  "monotonic_ms": 9031821.44,
  "level": "ERROR",
  "logger": "tool.file.read",
  "event": "tool_run_failed",
  "message": "File read failed",
  "process": "backend",
  "pid": 12044,
  "thread": "MainThread",
  "environment": "experiment"
}
```

规则：

- `timestamp` 使用带时区 ISO 8601；耗时计算使用单调时钟。
- `logger` 使用稳定点分命名，不使用源码文件绝对路径。
- `event` 使用稳定 snake_case 机器名；`message` 是短人类摘要。
- `level` 只允许 `TRACE`、`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。
- 不允许用级别代替状态；失败必须同时有对应 `event` 或 `status`。

### 6.2 关联字段

```json
{
  "trace_id": "trc_...",
  "span_id": "spn_...",
  "parent_span_id": "spn_...",
  "session_id": "ses_...",
  "request_id": "req_...",
  "task_run_id": "tsk_...",
  "tool_run_id": "tlr_...",
  "plugin_id": "plugin.example",
  "model_call_id": "mdl_..."
}
```

并非每个事件都必须拥有全部字段，但一次请求内已存在的上下文必须继续传播。后台任务必须创建新 trace，并用 `linked_trace_id` 指向触发来源，不能错误继承已结束的 HTTP 请求上下文。

### 6.3 状态与计时字段

```json
{
  "phase": "executing",
  "status": "failed",
  "attempt": 2,
  "duration_ms": 37,
  "queue_ms": 4,
  "timeout_ms": 10000
}
```

`phase` 与具体领域一致。工具统一使用：

```text
queued → resolving → authorizing → executing → verifying → terminal
```

终态为 `succeeded | failed | cancelled | denied | timed_out`。每次重试有独立 `attempt`，但属于同一个 ToolRun 时共享 `tool_run_id`；若重试会产生新的副作用，则必须创建新 ToolRun 并链接前次运行。

### 6.4 错误字段

```json
{
  "error": {
    "code": "FILE_NOT_FOUND",
    "type": "FileNotFoundError",
    "message": "The requested path does not exist",
    "retryable": false,
    "stack_ref": "stk_01J..."
  }
}
```

- `code` 是稳定产品错误码。
- `type` 是异常类别，不包含动态值。
- `message` 必须脱敏，不直接拼接完整输入。
- 开发模式可在本地 JSONL 保存脱敏堆栈；UI 默认折叠。
- `stack_ref` 关联堆栈，不把多行堆栈塞进列表摘要。
- 捕获异常时必须保留异常因果链；不得只输出“调用失败”。

### 6.5 数据摘要字段

允许记录：

- 参数名、参数数量、类型、大小、哈希和截断后的安全摘要。
- 路径相对于已授权工作区的 locator。
- HTTP 方法、规范化域名、状态码和响应字节数。
- 模型、Provider、token 数、延迟与错误类别。
- 产物 ID、MIME、大小、版本和校验哈希。

默认禁止记录：

- API Key、Cookie、Authorization Header、密码和访问令牌。
- 完整 system/developer prompt、完整用户消息和模型原始回复。
- 完整文件正文、知识切片、记忆正文和工具原始参数/结果。
- Provider 隐藏 chain-of-thought、reasoning token、系统内部推理草稿，以及未标记为可见产品输出的自由文本。
- 未经许可的用户名、绝对路径、邮件地址或账号标识。

允许作为敏感产品内容记录：

- 经 `mental-activity-log-v1` 验证且 `visibility=user_visible` 的心理活动或内心独白摘要。
- Feeling 插件显式提交的情绪名称、强度、短原因、衰减与注入事件。
- 与显式角色活动绑定的预期反应、等待上限、回复/工具动作摘要。

这类字段必须使用独立 `content_class=character_mental_activity`，受专门开关、长度上限、会话隔离、保留期、清除和支持包排除规则控制，不能伪装成普通无正文诊断元数据。

## 7. `trace-context-v1` 协议

### 7.1 创建与传播

- HTTP 请求进入 FastAPI 时创建或校验 `request_id` 与 `trace_id`。
- 聊天、TaskRun、ToolRun、模型调用和产物写入分别创建 span。
- `contextvars` 传播 Python 异步上下文；线程池和后台任务显式复制最小上下文。
- Electron 启动后端时创建 `launcher_session_id`，通过受控环境或启动参数传递，不包含密钥。
- 前端只接收展示所需关联 ID，不得伪造服务端授权上下文。
- 插件只能获得宿主下发的子 span，不能覆盖根 trace。

### 7.2 生命周期

- trace 在请求完成后可以继续关联已显式创建的 TaskRun，但不能无限存活。
- TaskRun 恢复时创建新 trace，并保存 `linked_task_run_id` 与前一 trace 引用。
- 用户取消产生独立取消 span，并关联目标运行。
- SSE 断线重连使用事件游标，不创建虚假的重复执行 trace。

## 8. ToolRun v2

### 8.1 权威字段

ToolRun v2 计划占用下一可用数据库迁移号；按当前 Schema 84 基线，目标为 Schema 85，正式施工前仍须检查是否被其他专项占用。

```text
ToolRun
├─ id
├─ trace_id / parent_span_id
├─ session_id / task_run_id
├─ plugin_id / tool_name / tool_version
├─ risk_level / permission_grant_id
├─ status / phase / attempt
├─ queued_at / started_at / finished_at / duration_ms
├─ arguments_summary_json / result_summary_json
├─ artifact_ids_json
├─ error_code / error_type / error_message / stack_ref
├─ cancellation_reason
├─ idempotency_key
└─ created_at / updated_at
```

### 8.2 状态机

```text
queued
  ├─ denied
  ├─ cancelled
  └─ authorizing
       ├─ denied
       ├─ cancelled
       └─ running
            ├─ succeeded
            ├─ failed
            ├─ timed_out
            └─ cancelled
```

约束：

- 终态不可改回运行态。
- 取消请求与取消完成分开记录。
- `succeeded` 必须有实际返回证据；产生文件时必须关联 Artifact。
- `denied` 不执行工具主体。
- 重试策略、幂等键和副作用分类必须由 ToolManifest 声明。
- 旧 `tool_logs` 在兼容期只读；不得继续成为新工具运行的唯一证据。

### 8.3 ToolRun 与日志的关系

每次状态转换至少产生一个结构化事件，但两者不要求一对一：进度、重试、子步骤和异常堆栈只存在日志中；最终状态、授权引用、结果摘要和产物引用存在 ToolRun 中。

## 9. 后端 Logger API

建议接口：

```python
logger = get_logger("tool.file.read")

logger.info(
    "tool_run_started",
    "Reading workspace file",
    tool_run_id=run.id,
    phase="executing",
    fields={"path_locator": safe_locator},
)

logger.exception(
    "tool_run_failed",
    "File read failed",
    error=exc,
    tool_run_id=run.id,
)
```

API 规则：

- `event` 与 `message` 分离。
- 结构化字段只接受可 JSON 序列化值和已登记的安全包装类型。
- `SecretValue`、原始 Request/Response、数据库连接与任意对象拒绝序列化。
- `logger.exception` 必须在异常处理上下文中调用并保留因果链。
- 领域包装器提供 `tool_span`、`model_span`、`task_span`，统一开始、成功、失败和耗时。
- 高频 progress 事件采样；状态转换、权限、失败和取消不得采样丢失。

## 10. 输出与保留策略

### 10.1 人类终端

固定列顺序为时间、级别、模块、关联短 ID、消息和关键字段。模块颜色通过稳定哈希分配，不能每次启动变化。错误必须显示异常类型和消息；堆栈另起缩进块。

开发默认级别为 `INFO`，可按模块临时提升到 `DEBUG`。`TRACE` 不进入普通发行默认配置。

### 10.2 JSONL 文件

建议目录：

```text
Xiadie-Experiment/logs/
├─ backend/current.jsonl
├─ desktop/current.jsonl
└─ archive/YYYY-MM-DD/*.jsonl.gz
```

默认策略：

- 单文件 10 MiB 或跨日轮转，任一条件先到即轮转。
- 默认保留 14 天且总量不超过 200 MiB。
- 超限时先删除最旧归档，不删除当前文件。
- 崩溃恢复时容忍最后一行不完整。
- 写入使用 UTF-8，一行一个完整 JSON 对象。
- 轮转与压缩在低优先级线程执行，失败仅告警，不阻断业务。

具体大小和保留天数进入设置，但必须有安全上下限。

### 10.3 内存环形缓冲区

- 默认保存最近 5,000 条或 8 MiB，任一上限先到即淘汰最旧事件。
- 每个事件拥有递增游标。
- ERROR/CRITICAL 可在容量压力下获得更高保留权，但不能无限增长。
- 进程重启后缓冲区清空；历史查询读取 JSONL 或审计库。

## 11. 诊断 API

计划提供：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/diagnostics/logs` | 按游标读取缓冲区快照 |
| GET | `/api/diagnostics/logs/stream` | SSE 实时事件 |
| GET | `/api/diagnostics/traces/{trace_id}` | 聚合单次因果链 |
| GET | `/api/diagnostics/tool-runs/{id}` | ToolRun 权威详情与相关日志 |
| POST | `/api/diagnostics/export` | 用户确认后生成脱敏支持包 |

安全规则：

- 只监听本机回环地址并要求现有本地 API 令牌。
- 诊断 API 与普通业务 API 使用相同来源校验。
- SSE 支持 `Last-Event-ID`；游标过旧时返回明确 gap 事件。
- 服务端再次应用展示脱敏，不信任落盘事件已经安全。
- 导出必须由用户主动触发，默认不包含数据库、聊天正文或用户文件。
- 不提供任意文件路径读取接口。

## 12. 前端“诊断终端”

### 12.1 信息结构

“运行日志”更名为“运行审计”，继续展示业务时间线。新增开发者入口“诊断终端”，默认不占据聊天主界面。

诊断终端包含：

- 顶部连接状态、暂停显示、自动滚动和事件速率。
- 级别、进程、模块、任务、工具、插件、状态和时间范围过滤。
- 全文搜索只针对已脱敏展示字段。
- 主列表使用等宽字体、虚拟滚动和稳定颜色。
- 单击事件打开详情抽屉，展示关联 ID、结构化字段、异常和跳转。
- 从 trace、TaskRun、ToolRun 互相跳转。
- 复制当前行、复制脱敏详情、清屏（只清视图）、导出筛选结果。
- 断线重连、日志缺口和后端重启有明确提示。

### 12.2 可读性规则

- 默认隐藏 DEBUG/TRACE。
- ERROR 行显示 `工具名 + 阶段 + 错误类型 + 消息`，不能只显示红色“失败”。
- 长字段折叠；关键状态无需展开即可看到。
- 模块颜色表达来源，级别颜色表达严重性，两者不混用。
- 时间可在本地时间和相对耗时间切换。
- “清屏”不删除文件或审计记录。
- 普通用户模式只展示友好错误与恢复建议；开发者模式展示诊断终端。

### 12.3 性能边界

- 使用批量刷新与虚拟列表，不为每条 SSE 事件单独触发整页重渲染。
- 页面不可见时降低 UI 刷新频率，但服务端缓冲继续工作。
- 默认最多展示 5,000 条；更早历史通过分页查询。
- 前端过滤不得阻塞聊天流或取消按钮。

## 13. Electron 与启动器日志

Electron 是 Xiadie 自带启动链，不另造独立 MoFox Launcher 式产品，但吸收其终端可读性能力。

必须覆盖：

- Electron 主进程启动、单实例锁、窗口、托盘和 IPC。
- 后端子进程命令版本、PID、端口、就绪等待、退出码和信号。
- stdout/stderr 按行解析；无法解析的行包装为 `legacy_process_output`。
- Vite/生产前端加载失败、preload 错误与 renderer 崩溃。
- 后端异常退出后的有限重启、退避和最终失败说明。
- 启动阶段日志在后端 SSE 尚未可用时由 Electron 本地缓冲。
- 后端就绪后可以在诊断终端切换 `desktop` / `backend` 进程来源。

不得把本地 API 令牌、完整启动环境、用户目录绝对路径或安全存储内容写入日志。

## 14. 隐私、脱敏与支持包

### 14.1 脱敏顺序

1. 调用点使用安全摘要，避免先构造敏感字符串。
2. Logger 根据字段类型和字段名执行结构化脱敏。
3. Sink 写入前执行最终扫描。
4. API 返回前按展示策略再次过滤。
5. 导出支持包执行最严格的独立清洗与清单检查。

常见替换：

- 密钥：`[REDACTED_SECRET]`
- 用户绝对目录：`<USER_HOME>/...`
- 授权工作区路径：`<WORKSPACE>/relative/path`
- 消息正文：长度、语言、哈希，不保存原文
- 文件正文：MIME、字节数、哈希，不保存内容

### 14.2 支持包内容

默认包含：

- 脱敏 JSONL 日志。
- 应用、Schema、Python、Node、Electron 和操作系统版本。
- 启用功能开关与非敏感配置。
- 最近失败 trace 的结构摘要。
- 数据库完整性检查结果，不包含数据库文件。
- 支持包 manifest、文件哈希和生成时间。

默认排除：

- API Key、令牌、Cookie、账号凭据。
- 聊天、记忆、知识库和用户文件正文。
- 原始模型 prompt/response。
- 心理活动、内心独白、Feeling 原因和融合叙事正文；只有用户在导出确认页单独勾选后才能加入，并须再次脱敏。
- 任意数据库副本。
- 未脱敏崩溃 dump。

导出前 UI 显示包含项、排除项、目标路径与大小估计。项目不自动上传支持包。

## 15. 未来插件系统日志契约

插件不得直接配置全局 Python logger、写核心日志目录或访问诊断 SSE。宿主通过 `PluginContext` 提供受限 logger：

```python
plugin_logger = context.get_logger("worker")
plugin_logger.info("job_started", "Plugin job started", fields={"job_id": safe_id})
```

宿主自动注入：

- `plugin_id`、插件版本和宿主版本。
- 当前 trace/span 与获准的 TaskRun/ToolRun。
- 插件权限快照引用。
- 速率限制、字段大小限制和脱敏策略。

插件不能：

- 伪造其他插件或核心模块名。
- 改写 trace 根、ToolRun 状态或权限结果。
- 记录密钥、未授权正文或 Provider 隐藏推理；显式 `user_visible` 角色活动必须走专门协议，不能作为任意 logger 字符串绕过治理。
- 绕过日志速率限制。
- 把日志当成插件间消息总线。

插件崩溃、加载失败、Manifest 不兼容、权限拒绝和 hook 超时必须以宿主事件记录，即使插件 logger 自身不可用。

## 16. 心理活动流、内心独白和 Feeling 日志

### 16.1 参考实现结论

`kokoro_flow_chatter` 将每轮控制动作中的 `thought`、`expected_reaction`、`max_wait_seconds` 和 `mood` 提取为显式决策元数据，写入有界 `MentalLog`，再与近期对话按时间线融合；其调试日志用 `💭` 显示内心想法，并同时显示回复、动作、等待和心情。它的 MentalLog 还区分规划、等待、超时、主动触发、用户打断和备忘等事件。

`feeling` 以会话隔离方式保存 `mood`、`intensity` 和短 `reason`，通过时间半衰期与对话轮数共同衰减。`set_bot_feeling` 成功时会将情绪、强度和原因写入日志，可选 debug 日志还会显示实际注入的活跃或平和状态。

参考来源：[`tt-P607/kokoro_flow_chatter`](https://github.com/tt-P607/kokoro_flow_chatter)、[`tt-P607/feeling`](https://github.com/tt-P607/feeling)。本次审计快照分别为 `993a9701`（KFC 2.2.1）与 `1e65640b`（Feeling 1.0.2），两者均只作行为参考，Xiadie 独立设计协议与实现。

### 16.2 产品决策

Xiadie **允许并计划实现**以下内容：

- 将模型显式生成的角色心理活动或内心独白写入本地日志。
- 在诊断终端中使用 `💭` 明确展示，而不是只保存不可见状态码。
- 将内心活动、实际回复、工具选择、Feeling 和系统事件按时间排序。
- 在后续上下文中按预算召回近期活动流，形成连续但有界的角色表达。
- 为用户提供启用、查看、暂停记录、清除与保留期控制。

这里的“内心独白”是模型按公开结构化字段生成、产品主动向用户展示的角色文本。它不等于、也不得声称是模型底层真实思维或 Provider 隐藏 chain-of-thought。

### 16.3 `mental-activity-log-v1`

```json
{
  "schema": "mental-activity-log-v1",
  "event_id": "mnt_01J...",
  "timestamp": "2026-08-02T14:08:21.180+08:00",
  "session_id": "ses_...",
  "trace_id": "trc_...",
  "turn_id": "turn_...",
  "event_kind": "bot_planning",
  "origin": "explicit_model_field",
  "visibility": "user_visible",
  "content_class": "character_mental_activity",
  "thought": "我想先确认文件是否存在，再告诉她准确结果。",
  "mood": "专注",
  "intensity": 0.42,
  "expected_reaction": "用户会确认目标路径",
  "action_summaries": ["file.read"],
  "retention_class": "conversation_bounded"
}
```

首批事件类型：

| `event_kind` | 用途 | 是否允许正文 |
|---|---|---|
| `bot_planning` | 本轮显式角色想法与动作选择 | 是，短文本 |
| `reply_committed` | 内心活动关联的真实回复已提交 | 只存回复 ID/摘要 |
| `tool_selected` | 选择某工具及面向用户的简短动机 | 是，短文本 |
| `feeling_changed` | 情绪、强度和短原因发生变化 | 是，短原因 |
| `feeling_decayed` | 时间/轮数衰减后的状态 | 否，只存结构化状态 |
| `generation_interrupted` | 新消息打断了本轮生成 | 否，只存关联 ID |
| `context_recalled` | 近期心理活动被上下文装配采用 | 否，只存条目 ID 与预算 |

`waiting_start`、`wait_timeout`、`do_nothing`、`pass_and_wait` 和主动续话相关事件暂不接入当前 Xiadie 产品主链；等心理活动流和任务线路稳定、且产品确实需要“不发送消息”语义时再单独启用。

### 16.4 写入来源与硬边界

允许来源：

1. 工具调用参数或结构化响应中的显式 `thought` / `mood` / `expected_reaction` 字段。
2. Feeling 插件调用受控接口提交的情绪、强度和短原因。
3. 系统根据可验证状态产生的无正文事件，如打断、衰减、过期和上下文采用。

禁止来源：

1. Provider 返回但未声明为用户可见的 reasoning token 或隐藏推理通道。
2. system/developer prompt、异常堆栈、模型内部草稿或调试抓包中的推理文本。
3. 事后要求另一个模型猜测“刚才真实在想什么”。
4. 把工具密钥、用户文件正文、记忆正文或完整聊天原文复制到 `thought`。
5. 用心理活动文本为未授权工具、外发、主动消息或权限扩大提供依据。

### 16.5 长度、保留与隐私

- `thought` 默认最多 240 个 Unicode 字符；`expected_reaction` 最多 120 字符。
- Feeling `mood` 最多 16 字符、`reason` 最多 80 字符、`intensity` 限制在 0～1。
- 每个会话默认保留最近 50 条心理活动，设置允许范围为 20～200；超限裁剪最旧条目。
- 默认只保存在本地并按会话隔离，不进入 Memory、PWM 或 Knowledge。
- 用户清除会话时可同时清除活动流；也提供单独清除入口。
- 日志页默认可见，但首次启用需说明这是 AI 生成的角色表达，不是底层真实思维。
- 支持包、崩溃上传和普通审计导出默认排除正文。
- 临时聊天只在内存保存，窗口或会话结束后清除。

### 16.6 日志展示

终端人类格式示例：

```text
[14:08:21] kfc.mental | INFO | 💭 我想先确认文件是否存在，再给出准确结果 [trace=8c31]
[14:08:21] feeling.state | INFO | 心情=专注 强度=0.42 原因=正在核对文件 [trace=8c31]
[14:08:21] tool.file.read | ERROR | FileNotFoundError: docs/a.md [trace=8c31]
[14:08:21] kfc.mental | INFO | 💭 路径不存在，我应该说明错误并请她确认位置 [trace=8c31]
```

展示规则：

- `💭` 与普通 DEBUG/INFO 事件在视觉上区分，并提供“心理活动”独立过滤器。
- 显示正文时必须同时显示其来源为“AI 显式生成”。
- Feeling 行显示情绪、强度、原因与衰减，但不得暗示生理或人类真实感受。
- 复制与导出遵守敏感内容规则；“清屏”仍只清视图。
- 普通错误排查不依赖心理活动正文；关闭该能力后工具诊断仍完整。

### 16.7 Feeling 插件施工约束

Feeling 可以采用与参考插件相似的会话隔离、时间衰减、轮次衰减和显式工具更新思路，但必须独立实现并遵守 Xiadie PluginHost：

- 插件拥有自己的状态命名空间，不直接写 Persona、MEM、PWM 或核心表。
- `set_feeling` 是受 Schema 验证的插件工具，记录 `mood/intensity/reason` 和调用来源。
- 活跃 Feeling 可输出 `ContextContribution` 与 `PresentationIntent`，由核心 owner 验证后使用。
- Feeling 日志允许显示短原因；完整 prompt 注入文本只在显式深度调试开关下显示。
- 插件关闭后停止衰减、注入和写入，不影响聊天、任务、工具与既有记忆。
- 不以情绪或独白扩大权限，也不恢复 LIFE 离线世界、关系压力或未授权主动触达。

## 17. Live2D 后期移除准备

日志 UI 与 Agent Core 不得依赖 Live2D renderer。施工时引入表现层边界：

```text
Agent Core → PresentationIntent → PresentationAdapter
                                  ├─ React UI
                                  ├─ Live2D（过渡期）
                                  └─ Future Shell
```

诊断事件只能引用稳定 `presentation_intent` 或 adapter 名称，不能把 Live2D 动作、模型资源路径或 Pixi 对象写入核心协议。实验路线后期，在非 Live2D 入口、托盘、通知与主窗口能够独立承载交互后，删除 Live2D adapter 与资产加载链，不影响日志、聊天、TaskRun、ToolRun 和插件。

## 18. 迁移与兼容

### 18.1 旧运行日志页

- 第一阶段保留现有 `/api/runtime-logs` 与页面行为。
- UI 文案改为“运行审计”，说明其数据来自业务表而非完整进程日志。
- 新诊断终端使用独立 API，不把 SSE 事件反写旧表。
- 待 ToolRun v2 稳定后，旧 `tool_logs` 查询转为兼容视图或迁移读取。
- 删除旧表前必须确认无生产写路径、无用户依赖并保留迁移报告。

### 18.2 Schema 85（已实施）

LOG.2 开工前执行：

1. 检查 `SCHEMA_VERSION` 与迁移号是否仍为 84。
2. 冻结 ToolRun v2 字段、索引、保留期和回滚脚本。
3. 备份真实数据库并验证恢复。
4. 新库、旧库升级和重复启动分别测试。
5. 若 85 已占用，顺延到下一可用号，不改写既有迁移。

## 19. 分阶段施工

### LOG.0：文档、协议与边界冻结

任务：

- [x] 完成本计划。
- [x] 冻结双界面模型、事件协议、隐私边界与阶段顺序。
- [x] 在 README、项目上下文、Cyrene 路线和所有权矩阵登记。
- [x] LOG.1 开工时记录 ConstructionBaseline（Schema 84、既有运行审计与 Electron 启动链作为施工前基线）。

退出门：所有后续实现能明确找到唯一协议和所有权；不再把业务审计页称为完整诊断日志。

### LOG.1：统一 Logger、终端与 JSONL

任务：

- 建立 Observability 配置、事件模型、上下文 API 和脱敏器。
- 接管后端启动、HTTP、模型、数据库和关键异常日志。
- 输出稳定颜色的人类终端与滚动 JSONL。
- 将现有零散 `print` 和无结构异常逐步迁移。
- 增加日志初始化失败、磁盘写满、轮转失败的降级测试。

退出门：启动、一次聊天、一次模型失败和一次数据库失败均能看到模块、级别、事件、trace 与脱敏错误；关闭文件 sink 不影响业务。

### LOG.2：TraceContext 与 ToolRun v2

任务：

- 实现 `trace-context-v1` 并贯穿 HTTP、SSE、模型调用和后台任务。
- 实现 ToolRun v2、状态机、Repository 与迁移。
- 建立 ToolManifest 包装器和权限阶段事件。
- 为成功、拒绝、取消、超时、异常和重试建立固定测试。
- 保留旧 `tool_logs` 只读兼容。

退出门：每次真实工具调用都有权威 ToolRun；任一失败能从用户请求追踪到异常；无工具调用时不制造 ToolRun。

### LOG.3：环形缓冲区与实时 SSE

任务：

- 实现有界缓冲、游标、批量订阅和背压。
- 实现快照、SSE、重连与 gap 事件。
- 限制单事件和单连接资源。
- 验证慢客户端、断线、后端重启和高频日志。

退出门：诊断流不阻塞聊天流；断线重连不重复执行工具；缓冲区内存严格有界。

### LOG.4：前端诊断终端

任务：

- 将现有页面明确命名为“运行审计”。
- 新增诊断终端、虚拟列表、过滤、搜索和详情抽屉。
- 支持 trace/TaskRun/ToolRun 跳转、复制和视图清屏。
- 对连接、断线、日志缺口和进程重启提供状态提示。
- 完成键盘、屏幕阅读器、窄窗和高事件率测试。

退出门：测试用户能在 30 秒内找出失败工具、阶段、错误类型、错误消息和关联任务；ERROR 不需要展开即可识别。

### LOG.5：Electron、导出与发布诊断

任务：

- Electron 主进程与后端子进程接入统一格式。
- 覆盖启动失败、端口占用、崩溃、退出码和有限重启。
- 实现日志设置、轮转、清理和支持包导出。
- 完成 Windows 打包态、只读目录、磁盘不足和权限失败测试。
- 文档化用户自助诊断流程。

退出门：启动器部署时无需开发工具即可定位前端、Electron 或后端故障；导出包通过秘密扫描与内容清单测试。

### LOG.6：插件日志契约

任务：

- `PluginContext.get_logger`、命名空间、速率限制和字段上限。
- 插件加载、hook、权限、工具和卸载事件。
- 插件隔离与崩溃归因。
- 插件日志兼容版本与认证测试。

退出门：故障可归因到具体插件、版本和 hook；插件不能伪造核心事件、泄露密钥或阻塞宿主。

## 20. 测试矩阵

| 类别 | 必测场景 | 硬门 |
|---|---|---|
| 协议 | 必填字段、未知字段、版本不兼容 | 无不合法事件进入 sink |
| 关联 | HTTP→Task→Tool→Artifact | trace 完整且无错误继承 |
| 工具 | 成功、拒绝、取消、超时、重试、异常 | ToolRun 终态与日志一致 |
| 隐私 | 密钥、Header、正文、路径、异常字符串 | 禁止内容命中为 0 |
| 性能 | 每秒 100/500/1000 事件 | 业务延迟门槛内、内存有界 |
| SSE | 重连、慢客户端、游标过期 | 无执行副作用、gap 明确 |
| 文件 | 跨日、满 10 MiB、磁盘满、尾行损坏 | 可恢复且不阻断业务 |
| UI | 过滤、搜索、滚动、5,000 条、错误详情 | 无明显卡顿，关键信息可见 |
| Electron | 端口占用、后端崩溃、renderer 崩溃 | 进程和退出原因可见 |
| 插件 | 噪声、伪造、秘密、崩溃 | 宿主隔离并明确归因 |

发布前必须额外运行仓库既有后端、前端、构建和 Electron contract 测试；日志施工不得降低聊天取消、权限和数据迁移硬门。

## 21. 可观测性自身指标

- `log_events_total{level,process}`
- `log_events_dropped_total{reason}`
- `log_sink_failures_total{sink}`
- `diagnostic_sse_connections`
- `diagnostic_sse_lag_ms`
- `redaction_matches_total{kind}`
- `tool_runs_total{tool,status}`
- `tool_run_duration_ms{tool}`
- `trace_incomplete_total{boundary}`
- `support_bundle_failures_total{stage}`

这些指标默认只保存在本地聚合值中，不包含用户正文或高基数原始 ID。

## 22. 代码施工映射

预期新增或调整位置：

```text
backend/app/observability/
├─ events.py
├─ context.py
├─ logger.py
├─ redaction.py
├─ sinks.py
├─ buffer.py
└─ api.py

backend/app/tools/
├─ models.py
├─ repository.py
└─ instrumentation.py

frontend/src/components/
├─ RuntimeAuditPage.tsx
└─ DiagnosticTerminalPage.tsx

frontend/src/services/
└─ diagnosticLogs.ts

desktop/
└─ logging / process lifecycle integration
```

实际文件名可服从现有模块结构，但协议、所有权和阶段门不得静默改变。跨阶段重大变更需 ADR。

## 23. README 与文档实时更新纪律

每完成一个 LOG 阶段，同一提交必须更新：

1. 根 `README.md` 当前状态、路线勾选、用户可见入口和测试结果。
2. 本文件对应阶段的任务、退出门证据与实施偏差。
3. `docs/CODEX_PROJECT_CONTEXT.md` 的当前能力基线和近期施工顺序。
4. Schema 或协议变化对应的 ADR、Protocol Registry 与迁移报告。
5. `docs/SPECIALTY_OWNERSHIP_AND_CONTRACT_MATRIX.md` 中新增对象的唯一所有者。

README 只写已实现事实；计划能力必须标为“计划中”或未勾选。不得先把未接入的诊断终端描述为可用。

## 24. 暂停与回滚条件

出现以下任一情况必须暂停扩展：

- 日志中出现密钥、完整用户正文、文件正文或隐藏推理。
- Logger 或 sink 故障阻断聊天、取消、权限拒绝或数据库事务。
- ToolRun 权威状态与日志终态不一致。
- SSE 导致无界内存、线程泄漏或明显影响聊天流。
- 插件可以伪造核心模块、修改 trace 根或绕过脱敏。
- 轮转或清理误删非日志文件。

回滚优先关闭新 sink 或诊断 UI，保留旧运行审计页与业务主链。数据库迁移必须使用前向修复或已验证恢复流程，不改写历史迁移。

## 25. 总体验收

LOG.0～LOG.5 完成时，必须满足：

1. 启动器部署环境中可以实时查看 Electron 与后端日志。
2. 任一工具失败都能直接看到工具名、阶段、错误类型、错误消息和关联任务。
3. 可以从一次用户请求跳转到 TaskRun、ToolRun、模型调用和产物证据。
4. 运行审计与诊断终端职责清楚，数据来源不混淆。
5. 日志文件有界、可轮转、可恢复、可清理。
6. 支持包由用户主动导出，内容透明且通过秘密扫描。
7. 全量测试与隐私硬门通过，日志故障不破坏业务。
8. README 与实际能力一致，没有把计划写成已实现。

## 26. 当前结论

LOG.1～LOG.5 的实验基线已经落地并投入当前实验版：Schema 85 提供 ToolRun v2 与 `mental-activity-log-v1`；后端提供统一 Logger、人类终端、滚动 JSONL、TraceContext、5,000 条/8 MiB 有界缓冲、游标/gap、诊断 SSE、查询 API 和脱敏支持包；前端提供“运行审计/诊断终端”双入口；Electron 将主进程、renderer 和后端子进程启动链写入本地日志并在后端可用时转发。

本轮实现对原计划有三项明确收敛：ToolRun v2 先提供权威 Schema、Repository、状态机与 `instrument` 包装器，待 CYR.3 ToolRegistry 出现后强制接入，不伪称现有业务已经拥有完整工具注册表；前端采用最多保留 5,000 条、最多渲染最近 1,000 条的有界列表，而非引入新的虚拟列表依赖；支持包默认排除显式心理活动正文，心理活动只在本机诊断流与会话有界存储中显示。

实验基线已通过脱敏、缓冲区、Trace、ToolRun 失败链、心理活动边界、支持包排除、Electron 错误规范化、前端重连/暂停/导出和生产构建测试。2026-08-02 最终门禁为后端 `2505 passed`、前端 `80 passed`，Vite 生产构建、Electron 语法检查、Python `compileall` 与真实本机鉴权 HTTP 诊断冒烟均通过。Windows 打包态只读目录、磁盘不足、慢客户端、1,000 events/s 与有限自动重启仍是正式发布前硬门；这些不阻止当前实验版日常使用，但完成前不得标记为发布认证通过。LOG.6 继续随 PluginHost 实施。
