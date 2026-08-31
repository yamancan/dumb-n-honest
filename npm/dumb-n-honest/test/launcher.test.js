"use strict";

const assert = require("node:assert/strict");
const { mkdirSync, mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { basename, join } = require("node:path");
const test = require("node:test");

const { defaultOutputDirectory } = require("../bin/dumb-n-honest.js");

test("default output directory is timestamped and collision-safe", () => {
  const root = mkdtempSync(join(tmpdir(), "dumb-n-honest-test-"));
  try {
    const now = new Date(2026, 8, 1, 12, 34, 56);
    const first = defaultOutputDirectory(root, now);
    assert.equal(basename(first), "dumb-n-honest-output-20260901-123456");
    mkdirSync(first);
    assert.equal(
      basename(defaultOutputDirectory(root, now)),
      "dumb-n-honest-output-20260901-123456-2",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
