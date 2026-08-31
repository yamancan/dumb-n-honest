from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DoctorCliTests(unittest.TestCase):
    def test_doctor_reports_counts_without_reading_content(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "claude_owned_en"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "doctor.py"),
                "--provider",
                "claude",
                "--claude-root",
                str(fixture),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("claude\t1\tok", completed.stdout)
        self.assertNotIn("I was wrong", completed.stdout)
        self.assertRegex(
            completed.stdout,
            r"png-browser\t(?:detected-may-require-approval|optional-missing)",
        )

    def test_doctor_fails_when_no_selected_history_exists(self) -> None:
        with tempfile.TemporaryDirectory() as empty_root:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "doctor.py"),
                    "--provider",
                    "codex",
                    "--codex-root",
                    empty_root,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("codex\t0\tno-jsonl", completed.stdout)


if __name__ == "__main__":
    unittest.main()
