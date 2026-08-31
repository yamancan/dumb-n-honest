#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from report import SKILL_ROOT, find_browser


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the static social preview image.")
    parser.add_argument(
        "--output",
        type=Path,
        default=SKILL_ROOT / "assets" / "social-preview.png",
    )
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("social preview output already exists")
    browser = find_browser()
    if browser is None:
        parser.error("a Chromium-family browser is required")
    source = SKILL_ROOT / "assets" / "social-preview.html"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dnh-social-preview-") as profile_dir:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile_dir}",
            "--run-all-compositor-stages-before-draw",
            "--window-size=1280,640",
            f"--screenshot={args.output}",
            source.resolve().as_uri(),
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
            rendered = completed.returncode == 0
        except subprocess.TimeoutExpired:
            rendered = args.output.is_file()
    if not rendered or not args.output.is_file():
        raise SystemExit("The social preview could not be rendered.")
    args.output.chmod(0o644)
    print(args.output)


if __name__ == "__main__":
    main()
