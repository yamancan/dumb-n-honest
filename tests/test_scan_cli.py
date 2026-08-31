from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScanCliTests(unittest.TestCase):
    def test_claude_english_owned_error_is_counted(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_owned_en"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        model = result["providers"]["claude"]["models"][0]
        self.assertEqual(model["model_id"], "claude-opus-5")
        self.assertEqual(model["answered_human_turns"], 1)
        self.assertEqual(model["owned_error"]["count"], 1)
        self.assertEqual(model["owned_error"]["by_language"], {"en": 1})
        self.assertEqual(model["owned_error"]["per_100_turns"], 100.0)
        self.assertEqual(model["conceded"]["count"], 0)
        self.assertEqual(model["conceded"]["per_100_turns"], 0.0)
        self.assertEqual(model["acknowledged_correction"]["count"], 1)
        self.assertEqual(model["acknowledged_correction"]["per_100_turns"], 100.0)
        self.assertEqual(model["acknowledged_correction"]["sample_status"], "exploratory")
        self.assertEqual(model["answered_turn_share_pct"], 100.0)
        self.assertEqual(model["effort"], {"high": 1})
        self.assertEqual(model["date_range"], {"first": "2026-01-01", "last": "2026-01-01"})
        self.assertEqual(
            model["reasoning"],
            {
                "observed_tokens": 12,
                "tokens_in_covered_answered_turns": 12,
                "covered_units": 1,
                "eligible_units": 1,
                "covered_answered_turns": 1,
                "coverage_pct": 100.0,
                "answered_turn_coverage_pct": 100.0,
                "tokens_per_covered_answered_turn": 12.0,
            },
        )
        diagnostics = result["providers"]["claude"]["diagnostics"]
        self.assertEqual(diagnostics["files_seen"], 1)
        self.assertEqual(diagnostics["files_read"], 1)
        self.assertEqual(diagnostics["malformed_records"], 0)
        self.assertEqual(diagnostics["human_turns_seen"], 1)
        self.assertEqual(diagnostics["answered_turns_included"], 1)
        self.assertEqual(diagnostics["unanswered_or_unattributed_turns"], 0)

    def test_claude_turkish_owned_error_wins_over_concession(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_owned_tr"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        model = result["providers"]["claude"]["models"][0]
        self.assertEqual(model["owned_error"]["count"], 1)
        self.assertEqual(model["owned_error"]["by_language"], {"tr": 1})
        self.assertEqual(model["conceded"]["count"], 0)
        self.assertEqual(model["acknowledged_correction"]["count"], 1)

    def test_english_and_turkish_concessions_stay_separate_from_owned_errors(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_conceded_bilingual"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        model = result["providers"]["claude"]["models"][0]
        self.assertEqual(model["answered_human_turns"], 2)
        self.assertEqual(model["owned_error"]["count"], 0)
        self.assertEqual(model["conceded"]["count"], 2)
        self.assertEqual(model["conceded"]["by_language"], {"en": 1, "tr": 1})
        self.assertEqual(model["acknowledged_correction"]["count"], 2)

    def test_quoted_conditional_code_and_meta_phrases_are_not_events(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_bilingual_negatives"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        model = result["providers"]["claude"]["models"][0]
        self.assertEqual(model["answered_human_turns"], 12)
        self.assertEqual(model["owned_error"]["count"], 0)
        self.assertEqual(model["conceded"]["count"], 0)
        self.assertEqual(model["acknowledged_correction"]["count"], 0)

    def test_documented_english_and_turkish_phrase_families_are_counted(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_bilingual_variants"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        model = result["providers"]["claude"]["models"][0]
        self.assertEqual(model["answered_human_turns"], 23)
        self.assertEqual(model["owned_error"]["count"], 14)
        self.assertEqual(model["owned_error"]["by_language"], {"en": 6, "tr": 8})
        self.assertEqual(
            model["owned_error"]["by_pattern"],
            {
                "en.owned.correct_previous": 1,
                "en.owned.got_wrong": 1,
                "en.owned.incorrect_action": 1,
                "en.owned.mis_verbs": 1,
                "en.owned.missed": 1,
                "en.owned.mistake": 1,
                "tr.owned.gozden_kacirdim": 1,
                "tr.owned.hataliydim": 1,
                "tr.owned.karistirdim": 1,
                "tr.owned.mistake": 2,
                "tr.owned.previous_wrong": 1,
                "tr.owned.take_back": 1,
                "tr.owned.yanlis_action": 1,
            },
        )
        self.assertEqual(model["conceded"]["count"], 6)
        self.assertEqual(model["conceded"]["by_language"], {"en": 2, "tr": 4})
        self.assertEqual(
            model["conceded"]["by_pattern"],
            {
                "en.conceded.thanks_correction": 1,
                "en.conceded.you_are_right": 1,
                "tr.conceded.correct_speaking": 1,
                "tr.conceded.haklisin": 1,
                "tr.conceded.thanks_correction": 1,
                "tr.conceded.uyari_yerinde": 1,
            },
        )
        self.assertEqual(model["soft_concession"]["count"], 2)
        self.assertEqual(
            model["soft_concession"]["by_pattern"],
            {"en.soft.catch": 1, "tr.soft.catch": 1},
        )
        self.assertEqual(model["acknowledged_correction"]["count"], 20)
        self.assertEqual(
            model["acknowledged_correction"]["count"],
            model["owned_error"]["count"] + model["conceded"]["count"],
        )

    def test_only_top_level_human_turns_enter_the_denominator(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_turn_boundaries"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        model = result["providers"]["claude"]["models"][0]
        self.assertEqual(model["answered_human_turns"], 1)
        self.assertEqual(model["owned_error"]["count"], 1)
        self.assertEqual(model["owned_error"]["by_pattern"], {"en.owned.i_was_wrong": 1})

    def test_mixed_model_turn_is_reported_and_excluded(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "claude_mixed_model"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        provider = result["providers"]["claude"]
        self.assertEqual(provider["models"], [])
        self.assertEqual(provider["diagnostics"]["mixed_model_turns"], 1)
        self.assertEqual(provider["diagnostics"]["human_turns_seen"], 1)
        self.assertEqual(provider["diagnostics"]["answered_turns_included"], 0)
        self.assertFalse(result["quality"]["shareable"])

    def test_transcript_symlinks_are_skipped_without_exposing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir, tempfile.TemporaryDirectory() as outside_dir:
            fixture_root = Path(fixture_dir)
            projects = fixture_root / "projects" / "demo"
            projects.mkdir(parents=True)
            valid_record = (
                '{"type":"user","message":{"role":"user","content":"Synthetic"}}\n'
                '{"type":"assistant","message":{"role":"assistant","model":"claude-opus-5",'
                '"content":[{"type":"text","text":"I was wrong."}]}}\n'
            )
            (projects / "valid.jsonl").write_text(valid_record, encoding="utf-8")
            outside = Path(outside_dir) / "outside.jsonl"
            outside.write_text(valid_record, encoding="utf-8")
            (projects / "linked.jsonl").symlink_to(outside)

            output = fixture_root / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        provider = result["providers"]["claude"]
        self.assertEqual(provider["models"][0]["answered_human_turns"], 1)
        self.assertEqual(provider["diagnostics"]["symlinks_skipped"], 1)
        self.assertNotIn(str(outside), completed.stderr)

    def test_codex_uses_the_same_bilingual_categories_and_turn_token_deltas(self) -> None:
        fixture_root = ROOT / "tests" / "fixtures" / "codex_bilingual"
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "codex",
                    "--codex-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))

        model = result["providers"]["codex"]["models"][0]
        self.assertEqual(model["model_id"], "gpt-5.6-sol")
        self.assertEqual(model["answered_human_turns"], 2)
        self.assertEqual(model["owned_error"]["count"], 2)
        self.assertEqual(model["owned_error"]["by_language"], {"en": 1, "tr": 1})
        self.assertEqual(model["conceded"]["count"], 0)
        self.assertEqual(model["effort"], {"ultra": 2})
        self.assertEqual(model["date_range"], {"first": "2026-01-04", "last": "2026-01-05"})
        self.assertEqual(
            model["reasoning"],
            {
                "observed_tokens": 140,
                "tokens_in_covered_answered_turns": 140,
                "covered_units": 2,
                "eligible_units": 2,
                "covered_answered_turns": 2,
                "coverage_pct": 100.0,
                "answered_turn_coverage_pct": 100.0,
                "tokens_per_covered_answered_turn": 70.0,
            },
        )

    def test_partial_claude_reasoning_is_not_presented_as_a_complete_turn_average(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "projects" / "demo" / "partial.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {
                    "type": "user",
                    "timestamp": "2026-01-07T00:00:00Z",
                    "message": {"role": "user", "content": "Synthetic"},
                },
                {
                    "type": "assistant",
                    "requestId": "synthetic-request-1",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-5",
                        "content": [{"type": "text", "text": "I was wrong."}],
                        "usage": {"output_tokens_details": {"thinking_tokens": 10}},
                    },
                },
                {
                    "type": "assistant",
                    "requestId": "synthetic-request-2",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-5",
                        "content": [{"type": "text", "text": "Corrected."}],
                        "usage": {},
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
            reasoning = json.loads(output.read_text(encoding="utf-8"))["providers"]["claude"][
                "models"
            ][0]["reasoning"]

        self.assertEqual(reasoning["observed_tokens"], 10)
        self.assertEqual(reasoning["covered_units"], 1)
        self.assertEqual(reasoning["eligible_units"], 2)
        self.assertEqual(reasoning["coverage_pct"], 50.0)
        self.assertEqual(reasoning["covered_answered_turns"], 0)
        self.assertEqual(reasoning["answered_turn_coverage_pct"], 0.0)
        self.assertEqual(reasoning["tokens_in_covered_answered_turns"], 0)
        self.assertIsNone(reasoning["tokens_per_covered_answered_turn"])

    def test_missing_claude_request_id_reduces_reasoning_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "projects" / "demo" / "missing-request.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {"type": "user", "message": {"role": "user", "content": "Synthetic"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-5",
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
            provider = json.loads(output.read_text(encoding="utf-8"))["providers"]["claude"]

        reasoning = provider["models"][0]["reasoning"]
        self.assertEqual(reasoning["eligible_units"], 1)
        self.assertEqual(reasoning["covered_units"], 0)
        self.assertEqual(reasoning["coverage_pct"], 0.0)
        self.assertEqual(provider["diagnostics"]["assistant_units_missing_request_id"], 1)

    def test_codex_reasoning_counter_reset_is_missing_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "sessions" / "2026" / "reset.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {"type": "session_meta", "payload": {"source": "cli", "id": "reset-session"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "high"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "one"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "Done."}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"reasoning_output_tokens": 100}}}},
                {"type": "event_msg", "payload": {"type": "task_complete"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "high"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "two"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "Done."}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"reasoning_output_tokens": 10}}}},
                {"type": "event_msg", "payload": {"type": "task_complete"}},
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
                    "codex",
                    "--codex-root",
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
            provider = json.loads(output.read_text(encoding="utf-8"))["providers"]["codex"]

        reasoning = provider["models"][0]["reasoning"]
        self.assertEqual(reasoning["observed_tokens"], 100)
        self.assertEqual(reasoning["covered_units"], 1)
        self.assertEqual(reasoning["eligible_units"], 2)
        self.assertEqual(provider["diagnostics"]["reasoning_counter_resets"], 1)

    def test_unknown_schema_is_reported_as_unshareable(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "sessions" / "2026" / "future.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                json.dumps({"type": "event_msg", "payload": {"type": "task_begin_v9"}}) + "\n",
                encoding="utf-8",
            )
            output = fixture_root / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "codex",
                    "--codex-root",
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
            result = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            result["providers"]["codex"]["diagnostics"]["status"],
            "UNSUPPORTED_OR_EMPTY_SCHEMA",
        )
        self.assertFalse(result["quality"]["shareable"])

    def test_excluded_codex_subagent_metadata_does_not_poison_quality(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            sessions = fixture_root / "sessions" / "2026"
            sessions.mkdir(parents=True)
            valid_records = [
                {"type": "session_meta", "payload": {"source": "cli", "id": "top-level"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.6-sol", "effort": "high"},
                },
                {"type": "event_msg", "payload": {"type": "user_message"}},
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "Done."},
                },
                {"type": "event_msg", "payload": {"type": "task_complete"}},
            ]
            subagent_records = [
                {
                    "type": "session_meta",
                    "payload": {"source": {"subagent": "synthetic"}, "id": "child"},
                },
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {
                    "type": "turn_context",
                    "payload": {
                        "model": "gpt-5.6-sol-private-canary",
                        "effort": "private-effort-canary",
                    },
                },
                {"type": "event_msg", "payload": {"type": "user_message"}},
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "Private canary."},
                },
                {"type": "event_msg", "payload": {"type": "task_complete"}},
            ]
            (sessions / "valid.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in valid_records),
                encoding="utf-8",
            )
            (sessions / "subagent.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in subagent_records),
                encoding="utf-8",
            )
            output = fixture_root / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "codex",
                    "--codex-root",
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
            result = json.loads(output.read_text(encoding="utf-8"))

        provider = result["providers"]["codex"]
        self.assertEqual(provider["diagnostics"]["subagent_sessions_excluded"], 1)
        self.assertEqual(provider["diagnostics"]["invalid_model_ids"], 0)
        self.assertEqual(provider["diagnostics"]["invalid_effort_values"], 0)
        self.assertEqual(provider["diagnostics"]["status"], "OK")
        self.assertTrue(result["quality"]["shareable"])

    def test_small_unknown_model_share_is_quarantined_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "sessions" / "2026" / "quarantine.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {"type": "session_meta", "payload": {"source": "cli", "id": "quarantine"}}
            ]
            for index in range(101):
                model = "gpt-5.6-sol" if index < 100 else "private-model-canary"
                records.extend(
                    [
                        {"type": "event_msg", "payload": {"type": "task_started"}},
                        {
                            "type": "turn_context",
                            "payload": {"model": model, "effort": "high"},
                        },
                        {"type": "event_msg", "payload": {"type": "user_message"}},
                        {
                            "type": "event_msg",
                            "payload": {"type": "agent_message", "message": "Done."},
                        },
                        {"type": "event_msg", "payload": {"type": "task_complete"}},
                    ]
                )
            session.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
            )
            output = fixture_root / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "codex",
                    "--codex-root",
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
            result = json.loads(output.read_text(encoding="utf-8"))

        provider = result["providers"]["codex"]
        diagnostics = provider["diagnostics"]
        self.assertEqual(provider["models"][0]["answered_human_turns"], 100)
        self.assertNotIn("redacted-invalid-model-id", str(provider["models"]))
        self.assertEqual(diagnostics["human_turns_seen"], 101)
        self.assertEqual(diagnostics["quarantined_model_turns"], 1)
        self.assertEqual(diagnostics["quarantined_model_turn_share_pct"], 0.99)
        self.assertTrue(diagnostics["turn_reconciliation_ok"])
        self.assertEqual(diagnostics["status"], "OK_WITH_WARNINGS")
        self.assertTrue(result["quality"]["shareable"])

    def test_large_unknown_model_share_remains_unshareable(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "sessions" / "2026" / "quarantine.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {"type": "session_meta", "payload": {"source": "cli", "id": "quarantine"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.6-sol", "effort": "high"},
                },
                {"type": "event_msg", "payload": {"type": "user_message"}},
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "Done."},
                },
                {"type": "event_msg", "payload": {"type": "task_complete"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {
                    "type": "turn_context",
                    "payload": {"model": "private-model-canary", "effort": "high"},
                },
                {"type": "event_msg", "payload": {"type": "user_message"}},
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "Done."},
                },
                {"type": "event_msg", "payload": {"type": "task_complete"}},
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
                    "codex",
                    "--codex-root",
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
            result = json.loads(output.read_text(encoding="utf-8"))

        diagnostics = result["providers"]["codex"]["diagnostics"]
        self.assertEqual(diagnostics["quarantined_model_turn_share_pct"], 50.0)
        self.assertEqual(diagnostics["status"], "INCOMPLETE")
        self.assertFalse(result["quality"]["shareable"])

    def test_recognized_schema_without_answered_turns_is_not_schema_drift(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "sessions" / "2026" / "empty.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {"type": "session_meta", "payload": {"source": "cli", "id": "empty-session"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "event_msg", "payload": {"type": "task_complete"}},
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
                    "codex",
                    "--codex-root",
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
            result = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            result["providers"]["codex"]["diagnostics"]["status"],
            "NO_ANSWERED_TURNS",
        )
        self.assertFalse(result["quality"]["shareable"])

    def test_visible_reply_is_required_for_the_answered_turn_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "projects" / "demo" / "unanswered.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {
                    "type": "user",
                    "message": {"role": "user", "content": "Synthetic"},
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-5",
                        "content": [{"type": "tool_use", "name": "Synthetic"}],
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
            provider = json.loads(output.read_text(encoding="utf-8"))["providers"]["claude"]

        self.assertEqual(provider["models"], [])
        self.assertEqual(provider["diagnostics"]["human_turns_seen"], 1)
        self.assertEqual(provider["diagnostics"]["unanswered_or_unattributed_turns"], 1)

    def test_malformed_records_are_counted_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "projects" / "demo" / "malformed.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                "not-json\n[]\n"
                '{"type":"user","message":"bad-shape"}\n'
                '{"type":"user","message":{"role":"user","content":"Synthetic"}}\n'
                '{"type":"assistant","message":"bad-shape"}\n'
                '{"type":"assistant","message":{"role":"assistant","model":"claude-opus-5",'
                '"content":[{"type":"text","text":"I was wrong."}]}}\n',
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
            provider = json.loads(output.read_text(encoding="utf-8"))["providers"]["claude"]

        self.assertEqual(provider["models"][0]["answered_human_turns"], 1)
        self.assertEqual(provider["diagnostics"]["malformed_records"], 4)
        self.assertTrue(provider["diagnostics"]["turn_reconciliation_ok"])
        self.assertEqual(provider["diagnostics"]["status"], "INCOMPLETE")

    def test_codex_mixed_model_turn_is_reported_and_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            session = fixture_root / "sessions" / "2026" / "mixed.jsonl"
            session.parent.mkdir(parents=True)
            records = [
                {"type": "session_meta", "payload": {"source": "cli"}},
                {
                    "type": "event_msg",
                    "timestamp": "2026-01-06T00:00:00Z",
                    "payload": {"type": "task_started"},
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "Synthetic"},
                },
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.5", "effort": "high"},
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "Working."},
                },
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.6-sol", "effort": "ultra"},
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "I was wrong."},
                },
                {"type": "event_msg", "payload": {"type": "task_complete"}},
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
                    "codex",
                    "--codex-root",
                    str(fixture_root),
                    "--languages",
                    "en,tr",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            provider = json.loads(output.read_text(encoding="utf-8"))["providers"]["codex"]

        self.assertEqual(provider["models"], [])
        self.assertEqual(provider["diagnostics"]["mixed_model_turns"], 1)
        self.assertEqual(provider["diagnostics"]["human_turns_seen"], 1)
        self.assertEqual(provider["diagnostics"]["answered_turns_included"], 0)

    def test_duplicate_codex_session_is_not_counted_twice(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            fixture_root = Path(fixture_dir)
            records = [
                {"type": "session_meta", "payload": {"source": "cli", "id": "same-session"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "high"}},
                {"type": "event_msg", "payload": {"type": "user_message", "message": "Synthetic"}},
                {"type": "event_msg", "payload": {"type": "agent_message", "message": "You're right."}},
                {"type": "event_msg", "payload": {"type": "task_complete"}},
            ]
            content = "".join(json.dumps(record) + "\n" for record in records)
            for relative in (
                Path("sessions/2026/live.jsonl"),
                Path("archived_sessions/2026/copied.jsonl"),
            ):
                path = fixture_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            output = fixture_root / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "codex",
                    "--codex-root",
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
            provider = json.loads(output.read_text(encoding="utf-8"))["providers"]["codex"]

        self.assertEqual(provider["models"][0]["answered_human_turns"], 1)
        self.assertEqual(provider["models"][0]["acknowledged_correction"]["count"], 1)
        self.assertEqual(provider["diagnostics"]["duplicate_session_files"], 1)

    def test_unknown_language_fails_without_a_path_or_traceback(self) -> None:
        canary = "private-language-path-canary"
        with tempfile.TemporaryDirectory(prefix=canary) as fixture_dir:
            output = Path(fixture_dir) / "results.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scan.py"),
                    "--provider",
                    "claude",
                    "--claude-root",
                    fixture_dir,
                    "--languages",
                    "en,unknown",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn(canary, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertIn("available: en, tr", completed.stderr)


if __name__ == "__main__":
    unittest.main()
