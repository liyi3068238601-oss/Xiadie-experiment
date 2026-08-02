import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import test from "node:test";

const require = createRequire(import.meta.url);
const { safeValue } = require("../../desktop/diagnostic-logger.js");
const desktopLogger = readFileSync(new URL("../../desktop/diagnostic-logger.js", import.meta.url), "utf8");
const main = readFileSync(new URL("../../desktop/main.js", import.meta.url), "utf8");
const terminal = readFileSync(new URL("../src/components/DiagnosticTerminalPage.tsx", import.meta.url), "utf8");

test("desktop diagnostic logger redacts credentials before file or ingest sinks", () => {
  const rendered = JSON.stringify(safeValue({
    api_key: "sk-should-never-appear",
    error: "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
  }));
  assert.doesNotMatch(rendered, /sk-should-never-appear/);
  assert.doesNotMatch(rendered, /abcdefghijklmnopqrstuvwxyz/);
  assert.match(rendered, /REDACTED_SECRET/);
});

test("Electron pipes backend output and forwards lifecycle failures to diagnostics", () => {
  assert.match(main, /stdio: \["ignore", "pipe", "pipe"\]/);
  assert.match(main, /XIADIE_LOG_DIR: logDir/);
  assert.match(main, /backend_start_failed/);
  assert.match(main, /backend_exited/);
  assert.match(main, /renderer_process_gone/);
  assert.match(main, /preload_failed/);
  assert.match(main, /\/api\/diagnostics\/ingest/);
  assert.match(desktopLogger, /normalizedError/);
  assert.match(desktopLogger, /error_type/);
  assert.match(desktopLogger, /error_message/);
});

test("diagnostic terminal keeps a bounded view with pause, reconnect and export", () => {
  assert.match(terminal, /slice\(-5000\)/);
  assert.match(terminal, /pausedRef/);
  assert.match(terminal, /reconnecting/);
  assert.match(terminal, /createSupportBundle/);
  assert.match(terminal, /最多渲染 1000 条/);
});
