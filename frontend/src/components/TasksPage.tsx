import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import * as api from "./../api";
import { toast } from "./../store";
import { lockUiState } from "../taskPlanUi.mjs";
import { riskLabel, recoveryCardVisible } from "../recoveryUi.mjs";
import { Icon } from "./Icon";

type DraftNode = {
  client_id: string;
  title: string;
  depends_on: string[];
  completion_criteria: string;
  input_refs?: Array<{ source_kind: api.TaskSourceLink["source_kind"]; source_id: string }>;
  user_locked?: boolean;
  locked_reason?: "edit" | "explicit" | null;
  recovery_class?: api.TaskNode["recovery_class"];
};
type PlanEditor = { taskId: string; runId: string; revision: number; requiresApproval: boolean; nodes: DraftNode[] };
const TERMINAL: api.TaskRunStatus[] = ["completed", "failed", "cancelled"];
const RUN_LABELS: Record<api.TaskRunStatus, string> = {
  draft: "草稿", planning: "规划中", awaiting_approval: "等待批准", ready: "可开始",
  running: "执行中", paused: "已暂停", recovery_required: "需要恢复",
  completed: "已完成", failed: "失败", cancelled: "已取消",
};

function SourceChip({ source }: { source: string }) {
  return <span className={`task-source${source === "chat" ? " from-chat" : ""}`}>{source === "chat" ? "来自对话" : "手动创建"}</span>;
}
function defaultNode(title: string): DraftNode {
  return { client_id: `step-${Date.now().toString(36)}`, title, depends_on: [], completion_criteria: "形成可核验的结果或明确失败原因" };
}
function eventLabel(event: api.TaskRunEvent) {
  return `${event.event_type}${event.from_status || event.to_status ? ` · ${event.from_status || ""} → ${event.to_status || ""}` : ""}`;
}

