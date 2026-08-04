# CYR.2C Segment 1（Planner / 计划卡 / 来源引用 / 锁定）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让聊天能把目标生成候选计划并落为 TaskRun 草稿；任务页支持"重新生成计划"；节点带来源引用与失效 fail closed；用户修改/显式锁定在重规划时不被覆盖。

**Architecture:** 后端新增纯 `task_planner`（ModelRouter 结构化输出 + 程序校验）与 Schema 88（节点锁定列 + `task_node_source_links`）；`replace_plan` 成为锁定保持与来源引用的唯一写入点；聊天 SSE 尾部下发 `plan_proposal` 事件，前端渲染计划卡；来源失效通过 KIG registry 解析 + 删除/归档钩子置为 `invalidated`。

**Tech Stack:** Python 3.12 / FastAPI / SQLite（Schema 88）/ 现有 `llm.complete_json` / KIG `kig_sources` registry；前端 React + 既有 `api.ts` / `chatSseProtocol.ts` / `TasksPage.tsx` / `ChatView.tsx`。

## Global Constraints

- 计划写入仍然只有 `PUT /plan` 一个入口（`from-proposal` 内部复用同一领域函数）；服务端是 DAG、上限、引用、锁定保持的唯一裁决者。
- 所有修改继续携带 `expected_revision`，统一 409 `{code,message,retry,current}`；新增错误码必须进 `task_run_contract.ERROR_SPECS`。
- 候选计划是瞬态数据：聊天关闭即失效，不新增 plan 提案表。
- 隐私：planner 只发送目标、任务上下文与当前计划结构；不发送记忆/文件正文与隐藏推理；事件与响应只有计划的有界字段。
- conversation 来源只记录引用与摘要，不做持久失效检测（spec §7.3 边界）。
- 节点上限 50、标题 ≤240、验收 ≤500、摘要 ≤240、引用 ≤20/节点；沿用 `redact_text` 长度约束。
- 不引入外部编排运行时、第二数据库或新依赖；演示模型（mock）不执行计划生成，静默跳过。

---

### Task 1: Schema 88 —— 节点锁定/恢复列与来源引用表

**Files:**
- Modify: `backend/app/db.py`（MIGRATIONS 末尾追加 `(88, ...)`）
- Test: `backend/tests/test_task_run_schema_88.py`

**Interfaces:**
- Consumes: 既有 `_apply_migrations`（自动按序应用新条目）。
- Produces: `task_nodes.user_locked`、`locked_reason`、`recovery_class` 列；`task_node_source_links` 表。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_task_run_schema_88.py`：
```python
from __future__ import annotations

import pytest

from app import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_schema_88_adds_lock_recovery_columns() -> None:
    conn = db.connect()
    try:
        cols = _columns(conn, "task_nodes")
        assert {"user_locked", "locked_reason", "recovery_class"} <= cols
        links = _columns(conn, "task_node_source_links")
        assert {"node_id", "source_kind", "source_id", "summary", "status",
                "invalidated_at", "invalidated_reason"} <= links
        assert db.get_schema_version() == 88
    finally:
        conn.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_run_schema_88.py -q`
Expected: FAIL（缺列/缺表/版本 87）。

- [ ] **Step 3: 在 `db.py` 追加迁移 88**

在 `MIGRATIONS` 列表末尾（`(87, ...)` 之后）追加：
```python
    (
        88,
        """
        -- CYR.2C: node lock semantics, recovery class, and source reference links.
        ALTER TABLE task_nodes ADD COLUMN user_locked INTEGER NOT NULL DEFAULT 0
            CHECK(user_locked IN (0,1));
        ALTER TABLE task_nodes ADD COLUMN locked_reason TEXT
            CHECK(locked_reason IS NULL OR locked_reason IN ('edit','explicit'));
        ALTER TABLE task_nodes ADD COLUMN recovery_class TEXT
            CHECK(recovery_class IS NULL OR recovery_class IN
                  ('side_effect_free','idempotent','side_effectful'));
        CREATE TABLE task_node_source_links (
            id TEXT PRIMARY KEY,
            task_run_id TEXT NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
            node_id TEXT NOT NULL REFERENCES task_nodes(id) ON DELETE CASCADE,
            source_kind TEXT NOT NULL CHECK(source_kind IN (
                'memory_fragment','memory_episode','memory_saga','memory_entity',
                'knowledge_source','conversation'
            )),
            source_id TEXT NOT NULL CHECK(length(source_id) BETWEEN 1 AND 200),
            summary TEXT NOT NULL DEFAULT '' CHECK(length(summary) <= 240),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','invalidated')),
            invalidated_at REAL,
            invalidated_reason TEXT CHECK(invalidated_reason IS NULL OR length(invalidated_reason) <= 240),
            created_at REAL NOT NULL
        );
        CREATE INDEX idx_task_source_links_run
            ON task_node_source_links(task_run_id,node_id,id);
        CREATE INDEX idx_task_source_links_source
            ON task_node_source_links(source_kind,source_id,status);
        """,
    ),
```

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_run_schema_88.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/db.py backend/tests/test_task_run_schema_88.py
git commit -m "feat(taskrun): add CYR.2C schema 88 lock and source links"
```

---

### Task 2: 合同内核新增错误码

**Files:**
- Modify: `backend/app/task_run_contract.py`
- Modify: `backend/tests/test_task_run_contract.py`

**Interfaces:**
- Consumes: 无。
- Produces: `ERROR_SPECS` 新增 `task_source_ref_unknown`、`task_source_ref_invalid`、`task_source_invalidated`、`task_plan_locked_node_modified`（均 `modify_then_retry`）。

- [ ] **Step 1: 写失败测试（追加到 test_task_run_contract.py）**

```python
def test_cyr2c_error_specs_present() -> None:
    for code in (
        "task_source_ref_unknown",
        "task_source_ref_invalid",
        "task_source_invalidated",
        "task_plan_locked_node_modified",
    ):
        assert code in contract.ERROR_SPECS
        assert contract.ERROR_SPECS[code].retry == "modify_then_retry"
```

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_run_contract.py -q`
Expected: FAIL（KeyError）。

- [ ] **Step 3: 追加错误码**

```python
    "task_source_ref_unknown": ErrorSpec(
        "计划引用了不存在的来源。", "modify_then_retry",
    ),
    "task_source_ref_invalid": ErrorSpec(
        "计划引用了已失效的来源。", "modify_then_retry",
    ),
    "task_source_invalidated": ErrorSpec(
        "计划包含已失效的来源引用，无法开始执行。", "modify_then_retry",
    ),
    "task_plan_locked_node_modified": ErrorSpec(
        "已锁定步骤在重新生成中不能修改。", "modify_then_retry",
    ),
```

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_run_contract.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/task_run_contract.py backend/tests/test_task_run_contract.py
git commit -m "feat(taskrun): add CYR.2C contract error specs"
```

---

### Task 3: KIG 来源解析补齐（episode/saga/entity）

**Files:**
- Modify: `backend/app/kig_sources.py`
- Modify: `backend/tests/test_kig1_sources.py`

