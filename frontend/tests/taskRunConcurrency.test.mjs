import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const tasks = readFileSync(new URL("../src/components/TasksPage.tsx", import.meta.url), "utf8");

test("TaskRun mutation helpers require the visible revision", () => {
  assert.match(api, /replaceTaskRunPlan = \([\s\S]*expectedRevision: number,[\s\S]*requiresApproval = false/);
  assert.match(api, /taskRunAction = \([\s\S]*expectedRevision: number/);
  assert.match(api, /taskNodeAction = \([\s\S]*expectedRevision: number,[\s\S]*evidence:/);
  assert.match(api, /linkTaskRunArtifact = \([\s\S]*expectedRevision: number/);
  assert.doesNotMatch(api, /expectedRevision\?: number/);
  assert.match(tasks, /taskRunAction\(run\.id, action, run\.revision\)/);
  assert.match(tasks, /run\.id, node\.id, action, run\.revision, evidence/);
});

test("conflict snapshots accept only same-run non-older state", () => {
  assert.match(api, /current\.id !== local\.id/);
  assert.match(api, /current\.revision >= local\.revision/);
  assert.match(tasks, /taskRunConflictSnapshot\(reason, local\)/);
  assert.match(tasks, /current \|\| await api\.getTaskRun\(local\.id\)/);
  assert.match(tasks, /replaceRun\(taskId, next\)/);
});

test("conflicts never replay mutations automatically", () => {
  const reconcile = tasks.slice(
    tasks.indexOf("const reconcileConflict"),
    tasks.indexOf("const runAction"),
  );
  assert.match(reconcile, /getTaskRun/);
  assert.doesNotMatch(reconcile, /taskRunAction|taskNodeAction|replaceTaskRunPlan/);
});

test("approval UI states the narrow permission boundary", () => {
  assert.match(tasks, />批准计划<\/button>/);
  assert.match(tasks, /这里只批准计划，不会授予文件、网络或工具权限。/);
});
