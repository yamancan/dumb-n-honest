#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
TOOL_VERSION = "0.2.6"
SCHEMA_VERSION = "2.0"
ADAPTER_VERSIONS = {"claude": "3", "codex": "3"}
MAX_QUARANTINED_MODEL_TURN_SHARE_PCT = 1.0
REDACTED_MODEL_ID = "redacted-invalid-model-id"
MODEL_ID_PATTERNS = {
    "claude": re.compile(
        r"(?:claude-(?:opus|sonnet|haiku|fable)-\d{1,2}(?:-\d{1,2}){0,2}(?:-\d{8})?"
        r"|claude-\d{1,2}(?:-\d{1,2})?-(?:opus|sonnet|haiku|fable)(?:-\d{8})?)"
    ),
    "codex": re.compile(
        r"(?:gpt-\d{1,2}(?:\.\d{1,2})*"
        r"(?:-(?:codex|mini|max|pro|sol|terra|luna|latest|spark)){0,4}"
        r"|o\d{1,2}(?:-(?:mini|pro|latest))?|codex-mini-latest|codex-auto-review)"
    ),
}
MAX_MODEL_ID_LENGTH = 64
SAFE_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra", "auto"}
)
MATCH_TRANSLATION = str.maketrans(
    {
        "ç": "c",
        "Ç": "C",
        "ğ": "g",
        "Ğ": "G",
        "ı": "i",
        "İ": "I",
        "ö": "o",
        "Ö": "O",
        "ş": "s",
        "Ş": "S",
        "ü": "u",
        "Ü": "U",
    }
)


def normalize_match_text(text: str) -> str:
    return text.translate(MATCH_TRANSLATION)


def compile_pattern(regex: str) -> re.Pattern[str]:
    return re.compile(normalize_match_text(regex), re.IGNORECASE)


def nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None


def safe_model_id(provider: str, value: object, fallback: str) -> str:
    pattern = MODEL_ID_PATTERNS[provider]
    if (
        isinstance(value, str)
        and len(value) <= MAX_MODEL_ID_LENGTH
        and pattern.fullmatch(value)
    ):
        return value
    return fallback


def safe_effort(value: object, fallback: str = "missing") -> str:
    if isinstance(value, str) and value in SAFE_EFFORTS:
        return value
    return fallback


def wilson_interval(count: int, total: int) -> dict[str, float]:
    if total <= 0:
        return {"low": 0.0, "high": 0.0}
    z = 1.959963984540054
    proportion = count / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return {
        "low": round(100 * max(0.0, center - margin), 2),
        "high": round(100 * min(1.0, center + margin), 2),
    }


def empty_event_bucket() -> dict[str, Any]:
    return {"count": 0, "by_language": {}, "by_pattern": {}}


def record_event(model_stats: dict[str, Any], event: tuple[str, str] | None) -> None:
    if event is None:
        return
    category, pattern_id = event
    language = pattern_id.split(".", 1)[0]
    bucket = model_stats[category]
    bucket["count"] += 1
    bucket["by_language"][language] = bucket["by_language"].get(language, 0) + 1
    bucket["by_pattern"][pattern_id] = bucket["by_pattern"].get(pattern_id, 0) + 1
    if category in ("owned_error", "conceded"):
        headline = model_stats["acknowledged_correction"]
        headline["count"] += 1
        headline["by_language"][language] = headline["by_language"].get(language, 0) + 1
        headline["by_pattern"][pattern_id] = headline["by_pattern"].get(pattern_id, 0) + 1


