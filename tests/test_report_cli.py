from __future__ import annotations

import json
import base64
import re
import subprocess
import sys
import tempfile
import unittest
import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from scripts.report import (
    DEFAULT_BENCHMARK_URL,
    build_alt_text,
    build_chart_svg,
    build_rows,
    build_tweet,
    friendly_model,
    model_family_and_version,
    render_png,
    selected_models,
)


ROOT = Path(__file__).resolve().parents[1]


class ReportCliTests(unittest.TestCase):
    def test_zero_acknowledgment_rate_does_not_look_like_zero_usage(self) -> None:
        result = json.loads((ROOT / "tests" / "fixtures" / "results" / "report.json").read_text(encoding="utf-8"))
        model = result["providers"]["claude"]["models"][2]
        model["answered_human_turns"] = 2
        for metric in ("owned_error", "conceded", "acknowledged_correction"):
            model[metric]["count"] = 0
            model[metric]["per_100_turns"] = 0.0
        models = [("claude", model)]
        rows = build_rows(models)
        self.assertIn("Usage: 2 answered turns · 0 acknowledgments", rows)
        self.assertIn("acks /100 turns", rows)
        chart = ET.fromstring(build_chart_svg(models, "Synthetic Fable chart", [], DEFAULT_BENCHMARK_URL))
        texts = [node.text for node in chart.findall(".//{http://www.w3.org/2000/svg}text")]
        self.assertIn("Usage: 2 answered turns · 0 acknowledgments", texts)
        self.assertIn("acks /100 turns", texts)

    def test_default_output_is_one_offline_workspace_with_low_sample_models(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "results" / "report.json"
        result = json.loads(fixture.read_text(encoding="utf-8"))
        result["private_path_canary"] = "/private/project-canary/session-canary"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "result.json"
            source.write_text(json.dumps(result), encoding="utf-8")
            output = root / "output"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "report.py"), "--input", str(source), "--output-dir", str(output)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            expected = {"report.html", "chart.png"} if shutil.which("rsvg-convert") else {"report.html"}
            self.assertEqual({path.name for path in output.iterdir()}, expected)
            workspace = (output / "report.html").read_text(encoding="utf-8")

        self.assertIn("Claude Fable 5", workspace)
        self.assertIn("Low sample", workspace)
        self.assertIn("Codex GPT-5.6 Sol", workspace)
        self.assertIn("Copy draft", workspace)
        self.assertIn("Save page", workspace)
        self.assertIn("Download chart", workspace)
        self.assertIn("Download PNG", workspace)
        self.assertIn('id="family-filter"', workspace)
        self.assertIn('id="older-models"', workspace)
        self.assertIn('class="model-toggle"', workspace)
        self.assertIn("Content-Security-Policy", workspace)
        self.assertNotIn("<script src=", workspace)
        self.assertNotIn("fonts.googleapis.com", workspace)
        self.assertNotIn("private_path_canary", workspace)
        self.assertNotIn("project-canary", workspace)
        self.assertNotIn("@@", workspace)
        chart_match = re.search(r'data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)', workspace)
        self.assertIsNotNone(chart_match)
        chart = ET.fromstring(base64.b64decode(chart_match.group(1)))
        chart_text = " ".join(chart.itertext())
        self.assertIn("Claude Fable 5", chart_text)
        self.assertIn("Low sample", chart_text)
        self.assertIn("Codex GPT-5.5", chart_text)

    @unittest.skipUnless(shutil.which("rsvg-convert"), "No SVG rasterizer installed")
    def test_default_png_is_a_real_share_image_matching_the_default_filters(self) -> None:
        result = json.loads((ROOT / "tests" / "fixtures" / "results" / "report.json").read_text(encoding="utf-8"))
        template = result["providers"]["codex"]["models"][0]
        result["providers"]["codex"]["models"] = [
            {**template, "model_id": model_id}
            for model_id in ("gpt-5.3-codex-spark", "gpt-5.6-sol", "gpt-6-sol", "gpt-6.1-sol")
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "result.json"
            source.write_text(json.dumps(result), encoding="utf-8")
            output = root / "output"
            completed = subprocess.run([sys.executable, str(ROOT / "scripts/report.py"), "--input", str(source), "--output-dir", str(output)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "chart.png").is_file())
            png = (output / "chart.png").read_bytes()
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", png[16:24]), (1080, 1350))
            workspace = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn('data:image/png;base64,' + base64.b64encode(png).decode("ascii"), workspace)
            chart_match = re.search(r'id="download-svg"[^>]*href="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)', workspace)
            self.assertIsNotNone(chart_match)
            chart = ET.fromstring(base64.b64decode(chart_match.group(1)))
            visible_names = [node.text for node in chart.findall(".//{http://www.w3.org/2000/svg}text")]
            self.assertNotIn("Codex GPT-5.3 Codex Spark", visible_names)
            self.assertIn("Codex GPT-6.1 Sol", visible_names)

    def test_old_generations_are_hidden_by_default_but_available_to_filters(self) -> None:
        result = json.loads((ROOT / "tests" / "fixtures" / "results" / "report.json").read_text(encoding="utf-8"))
        template = result["providers"]["codex"]["models"][0]
        result["providers"]["codex"]["models"] = [
            {**template, "model_id": model_id}
            for model_id in ("gpt-5.3-codex-spark", "gpt-5.4-mini", "gpt-5.6-sol", "gpt-6-sol", "gpt-6.1-sol")
        ]
        models, omitted = selected_models(result)
        ids = {model["model_id"] for _, model in models}
        self.assertEqual(ids.intersection({m["model_id"] for m in result["providers"]["codex"]["models"]}), {"gpt-5.6-sol", "gpt-6-sol", "gpt-6.1-sol"})
        self.assertEqual(omitted, 2)

    def test_workspace_filters_change_the_display_and_svg_export(self) -> None:
        if not shutil.which("node"):
            self.skipTest("No Node installed for optional DOM interaction check")
        available = subprocess.run(["node", "-e", "require.resolve('jsdom')"], cwd=ROOT, capture_output=True)
        if available.returncode:
            self.skipTest("No local jsdom; no runtime dependency is required")
        result = json.loads((ROOT / "tests" / "fixtures" / "results" / "report.json").read_text(encoding="utf-8"))
        template = result["providers"]["codex"]["models"][0]
        result["providers"]["codex"]["models"] = [{**template, "model_id": model_id} for model_id in ("gpt-5.3-codex-spark", "gpt-5.6-sol", "gpt-6-sol", "gpt-6.1-sol")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "result.json"
            source.write_text(json.dumps(result), encoding="utf-8")
            output = root / "output"
            generated = subprocess.run([sys.executable, str(ROOT / "scripts/report.py"), "--input", str(source), "--output-dir", str(output), "--no-png"], capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            verified = subprocess.run(["node", str(ROOT / "tests/workspace_filters.cjs")], input=(output / "report.html").read_text(encoding="utf-8"), capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_svg_export_fits_rows_and_preserves_quality_disclosures(self) -> None:
        result = json.loads((ROOT / "tests" / "fixtures" / "results" / "report.json").read_text(encoding="utf-8"))
        models, omitted = selected_models(result)
        notes = ["Codex: 4 turns excluded (unknown model, 0.19%)"]
        description = build_alt_text(models, omitted, notes, max_length=None)
        chart = ET.fromstring(build_chart_svg(models, description, notes, DEFAULT_BENCHMARK_URL))
        ns = {"svg": "http://www.w3.org/2000/svg"}
        visible_texts = chart.findall(".//svg:text", ns)
        self.assertIn(notes[0], [node.text for node in visible_texts])
        self.assertTrue(all(0 <= float(node.attrib["y"]) < int(chart.attrib["height"]) for node in visible_texts))
        for node in chart.findall(".//svg:rect", ns):
            self.assertLessEqual(float(node.attrib.get("x", 0)) + float(node.attrib["width"]), 1080)

    def test_report_rejects_active_link_schemes_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "report.py"), "--input", str(ROOT / "tests" / "fixtures" / "results" / "report.json"), "--output-dir", str(output), "--github-url", "javascript:alert(1)"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output.exists())

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
                    "--export-share-pack",
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
        self.assertIn("Claude Fable 5", html)
        self.assertIn("Low sample", html)
        self.assertNotIn("model omitted", html)
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

    def test_selection_keeps_three_latest_versions_per_family_and_sorts_by_rate(self) -> None:
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

        self.assertEqual(sum(provider == "claude" for provider, _ in models), 3)
        self.assertEqual(sum(provider == "codex" for provider, _ in models), 1)
        claude_ids = [model["model_id"] for provider, model in models if provider == "claude"]
        self.assertEqual(claude_ids, ["claude-opus-6", "claude-opus-5", "claude-opus-4"])
        self.assertEqual(omitted, 4)
        self.assertIn("Codex 5.6 Sol", build_tweet(models, None))
        self.assertIn(DEFAULT_BENCHMARK_URL, build_tweet(models, None))
        self.assertIn("4 older versions omitted", build_alt_text(models, omitted))

    def test_latest_version_selection_is_numeric_and_keeps_low_sample_fable(self) -> None:
        self.assertEqual(model_family_and_version("claude", "claude-opus-5-20260801"), ("opus", (5,)))
        self.assertEqual(model_family_and_version("claude", "claude-opus-5-5-20260801"), ("opus", (5, 5)))
        result = json.loads((ROOT / "tests" / "fixtures" / "results" / "report.json").read_text(encoding="utf-8"))
        template = result["providers"]["codex"]["models"][0]
        result["providers"]["codex"]["models"] = [
            {**template, "model_id": model_id, "answered_human_turns": turns,
             "acknowledged_correction": {**template["acknowledged_correction"], "per_100_turns": rate}}
            for model_id, turns, rate in (
                ("gpt-5.6-sol", 3471, 6.37), ("gpt-6-sol", 926, 4.32),
                ("gpt-6.1-sol", 515, 1.17), ("gpt-6.10-sol", 2, 0.0),
                ("gpt-6-astra", 910, 0.66),
            )
        ]
        models, omitted = selected_models(result)
        ids = [model["model_id"] for _, model in models]
        self.assertNotIn("gpt-5.6-sol", ids)
        self.assertIn("gpt-6.10-sol", ids)
        self.assertIn("gpt-6-astra", ids)
        self.assertIn("claude-fable-5", ids)
        self.assertEqual(omitted, 1)
        self.assertEqual([model["model_id"] for provider, model in models if provider == "codex"],
                         ["gpt-6-sol", "gpt-6.1-sol", "gpt-6-astra", "gpt-6.10-sol"])

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
                [sys.executable, str(ROOT / "scripts" / "report.py"), "--input", str(source), "--output-dir", str(root / "share"), "--export-share-pack", "--no-png"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            poster = (root / "share" / "poster.html").read_text(encoding="utf-8")
        self.assertIn("Codex GPT-6.1 Sol", poster)
        self.assertNotIn("Codex GPT-5.4 Mini", poster)
        self.assertIn("1 older version omitted", poster)
        self.assertIn("Low sample", poster)

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
                    "--export-share-pack",
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
                    "--export-share-pack",
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
