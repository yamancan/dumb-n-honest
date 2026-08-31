from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallCliTests(unittest.TestCase):
    def test_provider_specific_installation_is_explicit_only(self) -> None:
        source_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("disable-model-invocation", source_skill.split("---", 2)[1])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            codex = temp / "codex-skill"
            claude = temp / "claude-skill"
            for target, destination in (("codex", codex), ("claude", claude)):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "install.py"),
                        "--target",
                        target,
                        "--dest",
                        str(destination),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

            codex_skill = (codex / "SKILL.md").read_text(encoding="utf-8")
            claude_skill = (claude / "SKILL.md").read_text(encoding="utf-8")
            openai_yaml = (codex / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertNotIn("disable-model-invocation: true", codex_skill)
        self.assertIn("allow_implicit_invocation: false", openai_yaml)
        self.assertIn("disable-model-invocation: true", claude_skill)

    def test_installer_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "existing"
            destination.mkdir()
            marker = destination / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "install.py"),
                    "--target",
                    "codex",
                    "--dest",
                    str(destination),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
