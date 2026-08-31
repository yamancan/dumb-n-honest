#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from package import SKILL_ROOT, included_files


def default_destination(target: str) -> Path:
    base = ".claude" if target == "claude" else ".codex"
    return Path.home() / base / "skills" / "dumb-n-honest"


def claude_frontmatter(text: str) -> str:
    if re.search(r"(?m)^disable-model-invocation:\s*true\s*$", text):
        return text
    match = re.search(r"(?m)^description:.*$", text)
    if not match:
        raise SystemExit("Portable SKILL.md has no description field.")
    return text[: match.end()] + "\ndisable-model-invocation: true" + text[match.end() :]


def install(target: str, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise SystemExit("Install destination already exists; nothing was overwritten.")
    destination.mkdir(parents=True, mode=0o700)
    try:
        for source in included_files():
            relative = source.relative_to(SKILL_ROOT)
            target_path = destination / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if relative.as_posix() == "SKILL.md" and target == "claude":
                target_path.write_text(
                    claude_frontmatter(source.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
            else:
                shutil.copy2(source, target_path)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    print(destination)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install dumb-n-honest for local Codex or Claude Code use."
    )
    parser.add_argument("--target", choices=("codex", "claude"), required=True)
    parser.add_argument("--dest", type=Path)
    args = parser.parse_args()
    install(args.target, args.dest or default_destination(args.target))


if __name__ == "__main__":
    try:
        main()
    except OSError:
        raise SystemExit("The skill could not be installed at the selected destination.") from None
