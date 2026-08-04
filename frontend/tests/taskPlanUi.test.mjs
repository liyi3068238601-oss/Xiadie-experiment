import { planCardState, proposalToDraftNodes, lockUiState } from "../src/taskPlanUi.mjs";
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
  assert.equal(nodes[0].locked_reason, "explicit");
});

test("plan card state transitions are finite", () => {
  for (const state of ["loading", "pending", "editing", "failed", "cancelled"]) {
    assert.equal(planCardState(state), state);
  }
  assert.equal(planCardState("bogus"), "pending");
});

test("lock UI states cover three-way semantics", () => {
  assert.equal(lockUiState({ user_locked: true, locked_reason: "edit" }).label, "已锁定 · 编辑");
  assert.equal(lockUiState({ user_locked: true, locked_reason: "explicit" }).label, "已锁定");
  assert.equal(lockUiState({}).label, "");
});
