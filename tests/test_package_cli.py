from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.package import included_files, skill_version
from scripts.scan import TOOL_VERSION


ROOT = Path(__file__).resolve().parents[1]


class PackageCliTests(unittest.TestCase):
    def test_scanner_and_skill_versions_match(self) -> None:
        self.assertEqual(skill_version(), TOOL_VERSION)

    def test_release_tag_must_match_skill_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "wrong-tag.skill"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "package.py"),
                    "--check-tag",
                    "v9.9.9",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            output_created = output.exists()

        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(output_created)

    def test_package_is_deterministic_minimal_and_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            first = temp / "first.skill"
            second = temp / "second.skill"
            for output in (first, second):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "package.py"),
                        "--output",
                        str(output),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertIn("dumb-n-honest/SKILL.md", names)
                self.assertIn("dumb-n-honest/scripts/run.py", names)
                self.assertIn("dumb-n-honest/scripts/doctor.py", names)
                self.assertFalse(any("/.git" in name or "/tests/" in name for name in names))
                archive.extractall(temp / "extracted")

            skill = temp / "extracted" / "dumb-n-honest"
            output = temp / "smoke-output"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(skill / "scripts" / "run.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(ROOT / "tests" / "fixtures" / "claude_owned_en"),
                    "--output-dir",
                    str(output),
                    "--no-png",
                ],
                cwd=skill,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "results.json").is_file())
            self.assertTrue((output / "tweet.txt").is_file())

    def test_package_rejects_symlinked_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("SKILL.md", "README.md", "LICENSE"):
                (root / name).write_text(name, encoding="utf-8")
            for directory in ("agents", "assets", "patterns", "references", "scripts"):
                (root / directory).mkdir()
            target = root / "outside.txt"
            target.write_text("private", encoding="utf-8")
            link = root / "scripts" / "leak.txt"
            try:
                link.symlink_to(target)
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")

            with patch("scripts.package.SKILL_ROOT", root):
                with self.assertRaisesRegex(SystemExit, "must not contain symlinks"):
                    included_files()


if __name__ == "__main__":
    unittest.main()
