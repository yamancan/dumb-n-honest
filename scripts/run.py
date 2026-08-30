#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


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
    args = parser.parse_args()

    prepare_output_directory(args.output_dir)
    results = args.output_dir / "results.json"
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
    report = subprocess.run(
        report_command,
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if report.returncode != 0:
        raise SystemExit("Share-pack rendering failed; aggregate results.json was preserved.")

    print(scan.stdout, end="")
    print(report.stdout, end="")


if __name__ == "__main__":
    try:
        main()
    except OSError:
        raise SystemExit("The output directory could not be created or written.") from None
