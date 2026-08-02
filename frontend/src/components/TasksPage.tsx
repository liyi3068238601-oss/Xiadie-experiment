import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import * as api from "./../api";
import { toast } from "./../store";
import { Icon } from "./Icon";

function SourceChip({ source }: { source: string }) {
  const isChat = source === "chat";
  return <span className={`task-source${isChat ? " from-chat" : ""}`}>{isChat ? "来自对话" : "手动创建"}</span>;
}

const RUN_LABELS: Record<api.TaskRunStatus, string> = {
  draft: "草稿", planning: "规划中", awaiting_approval: "等待批准", ready: "可开始",
  running: "执行中", paused: "已暂停", recovery_required: "需要恢复",
  completed: "已完成", failed: "失败", cancelled: "已取消",
};

export function TasksPage() {
  const [tasks, setTasks] = useState<api.Task[]>([]);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<Record<string, api.TaskRun>>({});

  const refresh = () => {
    setLoading(true);
    api.listTasks()
      .then(async (list) => {
        setTasks(list.filter((task) => task.status !== "archived"));
        const latest = await Promise.all(list.map(async (task) => {
          const taskRuns = await api.listTaskRuns(task.id);
          if (!taskRuns[0]) return null;
          return [task.id, await api.getTaskRun(taskRuns[0].id)] as const;
        }));
        setRuns(Object.fromEntries(latest.filter((item): item is readonly [string, api.TaskRun] => item !== null)));
        setError(null);
      })
      .catch((reason) => setError(reason?.message || "加载任务失败"))
      .finally(() => setLoading(false));
  };

  const createExecution = async (task: api.Task) => {
    try {
      const run = await api.createTaskRun(task.id, task.title);
      await api.replaceTaskRunPlan(run.id, [{
        client_id: "deliver", title: task.title, depends_on: [],
        completion_criteria: "形成可核验的结果或明确失败原因",
      }], false, run.revision);
      toast("已建立执行计划，可在开始前继续由 Agent 调整");
      refresh();
    } catch (reason: any) {
      toast(reason?.message || "建立执行失败");
    }
  };

  const runAction = async (run: api.TaskRun, action: "approve" | "start" | "pause" | "resume" | "cancel" | "replan") => {
    try {
      await api.taskRunAction(run.id, action, run.revision);
      refresh();
    } catch (reason: any) {
      if (reason?.code === "task_run_revision_conflict") {
        toast("任务已在别处更新，已刷新到最新状态");
        refresh();
        return;
      }
      toast(reason?.message || "执行状态更新失败");
    }
  };

  const nodeAction = async (run: api.TaskRun, node: api.TaskNode, action: "start" | "succeed" | "fail" | "skip") => {
    try {
      await api.taskNodeAction(run.id, node.id, action,
        action === "fail"
          ? { error_code: "manual_step_failed", error_message: "用户标记步骤失败", expected_revision: run.revision }
          : { expected_revision: run.revision });
      refresh();
    } catch (reason: any) {
      if (reason?.code === "task_run_revision_conflict") {
        toast("步骤状态已经变化，已刷新任务");
        refresh();
        return;
      }
      toast(reason?.message || "步骤状态更新失败");
    }
  };

  useEffect(refresh, []);

  const add = async () => {
    const nextTitle = title.trim();
    if (!nextTitle || busy) return;
    setBusy(true);
    try {
      await api.createTask(nextTitle);
      setTitle("");
      toast("已新建任务");
      refresh();
    } catch (reason: any) {
      toast(reason?.message || "新建失败");
    } finally {
      setBusy(false);
    }
  };

  const changeStatus = async (id: string, status: api.Task["status"]) => {
    try {
      await api.updateTask(id, { status });
      refresh();
    } catch (reason: any) {
      toast(reason?.message || "更新失败");
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteTask(id);
      toast("已删除任务");
      refresh();
    } catch (reason: any) {
      toast(reason?.message || "删除失败");
    }
  };

  const groups: { key: api.Task["status"]; label: string; items: api.Task[] }[] = [
    { key: "doing", label: "进行中", items: tasks.filter((task) => task.status === "doing") },
    { key: "todo", label: "待办", items: tasks.filter((task) => task.status === "todo") },
    { key: "done", label: "已完成", items: tasks.filter((task) => task.status === "done") },
  ];
  const doneCount = groups[2].items.length;
  const openCount = tasks.length - doneCount;
  const completion = tasks.length ? Math.round((doneCount / tasks.length) * 100) : 0;

  return (
    <section className="page tasks-page" aria-labelledby="tasks-title">
      <header className="page-header compact-page-header">
        <div>
          <p className="page-eyebrow">TASKS</p>
          <h1 id="tasks-title">今日任务</h1>
          <p>随手记录，遐蝶帮你盯着。</p>
        </div>
        <span className="header-meta">{openCount} 项未完成</span>
      </header>

      <div className="task-create">
        <Icon name="plus" />
        <input
          placeholder="写点要做的事，回车即可新建…"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void add(); }}
        />
        <button onClick={() => void add()} disabled={busy || !title.trim()}>新增任务</button>
      </div>

      <div className="task-summary" aria-label="任务概览">
        <div><strong>{groups[1].items.length}</strong><span>待办</span></div>
        <div><strong>{groups[0].items.length}</strong><span>进行中</span></div>
        <div><strong>{doneCount}</strong><span>已完成</span></div>
        <div className="task-progress" style={{ "--progress": `${completion * 3.6}deg` } as CSSProperties}><span>{completion}%</span></div>
      </div>

      {error && <div className="empty">加载出错了：{error}</div>}
      {!error && loading && <div className="empty">正在整理任务…</div>}
      {!error && !loading && tasks.length === 0 && <div className="empty">今天还没有任务，要我先帮你记一个吗？</div>}

      {!error && !loading && groups.map((group) => group.items.length > 0 && (
        <section className={`task-group ${group.key}`} key={group.key}>
          <header><span>{group.label}</span><b>{group.items.length}</b></header>
          {group.items.map((task) => {
            const done = task.status === "done";
            const run = runs[task.id];
            return (
              <article className="task-item task-workbench" key={task.id}>
                <div className="task-primary-row">
                  <button
                    className={`task-check${done ? " checked" : ""}`}
                    aria-label={done ? "标记为待办" : "标记为完成"}
                    onClick={() => void changeStatus(task.id, done ? "todo" : "done")}
                  >{done ? "✓" : ""}</button>
                  <div className="task-copy">
                    <strong>{task.title}</strong>
                    <div>
                      <SourceChip source={task.source} />
                      {task.due_date && <span>{task.due_date}</span>}
                      {run && <span className={`task-run-status ${run.status}`}>{RUN_LABELS[run.status]}</span>}
                    </div>
                  </div>
                  <div className="task-actions">
                    {!run && !done && <button onClick={() => void createExecution(task)}>建立执行</button>}
                    {run?.status === "awaiting_approval" && <button onClick={() => void runAction(run, "approve")}>批准</button>}
                    {run?.status === "ready" && <button onClick={() => void runAction(run, "start")}>开始</button>}
                    {run?.status === "running" && <button onClick={() => void runAction(run, "pause")}>暂停</button>}
                    {(run?.status === "paused" || run?.status === "recovery_required") && <button onClick={() => void runAction(run, "resume")}>继续</button>}
                    {run && !["completed", "cancelled"].includes(run.status) && <button onClick={() => void runAction(run, "replan")}>重规划</button>}
                    {run && !["completed", "cancelled"].includes(run.status) && <button onClick={() => void runAction(run, "cancel")}>取消</button>}
                    <button className="danger" onClick={() => void remove(task.id)}>删除</button>
                  </div>
                </div>
                {run && <div className="task-run-panel">
                  <div className="task-run-progress">
                    <span>{run.progress_current}/{run.progress_total} 步</span>
                    <i><b style={{ width: `${run.progress_total ? (run.progress_current / run.progress_total) * 100 : 0}%` }} /></i>
                    <code>{run.id}</code>
                  </div>
                  {(run.waiting_reason || run.error_message) && <p className={run.error_message ? "error" : ""}>
                    {run.error_message || run.waiting_reason}
                  </p>}
                  {run.next_action && <p>下一步：{run.next_action}</p>}
                  {run.nodes?.map((node) => <div className={`task-node ${node.status}`} key={node.id}>
                    <span>{node.status === "succeeded" ? "✓" : node.position + 1}</span>
                    <strong>{node.title}</strong>
                    {run.status === "running" && node.status === "ready" && <button onClick={() => void nodeAction(run, node, "start")}>执行</button>}
                    {run.status === "running" && node.status === "running" && <>
                      <button onClick={() => void nodeAction(run, node, "succeed")}>完成</button>
                      <button className="danger" onClick={() => void nodeAction(run, node, "fail")}>失败</button>
                    </>}
                  </div>)}
                </div>}
              </article>
            );
          })}
        </section>
      ))}
    </section>
  );
}
