import { riskLabel, actionLabel, isRetryDisabled, recoveryCardVisible } from "../src/recoveryUi.mjs";
import test from "node:test";
import assert from "node:assert/strict";

test("risk labels map to pills", () => {
  assert.equal(riskLabel("low"), "风险 · 低");
  assert.equal(riskLabel("mid"), "风险 · 中");
  assert.equal(riskLabel("high"), "风险 · 高");
  assert.equal(riskLabel("none"), "无证据 · fail closed");
});

test("action labels stay honest before tool execution exists", () => {
  assert.equal(actionLabel("retry", false), "重试（接入工具后可用）");
  assert.equal(isRetryDisabled({ allowed: { retry: false } }), true);
});

test("recovery card only appears for interrupted statuses", () => {
  for (const status of ["paused", "recovery_required", "failed"]) {
    assert.equal(recoveryCardVisible(status), true);
  }
  for (const status of ["draft", "ready", "running", "completed"]) {
    assert.equal(recoveryCardVisible(status), false);
  }
});
