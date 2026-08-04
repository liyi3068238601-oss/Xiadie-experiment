import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "./../api";
import { toast } from "./../store";

const LEVELS: Array<api.DiagnosticLevel | "ALL"> = [
  "ALL", "TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
];
const LEVEL_LABEL: Record<string, string> = {
  ALL: "全部级别", TRACE: "TRACE", DEBUG: "DEBUG", INFO: "INFO",
  WARNING: "WARNING", ERROR: "ERROR", CRITICAL: "CRITICAL",
};

function eventText(item: api.DiagnosticLogEvent): string {
  return [
    item.timestamp, item.level, item.logger, item.event, item.message, item.process,
    item.trace_id, item.task_run_id, item.tool_run_id, item.plugin_id, item.phase,
    item.status, item.thought, item.mood, item.reason, item.error?.type,
    item.error?.code, item.error?.message,
  ].filter(Boolean).join(" ");
}

function compactTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return `[${value.slice(11, 23)}]`;
  const base = parsed.toLocaleTimeString("zh-CN", {
    hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  return `[${base}.${String(parsed.getMilliseconds()).padStart(3, "0")}]`;
}

const MODULE_COLORS = [
  "#9db8e8", "#8fceb0", "#e0c08f", "#c9a6e8", "#e39aa8",
  "#8fd0e0", "#b8c88f", "#e0a97e", "#a8b8e8", "#d5b3d9",
];

function moduleColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) | 0;
  return MODULE_COLORS[Math.abs(hash) % MODULE_COLORS.length];
}

function lineMessage(item: api.DiagnosticLogEvent): string {
  if (item.content_class === "character_mental_activity" && item.thought) return `💭 ${item.thought}`;
  const error = item.error;
  if (error) return `${item.message}${item.message ? " · " : ""}${error.type || "Error"}: ${error.message || error.code || "unknown"}`;
  return item.message || item.event;
}

