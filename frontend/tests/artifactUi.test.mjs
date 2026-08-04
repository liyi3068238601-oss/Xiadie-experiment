import { artifactKindLabel } from "../src/artifactUi.mjs";
import test from "node:test";
import assert from "node:assert/strict";

test("artifact kind labels", () => {
  assert.equal(artifactKindLabel("text"), "文本");
  assert.equal(artifactKindLabel("image"), "图片");
  assert.equal(artifactKindLabel("pdf"), "PDF");
  assert.equal(artifactKindLabel("unknown"), "文件");
});
