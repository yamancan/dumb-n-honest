from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import shutil
import struct
from pathlib import Path
from unittest.mock import patch

from scripts.report import (
    DEFAULT_BENCHMARK_URL,
    build_alt_text,
    build_tweet,
    friendly_model,
    render_png,
    selected_models,
)


ROOT = Path(__file__).resolve().parents[1]


class ReportCliTests(unittest.TestCase):
    def test_png_viewport_matches_the_measured_poster_height(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            poster = root / "poster.html"
            poster.write_text("synthetic poster", encoding="utf-8")
            output = root / "poster.png"

            def browser_run(args, **kwargs):
                if "--dump-dom" in args:
                    return subprocess.CompletedProcess(args, 0, '<html data-poster-height="1832"></html>')
                if "--window-size=1080,1832" in args:
                    output.write_bytes(b"synthetic screenshot")
                    return subprocess.CompletedProcess(args, 0)
                return subprocess.CompletedProcess(args, 1)

            with patch("scripts.report.find_browser", return_value=Path("synthetic-browser")), patch("scripts.report.subprocess.run", side_effect=browser_run):
                render_png(poster, output)
            self.assertTrue(output.is_file())

    def test_social_preview_asset_is_self_contained_and_current(self) -> None:
        html = (ROOT / "assets" / "social-preview.html").read_text(encoding="utf-8")
        png = (ROOT / "assets" / "social-preview.png").read_bytes()

        self.assertIn("width:1280px", html)
        self.assertIn("height:640px", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("npx dumb-n-honest", html)
        self.assertIn("github.com/yamancan/dumb-n-honest", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("https://", html)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (1280, 640))

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
        self.assertNotIn("English + Turkish", html)
        self.assertIn("Claude Opus 5", html)
        self.assertIn("Claude Opus 4.8", html)
        self.assertIn("Codex GPT-5.6 Sol", html)
        self.assertIn("Codex GPT-5.5", html)
        self.assertNotIn("Codex gpt-5.5", html)
        self.assertNotIn("Claude Fable 5", html)
        self.assertIn("1 additional low-sample model omitted", html)
        self.assertIn("Correction acknowledgments / 100 answered turns", html)
        self.assertIn("I was wrong", html)
        self.assertIn("You’re right", html)
        self.assertIn("5.00 owned", html)
        self.assertIn("3.00 conceded", html)
        self.assertIn('class="bar-owned" style="width:62.500%"', html)
        self.assertIn('class="bar-conceded" style="width:37.500%"', html)
        self.assertIn("Higher ≠ worse", html)
        self.assertIn("not model error rate", html)
        self.assertIn("Run yours locally", html)
        self.assertIn("npx dumb-n-honest", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertNotIn("answered-turn share", html)
        self.assertNotIn("reasoning tokens", html)
        self.assertNotIn("2026-01-01", html)
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertNotIn("<script src=", html)
        self.assertLessEqual(len(tweet), 280)
        self.assertIn("I counted “you're right” across 3,850 turns", tweet)
        self.assertIn("Opus 5 · 8.00", tweet)
        self.assertIn("Codex 5.6 Sol · 3.00", tweet)
        self.assertNotIn("5.00+3.00", tweet)
        self.assertNotIn("—", tweet)
        self.assertIn("🖤 owned + 🟠 conceded", tweet)
        self.assertIn("not error rate", tweet)
        self.assertIn("⚠️", tweet)
        self.assertIn("▶ Run yours locally: npx dumb-n-honest", tweet)
        self.assertIn("https://github.com/example/dumb-n-honest", tweet)
        self.assertIn("https://github.com/example/dumb-n-honest", html)
        self.assertLessEqual(len(alt_text), 1000)
        self.assertIn("Claude Opus 5", alt_text)
        self.assertIn("Codex GPT-5.6 Sol", alt_text)
        self.assertIn("5.00 owned and 3.00 conceded per 100 turns", alt_text)
        self.assertIn("Run yours locally with npx dumb-n-honest", alt_text)
        self.assertIn("https://github.com/example/dumb-n-honest", alt_text)

    def test_provider_balancing_keeps_codex_visible(self) -> None:
        def model(model_id: str, turns: int) -> dict[str, object]:
            return {
                "model_id": model_id,
                "answered_human_turns": turns,
                "acknowledged_correction": {
                    "count": 10,
                    "per_100_turns": 1.0,
                    "wilson_95_pct": {"low": 0.5, "high": 1.5},
                    "sample_status": "sample-sufficient",
                },
                "owned_error": {"count": 4, "per_100_turns": 0.4},
                "conceded": {"count": 6, "per_100_turns": 0.6},
            }

        result = {
            "providers": {
                "claude": {
                    "models": [model(f"claude-opus-{index}", 1000 - index) for index in range(7)]
                },
                "codex": {"models": [model("gpt-5.6-sol", 5000)]},
            }
        }
        models, omitted = selected_models(result)

        self.assertEqual(sum(provider == "claude" for provider, _ in models), 7)
        self.assertEqual(sum(provider == "codex" for provider, _ in models), 1)
        claude_ids = [model["model_id"] for provider, model in models if provider == "claude"]
        self.assertTrue(all(model_id.startswith("claude-opus-") for model_id in claude_ids[:2]))
        self.assertEqual(omitted, 0)
        self.assertIn("Codex 5.6 Sol", build_tweet(models, None))
        self.assertIn(DEFAULT_BENCHMARK_URL, build_tweet(models, None))
        self.assertNotIn("models omitted", build_alt_text(models, omitted))

    def test_poster_includes_sol_6_1_beyond_the_first_three_codex_models(self) -> None:
        result = json.loads((ROOT / "tests" / "fixtures" / "results" / "report.json").read_text(encoding="utf-8"))
        template = result["providers"]["codex"]["models"][0]
        result["providers"]["codex"]["models"] = [
            {**template, "model_id": model_id, "answered_human_turns": turns}
            for model_id, turns in (
                ("gpt-5.6-sol", 3471),
                ("gpt-6-sol", 926),
                ("gpt-6-astra", 910),
                ("gpt-6.1-sol", 507),
                ("gpt-5.4-mini", 99),
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "result.json"
            source.write_text(json.dumps(result), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "report.py"), "--input", str(source), "--output-dir", str(root / "share"), "--no-png"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            poster = (root / "share" / "poster.html").read_text(encoding="utf-8")
        self.assertIn("Codex GPT-6.1 Sol", poster)
        self.assertNotIn("Codex GPT-5.4 Mini", poster)
        self.assertIn("2 additional low-sample models omitted", poster)

    def test_quarantined_turns_are_disclosed_in_every_share_artifact(self) -> None:
        source = ROOT / "tests" / "fixtures" / "results" / "report.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            result = json.loads(source.read_text(encoding="utf-8"))
            result["quality"]["provider_status"]["codex"] = "OK_WITH_WARNINGS"
            result["providers"]["codex"]["diagnostics"].update(
                {
                    "quarantined_model_turns": 4,
                    "quarantined_model_turn_share_pct": 0.19,
                }
            )
            input_path = temp / "result.json"
            input_path.write_text(json.dumps(result), encoding="utf-8")
            output_dir = temp / "share"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "report.py"),
                    "--input",
                    str(input_path),
                    "--output-dir",
                    str(output_dir),
                    "--no-png",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            poster = (output_dir / "poster.html").read_text(encoding="utf-8")
            tweet = (output_dir / "tweet.txt").read_text(encoding="utf-8")
            alt_text = (output_dir / "alt-text.txt").read_text(encoding="utf-8")

        self.assertIn("Codex: 4 turns excluded (unknown model, 0.19%)", poster)
        self.assertIn("4 unattributed turns were excluded", tweet)
        self.assertLessEqual(len(tweet.strip()), 280)
        self.assertIn("Codex: 4 turns excluded (unknown model, 0.19%)", alt_text)

    def test_known_fable_and_codex_variants_get_clean_labels(self) -> None:
        self.assertEqual(
            friendly_model("claude", "claude-fable-4-2-20260801"),
            "Claude Fable 4.2 20260801",
        )
        self.assertEqual(friendly_model("codex", "gpt-5.6-terra"), "Codex GPT-5.6 Terra")

    def test_report_keeps_the_share_pack_when_png_is_blocked(self) -> None:
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
            png_path = Path(output_dir) / "poster.png"
            html_path = Path(output_dir) / "poster.html"
            if png_path.is_file():
                png = png_path.read_bytes()
                self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                width, height = struct.unpack(">II", png[16:24])
                self.assertEqual((width, height), (1080, 1350))
            else:
                self.assertTrue(html_path.is_file())
                self.assertIn("warning:", completed.stderr)

    def test_report_refuses_results_that_failed_quality_gates(self) -> None:
        source = ROOT / "tests" / "fixtures" / "results" / "report.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            result = json.loads(source.read_text(encoding="utf-8"))
            result["quality"] = {"shareable": False}
            input_path = temp / "result.json"
            input_path.write_text(json.dumps(result), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "report.py"),
                    "--input",
                    str(input_path),
                    "--output-dir",
                    str(temp / "share"),
                    "--no-png",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("quality checks failed", completed.stderr)

    def test_report_refuses_missing_quality_metadata(self) -> None:
        source = ROOT / "tests" / "fixtures" / "results" / "report.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            result = json.loads(source.read_text(encoding="utf-8"))
            result.pop("quality")
            input_path = temp / "result.json"
            input_path.write_text(json.dumps(result), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "report.py"),
                    "--input",
                    str(input_path),
                    "--output-dir",
                    str(temp / "share"),
                    "--no-png",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("quality checks failed", completed.stderr)


if __name__ == "__main__":
    unittest.main()
