import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const chat = readFileSync(new URL("../src/components/ChatView.tsx", import.meta.url), "utf8");
const settings = readFileSync(new URL("../src/components/SettingsPage.tsx", import.meta.url), "utf8");

test("single-agent persona sends only a bounded style snapshot on every chat request", () => {
  assert.doesNotMatch(api, /persona_mode\?: "companionship" \| "focused_work"/);
  assert.match(api, /persona_style\?:/);
  assert.doesNotMatch(chat, /persona_mode: personaMode/);
  assert.match(chat, /persona_style: personaStyle/);
  assert.doesNotMatch(chat, /type PersonaMode/);
  assert.doesNotMatch(chat, /useState<PersonaMode>/);
});

test("persona preferences are session-scoped and expose no arbitrary prompt input", () => {
  assert.match(chat, /xiadie-persona-v2:\$\{sessionId\}/);
  assert.match(chat, /xiadie-persona-v1:\$\{sessionId\}/);
  assert.doesNotMatch(chat, /JSON\.stringify\(\{ mode:/);
  assert.doesNotMatch(chat, /personaPrompt|systemPrompt|customPrompt/);
  for (const field of ["address_style", "detail_level", "poetic_level", "proactivity_level"]) {
    assert.match(chat, new RegExp(field));
  }
});

test("model quality is displayed as evidence and capability limits remain separate", () => {
  assert.match(api, /quality_status: "verified" \| "unverified"/);
  assert.match(api, /runtime_status: "compatible" \| "capability_limited" \| "incompatible"/);
  assert.match(api, /getPersonaStatus/);
  assert.match(settings, /模型质量：/);
  assert.match(settings, /“未验证”只表示尚无这组模型的质量评测记录/);
  assert.match(settings, /功能限制只依据真实能力探测/);
  assert.doesNotMatch(settings, /未认证模型不能使用 Persona/);
});
