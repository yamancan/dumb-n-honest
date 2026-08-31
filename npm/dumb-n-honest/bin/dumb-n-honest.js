#!/usr/bin/env node
"use strict";

const { createHash } = require("node:crypto");
const { spawnSync } = require("node:child_process");
const { mkdirSync, readFileSync, rmSync, statSync, writeFileSync, existsSync } = require("node:fs");
const { homedir } = require("node:os");
const { join } = require("node:path");

const DEFAULT_VERSION = "0.2.5";
const PINNED_SHA256 = {
  "0.2.5": "298da142699196fef4579917757474c4fd5238579e61d7300cde795e6ee19648",
};
const DEFAULT_BASE_URL = "https://github.com/yamancan/dumb-n-honest/releases/download";
const PACKAGE_FILE = (version) => `dumb-n-honest-v${version}.skill`;

const version = process.env.DUMB_N_HONEST_VERSION || DEFAULT_VERSION;
const baseUrl = (process.env.DUMB_N_HONEST_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
const installRoot = join(homedir(), ".dumb-n-honest", "versions", version);
const packagePath = join(installRoot, PACKAGE_FILE(version));
const skillRoot = join(installRoot, "dumb-n-honest");
const markerPath = join(installRoot, ".verified");

function fail(message) {
  process.stderr.write(`dumb-n-honest: ${message}\n`);
  process.exit(1);
}

function resolvePython() {
  const candidates = process.platform === "win32"
    ? [["py", ["-3"]], ["python", []], ["python3", []]]
    : [["python3", []], ["python3.14", []], ["python3.13", []], ["python3.12", []], ["python3.11", []], ["python3.10", []], ["python", []]];
  for (const [command, prefix] of candidates) {
    const probe = spawnSync(command, [...prefix, "--version"], { encoding: "utf8", windowsHide: true });
    if (probe.error || probe.status !== 0) continue;
    const match = /Python 3\.(\d+)/.exec(`${probe.stdout}${probe.stderr}`);
    if (match && Number(match[1]) >= 10) return [command, prefix];
  }
  return null;
}

function sha256(filePath) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

async function expectedSha256() {
  if (PINNED_SHA256[version]) return PINNED_SHA256[version];
  const response = await fetch(`${baseUrl}/v${version}/SHA256SUMS`);
  if (!response.ok) fail(`could not fetch SHA256SUMS for v${version} (HTTP ${response.status})`);
  const wanted = `  ${PACKAGE_FILE(version)}\n`;
  for (const line of (await response.text()).split("\n")) {
    if (line.endsWith(`/${PACKAGE_FILE(version)}`) || line.endsWith(wanted.trimEnd())) {
      return line.split(" ")[0];
    }
  }
  return fail(`SHA256SUMS for v${version} does not list ${PACKAGE_FILE(version)}`);
}

async function download() {
  const url = `${baseUrl}/v${version}/${PACKAGE_FILE(version)}`;
  const response = await fetch(url);
  if (!response.ok) fail(`could not download ${url} (HTTP ${response.status})`);
  const bytes = Buffer.from(await response.arrayBuffer());
  writeFileSync(packagePath, bytes, { mode: 0o600 });
}

async function ensureInstalled(python) {
  const expected = await expectedSha256();
  if (existsSync(markerPath) && readFileSync(markerPath, "utf8").trim() === expected && existsSync(join(skillRoot, "scripts", "run.py"))) {
    if (existsSync(packagePath) && sha256(packagePath) !== expected) {
      rmSync(installRoot, { recursive: true, force: true });
    } else {
      return;
    }
  } else if (existsSync(installRoot)) {
    rmSync(installRoot, { recursive: true, force: true });
  }
  mkdirSync(installRoot, { recursive: true });
  process.stderr.write(`dumb-n-honest: fetching verified release v${version}...\n`);
  await download();
  const actual = sha256(packagePath);
  if (actual !== expected) {
    rmSync(installRoot, { recursive: true, force: true });
    fail(`SHA256 mismatch for ${PACKAGE_FILE(version)}: expected ${expected}, got ${actual}. Nothing was executed.`);
  }
  const extract = spawnSync(python[0], [...python[1], "-m", "zipfile", "-e", packagePath, installRoot + require("node:path").sep], { encoding: "utf8", windowsHide: true });
  if (extract.error || extract.status !== 0) {
    rmSync(installRoot, { recursive: true, force: true });
    fail("the verified package could not be extracted with your Python installation.");
  }
  if (!existsSync(join(skillRoot, "scripts", "run.py"))) {
    rmSync(installRoot, { recursive: true, force: true });
    fail("the verified package did not contain the expected scripts.");
  }
  writeFileSync(markerPath, `${expected}\n`, { mode: 0o600 });
}

function usage() {
  process.stdout.write(`dumb-n-honest — private local correction-acknowledgment benchmark

Usage:
  dumb-n-honest doctor [--provider all|claude|codex]
  dumb-n-honest run --output-dir <new-dir> [--provider all|claude|codex] [--languages en,tr] [--no-png] [--require-png] [--github-url <url>]

Requires Python 3.10+ and local Claude Code or Codex history.
Downloads the official dumb-n-honest release, verifies its SHA256, and runs it locally.
No network requests are made by the audit itself; nothing is published automatically.

Environment:
  DUMB_N_HONEST_VERSION   release to use (default: ${DEFAULT_VERSION})
  DUMB_N_HONEST_BASE_URL  release mirror (default: ${DEFAULT_BASE_URL})
`);
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.includes("-h") || argv.includes("--help") || argv.length === 0) {
    usage();
    return;
  }
  const python = resolvePython();
  if (!python) fail("Python 3.10 or newer is required but was not found on PATH.");
  await ensureInstalled(python);
  let script;
  let rest;
  if (argv[0] === "doctor") {
    script = join(skillRoot, "scripts", "doctor.py");
    rest = argv.slice(1);
  } else if (argv[0] === "run" || argv[0].startsWith("--")) {
    script = join(skillRoot, "scripts", "run.py");
    rest = argv[0] === "run" ? argv.slice(1) : argv;
  } else {
    usage();
    process.exit(1);
  }
  if (!statSync(script).isFile()) fail(`missing script ${script}`);
  const result = spawnSync(python[0], [...python[1], script, ...rest], { stdio: "inherit", windowsHide: true });
  if (result.error) fail(`could not launch Python: ${result.error.message}`);
  process.exit(result.status === null ? 1 : result.status);
}

main().catch((error) => fail(error && error.message ? error.message : String(error)));
