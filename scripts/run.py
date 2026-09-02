#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]

PROVIDER_BADGE = {"claude": "🤖", "codex": "🧮"}
PROVIDER_LABEL = {"claude": "Claude Code", "codex": "Codex"}


def friendly_summary(results_path: Path, output_dir: Path) -> str | None:
    result = json.loads(results_path.read_text(encoding="utf-8"))
    headline = []
    total_turns = 0
    for provider in ("claude", "codex"):
        provider_result = result.get("providers", {}).get(provider, {})
        best = None
        for model in provider_result.get("models", []):
            total_turns += int(model.get("answered_human_turns") or 0)
            ack = model.get("acknowledged_correction") or {}
            rate = float(ack.get("per_100_turns") or 0)
            if best is None or rate > best[1]:
                best = (model.get("model_id", ""), rate, ack.get("sample_status", ""))
        if best:
            display = str(best[0])
            if provider == "claude" and display.startswith("claude-"):
                display = display.removeprefix("claude-").replace("-", " ").title()
            elif provider == "codex" and display.startswith("gpt-"):
                display = "GPT-" + display[4:].replace("-", " ").title()
            headline.append(f"{PROVIDER_BADGE[provider]} {display}: {best[1]:.2f}/100 {best[2]}")
    if not headline:
        return None
    lines = [
        "✅ Audit complete — here's your summary!",
        "Correction acknowledgments per 100 turns:",
        *headline,
        "",
        "🖤 “I was wrong” (owned) + 🟠 “You're right” (conceded).",
        "⚠️ Your personal workload, not a model error rate.",
    ]
    for label, filename in (
        ("Post for Twitter/X", "tweet.txt"),
        ("Image with the chart", "poster.png"),
        ("Chart description (alt text)", "alt-text.txt"),
        ("Full private results", "results.json"),
    ):
        path = output_dir / filename
        if path.is_file():
            lines.append(f"📄 {label}: {path}")
    lines.append("▶ Share these from the folder above, or run it on your own machine with: npx dumb-n-honest")
    return "\n".join(lines)


def prepare_output_directory(path: Path) -> None:
    if path.is_symlink():
        raise OSError
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise OSError
    else:
        path.mkdir(parents=True)
    path.chmod(0o700)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the private local audit and build its share pack."
    )
    parser.add_argument("--provider", choices=("all", "claude", "codex"), default="all")
    parser.add_argument("--claude-root", type=Path, default=Path.home() / ".claude")
    parser.add_argument("--codex-root", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--languages", default="en,tr")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-url")
    parser.add_argument("--no-png", action="store_true")
    parser.add_argument("--require-png", action="store_true")
    args = parser.parse_args()

    if args.no_png and args.require_png:
        parser.error("--no-png and --require-png cannot be combined")

    prepare_output_directory(args.output_dir)
    results = args.output_dir / "results.json"
    print(
        "Scanning local history; large archives may take 1–2 minutes.",
        file=sys.stderr,
        flush=True,
    )
    scan = subprocess.run(
        [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "scan.py"),
            "--provider",
            args.provider,
            "--claude-root",
            str(args.claude_root),
            "--codex-root",
            str(args.codex_root),
            "--languages",
            args.languages,
            "--output",
            str(results),
        ],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if scan.returncode != 0:
        raise SystemExit("The local transcript scan failed; no raw transcript content was emitted.")
    print("Scan complete; building share pack.", file=sys.stderr, flush=True)

    report_command = [
        sys.executable,
        str(SKILL_ROOT / "scripts" / "report.py"),
        "--input",
        str(results),
        "--output-dir",
        str(args.output_dir),
    ]
    if args.github_url:
        report_command.extend(("--github-url", args.github_url))
    if args.no_png:
        report_command.append("--no-png")
    if args.require_png:
        report_command.append("--require-png")
    report = subprocess.run(
        report_command,
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if report.returncode != 0:
        if report.stderr:
            print(report.stderr, end="", file=sys.stderr)
        raise SystemExit("Aggregate results.json was preserved; no share pack was generated.")

    print(scan.stdout, end="")
    print(report.stdout, end="")
    if report.stderr:
        print(report.stderr, end="", file=sys.stderr)

    summary = friendly_summary(results, args.output_dir)
    if summary:
        print("\n" + summary, end="", file=sys.stderr)
        print(file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except OSError:
        raise SystemExit("The output directory could not be created or written.") from None