**Interfaces:**
- Consumes: `db`、现有 `SourceRef`/`SourceAdapterRegistry` 模式。
- Produces: registry 新增 `memory_episode`、`memory_saga`、`memory_entity` resolver；`SOURCE_KINDS` 允许这几种。

- [ ] **Step 1: 写失败测试（追加到 test_kig1_sources.py）**

```python
def test_cyr2c_memory_source_resolvers() -> None:
    conn = db.connect()
    try:
        now = db.now()
        conn.execute(
            "INSERT INTO memory_episodes(id,title,summary,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            ("ep-1", "共同项目", "一起做的检索改进", "active", now, now),
        )
        conn.execute(
            "INSERT INTO memory_sagas(id,title,summary,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            ("sg-1", "知识库建设", "检索体系演进", "active", now, now),
        )
        conn.execute(
            "INSERT INTO memory_entities(id,name,summary,archived,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            ("en-1", "知识库", "用户的项目", 0, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    for kind, sid in (("memory_episode", "ep-1"), ("memory_saga", "sg-1"),
                      ("memory_entity", "en-1")):
        ref = kig_sources.registry.resolve(kind, sid)
        assert ref.status == "active"
```

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_kig1_sources.py -q`
Expected: FAIL（resolver 未注册 / SOURCE_KINDS 不允许）。

- [ ] **Step 3: 实现 resolver**

在 `kig_sources.py` 增加：
```python
def _memory_episode(source_id: str) -> SourceRef:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT id,summary,status,updated_at FROM memory_episodes WHERE id=?", (source_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise _missing("memory_episode", source_id)
    digest = f"{row['status']}:{row['updated_at']}:{_canonical_hash(row['summary'])}"
    return SourceRef("memory_episode", source_id, digest, _sha256(digest),
                     "active" if row["status"] in {"active", "completed"} else "inaccessible",
                     "private", f"memory://episodes/{source_id}")


def _memory_saga(source_id: str) -> SourceRef:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT id,summary,status,updated_at FROM memory_sagas WHERE id=?", (source_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise _missing("memory_saga", source_id)
    digest = f"{row['status']}:{row['updated_at']}:{_canonical_hash(row['summary'])}"
    return SourceRef("memory_saga", source_id, digest, _sha256(digest),
                     "active" if row["status"] in {"active", "completed"} else "inaccessible",
                     "private", f"memory://sagas/{source_id}")


def _memory_entity(source_id: str) -> SourceRef:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT id,name,summary,archived,updated_at FROM memory_entities WHERE id=?", (source_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise _missing("memory_entity", source_id)
    digest = f"{row['name']}:{row['updated_at']}:{_canonical_hash(row['summary'])}"
    return SourceRef("memory_entity", source_id, digest, _sha256(digest),
                     "inaccessible" if row["archived"] else "active",
                     "private", f"memory://entities/{source_id}")
```

同时把 `SOURCE_KINDS` 与注册表扩展：
```python
# 注册循环加入：
    "memory_episode": _memory_episode, "memory_saga": _memory_saga,
    "memory_entity": _memory_entity,
```
并在 `SOURCE_KINDS` 允许集中加入 `"memory_episode","memory_saga","memory_entity"`（按文件顶部现有定义方式）。

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_kig1_sources.py tests/test_task_run_schema_88.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/kig_sources.py backend/tests/test_kig1_sources.py
git commit -m "feat(kig): resolve CYR.2C memory episode/saga/entity sources"
```

---

### Task 4: task_runs —— 来源引用、锁定保持与失效阻塞

**Files:**
- Modify: `backend/app/task_runs.py`
- Modify: `backend/tests/test_task_runs.py`

**Interfaces:**
- Consumes: Task 1/2/3 的列、错误码、kig registry。
- Produces:
  - `validate_plan_shape(nodes) -> list[dict]`（公开包装 `_normalize_plan`，供 planner 使用）
  - `replace_plan(..., input_refs/lock 字段随节点传入)`：写来源链接、锁定列；锁定节点不可变校验
  - `get()`：节点返回 `user_locked/locked_reason/recovery_class/source_links`
  - `invalidate_source_links(source_kind, source_id, reason) -> int`
  - `start` 含失效引用时拒绝（`task_source_invalidated`）

- [ ] **Step 1: 写失败测试（追加到 test_task_runs.py）**

```python
def _doc_source() -> str:
    conn = db.connect()
    try:
        now = db.now()
        conn.execute(
            "INSERT INTO knowledge_documents(id,title,collection_id,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            ("kd-1", "检索设计", "col-1", "indexed", now, now),
        )
        conn.execute(
            "INSERT INTO knowledge_collections(id,name,created_at,updated_at) VALUES(?,?,?,?)",
            ("col-1", "默认", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return "kd-1"


def _with_refs(run: dict) -> dict:
    return task_runs.replace_plan(run["id"], [
        {"client_id": "step-a", "title": "梳理流程", "input_refs": [
            {"source_kind": "knowledge_source", "source_id": _doc_source()},
        ]},
    ], expected_revision=run["revision"])


def test_replace_plan_writes_source_links_and_locks() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="src-1")
    saved = _with_refs(run)
    node = saved["nodes"][0]
    assert node["source_links"][0]["source_kind"] == "knowledge_source"
    assert node["user_locked"] is False


def test_locked_node_preservation_enforced() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="lock-1")
    saved = task_runs.replace_plan(run["id"], [
        {"client_id": "a", "title": "第一步", "user_locked": True, "locked_reason": "explicit"},
    ], expected_revision=run["revision"])
    with pytest.raises(task_runs.TaskRunConflict) as exc:
        task_runs.replace_plan(run["id"], [
            {"client_id": "a", "title": "被改写"},
        ], expected_revision=saved["revision"])
    assert exc.value.code == "task_plan_locked_node_modified"


def test_invalidated_source_blocks_start() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="src-2")
    saved = _with_refs(run)
    assert task_runs.invalidate_source_links("knowledge_source", "kd-1", "文档已删除") == 1
    with pytest.raises(task_runs.TaskRunConflict) as exc:
        task_runs.start(saved["id"], expected_revision=saved["revision"])
    assert exc.value.code == "task_source_invalidated"
```

> 实现时若 `knowledge_documents`/`knowledge_collections` 实际 NOT NULL 列与上面 INSERT 不一致，以 `db.py` 中 CREATE TABLE 为准补齐字段（不改变断言）。

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_runs.py -q`
Expected: FAIL（列/表/字段缺失或行为未实现）。

- [ ] **Step 3: 实现 task_runs 变更**

在 `task_runs.py`：
1. 常量与校验：
```python
SOURCE_KINDS = {"memory_fragment", "memory_episode", "memory_saga",
                "memory_entity", "knowledge_source", "conversation"}
