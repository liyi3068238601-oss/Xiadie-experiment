export const riskLabel = (risk) => ({
  low: "风险 · 低",
  mid: "风险 · 中",
  high: "风险 · 高",
  none: "无证据 · fail closed",
}[risk] || "风险未知");

export const actionLabel = (action, retryAllowed) =>
  action === "retry" && !retryAllowed
    ? "重试（接入工具后可用）"
    : action === "retry" ? "重试" : action === "continue" ? "继续" : "重新规划";

export const isRetryDisabled = (advice) => advice?.allowed?.retry === false;

export const recoveryCardVisible = (status) =>
  ["paused", "recovery_required", "failed"].includes(status);