def finish_model_stats(model_stats: dict[str, Any], total_turns: int) -> None:
    turns = model_stats["answered_human_turns"]
    model_stats["answered_turn_share_pct"] = (
        round(100 * turns / total_turns, 2) if total_turns else 0.0
    )
    for category in ("acknowledged_correction", "owned_error", "conceded", "soft_concession"):
        bucket = model_stats[category]
        bucket["per_100_turns"] = round(100 * bucket["count"] / turns, 2) if turns else 0.0
    acknowledgment = model_stats["acknowledged_correction"]
    acknowledgment["wilson_95_pct"] = wilson_interval(acknowledgment["count"], turns)
    if turns < 500 or acknowledgment["count"] < 10:
        acknowledgment["sample_status"] = "exploratory"
    elif acknowledgment["count"] < 20:
        acknowledgment["sample_status"] = "sample-limited"
    else:
        acknowledgment["sample_status"] = "sample-sufficient"

    reasoning = model_stats["reasoning"]
    eligible = reasoning["eligible_units"]
    covered_turns = reasoning["covered_answered_turns"]
    reasoning["coverage_pct"] = (
        round(100 * reasoning["covered_units"] / eligible, 2) if eligible else 0.0
    )
    reasoning["answered_turn_coverage_pct"] = (
        round(100 * covered_turns / turns, 2) if turns else 0.0
    )
    reasoning["tokens_per_covered_answered_turn"] = (
        round(reasoning["tokens_in_covered_answered_turns"] / covered_turns, 2)
        if covered_turns
        else None
    )


def finish_provider_diagnostics(diagnostics: dict[str, Any]) -> None:
    diagnostics["turn_reconciliation_ok"] = diagnostics["human_turns_seen"] == sum(
        diagnostics[key]
        for key in (
            "answered_turns_included",
            "unanswered_or_unattributed_turns",
            "quarantined_model_turns",
            "mixed_model_turns",
            "turns_abandoned_file_error",
        )
    )
    human_turns = diagnostics["human_turns_seen"]
    quarantined = diagnostics["quarantined_model_turns"]
    diagnostics["quarantined_model_turn_share_pct"] = (
        round(100 * quarantined / human_turns, 2) if human_turns else 0.0
    )
    # Compare raw counts so a share that rounds down to the threshold cannot pass.
    quarantine_exceeds_threshold = (
        human_turns > 0
        and 100 * quarantined > MAX_QUARANTINED_MODEL_TURN_SHARE_PCT * human_turns
    )
    if not diagnostics["root_found"]:
        diagnostics["status"] = "MISSING_ROOT"
    elif diagnostics["files_seen"] == 0:
        diagnostics["status"] = "NO_FILES"
    elif (
        diagnostics["file_errors"]
        or diagnostics["malformed_records"]
        or diagnostics["invalid_effort_values"]
        or quarantine_exceeds_threshold
        or not diagnostics["turn_reconciliation_ok"]
    ):
        diagnostics["status"] = "INCOMPLETE"
    elif diagnostics["records_seen"] > 0 and diagnostics["recognized_records"] == 0:
        diagnostics["status"] = "UNSUPPORTED_OR_EMPTY_SCHEMA"
    elif diagnostics["answered_turns_included"] == 0:
        diagnostics["status"] = "NO_ANSWERED_TURNS"
    elif diagnostics["quarantined_model_turns"]:
        diagnostics["status"] = "OK_WITH_WARNINGS"
    else:
        diagnostics["status"] = "OK"


def visible_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def claude_is_human(record: dict[str, Any]) -> bool:
    if record.get("type") != "user" or record.get("isSidechain") is True:
        return False
    if record.get("isMeta") is True or record.get("isCompactSummary") is True:
        return False
    message = record.get("message") or {}
    if (
        message.get("role") != "user"
        or record.get("toolUseResult") is not None
        or record.get("sourceToolAssistantUUID") is not None
    ):
        return False
    content = message.get("content")
    if isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    ):
        return False
    text = content if isinstance(content, str) else " ".join(
        block.get("text", "")
        for block in (content or [])
        if isinstance(block, dict) and block.get("type") == "text"
    )
    injected_prefixes = (
        "<system-reminder",
        "<local-command",
        "<command-name>",
        "caveat: the messages below",
        "[request interrupted",
        "<task-notification",
        "<teammate-message",
    )
    return not text.lstrip().casefold().startswith(injected_prefixes)


