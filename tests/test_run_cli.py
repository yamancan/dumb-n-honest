from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RunCliTests(unittest.TestCase):
    def test_one_command_scans_and_writes_the_share_pack(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_owned_tr"
        with tempfile.TemporaryDirectory() as output_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output-dir",
                    output_dir,
                    "--no-png",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = Path(output_dir)
            self.assertTrue((output / "results.json").is_file())
            self.assertTrue((output / "poster.html").is_file())
            self.assertTrue((output / "tweet.txt").is_file())
            self.assertTrue((output / "alt-text.txt").is_file())
            self.assertIn(
                "correction acknowledgments",
                (output / "tweet.txt").read_text(encoding="utf-8"),
            )
            result = json.loads((output / "results.json").read_text(encoding="utf-8"))

        model = result["providers"]["claude"]["models"][0]
        self.assertEqual(model["owned_error"]["by_language"], {"tr": 1})
        self.assertNotIn("Haklısın", completed.stdout)
        self.assertEqual(model["acknowledged_correction"]["count"], 1)

    def test_incomplete_scan_keeps_private_results_but_refuses_share_pack(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir, tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "projects" / "demo" / "malformed.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                "not-json\n"
                '{"type":"user","message":{"role":"user","content":"Synthetic"}}\n'
                '{"type":"assistant","message":{"role":"assistant","model":"claude-opus-5",'
                '"content":[{"type":"text","text":"You are right."}]}}\n',
                encoding="utf-8",
            )
            output = Path(temp_dir) / "audit"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--output-dir",
                    str(output),
                    "--no-png",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue((output / "results.json").is_file())
            self.assertFalse((output / "poster.html").exists())
            self.assertIn("Scanning local history", completed.stderr)
            self.assertIn("Scan complete", completed.stderr)
            self.assertIn("malformed_records=1", completed.stderr)
            self.assertIn("Aggregate results.json was preserved", completed.stderr)

    def test_failures_do_not_echo_private_output_paths_or_tracebacks(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_owned_tr"
        with tempfile.TemporaryDirectory(prefix="private-output-canary-") as temp_dir:
            output_path = Path(temp_dir) / "already-a-file"
            output_path.write_text("occupied", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--output-dir",
                    str(output_path),
                    "--no-png",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("private-output-canary", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_existing_nonempty_output_directory_is_never_overwritten(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_owned_tr"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "prior-audit"
            output_path.mkdir()
            marker = output_path / "keep-me.txt"
            marker.write_text("original", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--output-dir",
                    str(output_path),
                    "--no-png",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "original")
            self.assertFalse((output_path / "results.json").exists())


if __name__ == "__main__":
    unittest.main()
