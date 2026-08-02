import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const tasks = readFileSync(new URL("../src/components/TasksPage.tsx", import.meta.url), "utf8");

test("TaskRun mutations carry the visible revision", () => {
  assert.match(api, /expected_revision: expectedRevision/);
  assert.match(tasks, /taskRunAction\(run\.id, action, run\.revision\)/);
  assert.match(tasks, /expected_revision: run\.revision/);
});

test("stale TaskRun responses refresh instead of overwriting newer state", () => {
  assert.match(api, /details\?: Record<string, unknown>/);
  assert.match(tasks, /task_run_revision_conflict/);
  assert.match(tasks, /任务已在别处更新，已刷新到最新状态/);
  assert.match(tasks, /步骤状态已经变化，已刷新任务/);
});