def claude_is_meta_boundary(record: dict[str, Any]) -> bool:
    return record.get("type") == "user" and (
        record.get("isMeta") is True or record.get("isCompactSummary") is True
    )


def open_transcript(path: Path):
    """Open a transcript; retry once if it vanished between glob and open."""
    try:
        return path.open("r", encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return path.open("r", encoding="utf-8", errors="replace")


def load_patterns(languages: list[str]) -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    loaded: dict[str, list[tuple[str, re.Pattern[str]]]] = {
        "owned_error": [],
        "conceded": [],
        "soft_concession": [],
        "global_exclude": [],
        "exclude": [],
    }
    for language in languages:
        path = SKILL_ROOT / "patterns" / f"{language}.json"
        definition = json.loads(path.read_text(encoding="utf-8"))
        for category in loaded:
            for pattern in definition[category]:
                loaded[category].append(
                    (pattern["id"], compile_pattern(pattern["regex"]))
                )
    return loaded


def clean_visible(text: str) -> str:
    normalized = text.replace("’", "'").replace("‘", "'")
    normalized = re.sub(r"(?:```|~~~).*?(?:```|~~~)", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"<code\b[^>]*>.*?</code>", " ", normalized, flags=re.DOTALL | re.IGNORECASE)
    normalized = re.sub(r"`[^`\n]*`", " ", normalized)
    normalized = re.sub(r"(?m)^\s*>.*$", " ", normalized)
    normalized = re.sub(r"(?m)^\s*\|.*\|\s*$", " ", normalized)
    normalized = re.sub(r'“[^“”\n]{0,500}”', " ", normalized)
    normalized = re.sub(r'"[^"\n]{0,500}"', " ", normalized)
    normalized = re.sub(r"(?<!\w)'[^'\n]{0,500}'(?!\w)", " ", normalized)
    normalized = re.sub(r"[\t\f\v ]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    return normalize_match_text(normalized.strip())


def classify(text: str, patterns: dict[str, list[tuple[str, re.Pattern[str]]]]) -> tuple[str, str] | None:
    cleaned = clean_visible(text)
    for _, pattern in patterns["global_exclude"]:
        cleaned = pattern.sub(" ", cleaned)
    eligible_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", cleaned):
        if (
            sentence
            and not sentence.rstrip().endswith("?")
            and not any(pattern.search(sentence) for _, pattern in patterns["exclude"])
        ):
            eligible_sentences.append(sentence)
    normalized = "\n".join(eligible_sentences)
    for category in ("owned_error", "conceded", "soft_concession"):
        for pattern_id, pattern in patterns[category]:
            if pattern.search(normalized):
                return category, pattern_id
    return None


def scan_claude(root: Path, patterns: dict[str, list[tuple[str, re.Pattern[str]]]]) -> dict[str, Any]:
    diagnostics = {
        "root_found": root.is_dir(),
        "files_seen": 0,
        "files_read": 0,
        "records_seen": 0,
        "recognized_records": 0,
        "malformed_records": 0,
        "human_turns_seen": 0,
        "answered_turns_included": 0,
        "unanswered_or_unattributed_turns": 0,
        "quarantined_model_turns": 0,
        "mixed_model_turns": 0,
        "turns_abandoned_file_error": 0,
        "symlinks_skipped": 0,
        "file_errors": 0,
        "invalid_model_ids": 0,
        "invalid_effort_values": 0,
        "assistant_units_missing_request_id": 0,
        "duplicate_session_files": 0,
        "subagent_files_excluded": 0,
        "meta_records_excluded": 0,
        "files_vanished": 0,
    }
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "answered_human_turns": 0,
            "sessions_with_answered_turns": 0,
            "acknowledged_correction": empty_event_bucket(),
            "owned_error": empty_event_bucket(),
            "conceded": empty_event_bucket(),
            "soft_concession": empty_event_bucket(),
            "effort": {},
            "date_range": {"first": None, "last": None},
            "reasoning": {
                "observed_tokens": 0,
                "tokens_in_covered_answered_turns": 0,
                "covered_units": 0,
                "eligible_units": 0,
                "covered_answered_turns": 0,
            },
        }
    )

    seen_session_ids: set[str] = set()
    # Sorted so attribution never depends on filesystem enumeration order.
    for path in sorted(
        root.glob("projects/**/*.jsonl"), key=lambda candidate: candidate.as_posix()
    ):
        diagnostics["files_seen"] += 1
        if "subagents" in path.relative_to(root).parts:
            # Subagent transcripts share the parent sessionId; they are sidechains,
            # not duplicates, and must never shadow the top-level session file.
            diagnostics["subagent_files_excluded"] += 1
            continue
        if path.is_symlink():
            diagnostics["symlinks_skipped"] += 1
            continue
        current: dict[str, Any] | None = None
        session_models: set[str] = set()
        missing_request_sequence = 0
        file_session_id: str | None = None
        duplicate_file = False

        def finish() -> None:
            nonlocal current
            if current is None:
                return
            if not current["texts"] or not current["models"]:
                diagnostics["unanswered_or_unattributed_turns"] += 1
                current = None
                return
            if REDACTED_MODEL_ID in current["models"]:
                diagnostics["quarantined_model_turns"] += 1
                current = None
                return
            if len(current["models"]) > 1:
                diagnostics["mixed_model_turns"] += 1
                current = None
                return
            model_id = next(iter(current["models"]))
            model_stats = stats[model_id]
            session_models.add(model_id)
            model_stats["answered_human_turns"] += 1
            diagnostics["answered_turns_included"] += 1
            record_event(model_stats, classify("\n".join(current["texts"]), patterns))
            effort = (
                next(iter(current["efforts"]))
                if len(current["efforts"]) == 1
                else "mixed/missing"
            )
            model_stats["effort"][effort] = model_stats["effort"].get(effort, 0) + 1
            if current["date"]:
                date_range = model_stats["date_range"]
                if date_range["first"] is None or current["date"] < date_range["first"]:
                    date_range["first"] = current["date"]
                if date_range["last"] is None or current["date"] > date_range["last"]:
                    date_range["last"] = current["date"]
            reasoning = model_stats["reasoning"]
            requests = current["requests"]
            observed = [value for value in requests.values() if value is not None]
            reasoning["eligible_units"] += len(requests)
            reasoning["covered_units"] += len(observed)
            observed_tokens = sum(observed)
            reasoning["observed_tokens"] += observed_tokens
            if requests and len(observed) == len(requests):
                reasoning["tokens_in_covered_answered_turns"] += observed_tokens
                reasoning["covered_answered_turns"] += 1
            current = None

        try:
            with open_transcript(path) as handle:
                diagnostics["files_read"] += 1
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        diagnostics["malformed_records"] += 1
                        continue
                    if not isinstance(record, dict):
                        diagnostics["malformed_records"] += 1
                        continue
                    diagnostics["records_seen"] += 1
                    session_id = record.get("sessionId")
                    if file_session_id is None and isinstance(session_id, str) and session_id:
                        file_session_id = session_id
                        if session_id in seen_session_ids:
                            diagnostics["duplicate_session_files"] += 1
                            duplicate_file = True
                        else:
                            seen_session_ids.add(session_id)
                    if duplicate_file:
                        current = None
                        break  # nothing further in this file may enter any counter
                    if claude_is_meta_boundary(record):
                        diagnostics["recognized_records"] += 1
                        diagnostics["meta_records_excluded"] += 1
                        finish()
                        current = None
                        continue
                    if record.get("type") in ("user", "assistant") and not isinstance(
                        record.get("message"), dict
                    ):
                        diagnostics["malformed_records"] += 1
                        continue
                    if claude_is_human(record):
                        diagnostics["recognized_records"] += 1
                        finish()
                        diagnostics["human_turns_seen"] += 1
                        timestamp = record.get("timestamp")
                        date = (
                            timestamp[:10]
                            if isinstance(timestamp, str)
                            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", timestamp[:10])
                            else None
                        )
                        current = {
                            "models": set(),
                            "efforts": set(),
                            "texts": [],
                            "requests": {},
                            "date": date,
                        }
                    elif (
                        record.get("type") == "assistant"
                        and current is not None
                        and record.get("isSidechain") is not True
                    ):
                        diagnostics["recognized_records"] += 1
                        message = record.get("message") or {}
                        model = message.get("model")
                        if isinstance(model, str) and model and model != "<synthetic>":
                            safe_model = safe_model_id(
                                "claude", model, REDACTED_MODEL_ID
                            )
                            if safe_model != model:
                                diagnostics["invalid_model_ids"] += 1
                            current["models"].add(safe_model)
                            effort = record.get("effort")
                            normalized_effort = safe_effort(effort)
                            if isinstance(effort, str) and normalized_effort != effort:
                                diagnostics["invalid_effort_values"] += 1
                            current["efforts"].add(
                                normalized_effort
                            )
                            text = visible_text(message.get("content"))
                            if text:
                                current["texts"].append(text)
                            request_id_value = record.get("requestId") or message.get("id")
                            request_id = (
                                request_id_value
                                if isinstance(request_id_value, str) and request_id_value
                                else None
                            )
                            if request_id is not None:
                                usage_value = message.get("usage")
                                usage = usage_value if isinstance(usage_value, dict) else {}
                                details_value = usage.get("output_tokens_details")
                                details = details_value if isinstance(details_value, dict) else {}
                                thinking = nonnegative_int(details.get("thinking_tokens"))
                                previous = current["requests"].get(request_id)
                                if thinking is not None:
                                    current["requests"][request_id] = max(
                                        thinking, int(previous or 0)
                                    )
                                elif request_id not in current["requests"]:
                                    current["requests"][request_id] = None
                            else:
                                missing_request_sequence += 1
                                diagnostics["assistant_units_missing_request_id"] += 1
                                current["requests"][f"missing-{missing_request_sequence}"] = None
            finish()
        except FileNotFoundError:
            # A top-level file disappeared mid-scan (active session). Fail closed.
            diagnostics["files_vanished"] += 1
            diagnostics["file_errors"] += 1
            if current is not None:
                diagnostics["turns_abandoned_file_error"] += 1
            current = None
        except OSError:
            diagnostics["file_errors"] += 1
            if current is not None:
                diagnostics["turns_abandoned_file_error"] += 1
            current = None

        for model_id in session_models:
            stats[model_id]["sessions_with_answered_turns"] += 1

    total_turns = sum(model["answered_human_turns"] for model in stats.values())
    models = []
    for model_id, model_stats in sorted(stats.items()):
        finish_model_stats(model_stats, total_turns)
        models.append({"model_id": model_id, **model_stats})
    finish_provider_diagnostics(diagnostics)
    return {"models": models, "diagnostics": diagnostics}


