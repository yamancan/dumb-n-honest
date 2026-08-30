from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PrivacyTests(unittest.TestCase):
    def test_scan_outputs_only_aggregates(self) -> None:
        canaries = (
            "private.person@example.invalid",
            "sk-private-canary-123456",
            "secret-project-canary",
            "synthetic-private-session-id",
            "private reply remainder",
        )
        with tempfile.TemporaryDirectory(prefix="secret-project-canary-") as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "projects" / "private" / "session.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {
                    "type": "user",
                    "sessionId": "synthetic-private-session-id",
                    "message": {
                        "role": "user",
                        "content": "Email private.person@example.invalid; token sk-private-canary-123456",
                    },
                },
                {
                    "type": "assistant",
                    "requestId": "synthetic-private-session-id",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-5",
                        "content": [
                            {
                                "type": "text",
                                "text": "I was wrong. private reply remainder",
                            }
                        ],
                    },
                },
            ]
            session.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            output = fixture_root / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            emitted = output.read_text(encoding="utf-8") + completed.stdout + completed.stderr

        for canary in canaries:
            with self.subTest(canary=canary):
                self.assertNotIn(canary, emitted)

    @unittest.skipIf(os.name == "nt", "POSIX directory modes only")
    def test_scan_does_not_change_permissions_on_an_existing_parent_directory(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "claude_owned_en"
        with tempfile.TemporaryDirectory() as output_dir:
            parent = Path(output_dir)
            parent.chmod(0o755)
            output = parent / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            mode = stat.S_IMODE(parent.stat().st_mode)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(mode, 0o755)

    def test_scan_refuses_to_overwrite_an_existing_output_file(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "claude_owned_en"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            output.write_text("keep", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            content = output.read_text(encoding="utf-8")

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(content, "keep")
