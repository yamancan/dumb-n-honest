from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReportCliTests(unittest.TestCase):
    def test_report_writes_network_free_html_tweet_and_alt_text(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "results" / "report.json"
        with tempfile.TemporaryDirectory() as output_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "report.py"),
                    "--input",
                    str(fixture),
                    "--output-dir",
                    output_dir,
                    "--no-png",
                    "--github-url",
                    "https://github.com/example/dumb-n-honest",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            html = (Path(output_dir) / "poster.html").read_text(encoding="utf-8")
            tweet = (Path(output_dir) / "tweet.txt").read_text(encoding="utf-8").strip()
            alt_text = (Path(output_dir) / "alt-text.txt").read_text(encoding="utf-8").strip()

        self.assertIn("Dumb n Honest", html)
        self.assertIn("English + Turkish", html)
        self.assertIn("Claude Opus 5", html)
        self.assertIn("Claude Opus 4.8", html)
        self.assertIn("Codex GPT-5.6 Sol", html)
        self.assertIn("Codex GPT-5.5", html)
        self.assertNotIn("Codex gpt-5.5", html)
        self.assertNotIn("Claude Fable 5", html)
        self.assertIn("1 low-sample model omitted", html)
        self.assertIn("admitted, not every mistake", html)
        self.assertIn("25% units · 20% turns", html)
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertNotIn("<script src=", html)
        self.assertLessEqual(len(tweet), 280)
        self.assertIn("explicitly admitted", tweet)
        self.assertIn("not all mistakes", tweet)
        self.assertIn("https://github.com/example/dumb-n-honest", tweet)
        self.assertLessEqual(len(alt_text), 1000)
        self.assertIn("Claude Opus 5", alt_text)
        self.assertIn("Codex GPT-5.6 Sol", alt_text)

    def test_report_renders_an_exact_1080_by_1350_png_when_browser_exists(self) -> None:
        browser_candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        has_browser = any(path.exists() for path in browser_candidates) or any(
            shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser")
        )
        if not has_browser:
            self.skipTest("No local Chromium-family browser")

        fixture = ROOT / "tests" / "fixtures" / "results" / "report.json"
        with tempfile.TemporaryDirectory() as output_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "report.py"),
                    "--input",
                    str(fixture),
                    "--output-dir",
                    output_dir,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            png = (Path(output_dir) / "poster.png").read_bytes()

        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (1080, 1350))


if __name__ == "__main__":
    unittest.main()