def scan_codex(root: Path, patterns: dict[str, list[tuple[str, re.Pattern[str]]]]) -> dict[str, Any]:
    diagnostics = {
        "root_found": root.is_dir(),
        "files_seen": 0,
        "files_read": 0,
        "records_seen": 0,
        "recognized_records": 0,
        "malformed_records": 0,
        "human_turns_seen": 0,
        "answered_turns_included": 0,
        "unanswered_or_unattributed_turns": 0,
        "quarantined_model_turns": 0,
        "subagent_sessions_excluded": 0,
        "mixed_model_turns": 0,
        "turns_abandoned_file_error": 0,
        "symlinks_skipped": 0,
        "file_errors": 0,
        "invalid_model_ids": 0,
        "invalid_effort_values": 0,
        "reasoning_counter_resets": 0,
        "duplicate_session_files": 0,
        "files_vanished": 0,
    }
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "answered_human_turns": 0,
            "sessions_with_answered_turns": 0,
            "acknowledged_correction": empty_event_bucket(),
            "owned_error": empty_event_bucket(),
            "conceded": empty_event_bucket(),
            "soft_concession": empty_event_bucket(),
            "effort": {},
            "date_range": {"first": None, "last": None},
            "reasoning": {
                "observed_tokens": 0,
                "tokens_in_covered_answered_turns": 0,
                "covered_units": 0,
                "eligible_units": 0,
                "covered_answered_turns": 0,
            },
        }
    )
    # Sorted so duplicate resolution never depends on filesystem enumeration order.
    paths = sorted(
        root.glob("sessions/**/*.jsonl"), key=lambda candidate: candidate.as_posix()
    ) + sorted(
        root.glob("archived_sessions/**/*.jsonl"),
        key=lambda candidate: candidate.as_posix(),
    )

    seen_session_ids: set[str] = set()
    for path in paths:
        diagnostics["files_seen"] += 1
        if path.is_symlink():
            diagnostics["symlinks_skipped"] += 1
            continue
        source_seen = False
        source_ok = True
        current: dict[str, Any] | None = None
        last_reasoning = 0
        session_models: set[str] = set()

        def finish() -> None:
            nonlocal current
            if current is None or not source_ok or not current["human"]:
                current = None
                return
            diagnostics["human_turns_seen"] += 1
            if not current["texts"] or not current["models"]:
                diagnostics["unanswered_or_unattributed_turns"] += 1
                current = None
                return
            if REDACTED_MODEL_ID in current["models"]:
                diagnostics["quarantined_model_turns"] += 1
                current = None
                return
            if len(current["models"]) > 1:
                diagnostics["mixed_model_turns"] += 1
                current = None
                return
            model_id = next(iter(current["models"]))
            model_stats = stats[model_id]
            session_models.add(model_id)
            model_stats["answered_human_turns"] += 1
            diagnostics["answered_turns_included"] += 1
            record_event(model_stats, classify("\n".join(current["texts"]), patterns))
            effort = (
                next(iter(current["efforts"]))
                if len(current["efforts"]) == 1
                else "mixed/missing"
            )
            model_stats["effort"][effort] = model_stats["effort"].get(effort, 0) + 1
            if current["date"]:
                date_range = model_stats["date_range"]
                if date_range["first"] is None or current["date"] < date_range["first"]:
                    date_range["first"] = current["date"]
                if date_range["last"] is None or current["date"] > date_range["last"]:
                    date_range["last"] = current["date"]
            reasoning = model_stats["reasoning"]
            reasoning["eligible_units"] += 1
            if current["token_seen"] and not current["token_counter_reset"]:
                turn_tokens = current["last_reasoning"] - current["baseline_reasoning"]
                reasoning["observed_tokens"] += turn_tokens
                reasoning["tokens_in_covered_answered_turns"] += turn_tokens
                reasoning["covered_units"] += 1
                reasoning["covered_answered_turns"] += 1
            elif current["token_counter_reset"]:
                diagnostics["reasoning_counter_resets"] += 1
            current = None

        try:
            with open_transcript(path) as handle:
                diagnostics["files_read"] += 1
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        diagnostics["malformed_records"] += 1
                        continue
                    if not isinstance(record, dict):
                        diagnostics["malformed_records"] += 1
                        continue
                    diagnostics["records_seen"] += 1
                    kind = record.get("type")
                    payload_value = record.get("payload")
                    if payload_value is not None and not isinstance(payload_value, dict):
                        diagnostics["malformed_records"] += 1
                        continue
                    payload = payload_value or {}
                    payload_type = payload.get("type")
                    if kind == "session_meta" and not source_seen:
                        diagnostics["recognized_records"] += 1
                        marker = json.dumps(payload.get("source"), sort_keys=True).casefold()
                        source_is_subagent = any(
                            token in marker for token in ("subagent", "collab", "spawn")
                        )
                        source_seen = True
                        if source_is_subagent:
                            diagnostics["subagent_sessions_excluded"] += 1
                            source_ok = False
                            current = None
                            break
                        session_id = payload.get("id")
                        if isinstance(session_id, str) and session_id:
                            if session_id in seen_session_ids:
                                diagnostics["duplicate_session_files"] += 1
                                source_ok = False
                                current = None
                                break
                            else:
                                seen_session_ids.add(session_id)
                    elif not source_ok:
                        break
                    elif kind == "event_msg" and payload_type == "task_started":
                        diagnostics["recognized_records"] += 1
                        finish()
                        timestamp = record.get("timestamp")
                        date = (
                            timestamp[:10]
                            if isinstance(timestamp, str)
                            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", timestamp[:10])
                            else None
                        )
                        current = {
                            "models": set(),
                            "efforts": set(),
                            "human": False,
                            "texts": [],
                            "baseline_reasoning": last_reasoning,
                            "last_reasoning": last_reasoning,
                            "token_seen": False,
                            "token_counter_reset": False,
                            "date": date,
                        }
                    elif kind == "turn_context" and current is not None:
                        diagnostics["recognized_records"] += 1
                        model = payload.get("model")
                        if isinstance(model, str) and model and model != "<synthetic>":
                            safe_model = safe_model_id(
                                "codex", model, REDACTED_MODEL_ID
                            )
                            if safe_model != model:
                                diagnostics["invalid_model_ids"] += 1
                            current["models"].add(safe_model)
                        effort = payload.get("effort")
                        normalized_effort = safe_effort(effort)
                        if isinstance(effort, str) and normalized_effort != effort:
                            diagnostics["invalid_effort_values"] += 1
                        current["efforts"].add(normalized_effort)
                    elif (
                        kind == "event_msg"
                        and payload_type == "user_message"
                        and current is not None
                    ):
                        diagnostics["recognized_records"] += 1
                        current["human"] = True
                    elif (
                        kind == "event_msg"
                        and payload_type == "agent_message"
                        and current is not None
                        and isinstance(payload.get("message"), str)
                    ):
                        diagnostics["recognized_records"] += 1
                        current["texts"].append(payload["message"])
                    elif kind == "event_msg" and payload_type == "token_count":
                        diagnostics["recognized_records"] += 1
                        total = (
                            ((payload.get("info") or {}).get("total_token_usage") or {}).get(
                                "reasoning_output_tokens"
                            )
                        )
                        parsed_total = nonnegative_int(total)
                        if parsed_total is not None:
                            if current is not None and parsed_total < current["baseline_reasoning"]:
                                current["token_counter_reset"] = True
                            last_reasoning = parsed_total
                            if current is not None:
                                current["last_reasoning"] = last_reasoning
                                current["token_seen"] = True
                    elif kind == "event_msg" and payload_type == "task_complete":
                        diagnostics["recognized_records"] += 1
                        finish()
            finish()
        except FileNotFoundError:
            diagnostics["files_vanished"] += 1
            diagnostics["file_errors"] += 1
            if current is not None and source_ok and current["human"]:
                diagnostics["human_turns_seen"] += 1
                diagnostics["turns_abandoned_file_error"] += 1
            current = None
        except OSError:
            diagnostics["file_errors"] += 1
            if current is not None and source_ok and current["human"]:
                diagnostics["human_turns_seen"] += 1
                diagnostics["turns_abandoned_file_error"] += 1
            current = None

        for model_id in session_models:
            stats[model_id]["sessions_with_answered_turns"] += 1

    total_turns = sum(model["answered_human_turns"] for model in stats.values())
    models = []
    for model_id, model_stats in sorted(stats.items()):
        finish_model_stats(model_stats, total_turns)
        models.append({"model_id": model_id, **model_stats})
    finish_provider_diagnostics(diagnostics)
    return {"models": models, "diagnostics": diagnostics}


