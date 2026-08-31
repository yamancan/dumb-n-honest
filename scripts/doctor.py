#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report import find_browser


def history_count(provider: str, root: Path) -> int:
    if provider == "claude":
        return sum(1 for path in root.glob("projects/**/*.jsonl") if not path.is_symlink())
    return sum(
        1
        for pattern in ("sessions/**/*.jsonl", "archived_sessions/**/*.jsonl")
        for path in root.glob(pattern)
        if not path.is_symlink()
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check local requirements without reading transcript contents."
    )
    parser.add_argument("--provider", choices=("all", "claude", "codex"), default="all")
    parser.add_argument("--claude-root", type=Path, default=Path.home() / ".claude")
    parser.add_argument("--codex-root", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()

    providers = ("claude", "codex") if args.provider == "all" else (args.provider,)
    roots = {"claude": args.claude_root, "codex": args.codex_root}
    available = 0
    print(f"python\t{sys.version_info.major}.{sys.version_info.minor}\tok")
    for provider in providers:
        root = roots[provider]
        files = history_count(provider, root) if root.is_dir() else 0
        status = "ok" if files else ("missing-root" if not root.is_dir() else "no-jsonl")
        available += int(files > 0)
        print(f"{provider}\t{files}\t{status}")
    browser_status = "detected-may-require-approval" if find_browser() else "optional-missing"
    print(f"png-browser\t{browser_status}")
    if not available:
        raise SystemExit("No supported local history files were found.")


if __name__ == "__main__":
    main()
