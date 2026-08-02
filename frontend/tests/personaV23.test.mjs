import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const chat = readFileSync(new URL("../src/components/ChatView.tsx", import.meta.url), "utf8");

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
