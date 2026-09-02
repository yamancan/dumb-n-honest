#!/usr/bin/env node
"use strict";

const { createHash } = require("node:crypto");
const { spawnSync } = require("node:child_process");
const {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} = require("node:fs");
const { homedir, tmpdir } = require("node:os");
const { join } = require("node:path");

const DEFAULT_VERSION = "0.2.8";
const PINNED_SHA256 = {
  "0.2.5": "298da142699196fef4579917757474c4fd5238579e61d7300cde795e6ee19648",
  "0.2.6": "4d4206c18d39571c5b34f8a20f432ed560d11db6f4f38ad1a51be277fe1d70bd",
  "0.2.7": "fb2bb3279da8bfa846eb34b3a9483d200f87bf208c4a36d1e4e104c6f679c270",
  "0.2.8": "7985b0c3c3b35d6d64fc36fc09190ab7c7f08e72fdf04dd33ab940446f0dc95a",
};
const DEFAULT_BASE_URL = "https://github.com/yamancan/dumb-n-honest/releases/download";
const MAX_PACKAGE_BYTES = 10 * 1024 * 1024;
const PACKAGE_FILE = (version) => `dumb-n-honest-v${version}.skill`;

const version = process.env.DUMB_N_HONEST_VERSION || DEFAULT_VERSION;
const baseUrl = (process.env.DUMB_N_HONEST_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
const cacheRoot = process.env.DUMB_N_HONEST_CACHE_DIR
  ? join(process.env.DUMB_N_HONEST_CACHE_DIR, version)
  : join(homedir(), ".dumb-n-honest", "versions", version);
const packagePath = join(cacheRoot, PACKAGE_FILE(version));

function fail(message) {
  throw new Error(message);
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

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function expectedSha256() {
  const expected = PINNED_SHA256[version];
  if (!expected) {
    fail(`release v${version} is not pinned by this launcher. Install a newer dumb-n-honest npm package instead.`);
  }
  return expected;
}

function prepareCache() {
  if (existsSync(cacheRoot) && lstatSync(cacheRoot).isSymbolicLink()) {
    fail(`cache directory must not be a symlink: ${cacheRoot}`);
  }
  mkdirSync(cacheRoot, { recursive: true, mode: 0o700 });
  try {
    chmodSync(cacheRoot, 0o700);
  } catch {}
}

async function downloadPackage() {
  const url = `${baseUrl}/v${version}/${PACKAGE_FILE(version)}`;
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok) fail(`could not download ${url} (HTTP ${response.status})`);
  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > MAX_PACKAGE_BYTES) {
    fail(`release package is larger than ${MAX_PACKAGE_BYTES} bytes`);
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length > MAX_PACKAGE_BYTES) fail(`release package is larger than ${MAX_PACKAGE_BYTES} bytes`);
  return bytes;
}

async function verifiedPackage() {
  const expected = expectedSha256();
  prepareCache();
  if (existsSync(packagePath)) {
    if (lstatSync(packagePath).isSymbolicLink()) fail(`cached package must not be a symlink: ${packagePath}`);
    const cached = readFileSync(packagePath);
    if (sha256(cached) === expected) return cached;
    rmSync(packagePath, { force: true });
  }
  process.stderr.write(`dumb-n-honest: fetching verified release v${version}...\n`);
  const downloaded = await downloadPackage();
  const actual = sha256(downloaded);
  if (actual !== expected) {
    fail(`SHA256 mismatch for ${PACKAGE_FILE(version)}: expected ${expected}, got ${actual}. Nothing was executed.`);
  }
  writeFileSync(packagePath, downloaded, { flag: "wx", mode: 0o600 });
  return downloaded;
}

function usage() {
  process.stdout.write(`dumb-n-honest — private local correction-acknowledgment benchmark

Usage:
  dumb-n-honest
  dumb-n-honest doctor [--provider all|claude|codex]
  dumb-n-honest run --output-dir <new-dir> [--provider all|claude|codex] [--languages en,tr] [--no-png] [--require-png] [--github-url <url>]

With no arguments, the audit runs with both providers and both language packs and writes to a new
timestamped dumb-n-honest-output directory in the current working directory.

Requires Python 3.10+ and local Claude Code or Codex history.
The launcher downloads a pinned release once and verifies its SHA256 before every run.
The verified release is extracted to a fresh temporary directory and removed after execution.
The audit itself makes no network requests and publishes nothing automatically.

Environment:
  DUMB_N_HONEST_VERSION    pinned release to use (default: ${DEFAULT_VERSION})
  DUMB_N_HONEST_BASE_URL   release mirror (default: ${DEFAULT_BASE_URL})
  DUMB_N_HONEST_CACHE_DIR  package cache location
`);
}

function defaultOutputDirectory(baseDirectory = process.cwd(), now = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  const timestamp = [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
    "-",
    pad(now.getHours()),
    pad(now.getMinutes()),
    pad(now.getSeconds()),
  ].join("");
  const baseName = `dumb-n-honest-output-${timestamp}`;
  let candidate = join(baseDirectory, baseName);
  let suffix = 2;
  while (existsSync(candidate)) {
    candidate = join(baseDirectory, `${baseName}-${suffix}`);
    suffix += 1;
  }
  return candidate;
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.includes("-h") || argv.includes("--help")) {
    usage();
    return 0;
  }
  const python = resolvePython();
  if (!python) fail("Python 3.10 or newer is required but was not found on PATH.");
  const packageBytes = await verifiedPackage();
  const executionRoot = mkdtempSync(join(tmpdir(), "dumb-n-honest-run-"));
  try {
    const executionPackage = join(executionRoot, PACKAGE_FILE(version));
    writeFileSync(executionPackage, packageBytes, { mode: 0o600 });
    const extract = spawnSync(
      python[0],
      [...python[1], "-m", "zipfile", "-e", executionPackage, executionRoot],
      { encoding: "utf8", windowsHide: true },
    );
    if (extract.error || extract.status !== 0) fail("the verified package could not be extracted with your Python installation.");
    const skillRoot = join(executionRoot, "dumb-n-honest");
    let script;
    let rest;
    if (argv.length === 0) {
      const outputDirectory = defaultOutputDirectory();
      process.stderr.write(`dumb-n-honest: running audit; output directory: ${outputDirectory}\n`);
      script = join(skillRoot, "scripts", "run.py");
      rest = ["--output-dir", outputDirectory];
    } else if (argv[0] === "doctor") {
      script = join(skillRoot, "scripts", "doctor.py");
      rest = argv.slice(1);
    } else if (argv[0] === "run" || argv[0].startsWith("--")) {
      script = join(skillRoot, "scripts", "run.py");
      rest = argv[0] === "run" ? argv.slice(1) : argv;
    } else {
      usage();
      return 1;
    }
    if (!existsSync(script) || !statSync(script).isFile()) fail(`missing script ${script}`);
    const result = spawnSync(python[0], [...python[1], script, ...rest], { stdio: "inherit", windowsHide: true });
    if (result.error) fail(`could not launch Python: ${result.error.message}`);
    return result.status === null ? 1 : result.status;
  } finally {
    rmSync(executionRoot, { recursive: true, force: true });
  }
}

if (require.main === module) {
  main()
    .then((status) => {
      process.exitCode = status;
    })
    .catch((error) => {
      process.stderr.write(`dumb-n-honest: ${error && error.message ? error.message : String(error)}\n`);
      process.exitCode = 1;
    });
}

module.exports = { defaultOutputDirectory };
