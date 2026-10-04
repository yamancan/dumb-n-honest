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


def force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


force_utf8_output()


def friendly_summary(results_path: Path, output_dir: Path) -> str | None:
    result = json.loads(results_path.read_text(encoding="utf-8"))
    providers = []
    total_turns = 0
    for provider in ("claude", "codex"):
        provider_result = result.get("providers", {}).get(provider, {})
        turns = 0
        for model in provider_result.get("models", []):
            turns += int(model.get("answered_human_turns") or 0)
        total_turns += turns
        if turns:
            providers.append(f"{PROVIDER_LABEL[provider]}: {turns:,} answered turns")
    if not providers:
        return None
    lines = [
        f"Audit complete: {total_turns:,} answered turns.",
        *providers,
        "",
        "🖤 “I was wrong” (owned) + 🟠 “You're right” (conceded).",
        "⚠️ Your personal workload, not a model error rate.",
    ]
    for label, filename in (
        ("Open your audit workspace", "report.html"),
        ("Ready-to-share chart", "chart.png"),
        ("Post for Twitter/X", "tweet.txt"),
        ("Image with the chart", "poster.png"),
        ("Chart description (alt text)", "alt-text.txt"),
        ("Full private results", "results.json"),
    ):
        path = output_dir / filename
        if path.is_file():
            lines.append(f"📄 {label}: {path}")
    lines.append("The workspace contains the chart, editable draft, description and downloads.")
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
        description="Run the private local audit and build one offline report workspace."
    )
    parser.add_argument("--provider", choices=("all", "claude", "codex"), default="all")
    parser.add_argument("--claude-root", type=Path, default=Path.home() / ".claude")
    parser.add_argument("--codex-root", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--languages", default="en,tr")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-url")
    parser.add_argument("--no-png", action="store_true")
    parser.add_argument("--require-png", action="store_true")
    parser.add_argument("--export-share-pack", action="store_true", help="Also export separate poster, draft and alt-text files.")
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
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if scan.returncode != 0:
        raise SystemExit("The local transcript scan failed; no raw transcript content was emitted.")
    print("Scan complete; building report workspace.", file=sys.stderr, flush=True)

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
    if args.export_share_pack:
        report_command.append("--export-share-pack")
    report = subprocess.run(
        report_command,
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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
