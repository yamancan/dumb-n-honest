from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.scan import finish_provider_diagnostics, load_patterns, scan_claude


ROOT = Path(__file__).resolve().parents[1]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def run_scan(provider: str, root: Path) -> dict:
    output = root / "results.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "scan.py"),
            "--provider",
            provider,
            f"--{provider}-root",
            str(root),
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
    assert completed.returncode == 0, completed.stderr
    return json.loads(output.read_text(encoding="utf-8"))["providers"][provider]


def human(text: str, **extra: object) -> dict:
    return {"type": "user", "sessionId": "s1", "message": {"role": "user", "content": text}, **extra}


def reply(text: str, **extra: object) -> dict:
    return {
        "type": "assistant",
        "sessionId": "s1",
        "requestId": f"synthetic-{abs(hash(text)) % 10_000}",
        "message": {
            "role": "assistant",
            "model": "claude-opus-5",
            "content": [{"type": "text", "text": text}],
        },
        **extra,
    }


class ClaudeLayoutTests(unittest.TestCase):
    def test_subagent_files_never_shadow_the_top_level_session(self) -> None:
        # Real Claude Code layout: projects/<slug>/<sid>/subagents/*.jsonl shares the
        # parent sessionId. The subagent path sorts BEFORE the top-level file here, so
        # a sessionId-only dedup would drop the real session.
        with tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(fixture_dir)
            write_jsonl(
                root / "projects" / "demo" / "aa-session" / "subagents" / "agent-1.jsonl",
                [
                    human("Synthetic subagent prompt.", isSidechain=True),
                    reply("I was wrong.", isSidechain=True),
                ],
            )
            write_jsonl(
                root / "projects" / "demo" / "zz-session.jsonl",
                [human("Check the arithmetic."), reply("I was wrong. The total is 42.")],
            )
            provider = run_scan("claude", root)

        diagnostics = provider["diagnostics"]
        self.assertEqual(diagnostics["files_seen"], 2)
        self.assertEqual(diagnostics["subagent_files_excluded"], 1)
        self.assertEqual(diagnostics["duplicate_session_files"], 0)
        self.assertEqual(diagnostics["answered_turns_included"], 1)
        self.assertEqual(diagnostics["status"], "OK")
        self.assertEqual(provider["models"][0]["acknowledged_correction"]["count"], 1)

    def test_meta_and_compact_summary_records_are_not_human_turns(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(fixture_dir)
            write_jsonl(
                root / "projects" / "demo" / "session.jsonl",
                [
                    human("Check the arithmetic."),
                    reply("Working."),
                    human("Synthetic meta note.", isMeta=True),
                    reply("I was wrong. The total is 42."),
                    human("Synthetic compact summary.", isCompactSummary=True),
                    reply("Continuing."),
                ],
            )
            provider = run_scan("claude", root)

        diagnostics = provider["diagnostics"]
        self.assertEqual(diagnostics["human_turns_seen"], 1)
        self.assertEqual(diagnostics["answered_turns_included"], 1)
        self.assertEqual(diagnostics["unanswered_or_unattributed_turns"], 0)
        self.assertEqual(diagnostics["meta_records_excluded"], 2)
        self.assertEqual(provider["models"][0]["answered_human_turns"], 1)
        self.assertEqual(provider["models"][0]["acknowledged_correction"]["count"], 0)

    def test_true_duplicate_session_stops_parsing_before_it_can_poison_quality(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(fixture_dir)
            write_jsonl(
                root / "projects" / "demo" / "a.jsonl",
                [human("Check."), reply("You're right.")],
            )
            duplicate = root / "projects" / "demo" / "b.jsonl"
            duplicate.write_text(
                json.dumps(human("Check.")) + "\nnot-json\n[]\n",
                encoding="utf-8",
            )
            provider = run_scan("claude", root)

        diagnostics = provider["diagnostics"]
        self.assertEqual(diagnostics["duplicate_session_files"], 1)
        self.assertEqual(diagnostics["malformed_records"], 0)
        self.assertEqual(diagnostics["answered_turns_included"], 1)
        self.assertEqual(diagnostics["status"], "OK")

    def test_vanished_top_level_file_is_retried_once_then_fails_closed(self) -> None:
        patterns = load_patterns(["en"])
        with tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(fixture_dir)
            write_jsonl(root / "projects" / "demo" / "a.jsonl", [human("Check."), reply("You're right.")])
            write_jsonl(root / "projects" / "demo" / "b.jsonl", [human("Check."), reply("You're right.")])
            write_jsonl(root / "projects" / "demo" / "c.jsonl", [human("Check."), reply("You're right.")])
            for record_path in (root / "projects" / "demo" / "b.jsonl", root / "projects" / "demo" / "c.jsonl"):
                # Give each file its own sessionId so dedup does not interfere.
                text = record_path.read_text(encoding="utf-8").replace('"s1"', f'"{record_path.stem}"')
                record_path.write_text(text, encoding="utf-8")

            real_open = Path.open
            attempts: dict[str, int] = {}

            def flaky_open(self: Path, *args: object, **kwargs: object):
                attempts[self.name] = attempts.get(self.name, 0) + 1
                if self.name == "b.jsonl" and attempts[self.name] == 1:
                    raise FileNotFoundError(str(self))  # transient: retry succeeds
                if self.name == "c.jsonl":
                    raise FileNotFoundError(str(self))  # gone for good
                return real_open(self, *args, **kwargs)

            with mock.patch.object(Path, "open", flaky_open):
                result = scan_claude(root, patterns)

        diagnostics = result["diagnostics"]
        self.assertEqual(attempts["b.jsonl"], 2)
        self.assertEqual(attempts["c.jsonl"], 2)
        self.assertEqual(diagnostics["files_seen"], 3)
        self.assertEqual(diagnostics["files_read"], 2)
        self.assertEqual(diagnostics["files_vanished"], 1)
        self.assertEqual(diagnostics["file_errors"], 1)
        self.assertEqual(diagnostics["answered_turns_included"], 2)
        self.assertEqual(diagnostics["status"], "INCOMPLETE")


class CodexLayoutTests(unittest.TestCase):
    def test_response_item_messages_count_answered_turns_and_reasoning_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(fixture_dir)
            write_jsonl(
                root / "sessions" / "2026" / "main.jsonl",
                [
                    {"type": "session_meta", "payload": {"source": "cli", "id": "synthetic-main"}},
                    {"type": "event_msg", "timestamp": "2026-10-01T10:00:00Z", "payload": {"type": "task_started"}},
                    {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "xhigh"}},
                    {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Check the arithmetic."}, {"type": "input_image", "image_url": "synthetic-image"}]}},
                    {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "UserMessage", "id": "synthetic-user", "content": [{"type": "text", "text": "Check the arithmetic."}]}}},
                    {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "AgentMessage", "id": "synthetic-reply", "content": [{"type": "Text", "text": "I was wrong. The total is 42."}]}}},
                    {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "I was wrong."}, {"type": "output_text", "text": "The total is 42."}]}},
                    {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"reasoning_output_tokens": 100}}}},
                    {"type": "event_msg", "payload": {"type": "task_complete"}},
                    {"type": "event_msg", "timestamp": "2026-10-02T10:00:00Z", "payload": {"type": "task_started"}},
                    {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "xhigh"}},
                    {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Sonucu kontrol et."}]}},
                    {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Haklısın; sonuç 42."}]}},
                    {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"reasoning_output_tokens": 140}}}},
                    {"type": "event_msg", "payload": {"type": "task_complete"}},
                ],
            )
            provider = run_scan("codex", root)

        diagnostics = provider["diagnostics"]
        self.assertEqual(diagnostics["human_turns_seen"], 2)
        self.assertEqual(diagnostics["answered_turns_included"], 2)
        self.assertEqual(diagnostics["status"], "OK")
        self.assertTrue(diagnostics["turn_reconciliation_ok"])
        model = provider["models"][0]
        self.assertEqual(model["model_id"], "gpt-6.1-sol")
        self.assertEqual(model["answered_human_turns"], 2)
        self.assertEqual(model["owned_error"]["count"], 1)
        self.assertEqual(model["conceded"]["count"], 1)
        self.assertEqual(model["acknowledged_correction"]["count"], 2)
        self.assertEqual(model["effort"], {"xhigh": 2})
        self.assertEqual(model["date_range"], {"first": "2026-10-01", "last": "2026-10-02"})
        self.assertEqual(model["reasoning"]["observed_tokens"], 140)
        self.assertEqual(model["reasoning"]["covered_answered_turns"], 2)
        self.assertEqual(model["reasoning"]["tokens_per_covered_answered_turn"], 70.0)

    def test_legacy_and_response_item_messages_do_not_duplicate_a_turn(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(fixture_dir)
            write_jsonl(
                root / "sessions" / "main.jsonl",
                [
                    {"type": "event_msg", "payload": {"type": "task_started"}},
                    {"type": "turn_context", "payload": {"model": "gpt-6-sol", "effort": "high"}},
                    {"type": "event_msg", "payload": {"type": "user_message", "message": "Check."}},
                    {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Check."}]}},
                    {"type": "event_msg", "payload": {"type": "agent_message", "message": "You're right."}},
                    {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "You're right."}]}},
                    {"type": "event_msg", "payload": {"type": "task_complete"}},
                ],
            )
            provider = run_scan("codex", root)

        self.assertEqual(provider["diagnostics"]["human_turns_seen"], 1)
        self.assertEqual(provider["models"][0]["answered_human_turns"], 1)
        self.assertEqual(provider["models"][0]["acknowledged_correction"]["count"], 1)

    def test_response_items_exclude_injected_messages_and_hidden_text(self) -> None:
        cases = [
            ("environment", "user", "<environment_context>synthetic context</environment_context>", "final", "I was wrong.", 0, 0),
            ("instructions", "user", "# AGENTS.md instructions for synthetic project", "final", "I was wrong.", 0, 0),
            ("developer", "developer", "Synthetic instruction.", "final", "I was wrong.", 0, 0),
            ("system", "system", "Synthetic instruction.", "final", "I was wrong.", 0, 0),
            ("analysis", "user", "Check.", "analysis", "I was wrong.", 1, 0),
            ("visible", "user", "Check.", "commentary", "The total is 42.", 1, 1),
            ("empty", "user", "Check.", "final", "", 1, 0),
        ]
        for name, role, prompt, channel, text, human_turns, answered_turns in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as fixture_dir:
                root = Path(fixture_dir)
                write_jsonl(
                    root / "sessions" / "main.jsonl",
                    [
                        {"type": "event_msg", "payload": {"type": "task_started"}},
                        {"type": "turn_context", "payload": {"model": "gpt-6-luna", "effort": "high"}},
                        {"type": "response_item", "payload": {"type": "message", "role": role, "content": [{"type": "input_text", "text": prompt}]}},
                        {"type": "response_item", "payload": {"type": "agent_message", "content": [{"type": "input_text", "text": "I was wrong. Synthetic subagent message."}]}},
                        {"type": "response_item", "payload": {"type": "function_call_output", "output": "I was wrong. Synthetic tool output."}},
                        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "AgentMessage", "content": [{"type": "Text", "text": "I was wrong. Synthetic duplicated item."}]}}},
                        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "channel": channel, "content": [{"type": "output_text", "text": text}]}},
                        {"type": "event_msg", "payload": {"type": "task_complete"}},
                    ],
                )
                provider = run_scan("codex", root)
                self.assertEqual(provider["diagnostics"]["human_turns_seen"], human_turns)
                self.assertEqual(provider["diagnostics"]["answered_turns_included"], answered_turns)
                if answered_turns:
                    self.assertEqual(provider["models"][0]["acknowledged_correction"]["count"], 0)

    def test_excluded_session_stops_parsing_before_malformed_lines(self) -> None:
        with tempfile.TemporaryDirectory() as fixture_dir:
            root = Path(fixture_dir)
            excluded = root / "sessions" / "2026" / "a-sub.jsonl"
            excluded.parent.mkdir(parents=True)
            excluded.write_text(
                json.dumps({"type": "session_meta", "payload": {"source": {"subagent": {"other": "guardian"}}, "id": "same-session"}})
                + "\nnot-json\n",
                encoding="utf-8",
            )
            write_jsonl(
                root / "sessions" / "2026" / "z-main.jsonl",
                [
                    {"type": "session_meta", "payload": {"source": "cli", "id": "same-session"}},
                    {"type": "event_msg", "payload": {"type": "task_started"}},
                    {"type": "turn_context", "payload": {"model": "gpt-5.3-codex-spark", "effort": "high"}},
                    {"type": "event_msg", "payload": {"type": "user_message", "message": "Synthetic"}},
                    {"type": "event_msg", "payload": {"type": "agent_message", "message": "You're right."}},
                    {"type": "event_msg", "payload": {"type": "task_complete"}},
                ],
            )
            provider = run_scan("codex", root)

        diagnostics = provider["diagnostics"]
        self.assertEqual(diagnostics["subagent_sessions_excluded"], 1)
        self.assertEqual(diagnostics["duplicate_session_files"], 0)
        self.assertEqual(diagnostics["malformed_records"], 0)
        self.assertEqual(diagnostics["invalid_model_ids"], 0)
        self.assertEqual(diagnostics["status"], "OK")
        self.assertEqual(provider["models"][0]["model_id"], "gpt-5.3-codex-spark")


