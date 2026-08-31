from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.scan import safe_effort, safe_model_id


ROOT = Path(__file__).resolve().parents[1]


class PrivacyTests(unittest.TestCase):
    def test_model_and_effort_allowlists_are_provider_specific(self) -> None:
        self.assertEqual(
            safe_model_id("claude", "claude-fable-4-2-20260801", "redacted"),
            "claude-fable-4-2-20260801",
        )
        self.assertEqual(
            safe_model_id("codex", "gpt-5.6-terra", "redacted"),
            "gpt-5.6-terra",
        )
        self.assertEqual(
            safe_model_id("claude", "claude-opus-5-secret-project", "redacted"),
            "redacted",
        )
        self.assertEqual(
            safe_model_id("codex", "gpt-5.6-private-path", "redacted"),
            "redacted",
        )
        self.assertEqual(
            safe_model_id("codex", "gpt-5.3-codex-spark", "redacted"),
            "gpt-5.3-codex-spark",
        )
        self.assertEqual(
            safe_model_id("codex", "codex-auto-review", "redacted"),
            "codex-auto-review",
        )
        self.assertEqual(
            safe_model_id("codex", "gpt-5.3-codex-spark-private-client", "redacted"),
            "redacted",
        )
        self.assertEqual(
            safe_model_id("codex", "gpt-" + "1" * 100, "redacted"),
            "redacted",
        )
        self.assertEqual(safe_effort("ultra"), "ultra")
        self.assertEqual(safe_effort("ultra-secret"), "missing")

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

    def test_untrusted_model_and_effort_fields_cannot_leak_text(self) -> None:
        model_canary = "claude-opus-5-secret-project-canary"
        effort_canary = "ultra-secret"
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "projects" / "private" / "session.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {"type": "user", "message": {"role": "user", "content": "Synthetic"}},
                {
                    "type": "assistant",
                    "effort": effort_canary,
                    "message": {
                        "role": "assistant",
                        "model": model_canary,
                        "content": [{"type": "text", "text": "You're right."}],
                    },
                },
            ]
            session.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
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
            result = json.loads(output.read_text(encoding="utf-8"))

        self.assertNotIn(model_canary, emitted)
        self.assertNotIn(effort_canary, emitted)
        provider = result["providers"]["claude"]
        self.assertEqual(provider["models"], [])
        self.assertEqual(provider["diagnostics"]["quarantined_model_turns"], 1)
        self.assertEqual(provider["diagnostics"]["quarantined_model_turn_share_pct"], 100.0)
        self.assertEqual(provider["diagnostics"]["status"], "INCOMPLETE")
        self.assertFalse(result["quality"]["shareable"])