export function TasksPage() {
  const [tasks, setTasks] = useState<api.Task[]>([]);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<Record<string, api.TaskRun>>({});
  const [history, setHistory] = useState<Record<string, api.TaskRun[]>>({});
  const [historyOpen, setHistoryOpen] = useState<Record<string, boolean>>({});
  const [editor, setEditor] = useState<PlanEditor | null>(null);
  const [showEvents, setShowEvents] = useState<Record<string, boolean>>({});
  const [recovery, setRecovery] = useState<Record<string, api.TaskRunRecovery>>({});
  const streamCursor = useRef<Record<string, string>>({});

  const replaceRun = (taskId: string, run: api.TaskRun) => setRuns((current) => ({ ...current, [taskId]: run }));
  const loadRecovery = async (run: api.TaskRun) => {
    try {
      const result = await api.getTaskRunRecovery(run.id);
      setRecovery((current) => ({ ...current, [run.id]: result }));
    } catch {
      // 面板是辅助视图，失败不阻塞任务列表
    }
  };
  const refreshHistory = async (taskId: string) => {
    const items = await api.listTaskRuns(taskId);
    setHistory((current) => ({ ...current, [taskId]: items }));
  };
  const refresh = () => {
    setLoading(true);
    api.listTasks().then(async (list) => {
      setTasks(list.filter((task) => task.status !== "archived"));
      const latest = await Promise.all(list.map(async (task) => {
        const items = await api.listTaskRuns(task.id);
        return items[0] ? [task.id, await api.getTaskRun(items[0].id), items] as const : null;
      }));
      setRuns(Object.fromEntries(latest.filter((item): item is readonly [string, api.TaskRun, api.TaskRun[]] => item !== null).map(([id, run]) => [id, run])));
      setHistory(Object.fromEntries(latest.filter((item): item is readonly [string, api.TaskRun, api.TaskRun[]] => item !== null).map(([id, , items]) => [id, items])));
      setError(null);
    }).catch((reason) => setError(reason?.message || "加载任务失败")).finally(() => setLoading(false));
  };

  const reconcileConflict = async (taskId: string, local: api.TaskRun, reason: unknown) => {
    const current = api.taskRunConflictSnapshot(reason, local);
    const next = current || await api.getTaskRun(local.id);
    replaceRun(taskId, next);
    if (reason instanceof api.ApiError) {
      const detail = reason.details as Partial<api.TaskRunConflictDetail> | undefined;
      toast(`${detail?.message || reason.message} ${api.taskRunRetryMessage(detail?.retry)}`);
    }
  };
  const handleRunError = async (run: api.TaskRun, reason: unknown, fallback: string) => {
    if (reason instanceof api.ApiError && reason.status === 409) {
      try { await reconcileConflict(run.task_id, run, reason); } catch (refreshError: any) { toast(refreshError?.message || "任务已更新，但无法读取最新状态"); }
      return;
    }
    toast((reason as any)?.message || fallback);
  };
  const runAction = async (run: api.TaskRun, action: "approve" | "start" | "pause" | "resume" | "cancel" | "replan") => {
    try { replaceRun(run.task_id, await api.taskRunAction(run.id, action, run.revision)); await refreshHistory(run.task_id); }
    catch (reason) { await handleRunError(run, reason, "执行状态更新失败"); }
  };
  const nodeAction = async (run: api.TaskRun, node: api.TaskNode, action: "start" | "succeed" | "fail" | "skip") => {
    try {
      const evidence = action === "fail" ? { error_code: "manual_step_failed", error_message: "用户标记步骤失败" }
        : action === "skip" ? { reason_code: "manual_skip", reason_summary: "用户在工作台跳过此步骤" } : {};
      replaceRun(run.task_id, await api.taskNodeAction(run.id, node.id, action, run.revision, evidence));
    } catch (reason) { await handleRunError(run, reason, "步骤状态更新失败"); }
  };

  const openEditor = (taskId: string, run: api.TaskRun, fallbackTitle: string) => {
    const nodes = run.nodes?.map((node) => ({
      client_id: node.client_id,
      title: node.title,
      depends_on: node.depends_on,
      completion_criteria: node.completion_criteria,
      input_refs: (node.source_links || []).map((link) => ({ source_kind: link.source_kind, source_id: link.source_id })),
      user_locked: Boolean(node.user_locked),
      locked_reason: node.locked_reason || null,
      recovery_class: node.recovery_class || null,
    })) || [defaultNode(fallbackTitle)];
    setEditor({ taskId, runId: run.id, revision: run.revision, requiresApproval: Boolean(run.requires_approval), nodes });
  };
  const touchNode = (clientId: string, patch: Partial<DraftNode>) =>
    setEditor((current) => current ? {
      ...current,
      nodes: current.nodes.map((node) => node.client_id === clientId
        ? { ...node, ...patch, user_locked: true, locked_reason: "edit" } : node),
    } : current);
  const toggleLock = (clientId: string) =>
    setEditor((current) => current ? {
      ...current,
      nodes: current.nodes.map((node) => node.client_id === clientId
        ? (node.user_locked
            ? { ...node, user_locked: false, locked_reason: null }
            : { ...node, user_locked: true, locked_reason: "explicit" })
        : node),
    } : current);
  const replanWithPlanner = async (task: api.Task, run: api.TaskRun) => {
    const lockedCount = (run.nodes || []).filter((node) => node.user_locked).length;
    if (!window.confirm(`重新生成会保留 ${lockedCount} 个已锁定节点；未锁定节点可能被改写。`)) return;
    try {
      const proposal = await api.plannerProposal(run.id);
      setEditor({
        taskId: task.id, runId: run.id, revision: run.revision,
        requiresApproval: proposal.requires_approval,
        nodes: proposal.nodes.map((node) => ({
          client_id: node.client_id,
          title: node.title,
          depends_on: node.depends_on || [],
          completion_criteria: node.completion_criteria || "",
          input_refs: node.input_refs || [],
          user_locked: Boolean(node.user_locked),
          locked_reason: node.locked_reason || (node.user_locked ? "explicit" : null),
          recovery_class: node.recovery_class || null,
        })),
      });
      toast("候选计划已生成，请审阅后提交（锁定节点不会改动）。");
    } catch (reason: any) { toast(reason?.message || "候选计划生成失败"); }
  };
  const createExecution = async (task: api.Task) => {
    try {
      const run = await api.createTaskRun(task.id, task.title);
      replaceRun(task.id, run); await refreshHistory(task.id); openEditor(task.id, run, task.title);
      toast("已建立执行草稿。请先编辑计划，再提交或批准。");
    } catch (reason: any) { toast(reason?.message || "建立执行失败"); }
  };
  const editPlan = async (task: api.Task, run: api.TaskRun) => {
    try {
      const editable = ["draft", "planning", "paused", "recovery_required", "failed"].includes(run.status);
      const next = editable ? run : await api.taskRunAction(run.id, "replan", run.revision);
      replaceRun(task.id, next); openEditor(task.id, next, task.title);
    } catch (reason) { await handleRunError(run, reason, "无法进入计划编辑"); }
  };
  const savePlan = async () => {
    if (!editor) return;
    const run = runs[editor.taskId];
    if (!run || run.id !== editor.runId) return;
    try {
      const saved = await api.replaceTaskRunPlan(editor.runId, editor.nodes, editor.revision, editor.requiresApproval);
      replaceRun(editor.taskId, saved); await refreshHistory(editor.taskId); setEditor(null);
      toast(saved.requires_approval ? "计划已保存，等待明确批准" : "计划已保存，可以开始执行");
    } catch (reason) { await handleRunError(run, reason, "计划保存失败"); }
  };
  const rerun = async (task: api.Task, source: api.TaskRun) => {
    try {
      const detail = source.nodes ? source : await api.getTaskRun(source.id);
      const run = await api.createTaskRun(task.id, detail.goal_summary || task.title);
      const nodes = detail.nodes?.map((node) => ({ client_id: node.client_id, title: node.title, depends_on: node.depends_on, completion_criteria: node.completion_criteria })) || [defaultNode(task.title)];
      const saved = await api.replaceTaskRunPlan(run.id, nodes, run.revision, Boolean(detail.requires_approval));
      replaceRun(task.id, saved); await refreshHistory(task.id);
      toast("已从历史执行创建新的计划；它不会自动开始。");
    } catch (reason: any) { toast(reason?.message || "再次执行创建失败"); }
  };

  useEffect(refresh, []);
  useEffect(() => {
    Object.values(runs).forEach((run) => { void loadRecovery(run); });
  }, [runs]);
  useEffect(() => {
    const active = Object.values(runs).filter((run) => !TERMINAL.includes(run.status));
    const controller = new AbortController();
    active.forEach((run) => {
      const start = async () => {
        try {
          await api.streamTaskRunEvents(run.id, streamCursor.current[run.id], async (kind, data) => {
            if (kind === "gap") { streamCursor.current[run.id] = ""; }
            const event = kind === "task_run_event" ? data as unknown as api.TaskRunEvent : null;
            if (event?.id) streamCursor.current[run.id] = event.id;
            if (kind === "task_run_event" || kind === "gap") {
              try { replaceRun(run.task_id, await api.getTaskRun(run.id)); await refreshHistory(run.task_id); } catch { /* next manual refresh is safe */ }
            }
          }, controller.signal);
        } catch (reason) {
          if (!(reason instanceof DOMException && reason.name === "AbortError")) console.warn("TaskRun event stream ended", reason);
        }
      };
      void start();
    });
    return () => controller.abort();
  }, [runs]);

  const add = async () => { const value = title.trim(); if (!value || busy) return; setBusy(true); try { await api.createTask(value); setTitle(""); refresh(); } catch (reason: any) { toast(reason?.message || "新建失败"); } finally { setBusy(false); } };
  const changeStatus = async (id: string, status: api.Task["status"]) => { try { await api.updateTask(id, { status }); refresh(); } catch (reason: any) { toast(reason?.message || "更新失败"); } };
  const remove = async (id: string) => { try { await api.deleteTask(id); toast("已删除任务"); refresh(); } catch (reason: any) { toast(reason?.message || "删除失败"); } };
  const groups: { key: api.Task["status"]; label: string; items: api.Task[] }[] = [
    { key: "doing", label: "进行中", items: tasks.filter((task) => task.status === "doing") }, { key: "todo", label: "待办", items: tasks.filter((task) => task.status === "todo") }, { key: "done", label: "已完成", items: tasks.filter((task) => task.status === "done") },
  ];
  const doneCount = groups[2].items.length; const openCount = tasks.length - doneCount; const completion = tasks.length ? Math.round(doneCount / tasks.length * 100) : 0;

  return <section className="page tasks-page" aria-labelledby="tasks-title">
    <header className="page-header compact-page-header"><div><p className="page-eyebrow">TASKS / CYR.2B</p><h1 id="tasks-title">今日任务</h1><p>先看清计划和证据，再决定如何推进。</p></div><span className="header-meta">{openCount} 项未完成</span></header>
    <div className="task-create"><Icon name="plus" /><input placeholder="写点要做的事，回车即可新建" value={title} onChange={(event) => setTitle(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void add(); }} /><button onClick={() => void add()} disabled={busy || !title.trim()}>新增任务</button></div>
    <div className="task-summary" aria-label="任务概览"><div><strong>{groups[1].items.length}</strong><span>待办</span></div><div><strong>{groups[0].items.length}</strong><span>进行中</span></div><div><strong>{doneCount}</strong><span>已完成</span></div><div className="task-progress" style={{ "--progress": `${completion * 3.6}deg` } as CSSProperties}><span>{completion}%</span></div></div>
    {error && <div className="empty">加载出错：{error}</div>}{!error && loading && <div className="empty">正在整理任务…</div>}
    {!error && !loading && groups.map((group) => group.items.length > 0 && <section className={`task-group ${group.key}`} key={group.key}><header><span>{group.label}</span><b>{group.items.length}</b></header>{group.items.map((task) => {
      const done = task.status === "done"; const run = runs[task.id]; const items = history[task.id] || []; const rec = run ? recovery[run.id] : undefined;
      return <article className="task-item task-workbench" key={task.id}><div className="task-primary-row"><button className={`task-check${done ? " checked" : ""}`} aria-label={done ? "标记为待办" : "标记为完成"} onClick={() => void changeStatus(task.id, done ? "todo" : "done")}>{done ? "✓" : ""}</button><div className="task-copy"><strong>{task.title}</strong><div><SourceChip source={task.source} />{task.due_date && <span>{task.due_date}</span>}{run && <span className={`task-run-status ${run.status}`}>{RUN_LABELS[run.status]}</span>}</div></div><div className="task-actions">{!run && !done && <button onClick={() => void createExecution(task)}>建立执行</button>}{run?.status === "awaiting_approval" && <button onClick={() => void runAction(run, "approve")}>批准计划</button>}{run?.status === "ready" && <button onClick={() => void runAction(run, "start")}>开始</button>}{run?.status === "running" && <button onClick={() => void runAction(run, "pause")}>暂停</button>}{(run?.status === "paused" || run?.status === "recovery_required") && <button onClick={() => void runAction(run, "resume")}>继续</button>}{run && !TERMINAL.includes(run.status) && <button onClick={() => void editPlan(task, run)}>编辑计划</button>}{run && !TERMINAL.includes(run.status) && <button onClick={() => void replanWithPlanner(task, run)}>重新生成计划</button>}<button onClick={() => setHistoryOpen((current) => ({ ...current, [task.id]: !current[task.id] }))}>历史 {items.length}</button><button className="danger" onClick={() => void remove(task.id)}>删除</button></div></div>
      {run && <div className="task-run-panel"><div className="task-run-progress"><span>{run.progress_current}/{run.progress_total} 步</span><i><b style={{ width: `${run.progress_total ? run.progress_current / run.progress_total * 100 : 0}%` }} /></i><code>{run.id}</code></div>{run.status === "awaiting_approval" && <p>这里只批准计划，不会授予文件、网络或工具权限。</p>}{(run.waiting_reason || run.error_message) && <p className={run.error_message ? "error" : ""}>{run.error_message || run.waiting_reason}</p>}{run.next_action && <p>下一步：{run.next_action}</p>}{run.nodes?.some((node) => (node.source_links || []).some((link) => link.status === "invalidated")) && <div className="run-banner invalid" role="alert"><strong>有节点引用已失效，无法开始执行</strong><p>请移除失效引用，或重新生成计划。</p></div>}{recoveryCardVisible(run.status) && <><article className="recovery-card" data-mode={rec?.last_evidence ? "data" : "empty"}><header><div><span className="page-eyebrow">恢复建议</span><h2>{rec?.last_evidence ? "基于最后一次工具证据" : "暂无工具执行记录"}</h2></div><span className={`risk-pill ${rec?.risk || "none"}`}>{riskLabel(rec?.risk || "none")}</span></header>{rec?.last_evidence ? <div className="recovery-evidence"><div className="evidence-row"><span className="evidence-label">工具</span><strong>{rec.last_evidence.tool_name}</strong></div><div className="evidence-row"><span className="evidence-label">阶段</span><span>{rec.last_evidence.phase} · {rec.last_evidence.status}</span></div>{rec.last_evidence.trace_id && <div className="evidence-row"><span className="evidence-label">trace</span><code>{rec.last_evidence.trace_id.slice(0, 8)}…</code></div>}{rec.last_evidence.error_message && <div className="evidence-row"><span className="evidence-label">错误</span><span className="redacted">{rec.last_evidence.error_message}</span></div>}</div> : <p className="empty-copy">当前运行没有工具执行记录；接入工具后将在这里显示恢复建议。</p>}<div className="recovery-actions"><button className="primary" disabled={!rec?.allowed.continue || run.status === "failed"} onClick={() => void runAction(run, "resume")}>继续</button><button disabled title={rec?.reasons?.retry || "工具执行接入后可重试"}>重试（接入工具后可用）</button><button className="ghost" onClick={() => void editPlan(task, run)}>重新规划</button></div></article>{run.status === "recovery_required" && <div className="run-banner warn"><strong>应用中断，任务已进入保护状态，不会自动继续</strong></div>}</>}{run.nodes?.map((node) => <div className={`task-node ${node.status}`} key={node.id} data-lock={node.user_locked ? "explicit" : "none"}><span>{node.status === "succeeded" ? "✓" : node.position + 1}</span><strong>{node.title}</strong>{lockUiState(node).label && <span className="node-lock-pill">{lockUiState(node).label}</span>}<small>{node.depends_on.length ? `依赖：${node.depends_on.join("、")}` : "无前置依赖"}</small>{node.completion_criteria && <em>验收：{node.completion_criteria}</em>}{node.skip_reason_code && <em>跳过：{node.skip_reason_code}</em>}{(node.source_links || []).length > 0 && <div className="node-source-row">{(node.source_links || []).map((link) => <span key={link.id} className={`source-ref-chip ${link.status === "invalidated" ? "invalid" : link.source_kind}`} title={link.invalidated_reason || link.summary || link.source_kind}>{link.source_kind === "knowledge_source" ? "知识" : link.source_kind === "conversation" ? "对话" : "记忆"}</span>)}</div>}{run.status === "running" && node.status === "ready" && <button onClick={() => void nodeAction(run, node, "start")}>执行</button>}{run.status === "running" && node.status === "ready" && <button onClick={() => void nodeAction(run, node, "skip")}>跳过</button>}{run.status === "running" && node.status === "running" && <><button onClick={() => void nodeAction(run, node, "succeed")}>完成</button><button className="danger" onClick={() => void nodeAction(run, node, "fail")}>失败</button></>}</div>)}<button className="task-event-toggle" onClick={() => setShowEvents((current) => ({ ...current, [run.id]: !current[run.id] }))}>{showEvents[run.id] ? "收起事件" : `查看事件 ${run.events?.length || 0}`}</button>{showEvents[run.id] && <div className="task-event-list">{run.events?.map((event) => <div key={event.id}><code>r{event.revision}</code><span>{eventLabel(event)}</span>{event.reason_code && <em>{event.reason_code}</em>}</div>)}</div>}</div>}
      {historyOpen[task.id] && <div className="task-history">{items.length === 0 ? <span>尚无执行历史</span> : items.map((item) => <div key={item.id}><button onClick={() => void api.getTaskRun(item.id).then((detail) => replaceRun(task.id, detail))}><strong>{RUN_LABELS[item.status]}</strong><code>{item.id}</code><small>r{item.revision}</small></button>{TERMINAL.includes(item.status) && <button onClick={() => void rerun(task, item)}>再次执行</button>}</div>)}</div>}
      </article>;
    })}</section>)}
    {editor && <section className="task-plan-editor" aria-label="计划编辑器"><header><div><strong>编辑执行计划</strong><small>提交会替换当前计划并产生新版本；批准始终只针对该版本。</small></div><button onClick={() => setEditor(null)}>关闭</button></header><label className="task-approval"><input type="checkbox" checked={editor.requiresApproval} onChange={(event) => setEditor({ ...editor, requiresApproval: event.target.checked })} /> 提交后要求明确批准再开始</label>{editor.nodes.map((node, index) => <div className="task-plan-node" data-lock={node.user_locked ? "explicit" : "none"} key={node.client_id}><div><b>步骤 {index + 1}</b>{lockUiState(node).label && <span className="node-lock-pill">{lockUiState(node).label}</span>}<button className="node-lock-btn" aria-label={node.user_locked ? "解锁节点" : "锁定节点"} onClick={() => toggleLock(node.client_id)}>{node.user_locked ? "🔒" : "🔓"}</button><button onClick={() => setEditor({ ...editor, nodes: editor.nodes.filter((item) => item.client_id !== node.client_id).map((item) => ({ ...item, depends_on: item.depends_on.filter((id) => id !== node.client_id) })) })} disabled={editor.nodes.length === 1}>移除</button></div><input value={node.title} placeholder="步骤标题" disabled={node.user_locked} onChange={(event) => touchNode(node.client_id, { title: event.target.value })} /><textarea value={node.completion_criteria} placeholder="验收条件" disabled={node.user_locked} onChange={(event) => touchNode(node.client_id, { completion_criteria: event.target.value })} /><label>依赖步骤<select multiple value={node.depends_on} disabled={node.user_locked} onChange={(event) => touchNode(node.client_id, { depends_on: Array.from(event.currentTarget.selectedOptions, (option) => option.value) })}>{editor.nodes.filter((item) => item.client_id !== node.client_id).map((item) => <option key={item.client_id} value={item.client_id}>{item.title || item.client_id}</option>)}</select></label></div>)}<footer><button onClick={() => setEditor({ ...editor, nodes: [...editor.nodes, defaultNode("")] })}>添加步骤</button><button className="primary" onClick={() => void savePlan()} disabled={editor.nodes.some((node) => !node.title.trim())}>提交计划</button></footer></section>}
  </section>;
}
