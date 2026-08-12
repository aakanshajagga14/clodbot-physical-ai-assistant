import assert from "node:assert/strict";
import test from "node:test";

test("dashboard source contains the flagship safety surfaces", async () => {
  const source = await import("node:fs/promises").then((fs) => fs.readFile(new URL("../app/dashboard.tsx", import.meta.url), "utf8"));
  assert.match(source, /Predictive Safety/);
  assert.match(source, /Facility Overview/);
  assert.match(source, /presentation mode/);
  assert.match(source, /Demo controls/);
  assert.match(source, /Perception/);
  assert.match(source, /Clodbot Intelligence/);
  assert.match(source, /CyberwaveRobotViewport/);
  assert.match(source, /SO-101 CATALOG TWIN/);
  assert.match(source, /Cyberwave/);
  assert.match(source, /api\/intent/);
  assert.match(source, /WebSocket/);
});