def parse_languages(value: str) -> list[str]:
    languages = list(
        dict.fromkeys(part.strip().lower() for part in value.split(",") if part.strip())
    )
    if not languages:
        raise argparse.ArgumentTypeError("select at least one language")
    available = sorted(path.stem for path in (SKILL_ROOT / "patterns").glob("*.json"))
    if any(language not in available for language in languages):
        raise argparse.ArgumentTypeError(
            f"unsupported language pack; available: {', '.join(available)}"
        )
    return languages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit explicit coding-agent self-corrections in local transcripts."
    )
    parser.add_argument("--provider", choices=("all", "claude", "codex"), default="all")
    parser.add_argument("--claude-root", type=Path, default=Path.home() / ".claude")
    parser.add_argument("--codex-root", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--languages", type=parse_languages, default=["en", "tr"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        patterns = load_patterns(args.languages)
    except (OSError, ValueError, KeyError, TypeError, re.error):
        parser.error("selected language packs could not be loaded")
    providers = {}
    if args.provider in ("all", "claude"):
        providers["claude"] = scan_claude(args.claude_root, patterns)
    if args.provider in ("all", "codex"):
        providers["codex"] = scan_codex(args.codex_root, patterns)
    statuses = {
        provider: provider_result["diagnostics"]["status"]
        for provider, provider_result in providers.items()
    }
    valid_statuses = {"OK", "OK_WITH_WARNINGS"}
    valid_providers = [
        provider for provider, status in statuses.items() if status in valid_statuses
    ]
    blocking_statuses = {"INCOMPLETE", "UNSUPPORTED_OR_EMPTY_SCHEMA"}
    shareable = bool(valid_providers) and not any(
        status in blocking_statuses for status in statuses.values()
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "tool": {
            "name": "dumb-n-honest",
            "version": TOOL_VERSION,
            "adapter_versions": ADAPTER_VERSIONS,
            "pattern_pack_version": "2",
        },
        "languages": args.languages,
        "providers": providers,
        "quality": {
            "shareable": shareable,
            "provider_status": statuses,
            "valid_providers": valid_providers,
        },
    }
    try:
        if args.output.exists() or args.output.is_symlink():
            parser.error("aggregate output already exists")
        parent_was_created = not args.output.parent.exists()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if parent_was_created:
            args.output.parent.chmod(0o700)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        args.output.chmod(0o600)
    except OSError:
        parser.error("aggregate output could not be written")
    print(
        "provider\tmodel\tturns\tturn_share_pct\tacknowledged\tack_per_100\t"
        "ci95_low\tci95_high\tsample_status\towned\tconceded\tsoft_concession\t"
        "reasoning_unit_coverage_pct\t"
        "reasoning_turn_coverage_pct"
    )
    for provider, provider_result in result["providers"].items():
        for model in provider_result["models"]:
            print(
                f"{provider}\t{model['model_id']}\t{model['answered_human_turns']}\t"
                f"{model['answered_turn_share_pct']:.2f}\t"
                f"{model['acknowledged_correction']['count']}\t"
                f"{model['acknowledged_correction']['per_100_turns']:.2f}\t"
                f"{model['acknowledged_correction']['wilson_95_pct']['low']:.2f}\t"
                f"{model['acknowledged_correction']['wilson_95_pct']['high']:.2f}\t"
                f"{model['acknowledged_correction']['sample_status']}\t"
                f"{model['owned_error']['count']}\t{model['conceded']['count']}\t"
                f"{model['soft_concession']['count']}\t"
                f"{model['reasoning']['coverage_pct']:.2f}\t"
                f"{model['reasoning']['answered_turn_coverage_pct']:.2f}"
            )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "The local transcript scan failed; no raw transcript content was emitted."
        ) from None
