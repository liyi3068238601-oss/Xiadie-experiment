import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const main = readFileSync(new URL("../main.js", import.meta.url), "utf8");
const preload = readFileSync(new URL("../preload.js", import.meta.url), "utf8");
const builder = readFileSync(new URL("../electron-builder.yml", import.meta.url), "utf8");
const launcher = readFileSync(new URL("../../scripts/start-dev.ps1", import.meta.url), "utf8");
const security = readFileSync(new URL("../../backend/app/security.py", import.meta.url), "utf8");

test("tray owns background lifetime while windows may close", () => {
  assert.match(main, /tray = new Tray\(icon\)/);
  assert.match(main, /app\.on\("window-all-closed"/);
  assert.match(main, /if \(!app\.isQuitting\)/);
  assert.match(main, /tray\.on\("click", \(\) => createMainWindow\(\)\)/);
});

test("suspend stops delivery and resume installs backend guard before polling", () => {
  assert.match(main, /powerMonitor\.on\("suspend", \(\) => stopDeliveryBridge\(\)\)/);
  assert.match(main, /powerMonitor\.on\("resume"/);
  assert.match(main, /\/api\/proactive\/runtime\/system-resume/);
  assert.match(main, /\.finally\(\(\) => startDeliveryBridge\(\)\)/);
});

test("quit stops polling and terminates the owned backend", () => {
  assert.match(main, /app\.on\("before-quit"/);
  assert.match(main, /stopDeliveryBridge\(\)/);
  assert.match(main, /if \(backendProc\) backendProc\.kill\(\)/);
  assert.match(main, /XIADIE_PARENT_PID: String\(process\.pid\)/);
});

test("experiment identity, storage and ports are isolated from the LIFE product", () => {
  assert.match(main, /APP_ID = "com\.xiadie\.agent\.experiment"/);
  assert.match(main, /USER_DATA_DIR_NAME = "Xiadie-Experiment"/);
  assert.match(main, /app\.setPath\("userData"/);
  assert.match(main, /const BACKEND_PORT = 9756/);
  assert.match(main, /DEV_URL = "http:\/\/127\.0\.0\.1:6173"/);
  assert.match(main, /XIADIE_PORT: String\(BACKEND_PORT\)/);
  assert.match(main, /requestSingleInstanceLock\(\{ variant: "xiadie-experiment" \}\)/);
  assert.match(preload, /http:\/\/127\.0\.0\.1:9756/);
  assert.match(builder, /appId: com\.xiadie\.agent\.experiment/);
  assert.match(builder, /productName: 遐蝶实验版/);
  assert.match(launcher, /\$backendPort = 9756/);
  assert.match(launcher, /\$frontendPort = 6173/);
  assert.match(launcher, /Xiadie-Experiment\\dev-logs/);
  assert.match(launcher, /XIADIE_DATA_DIR = Join-Path \$root "backend\\data"/);
  assert.match(security, /http:\/\/127\.0\.0\.1:6173/);
  assert.doesNotMatch(security, /http:\/\/127\.0\.0\.1:5173/);
});