RECOVERY_CLASSES = {"side_effect_free", "idempotent", "side_effectful"}
```
2. `_normalize_plan` 每个节点增加解析（在 `prepared.append` 前）：
```python
        raw_refs = raw.get("input_refs") or []
        if not isinstance(raw_refs, list) or len(raw_refs) > 20:
            raise TaskRunConflict("task_plan_dependencies_invalid")
        refs: list[dict[str, str]] = []
        for ref in raw_refs:
            kind = _text(ref.get("source_kind") if isinstance(ref, dict) else None, 40)
            source_id = _text(ref.get("source_id") if isinstance(ref, dict) else None, 200)
            if kind not in SOURCE_KINDS or not source_id:
                raise TaskRunConflict("task_source_ref_invalid")
            refs.append({"source_kind": kind, "source_id": source_id})
        locked = bool(raw.get("user_locked"))
        locked_reason = _text(raw.get("locked_reason"), 20) or None
        if locked_reason not in (None, "edit", "explicit"):
            raise TaskRunConflict("task_plan_node_invalid")
        recovery_class = _text(raw.get("recovery_class"), 30) or None
        if recovery_class is not None and recovery_class not in RECOVERY_CLASSES:
            raise TaskRunConflict("task_plan_node_invalid")
```
并把 `input_refs`、`user_locked`、`locked_reason`、`recovery_class` 并入 `prepared.append`。
3. 公开校验包装：
```python
def validate_plan_shape(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure plan-shape validation shared by planner and workbench (raises TaskRunConflict)."""
    return _normalize_plan(nodes)
```
4. 来源解析（KIG registry + 有界摘要）：
```python
def _resolve_source_link(conn, ref: dict[str, str]) -> tuple[str, str]:
    kind, source_id = ref["source_kind"], ref["source_id"]
    if kind == "conversation":
        return "active", ""  # 边界见 spec §7.3：只记录，不做失效检测
    kig_kind = "knowledge_document" if kind == "knowledge_source" else kind
    try:
        source_ref = kig_sources.registry.resolve(kig_kind, source_id)
    except kig_sources.SourceRefError as exc:
        if exc.code == "source_missing":
            raise TaskRunConflict("task_source_ref_unknown")
        raise TaskRunConflict("task_source_ref_invalid")
    if source_ref.status != "active":
        raise TaskRunConflict("task_source_ref_invalid")
    summary = _source_summary(conn, kind, source_id)
    return "active", summary


def _source_summary(conn, kind: str, source_id: str) -> str:
    sqls = {
        "memory_fragment": ("SELECT content FROM memory_fragments WHERE id=?", lambda r: r["content"]),
        "memory_episode": ("SELECT summary FROM memory_episodes WHERE id=?", lambda r: r["summary"]),
        "memory_saga": ("SELECT summary FROM memory_sagas WHERE id=?", lambda r: r["summary"]),
        "memory_entity": ("SELECT name,summary FROM memory_entities WHERE id=?",
                          lambda r: f"{r['name']}：{r['summary']}"),
        "knowledge_source": ("SELECT title FROM knowledge_documents WHERE id=?", lambda r: r["title"]),
    }
    sql, extract = sqls[kind]
    row = conn.execute(sql, (source_id,)).fetchone()
    return redact_text(extract(row) if row is not None else "", limit=240)
```
5. `replace_plan`：
   - 在 `_normalize_plan` 后、`decide_run` 前，读取既有锁定节点并校验保持：
```python
        existing_nodes = conn.execute(
            "SELECT * FROM task_nodes WHERE task_run_id=? ORDER BY position", (run_id,),
        ).fetchall()
        locked_existing = {r["client_id"]: dict(r) for r in existing_nodes if r["user_locked"]}
        for item in plan:
            prev = locked_existing.get(item["client_id"])
            if prev is None:
                continue
            prev_refs = _stored_source_refs(conn, prev["id"])
            if (prev["title"] != item["title"]
                    or prev["completion_criteria"] != item["completion_criteria"]
                    or json.loads(prev["depends_on_json"] or "[]") != item["depends_on"]
                    or prev_refs != item["input_refs"]):
                raise _MutationConflict(TaskRunConflict(
                    "task_plan_locked_node_modified", run_id=run_id,
                ))
```
   - 插入节点 SQL 增加 `user_locked,locked_reason,recovery_class` 列。
   - 删除节点后调用 `_replace_source_links(conn, run_id, node_db_id, refs)`：
```python
def _stored_source_refs(conn, node_id: str) -> list[dict[str, str]]:
    return [{"source_kind": r["source_kind"], "source_id": r["source_id"]}
            for r in conn.execute(
                "SELECT source_kind,source_id FROM task_node_source_links "
                "WHERE node_id=? ORDER BY id", (node_id,),
            ).fetchall()]


def _replace_source_links(conn, run_id: str, node_id: str,
                          refs: list[dict[str, str]]) -> None:
    conn.execute("DELETE FROM task_node_source_links WHERE node_id=?", (node_id,))
    for ref in refs:
        status, summary = _resolve_source_link(conn, ref)
        conn.execute(
            "INSERT INTO task_node_source_links(id,task_run_id,node_id,source_kind,source_id,"
            "summary,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (f"tsl_{db.new_id()}", run_id, node_id, ref["source_kind"], ref["source_id"],
             summary, status, db.now()),
        )
```
   - `get()` 节点解码追加：
```python
        item["source_links"] = [dict(row) for row in conn.execute(
            "SELECT id,source_kind,source_id,summary,status,invalidated_at,invalidated_reason "
            "FROM task_node_source_links WHERE node_id=? ORDER BY id", (row["id"],),
        ).fetchall()]
```
6. 失效与阻塞：
```python
def invalidate_source_links(source_kind: str, source_id: str, reason: str) -> int:
    conn = db.connect()
    try:
        now = db.now()
        updated = conn.execute(
            "UPDATE task_node_source_links SET status='invalidated',invalidated_at=?,"
            "invalidated_reason=? WHERE source_kind=? AND source_id=? AND status='active'",
            (now, redact_text(reason, 240), source_kind, source_id),
        ).rowcount
        conn.commit()
        return int(updated or 0)
    finally:
        conn.close()
```
   - `_run_command` 中 `command == "start"` 且决策为 apply 时：
```python
        if command == "start" and conn.execute(
            "SELECT 1 FROM task_node_source_links WHERE task_run_id=? AND status='invalidated' "
            "LIMIT 1", (run_id,),
        ).fetchone() is not None:
            raise _MutationConflict(TaskRunConflict("task_source_invalidated", run_id=run_id))
```
   - `_refresh_ready_nodes`：节点有失效链接时保持 `blocked`：
```python
        has_invalid = conn.execute(
            "SELECT 1 FROM task_node_source_links WHERE node_id=? AND status='invalidated' LIMIT 1",
            (row["id"],),
        ).fetchone() is not None
        if has_invalid:
            status = "blocked"
```

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_runs.py tests/test_task_run_schema_88.py -q`
Expected: PASS（含新增三个用例与既有回归）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/task_runs.py backend/tests/test_task_runs.py
git commit -m "feat(taskrun): source links, lock preservation, invalid-source blocking"
```

---

### Task 5: task_planner 纯模块

**Files:**
- Create: `backend/app/task_planner.py`
- Create: `backend/tests/test_task_planner.py`

**Interfaces:**
- Consumes: `llm.complete_json`、`task_runs.validate_plan_shape`、`db`（provider 由调用方传入）。
- Produces:
  - `matches_planning_intent(content: str) -> bool`
  - `PROPOSAL_PROMPT(goal, context, locked_nodes) -> str`
  - `parse_proposal_json(text: str) -> dict`
  - `validate_proposal(proposal: dict) -> tuple[dict, list[str]]`（规范化节点 + 可读错误）
  - `async generate_proposal(*, provider, model, goal, context, locked_nodes) -> dict`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_task_planner.py`：
```python
from __future__ import annotations

import pytest

from app import llm, task_planner


def test_intent_fixed_set() -> None:
    assert task_planner.matches_planning_intent("帮我拆解知识库检索改进方案，列成步骤")
    assert task_planner.matches_planning_intent("写一个实现计划，拆成依赖步骤")
    assert not task_planner.matches_planning_intent("今天天气怎么样")


def test_parse_and_validate_proposal() -> None:
    text = ('{"goal_summary":"改进检索","requires_approval":true,'
            '"nodes":[{"client_id":"a","title":"梳理流程","depends_on":[],'
            '"completion_criteria":"输出清单","input_refs":['
            '{"source_kind":"knowledge_source","source_id":"kd-1"}]}]}')
    proposal = task_planner.parse_proposal_json(text)
    validated, errors = task_planner.validate_proposal(proposal)
    assert not errors
    assert validated["nodes"][0]["title"] == "梳理流程"


def test_validate_rejects_cycle_with_readable_errors() -> None:
    _, errors = task_planner.validate_proposal({
        "goal_summary": "x",
        "nodes": [
            {"client_id": "a", "title": "A", "depends_on": ["b"]},
            {"client_id": "b", "title": "B", "depends_on": ["a"]},
        ],
    })
    assert errors


@pytest.mark.asyncio
async def test_generate_with_mock_provider_fails_closed() -> None:
    with pytest.raises(llm.LLMError):
        await task_planner.generate_proposal(
            provider=None, model="xiadie-mock", goal="做个计划",
        )
```

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_planner.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 task_planner.py**

```python
"""CYR.2C lightweight Agent Planner: model proposals, program validation only."""
from __future__ import annotations

import json
import re
from typing import Any

from . import llm, task_runs
from .observability import log_event

PLANNER_MAX_TOKENS = 1_024
PLANNER_TIMEOUT_SECONDS = 30.0

_INTENT_PATTERN = re.compile(
    r"(?:帮我|请|麻烦你)?(?:把|将)?(.{0,60}?)(?:拆解|规划|计划|方案|步骤|流程|实现|落地)"
    r"|(?:列成|写成|整理成)(?:一个)?(?:步骤|计划|方案)",
)


def matches_planning_intent(content: str) -> bool:
    text = (content or "").strip()
    if not text or len(text) > 800:
        return False
    return bool(_INTENT_PATTERN.search(text))


def _locked_constraints(locked_nodes: list[dict[str, Any]]) -> str:
    if not locked_nodes:
        return "（无锁定节点）"
    lines = [f"- {n.get('title')} (client_id={n.get('client_id')}；标题、验收、依赖逐字保留)" for n in locked_nodes]
    return "\n".join(lines)


def proposal_prompt(goal: str, context: str, locked_nodes: list[dict[str, Any]]) -> str:
    return (
        "你是遐蝶的任务规划器。根据用户目标输出 JSON 计划提案，不要输出其他文字。\n"
        "JSON 结构：{\"goal_summary\": str(≤200字), \"requires_approval\": bool, "
        "\"nodes\": [{\"client_id\": \"step-1\", \"title\": str(≤60字), "
        "\"completion_criteria\": str(≤300字), \"depends_on\": [client_id], "
        "\"input_refs\": [{\"source_kind\": \"knowledge_source|memory_fragment|"
        "memory_episode|memory_saga|memory_entity|conversation\", \"source_id\": str}]}]}\n"
        f"用户目标：{goal}\n可用上下文（有界，不得杜撰来源 id）：{context}\n"
        f"锁定节点（必须逐字保留，不得修改、删除或改变其依赖）：\n{_locked_constraints(locked_nodes)}\n"
        "约束：最多 50 个节点；client_id 唯一；depends_on 只能引用本计划内的 client_id；"
        "禁止循环依赖；没有把握的来源不要引用；计划批准不等于任何工具权限。"
    )


def parse_proposal_json(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("proposal must be an object")
    return payload


def validate_proposal(proposal: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize and validate; returns (normalized, readable_errors)."""
    errors: list[str] = []
    if not isinstance(proposal, dict):
        return {}, ["提案不是有效对象"]
    nodes = proposal.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return {}, ["提案没有步骤"]
    try:
        normalized_nodes = task_runs.validate_plan_shape(nodes)
    except task_runs.TaskRunConflict as exc:
        return {}, [exc.message]
    except Exception:  # noqa: BLE001 - planner 提案必须 fail closed
        return {}, ["提案无法解析"]
    goal = str(proposal.get("goal_summary") or "").strip()[:200]
    if not goal:
        errors.append("缺少目标摘要")
    return {
        "goal_summary": goal,
        "requires_approval": bool(proposal.get("requires_approval")),
        "nodes": normalized_nodes,
    }, errors


async def generate_proposal(*, provider: dict | None, model: str, goal: str,
                            context: str = "", locked_nodes: list[dict[str, Any]] | None = None,
                            ) -> dict[str, Any]:
    if provider is None or provider.get("id") == "mock" or not provider.get("base_url"):
        raise llm.LLMError("规划模型不可用", "演示模型不执行计划生成。")
    response = await llm.complete_json(
        provider, model,
        [{"role": "user", "content": proposal_prompt(goal, context, locked_nodes or [])}],
        max_tokens=PLANNER_MAX_TOKENS,
        timeout_seconds=PLANNER_TIMEOUT_SECONDS,
        temperature=0.0,
        json_mode=True,
    )
    try:
        raw = parse_proposal_json(response["text"])
    except (ValueError, json.JSONDecodeError) as exc:
        log_event("task.planner", "WARNING", "planner JSON unparseable",
                  fields={"model": model, "error": str(exc)[:200]})
        raise llm.LLMError("规划模型输出无法解析", "请调整目标后重试。") from exc
    proposal, errors = validate_proposal(raw)
    if errors:
        log_event("task.planner", "WARNING", "planner proposal rejected",
                  fields={"model": model, "errors": errors[:5]})
        raise llm.LLMError("计划未通过程序校验", "；".join(errors[:5]))
    log_event("task.planner", "INFO", "planner proposal generated",
              fields={"model": model, "node_count": len(proposal["nodes"]),
                      "requires_approval": proposal["requires_approval"]})
    return proposal
```

> 提示：`validate_plan_shape` 返回的节点已含 `input_refs`、`user_locked`、`locked_reason`、`recovery_class` 字段（默认 False/None）。

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_planner.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/task_planner.py backend/tests/test_task_planner.py
git commit -m "feat(taskrun): add lightweight agent planner module"
```

---

### Task 6: API —— from-proposal 与 planner-proposal

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_task_runs.py`

**Interfaces:**
- Consumes: Task 4/5 的函数。
- Produces:
  - `POST /api/task-runs/from-proposal`（body：`PlanProposalIn`）
  - `POST /api/task-runs/{run_id}/planner-proposal`（返回候选，不落库）
  - `TaskPlanNodeIn` 扩展 `input_refs/user_locked/locked_reason/recovery_class`

- [ ] **Step 1: 写失败测试（追加到 test_task_runs.py）**

```python
def test_http_from_proposal_creates_task_and_draft() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    session = client.post("/api/sessions", json={}).json()
    body = {
        "goal_summary": "改进检索流程",
        "requires_approval": True,
        "source_session_id": session["id"],
        "nodes": [{"client_id": "a", "title": "梳理流程", "depends_on": [],
                   "completion_criteria": "输出清单",
                   "input_refs": [{"source_kind": "knowledge_source", "source_id": _doc_source()}]}],
    }
    response = client.post("/api/task-runs/from-proposal", json=body)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "awaiting_approval"
    assert run["nodes"][0]["source_links"][0]["source_kind"] == "knowledge_source"


def test_http_from_proposal_rejects_invalid_plan() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    body = {
        "goal_summary": "坏计划",
        "nodes": [{"client_id": "a", "title": "A", "depends_on": ["b"]},
                  {"client_id": "b", "title": "B", "depends_on": ["a"]}],
    }
    response = client.post("/api/task-runs/from-proposal", json=body)
    assert response.status_code == 422


def test_http_planner_proposal_mock_fails_closed() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    run = task_runs.create(task_id=_task(), idempotency_key="planner-1")
    response = client.post(f"/api/task-runs/{run['id']}/planner-proposal", json={})
    assert response.status_code == 422
```

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_runs.py -q`
Expected: FAIL（404 路由不存在）。

- [ ] **Step 3: 实现 main.py**

1. 扩展模型：
```python
class TaskSourceRefIn(BaseModel):
    source_kind: Literal["memory_fragment", "memory_episode", "memory_saga",
                         "memory_entity", "knowledge_source", "conversation"]
    source_id: str = Field(min_length=1, max_length=200)


class TaskPlanNodeIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    completion_criteria: str = Field(default="", max_length=500)
    input_refs: list[TaskSourceRefIn] = Field(default_factory=list, max_length=20)
    user_locked: bool = False
    locked_reason: Optional[Literal["edit", "explicit"]] = None
    recovery_class: Optional[Literal["side_effect_free", "idempotent", "side_effectful"]] = None


class PlanProposalIn(BaseModel):
    goal_summary: str = Field(min_length=1, max_length=200)
    requires_approval: bool = False
    source_session_id: Optional[str] = Field(default=None, max_length=80)
    nodes: list[TaskPlanNodeIn] = Field(min_length=1, max_length=50)
```
2. 路由（放在任务路由区末尾，`/api/task-runs/artifacts` 之后）：
```python
@app.post("/api/task-runs/from-proposal")
def create_run_from_proposal(body: PlanProposalIn) -> dict:
    try:
        proposal, errors = task_planner.validate_proposal({
            "goal_summary": body.goal_summary,
            "requires_approval": body.requires_approval,
            "nodes": [item.model_dump() for item in body.nodes],
        })
    except Exception:  # noqa: BLE001 - 提案必须 fail closed
        raise HTTPException(422, "提案无法解析")
    if errors:
        raise HTTPException(422, {"code": "task_plan_proposal_invalid",
                                  "message": "；".join(errors)})
    task = create_task(TaskIn(
        title=proposal["goal_summary"][:80] or "未命名任务",
        source_session_id=body.source_session_id,
    ))
    run = task_runs.create(task_id=task["id"],
                           goal_summary=proposal["goal_summary"],
                           source_session_id=body.source_session_id)
    return _task_run_call(lambda: task_runs.replace_plan(
        run["id"], proposal["nodes"], requires_approval=proposal["requires_approval"],
        expected_revision=run["revision"],
    ))


@app.post("/api/task-runs/{run_id}/planner-proposal")
async def generate_run_plan_proposal(run_id: str) -> dict:
    run = task_runs.get(run_id)
    if run is None:
        raise HTTPException(404, "task_run_not_found")
    provider, model = _current_model()
    locked_nodes = [node for node in (run["nodes"] or []) if node.get("user_locked")]
    context = f"当前目标：{run['goal_summary']}"
    if run.get("nodes"):
        context += "\n当前计划结构：" + json.dumps(
            [{"client_id": n["client_id"], "title": n["title"],
              "depends_on": n["depends_on"], "completion_criteria": n["completion_criteria"]}
             for n in run["nodes"]], ensure_ascii=False,
        )[:2000]
    try:
        proposal = await task_planner.generate_proposal(
            provider=provider, model=model, goal=run["goal_summary"],
            context=context, locked_nodes=locked_nodes,
        )
    except llm.LLMError as error:
        raise HTTPException(422, {"code": "planner_unavailable",
                                  "message": error.hint or error.message})
    return proposal
```
> `create_task`/`TaskIn` 是模块内已存在的函数与模型，直接复用。

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_runs.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/main.py backend/tests/test_task_runs.py
git commit -m "feat(taskrun): from-proposal and planner-proposal endpoints"
```

---

### Task 7: 聊天 SSE plan_proposal 事件（后端）

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_task_planner.py`（意图匹配已覆盖）；新增 `backend/tests/test_chat_plan_proposal.py`

**Interfaces:**
- Consumes: Task 5 的 `matches_planning_intent`/`generate_proposal`。
- Produces: 聊天流尾部 `event: plan_proposal`；演示模型/失败时静默跳过。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_chat_plan_proposal.py`：
```python
from __future__ import annotations

import pytest

from app import db, task_planner


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_mock_chat_never_emits_plan_proposal() -> None:
    # 演示模型下 gen() 不调用 planner：以意图匹配与生成 fail closed 组合断言。
    assert task_planner.matches_planning_intent("帮我拆解一个方案，列成步骤")
    # 生成失败关闭（mock provider）由 test_task_planner 覆盖；此处锁行为契约。
    assert db.get_schema_version() == 88
```

> 后端对 SSE 流的集成测试：在 `main.py` gen() 中，`plan_proposal` 生成失败只记录 WARNING 并跳过，不允许破坏已完成回复——用 `test_chat_plan_proposal.py` 锁 schema 版本 + 意图契约即可；真实模型路径以 planner 单测为准。

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_chat_plan_proposal.py -q`
Expected: FAIL（schema 版本为 87）。

- [ ] **Step 3: 实现 main.py gen() 追加**

在 chat 的 `gen()` 内、`yield _sse("done", ...)` 之后追加：
```python
        if (
            not body.regenerate
            and not temporary_chat
            and provider is not None
            and provider.get("id") != "mock"
            and task_planner.matches_planning_intent(effective_content)
        ):
            try:
                proposal = await task_planner.generate_proposal(
                    provider=provider, model=model, goal=effective_content[:200],
                )
                yield _sse("plan_proposal", proposal)
            except Exception:  # noqa: BLE001 - 规划失败不能破坏已完成回复
                logger.warning("plan_proposal_failed session_id=%s", body.session_id,
                               exc_info=True)
```

> `provider`/`model` 已在 gen() 作用域内可用（chat 入口 `_current_model()` 取得）。若 gen() 定义在 chat() 内部且未捕获这些变量，将它们从 chat() 作用域闭包传入（保持现有结构，不做大改）。

- [ ] **Step 4: 运行确认通过**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_chat_plan_proposal.py tests/test_task_planner.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/main.py backend/tests/test_chat_plan_proposal.py
git commit -m "feat(chat): emit plan_proposal event after planning-intent replies"
```

---

### Task 8: 前端协议与 API（plan_proposal / from-proposal / planner-proposal）

**Files:**
- Modify: `frontend/src/chatSseProtocol.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/tests/fixtures/chatSseProtocol.mjs`、`frontend/tests/chatSseFinal.test.mjs`、`frontend/tests/taskRunUx.test.mjs`

**Interfaces:**
- Consumes: 既有 `dispatchChatSseEvent`/`j()`。
- Produces:
  - `ChatSseCallbacks.onPlanProposal?(proposal)`
  - `PlanProposal` / `TaskSourceLink` / `TaskRunProposalNode` 类型
  - `createTaskRunFromProposal(proposal)`、`plannerProposal(runId)`

- [ ] **Step 1: 写失败测试**

先更新 fixture `frontend/tests/fixtures/chatSseProtocol.mjs`，使其镜像 TS 协议的新分支（后续 Task 9 的 ChatView 测试也依赖它）：
```js
export function dispatchChatSseEvent(event, data, callbacks, state) {
  // ...既有分支
  else if (event === "plan_proposal") callbacks.onPlanProposal?.(data);
  // ...done 分支保持最后
}
```

在 `chatSseFinal.test.mjs` 追加（从 fixture 导入，与现有测试一致）：
```js
test("plan_proposal event dispatches to onPlanProposal", () => {
  const calls = [];
  dispatchChatSseEvent("plan_proposal", { goal_summary: "x" }, {
    onPlanProposal: (p) => calls.push(p),
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].goal_summary, "x");
});
```

在 `taskRunUx.test.mjs` 追加（api.ts 用源码正则断言，与现有风格一致）：
```js
test("CYR.2C planner endpoints and proposal types are wired in api", () => {
  assert.match(api, /createTaskRunFromProposal/);
  assert.match(api, /\/api\/task-runs\/from-proposal/);
  assert.match(api, /plannerProposal/);
  assert.match(api, /\/api\/task-runs\/\$\{encodeURIComponent\(runId\)\}\/planner-proposal/);
  assert.match(api, /onPlanProposal/);
});
```

- [ ] **Step 2: 运行确认失败**

Run: `frontend\node --test tests/chatSseFinal.test.mjs`
Expected: FAIL（onPlanProposal 未定义/未分发）。

- [ ] **Step 3: 实现**

`chatSseProtocol.ts`：
```ts
export interface ChatSseCallbacks {
  // ...既有回调
  onPlanProposal?: (proposal: any) => void;
}
// dispatchChatSseEvent 增加分支：
  else if (event === "plan_proposal") callbacks.onPlanProposal?.(data);
```

`api.ts` 追加类型与函数：
```ts
export interface TaskSourceLink {
  id: string;
  source_kind: "memory_fragment" | "memory_episode" | "memory_saga" | "memory_entity"
    | "knowledge_source" | "conversation";
  source_id: string;
  summary: string;
  status: "active" | "invalidated";
  invalidated_at?: number | null;
  invalidated_reason?: string | null;
}
// TaskNode 接口追加：
  user_locked?: boolean;
  locked_reason?: "edit" | "explicit" | null;
  recovery_class?: "side_effect_free" | "idempotent" | "side_effectful" | null;
  source_links?: TaskSourceLink[];

export interface PlanProposalNode {
  client_id: string;
  title: string;
  depends_on?: string[];
  completion_criteria?: string;
  input_refs?: Array<{ source_kind: TaskSourceLink["source_kind"]; source_id: string }>;
  user_locked?: boolean;
  locked_reason?: "edit" | "explicit";
  recovery_class?: TaskNode["recovery_class"];
}
export interface PlanProposal {
  goal_summary: string;
  requires_approval: boolean;
  nodes: PlanProposalNode[];
}

export const createTaskRunFromProposal = (proposal: PlanProposal, sourceSessionId?: string) =>
  j<TaskRun>("/api/task-runs/from-proposal", {
    method: "POST",
    body: JSON.stringify({ ...proposal, source_session_id: sourceSessionId }),
  });
export const plannerProposal = (runId: string) =>
  j<PlanProposal>(`/api/task-runs/${encodeURIComponent(runId)}/planner-proposal`, {
    method: "POST", body: JSON.stringify({}),
  });
```
同时扩展 `ChatCallbacks` 的 `onPlanProposal`。`chatSseProtocol.ts` 同步给 `ChatSseCallbacks` 加 `onPlanProposal` 并新增 `else if (event === "plan_proposal")` 分支。

- [ ] **Step 4: 运行确认通过**

Run: `frontend\node --test tests/chatSseFinal.test.mjs tests/taskRunUx.test.mjs`
Expected: PASS。再跑 `npm.cmd run build` 确认 TS 编译。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/chatSseProtocol.ts frontend/src/api.ts frontend/tests
git commit -m "feat(frontend): plan_proposal protocol and task planner api"
```

---

### Task 9: 前端聊天计划卡（ChatView）

**Files:**
- Modify: `frontend/src/components/ChatView.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/taskPlanUi.mjs` + `frontend/tests/taskPlanUi.test.mjs`

**Interfaces:**
- Consumes: `api.streamChat` 的 `onPlanProposal`、`api.createTaskRunFromProposal`。
- Produces: 聊天气泡后渲染计划卡；「进入工作台编辑」落 draft 并跳转任务页；「取消」清除。

- [ ] **Step 1: 写失败测试（taskPlanUi.test.mjs）**

```js
import { planCardState, proposalToDraftNodes } from "../src/taskPlanUi.mjs";
import test from "node:test";
import assert from "node:assert/strict";

test("proposal nodes map to workbench draft nodes", () => {
  const nodes = proposalToDraftNodes([
    { client_id: "a", title: "A", completion_criteria: "ok",
      input_refs: [{ source_kind: "knowledge_source", source_id: "kd-1" }],
      user_locked: true, locked_reason: "explicit" },
  ]);
  assert.equal(nodes[0].client_id, "a");
  assert.equal(nodes[0].input_refs[0].source_id, "kd-1");
  assert.equal(nodes[0].user_locked, true);
});

test("plan card state transitions are finite", () => {
  for (const s of ["loading", "pending", "editing", "failed", "cancelled"]) {
    assert.equal(planCardState(s), s);
  }
});
```

- [ ] **Step 2: 运行确认失败**

Run: `frontend\node --test tests/taskPlanUi.test.mjs`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现**

`frontend/src/taskPlanUi.mjs`：
```js
export const PLAN_CARD_STATES = ["loading", "pending", "editing", "failed", "cancelled"];
export const planCardState = (state) => (PLAN_CARD_STATES.includes(state) ? state : "pending");
export const proposalToDraftNodes = (nodes) =>
  (nodes || []).map((n) => ({
    client_id: n.client_id,
    title: n.title,
    depends_on: n.depends_on || [],
    completion_criteria: n.completion_criteria || "",
    input_refs: n.input_refs || [],
    user_locked: Boolean(n.user_locked),
    locked_reason: n.locked_reason || (n.user_locked ? "explicit" : null),
    recovery_class: n.recovery_class || null,
  }));
```

`ChatView.tsx`：
- 状态：`const [planProposal, setPlanProposal] = useState<api.PlanProposal | null>(null);`
- `streamChat` 回调追加：`onPlanProposal: (p) => { if (activeInView()) setPlanProposal(p); }`
- 发送/重新生成/切换会话时 `setPlanProposal(null)`。
- 在最后一条 assistant 消息之后渲染（复用消息区布局）：
```tsx
{planProposal && (
  <div className="msg assistant">
    <div className="avatar">◇</div>
    <div className="bubble">
      <div className="plan-card">
        <div className="plan-head">
          <span className="page-eyebrow">候选计划</span>
          <span className="task-run-status">待确认</span>
        </div>
        <div className="plan-goal">{planProposal.goal_summary}</div>
        <div className="plan-stats">
          <span><b>{planProposal.nodes.length}</b> 步骤</span>
          <span><b>{planProposal.nodes.filter((n) => n.depends_on?.length).length}</b> 依赖</span>
          <span><b>{planProposal.nodes.reduce((s, n) => s + (n.input_refs?.length || 0), 0)}</b> 来源</span>
          <span>{planProposal.requires_approval ? "需批准" : "无需批准"}</span>
        </div>
        <ol className="plan-nodes">
          {planProposal.nodes.slice(0, 3).map((node, i) => (
            <li key={node.client_id}>
              <span className="node-idx">{i + 1}</span>
              <div>
                <strong>{node.title}</strong>
                {(node.depends_on || []).length > 0 && (
                  <small className="dep">← 依赖 {node.depends_on.map((d) =>
                    planProposal.nodes.findIndex((n) => n.client_id === d) + 1).join("、")}</small>
                )}
              </div>
            </li>
          ))}
        </ol>
        {planProposal.nodes.length > 3 && <button className="more-nodes">+{planProposal.nodes.length - 3} 更多</button>}
        <div className="plan-actions">
          <button className="plan-primary" onClick={() => void enterWorkbench(planProposal)}>进入工作台编辑</button>
          <button className="plan-ghost" onClick={() => setPlanProposal(null)}>取消</button>
        </div>
        <div className="plan-note">确认后创建任务草稿，不会自动开始执行</div>
      </div>
    </div>
  </div>
)}
```
- 处理函数：
```tsx
const enterWorkbench = async (proposal: api.PlanProposal) => {
  try {
    const run = await api.createTaskRunFromProposal(proposal, activeSessionId);
    setPlanProposal(null);
    toast("已建立任务草稿，请在工作台确认计划。");
    onOpenTasks();
  } catch (reason) {
    toast((reason as Error)?.message || "创建任务草稿失败");
  }
};
```
（`toast` 从 `./../store` 导入，`onOpenTasks` 已是 ChatView 属性。）

`styles.css` 追加（与现有 tokens 一致，取自 UI 设计 v0.2）：
```css
.plan-card { display:grid; gap:9px; width:min(480px,100%); padding:14px 15px 12px;
  border:1px solid rgba(157,132,255,.3); border-left:3px solid var(--violet);
  border-radius:16px; color:#dcd6ec;
  background:radial-gradient(circle at 95% 0,rgba(69,199,255,.08),transparent 32%),
    linear-gradient(145deg,rgba(38,25,70,.97),rgba(20,14,42,.97)); }
.plan-head{display:flex;align-items:center;justify-content:space-between}
.plan-goal{font-size:13px;font-weight:600;color:#f1edfb}
.plan-stats{display:flex;flex-wrap:wrap;gap:5px 14px;color:var(--text-faint);font-size:9px}
.plan-stats b{color:var(--violet-soft)}
.plan-nodes{list-style:none;display:grid;gap:5px}
.plan-nodes li{display:flex;align-items:flex-start;gap:9px;padding:7px 9px;
  border:1px solid rgba(157,132,255,.13);border-radius:10px;background:rgba(255,255,255,.025)}
.node-idx{display:grid;width:18px;height:18px;place-items:center;border-radius:6px;
  color:var(--violet-soft);background:rgba(124,92,255,.16);font-size:9px}
.plan-nodes strong{font-size:11px;color:#dcd6e9}
.plan-nodes small{color:var(--text-faint);font-size:9px}
.plan-nodes small.dep{color:#b7a9ea}
.more-nodes{justify-self:start;color:var(--violet-soft);font-size:10px}
.plan-actions{display:flex;gap:8px}
.plan-primary{padding:8px 14px;border-radius:var(--radius-sm);color:#fff;font-size:11px;
  font-weight:600;background:linear-gradient(135deg,var(--violet),var(--indigo));
  box-shadow:0 0 16px rgba(124,92,255,.3)}
.plan-ghost{padding:8px 14px;border:1px solid var(--glass-border-lit);border-radius:var(--radius-sm);
  color:var(--text-dim);font-size:11px}
.plan-note{color:var(--text-faint);font-size:9px}
```

- [ ] **Step 4: 运行确认通过**

Run: `frontend\node --test tests/taskPlanUi.test.mjs tests/chatSseFinal.test.mjs` + `npm.cmd run build`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/taskPlanUi.mjs frontend/src/components/ChatView.tsx frontend/src/styles.css frontend/tests
git commit -m "feat(chat): render plan proposal card and enter workbench"
```

---

### Task 10: 任务页「重新生成计划」、锁定与来源 UI

**Files:**
- Modify: `frontend/src/components/TasksPage.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/taskRunUx.test.mjs`

**Interfaces:**
- Consumes: `api.plannerProposal`、`api.replaceTaskRunPlan`（扩展节点字段）、`proposalToDraftNodes`。
- Produces: 运行面板锁定控件、来源 chips、失效横幅；计划编辑器锁定；「重新生成计划」确认弹层。

- [ ] **Step 1: 写失败测试（追加到 taskRunUx.test.mjs）**

```js
import { lockUiState } from "../src/taskPlanUi.mjs";
test("lock UI states cover three-way semantics", () => {
  assert.equal(lockUiState({ user_locked: true, locked_reason: "edit" }).label, "已锁定 · 编辑");
  assert.equal(lockUiState({ user_locked: true, locked_reason: "explicit" }).label, "已锁定");
  assert.equal(lockUiState({}).label, "");
});
```

`taskPlanUi.mjs` 追加：
```js
export const lockUiState = (node) => {
  if (!node?.user_locked) return { label: "", locked: false };
  return { locked: true, label: node.locked_reason === "edit" ? "已锁定 · 编辑" : "已锁定" };
};
```

- [ ] **Step 2: 运行确认失败**

Run: `frontend\node --test tests/taskRunUx.test.mjs`
Expected: FAIL（lockUiState 不存在）。

- [ ] **Step 3: 实现 TasksPage**

1. `DraftNode` 类型扩展：`input_refs?: api.PlanProposalNode["input_refs"]; user_locked?: boolean; locked_reason?: "edit" | "explicit" | null;`
2. `openEditor` 保留既有节点字段，并把 `user_locked/locked_reason/input_refs` 带入 draft。
3. 节点编辑回调：用户修改标题/验收/依赖时自动置 `user_locked: true, locked_reason: "edit"`：
```tsx
const touchNode = (clientId: string, patch: Partial<DraftNode>) =>
  setEditor((current) => current ? {
    ...current,
    nodes: current.nodes.map((n) => n.client_id === clientId
      ? { ...n, ...patch, user_locked: true, locked_reason: "edit" } : n),
  } : current);
```
4. 锁定按钮（编辑器和运行面板共用）：
```tsx
const toggleLock = (clientId: string) =>
  setEditor((current) => current ? {
    ...current,
    nodes: current.nodes.map((n) => n.client_id === clientId
      ? (n.user_locked
          ? { ...n, user_locked: false, locked_reason: null }
          : { ...n, user_locked: true, locked_reason: "explicit" })
      : n),
  } : current);
```
5. 编辑器渲染：标题输入 `disabled={node.user_locked}`（锁定节点只读，视觉用 `.task-plan-node[data-lock]` 类 + 锁按钮 + pill）。锁按钮放每行 `b` 右侧。
6. 运行面板节点：读 `run.nodes` 的 `user_locked/source_links`，渲染锁 pill 与 `source-ref-chip`；失效 chip 加 `invalid` 类与 `title` 提示；存在 `source_links.some(s => s.status === "invalidated")` 时显示失效横幅。
7. 「重新生成计划」：
```tsx
const replanWithPlanner = async (task: api.Task, run: api.TaskRun) => {
  try {
    const proposal = await api.plannerProposal(run.id);
    setEditor({
      taskId: task.id, runId: run.id, revision: run.revision,
      requiresApproval: proposal.requires_approval,
      nodes: proposalToDraftNodes(proposal.nodes),
    });
    toast("候选计划已生成，请审阅后提交（锁定节点不会改动）。");
  } catch (reason) {
    toast((reason as Error)?.message || "候选计划生成失败");
  }
};
```
按钮位置：`task-actions` 内「编辑计划」旁：
```tsx
<button onClick={() => void replanWithPlanner(task, run)}>重新生成计划</button>
```
8. 保存路径：`savePlan` 调用 `api.replaceTaskRunPlan(editor.runId, editor.nodes, ...)`，节点对象已带新字段（api.ts 的 `replaceTaskRunPlan` 节点参数需扩展 `input_refs/user_locked/locked_reason/recovery_class` 透传）。

`styles.css` 追加（按 UI 设计 v0.2）：
```css
.run-banner{display:flex;align-items:flex-start;gap:9px;padding:9px 11px;border:1px solid;border-radius:var(--radius-sm);font-size:10px}
.run-banner.invalid{border-color:rgba(233,135,154,.35);background:rgba(233,135,154,.06);border-left:3px solid var(--danger)}
.run-banner.invalid strong{color:#f0b3bf}
.node-lock-pill{padding:2px 6px;border-radius:99px;color:#b9a9f7;background:rgba(124,92,255,.12);font-size:8px}
.node-lock-btn{display:grid;width:24px;height:24px;place-items:center;border-radius:6px;color:var(--text-faint)}
.task-node[data-lock="explicit"]{border-left-color:var(--violet)}
.source-ref-chip{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border:1px solid rgba(157,132,255,.13);border-radius:6px;color:#948ba8;background:rgba(255,255,255,.025);font-size:8px;cursor:help}
.source-ref-chip.invalid{border-color:rgba(233,135,154,.4);color:#f0b3bf;background:rgba(233,135,154,.07);text-decoration:line-through}
.task-plan-node[data-lock="explicit"]{border-left-color:var(--violet)}
```

- [ ] **Step 4: 运行确认通过**

Run: `frontend\node --test tests/taskRunUx.test.mjs tests/taskPlanUi.test.mjs` + `npm.cmd run build`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/TasksPage.tsx frontend/src/styles.css frontend/src/taskPlanUi.mjs frontend/tests
git commit -m "feat(tasks): replan entry, node locks and source reference chips"
```

---

### Task 11: 失效钩子与全量门禁

**Files:**
- Modify: `backend/app/knowledge_management.py`、`backend/app/memory.py`、`backend/app/entities.py`、`backend/app/main.py`
- Modify: `backend/tests/test_task_runs.py`（失效钩子用例）

**Interfaces:**
- Consumes: `task_runs.invalidate_source_links`。
- Produces: 来源删除/归档时把相关 `task_node_source_links` 置 `invalidated`。

- [ ] **Step 1: 写失败测试（追加到 test_task_runs.py）**

```python
def test_delete_hooks_invalidate_links() -> None:
    run = task_runs.create(task_id=_task(), idempotency_key="hook-1")
    _with_refs(run)  # 使用 knowledge_source kd-1
    import knowledge_management as km
    assert km.set_archived("kd-1", archived=True) is not None
    conn = db.connect()
    try:
        status = conn.execute(
            "SELECT status FROM task_node_source_links WHERE source_id='kd-1'",
        ).fetchone()["status"]
    finally:
        conn.close()
    assert status == "invalidated"
```

- [ ] **Step 2: 运行确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_task_runs.py -q`
Expected: FAIL（状态仍 active）。

- [ ] **Step 3: 实现钩子**

在各模块归档/删除路径内调用（返回前）：
```python
from . import task_runs  # 模块顶部已有部分导入；按文件现有风格追加
```
- `knowledge_management.set_archived(..., archived=True)`：`task_runs.invalidate_source_links("knowledge_source", document_id, "文档已归档")`
- `knowledge_management._delete_claimed(run)`：删除前 `task_runs.invalidate_source_links("knowledge_source", run["document_id"], "文档已删除")`
- `memory.delete_memory(mid, ...)`：删除前 `task_runs.invalidate_source_links("memory_fragment", mid, "记忆已删除")`
- `entities.archive_entity(eid)`：`task_runs.invalidate_source_links("memory_entity", eid, "实体已归档")`
- `main.py` 的 episode/saga lifecycle 路由（`/api/episodes/{episode_id}/lifecycle` 与 `/api/sagas/{saga_id}/lifecycle`）：当 body 将对象置为已归档/已删除状态时，调用对应 `invalidate_source_links`。

> 实现时如 `set_archived`/`_delete_claimed`/`delete_memory` 内部已有 `conn` 事务，钩子在提交前后均可调用（函数独立开连接，简单可靠）；失败只记 warning，不阻塞删除。

- [ ] **Step 4: 运行全量门禁**

```bash
cd backend && .\.venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend && node --test tests/*.test.mjs
npm.cmd run build
cd ..\backend && .\.venv\Scripts\python.exe -m compileall -q app tests
git diff --check
```
Expected: 全部通过（现存非阻塞提示白名单：Starlette/httpx 弃用、pytest cache 权限、Live2D Classic Vite 提示）。

- [ ] **Step 5: 提交**

```bash
git add backend/app frontend/src frontend/tests
git commit -m "feat(taskrun): source invalidation hooks and CYR.2C segment 1 gates"
```
