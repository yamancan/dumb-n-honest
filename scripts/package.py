#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
INCLUDED_ROOT_FILES = ("SKILL.md", "README.md", "LICENSE")
INCLUDED_DIRECTORIES = ("agents", "assets", "patterns", "references", "scripts")


def skill_version() -> str:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r'^\s*version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)', text, re.MULTILINE)
    if not match:
        raise SystemExit("SKILL.md does not contain a semantic metadata version.")
    return match.group(1)


def included_files() -> list[Path]:
    files = []
    for name in INCLUDED_ROOT_FILES:
        path = SKILL_ROOT / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Package source must be a regular file: {name}")
        files.append(path)
    for directory in INCLUDED_DIRECTORIES:
        source_root = SKILL_ROOT / directory
        if source_root.is_symlink() or not source_root.is_dir():
            raise SystemExit(f"Package source must be a regular directory: {directory}")
        for path in source_root.rglob("*"):
            if path.is_symlink():
                relative = path.relative_to(SKILL_ROOT).as_posix()
                raise SystemExit(f"Package source must not contain symlinks: {relative}")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(SKILL_ROOT).as_posix())


def write_package(output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise SystemExit("Package output already exists; nothing was overwritten.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in included_files():
            relative = Path("dumb-n-honest") / path.relative_to(SKILL_ROOT)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if path.suffix == ".py" else 0o644) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    output.chmod(0o644)
    print(output)


def main() -> None:
    version = skill_version()
    parser = argparse.ArgumentParser(description="Build a deterministic dumb-n-honest skill bundle.")
    parser.add_argument(
        "--check-tag",
        help="Refuse packaging unless this release tag equals the SKILL.md version.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SKILL_ROOT / "dist" / f"dumb-n-honest-v{version}.skill",
    )
    args = parser.parse_args()
    if args.check_tag is not None and args.check_tag != f"v{version}":
        parser.error(f"release tag must be v{version}")
    write_package(args.output)


if __name__ == "__main__":
    main()