export function DiagnosticTerminalPage({ onAudit }: { onAudit: () => void }) {
  const [events, setEvents] = useState<api.DiagnosticLogEvent[]>([]);
  const [connection, setConnection] = useState<"connecting" | "live" | "reconnecting" | "offline">("connecting");
  const [level, setLevel] = useState<api.DiagnosticLevel | "ALL">("INFO");
  const [processFilter, setProcessFilter] = useState("all");
  const [loggerFilter, setLoggerFilter] = useState("");
  const [search, setSearch] = useState("");
  const [mentalOnly, setMentalOnly] = useState(false);
  const [paused, setPaused] = useState(false);
  const [pausedCount, setPausedCount] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);
  const [selected, setSelected] = useState<api.DiagnosticLogEvent | null>(null);
  const [gap, setGap] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const pendingRef = useRef<api.DiagnosticLogEvent[]>([]);
  const pausedRef = useRef<api.DiagnosticLogEvent[]>([]);
  const latestCursorRef = useRef(0);
  const pausedRefState = useRef(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { pausedRefState.current = paused; }, [paused]);

  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();
    const append = (item: api.DiagnosticLogEvent) => {
      latestCursorRef.current = Math.max(latestCursorRef.current, item.cursor || 0);
      if (pausedRefState.current) {
        pausedRef.current.push(item);
        if (pausedRef.current.length > 5000) pausedRef.current = pausedRef.current.slice(-5000);
        setPausedCount(pausedRef.current.length);
      } else {
        pendingRef.current.push(item);
      }
    };
    const flushTimer = window.setInterval(() => {
      if (!mounted || pendingRef.current.length === 0) return;
      const batch = pendingRef.current.splice(0);
      setEvents((current) => {
        const seen = new Set(current.map((item) => item.event_id));
        const merged = [...current, ...batch.filter((item) => !seen.has(item.event_id))];
        return merged.slice(-5000);
      });
    }, 100);

    const run = async () => {
      try {
        const snapshot = await api.listDiagnosticLogs({ limit: 5000 });
        if (!mounted) return;
        setEvents(snapshot.items);
        latestCursorRef.current = snapshot.latest_cursor;
        if (snapshot.gap) setGap("早期日志已从内存缓冲区淘汰");
      } catch {
        if (mounted) setConnection("offline");
      }
      let delay = 600;
      while (mounted && !controller.signal.aborted) {
        try {
          setConnection((current) => current === "live" ? "reconnecting" : "connecting");
          await api.streamDiagnosticLogs(latestCursorRef.current, controller.signal, {
            onConnected: () => { if (mounted) setConnection("live"); },
            onLog: append,
            onGap: (oldest) => { if (mounted) setGap(`日志游标已过期，从 ${oldest} 继续`); },
          });
          delay = 600;
        } catch (error) {
          if (controller.signal.aborted) break;
          setConnection("reconnecting");
        }
        await new Promise((resolve) => window.setTimeout(resolve, delay));
        delay = Math.min(8000, delay * 2);
      }
    };
    void run();
    return () => {
      mounted = false;
      controller.abort();
      window.clearInterval(flushTimer);
    };
  }, []);

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return events.filter((item) => {
      if (level !== "ALL" && item.level !== level) return false;
      if (processFilter !== "all" && item.process !== processFilter) return false;
      if (loggerFilter && !item.logger.toLocaleLowerCase().includes(loggerFilter.toLocaleLowerCase())) return false;
      if (mentalOnly && item.content_class !== "character_mental_activity") return false;
      return !needle || eventText(item).toLocaleLowerCase().includes(needle);
    }).slice(-1000);
  }, [events, level, processFilter, loggerFilter, mentalOnly, search]);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [visible.length, autoScroll]);

  const resume = () => {
    const queued = pausedRef.current.splice(0);
    setEvents((current) => [...current, ...queued].slice(-5000));
    setPausedCount(0);
    setPaused(false);
  };

  const exportBundle = async () => {
    setExporting(true);
    try {
      const bundle = await api.createSupportBundle();
      await api.downloadSupportBundle(bundle);
      toast(`诊断包已导出：${bundle.filename}`);
    } catch (error: any) {
      toast(error?.message || "诊断包导出失败");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="page runtime-logs-page diagnostic-page">
      <header className="page-header compact-page-header runtime-log-header">
        <div>
          <p className="page-eyebrow">LIVE DIAGNOSTIC TERMINAL</p>
          <h1>诊断终端</h1>
          <p>实时查看进程、模块、工具阶段、异常与显式角色心理活动。</p>
        </div>
        <div className="runtime-log-actions">
          <button className="btn ghost" onClick={onAudit}>运行审计</button>
          <button className="btn ghost" onClick={() => paused ? resume() : setPaused(true)}>
            {paused ? `继续（${pausedCount}）` : "暂停显示"}
          </button>
          <button className="btn ghost" onClick={() => { setEvents([]); setSelected(null); }}>清屏</button>
          <button className="btn ghost" disabled={exporting} onClick={exportBundle}>
            {exporting ? "正在导出…" : "导出诊断包"}
          </button>
        </div>
      </header>

      <div className="diagnostic-statusbar">
        <span className={`diagnostic-connection ${connection}`}><i />{
          connection === "live" ? "实时连接" : connection === "reconnecting" ? "正在重连" :
            connection === "offline" ? "后端离线" : "正在连接"
        }</span>
        <span>缓冲 {events.length}/5000</span>
        <span>当前显示 {visible.length}{events.length > 1000 ? "（最多渲染 1000 条）" : ""}</span>
        {gap ? <button onClick={() => setGap(null)}>{gap} ×</button> : null}
      </div>

      <div className="runtime-privacy-note">
        <span className="runtime-privacy-icon">i</span>
        <span>日志默认脱敏。带 💭 的内容是 AI 显式生成并声明为用户可见的角色表达，不是 Provider 隐藏思维链；支持包默认排除其正文。</span>
      </div>

      <div className="diagnostic-toolbar">
        <select value={level} onChange={(event) => setLevel(event.target.value as typeof level)}>
          {LEVELS.map((item) => <option key={item} value={item}>{LEVEL_LABEL[item]}</option>)}
        </select>
        <select value={processFilter} onChange={(event) => setProcessFilter(event.target.value)}>
          <option value="all">全部进程</option>
          <option value="backend">Backend</option>
          <option value="desktop">Electron</option>
          <option value="plugin">Plugin</option>
        </select>
        <input value={loggerFilter} onChange={(event) => setLoggerFilter(event.target.value)} placeholder="模块，如 tool.file" />
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索工具、错误、trace…" />
        <label><input type="checkbox" checked={mentalOnly} onChange={(event) => setMentalOnly(event.target.checked)} /> 心理活动</label>
        <label><input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} /> 自动滚动</label>
      </div>

      <div className="diagnostic-terminal" role="log" aria-live="off">
        {visible.length === 0 ? <div className="diagnostic-empty">当前筛选条件下没有诊断事件</div> : null}
        {visible.map((item) => (
          <button
            key={item.event_id}
            className={`diagnostic-line level-${item.level.toLocaleLowerCase()} ${item.content_class === "character_mental_activity" ? "mental" : ""}`}
            onClick={() => setSelected(item)}
            title="查看结构化详情"
          >
            <time>{compactTime(item.timestamp)}</time>
            <strong>{LEVEL_LABEL[item.level] || item.level.slice(0, 3)}</strong>
            <span className="diagnostic-process">{item.process}</span>
            <span className="diagnostic-logger" style={{ color: moduleColor(item.logger) }}>{item.logger}</span>
            <span className="diagnostic-correlation">{item.tool_run_id || item.task_run_id || item.trace_id?.slice(-8) || ""}</span>
            <span className="diagnostic-message">{lineMessage(item)}</span>
          </button>
        ))}
        <div ref={bottomRef} />
      </div>

      {selected ? (
        <div className="diagnostic-detail">
          <header>
            <strong>{selected.logger} · {selected.event}</strong>
            <button onClick={() => navigator.clipboard.writeText(JSON.stringify(selected, null, 2)).then(() => toast("已复制脱敏详情"))}>复制</button>
            <button onClick={() => setSelected(null)}>关闭</button>
          </header>
          {selected.error ? (
            <div className="diagnostic-error-summary">
              <strong>{selected.error.type || "Error"}</strong>
              <span>{selected.error.message || selected.error.code}</span>
            </div>
          ) : null}
          <pre>{JSON.stringify(selected, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}
