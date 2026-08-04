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