class QuarantineThresholdTests(unittest.TestCase):
    def diagnostics(self, human_turns: int, quarantined: int) -> dict:
        return {
            "root_found": True,
            "files_seen": 1,
            "files_read": 1,
            "records_seen": 10,
            "recognized_records": 10,
            "malformed_records": 0,
            "human_turns_seen": human_turns,
            "answered_turns_included": human_turns - quarantined,
            "unanswered_or_unattributed_turns": 0,
            "quarantined_model_turns": quarantined,
            "mixed_model_turns": 0,
            "turns_abandoned_file_error": 0,
            "file_errors": 0,
            "invalid_effort_values": 0,
        }

    def test_share_that_rounds_down_to_the_threshold_still_blocks(self) -> None:
        diagnostics = self.diagnostics(20_050, 201)  # 1.0025% -> displays as 1.0
        finish_provider_diagnostics(diagnostics)
        self.assertEqual(diagnostics["quarantined_model_turn_share_pct"], 1.0)
        self.assertEqual(diagnostics["status"], "INCOMPLETE")

    def test_exactly_one_percent_is_still_a_warning(self) -> None:
        diagnostics = self.diagnostics(20_000, 200)
        finish_provider_diagnostics(diagnostics)
        self.assertEqual(diagnostics["status"], "OK_WITH_WARNINGS")


if __name__ == "__main__":
    unittest.main()
