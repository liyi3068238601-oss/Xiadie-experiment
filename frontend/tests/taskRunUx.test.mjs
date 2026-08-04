import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const tasks = readFileSync(new URL("../src/components/TasksPage.tsx", import.meta.url), "utf8");

test("TaskRun UX keeps authenticated event streaming separate from diagnostic logs", () => {
  assert.match(api, /streamTaskRunEvents/);
  assert.match(api, /events\/stream/);
  assert.match(api, /headers: requestHeaders\(\)/);
  assert.doesNotMatch(api.slice(api.indexOf("streamTaskRunEvents"), api.indexOf("replaceTaskRunPlan")), /EventSource/);
  assert.match(tasks, /streamTaskRunEvents\(run\.id/);
});

test("planner, evidence and repeat execution remain visible TaskRun actions", () => {
  assert.match(tasks, /编辑执行计划/);
  assert.match(tasks, /依赖步骤/);
  assert.match(tasks, /验收条件/);
  assert.match(tasks, /这里只批准计划，不会授予文件、网络或工具权限/);
  assert.match(tasks, /再次执行/);
  assert.match(tasks, /查看事件/);
  assert.match(tasks, /nodeAction\(run, node, "skip"\)/);
});

test("CYR.2C planner endpoints and proposal types are wired in api", () => {
  assert.match(api, /createTaskRunFromProposal/);
  assert.match(api, /\/api\/task-runs\/from-proposal/);
  assert.match(api, /plannerProposal/);
  assert.match(api, /\/api\/task-runs\/\$\{encodeURIComponent\(runId\)\}\/planner-proposal/);
  assert.match(api, /onPlanProposal/);
  assert.match(api, /TaskSourceLink/);
});

test("CYR.2C workbench exposes replan, locks and source chips", () => {
  assert.match(tasks, /重新生成计划/);
  assert.match(tasks, /replanWithPlanner/);
  assert.match(tasks, /source-ref-chip/);
  assert.match(tasks, /node-lock-pill/);
  assert.match(tasks, /lockUiState\(node\)/);
  assert.match(tasks, /run-banner invalid/);
});

test("CYR.2C recovery panel is wired into the run panel", () => {
  assert.match(tasks, /recoveryCardVisible\(run\.status\)/);
  assert.match(tasks, /getTaskRunRecovery/);
  assert.match(tasks, /recovery-card/);
  assert.match(tasks, /riskLabel/);
  assert.match(tasks, /重试（接入工具后可用）/);
});

test("CYR.2D chain acceptance keeps trace and evidence visible", () => {
  assert.match(tasks, /task-run-progress/);
  assert.match(tasks, /查看事件/);
  assert.match(tasks, /run\.id/);
  assert.match(tasks, /recoveryCardVisible/);
});

test("CYR.3 tool permission api is wired", () => {
  assert.match(api, /confirmToolPermission/);
  assert.match(api, /denyToolPermission/);
  assert.match(api, /listPendingToolPermissions/);
  assert.match(api, /ToolPermissionRequest/);
  assert.match(api, /tool-permissions\/requests/);
});
