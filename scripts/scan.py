#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
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


def load_patterns(languages: list[str]) -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    loaded: dict[str, list[tuple[str, re.Pattern[str]]]] = {
        "owned_error": [],
        "conceded": [],
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
    normalized = re.sub(r"```.*?```", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"`[^`\n]*`", " ", normalized)
    normalized = re.sub(r"(?m)^\s*>.*$", " ", normalized)
    normalized = re.sub(r'“[^“”\n]{0,500}”', " ", normalized)
    normalized = re.sub(r'"[^"\n]{0,500}"', " ", normalized)
    return normalize_match_text(re.sub(r"\s+", " ", normalized).strip())


def classify(text: str, patterns: dict[str, list[tuple[str, re.Pattern[str]]]]) -> tuple[str, str] | None:
    eligible_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", clean_visible(text)):
        if (
            sentence
            and not sentence.rstrip().endswith("?")
            and not any(pattern.search(sentence) for _, pattern in patterns["exclude"])
        ):
            eligible_sentences.append(sentence)
    normalized = "\n".join(eligible_sentences)
    for category in ("owned_error", "conceded"):
        for pattern_id, pattern in patterns[category]:
            if pattern.search(normalized):
                return category, pattern_id
    return None


def scan_claude(root: Path, patterns: dict[str, list[tuple[str, re.Pattern[str]]]]) -> dict[str, Any]:
    diagnostics = {
        "root_found": root.is_dir(),
        "files_seen": 0,
        "files_read": 0,
        "malformed_records": 0,
        "human_turns_seen": 0,
        "answered_turns_included": 0,
        "unanswered_or_unattributed_turns": 0,
        "mixed_model_turns": 0,
        "turns_abandoned_file_error": 0,
        "symlinks_skipped": 0,
        "file_errors": 0,
    }
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "answered_human_turns": 0,
            "owned_error": {"count": 0, "by_language": {}, "by_pattern": {}},
            "conceded": {"count": 0, "by_language": {}, "by_pattern": {}},
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

    for path in root.glob("projects/**/*.jsonl"):
        diagnostics["files_seen"] += 1
        if path.is_symlink():
            diagnostics["symlinks_skipped"] += 1
            continue
        current: dict[str, Any] | None = None

        def finish() -> None:
            nonlocal current
            if current is None:
                return
            if not current["texts"] or not current["models"]:
                diagnostics["unanswered_or_unattributed_turns"] += 1
                current = None
                return
            if len(current["models"]) > 1:
                diagnostics["mixed_model_turns"] += 1
                current = None
                return
            model_id = next(iter(current["models"]))
            model_stats = stats[model_id]
            model_stats["answered_human_turns"] += 1
            diagnostics["answered_turns_included"] += 1
            event = classify("\n".join(current["texts"]), patterns)
            if event is not None:
                category, pattern_id = event
                language = pattern_id.split(".", 1)[0]
                model_stats[category]["count"] += 1
                by_language = model_stats[category]["by_language"]
                by_language[language] = by_language.get(language, 0) + 1
                by_pattern = model_stats[category]["by_pattern"]
                by_pattern[pattern_id] = by_pattern.get(pattern_id, 0) + 1
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
            with path.open("r", encoding="utf-8", errors="replace") as handle:
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
                    if record.get("type") in ("user", "assistant") and not isinstance(
                        record.get("message"), dict
                    ):
                        diagnostics["malformed_records"] += 1
                        continue
                    if claude_is_human(record):
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
                        message = record.get("message") or {}
                        model = message.get("model")
                        if isinstance(model, str) and model and model != "<synthetic>":
                            current["models"].add(model)
                            effort = record.get("effort")
                            current["efforts"].add(
                                effort if isinstance(effort, str) and effort else "missing"
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
            finish()
        except OSError:
            diagnostics["file_errors"] += 1
            if current is not None:
                diagnostics["turns_abandoned_file_error"] += 1
            current = None

    total_turns = sum(model["answered_human_turns"] for model in stats.values())
    models = []
    for model_id, model_stats in sorted(stats.items()):
        turns = model_stats["answered_human_turns"]
        model_stats["usage_share_pct"] = round(100 * turns / total_turns, 2) if total_turns else 0.0
        for category in ("owned_error", "conceded"):
            bucket = model_stats[category]
            bucket["per_100_turns"] = round(100 * bucket["count"] / turns, 2) if turns else 0.0
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
        models.append({"model_id": model_id, **model_stats})
    diagnostics["turn_reconciliation_ok"] = diagnostics["human_turns_seen"] == sum(
        diagnostics[key]
        for key in (
            "answered_turns_included",
            "unanswered_or_unattributed_turns",
            "mixed_model_turns",
            "turns_abandoned_file_error",
        )
    )
    return {"models": models, "diagnostics": diagnostics}


def scan_codex(root: Path, patterns: dict[str, list[tuple[str, re.Pattern[str]]]]) -> dict[str, Any]:
    diagnostics = {
        "root_found": root.is_dir(),
        "files_seen": 0,
        "files_read": 0,
        "malformed_records": 0,
        "human_turns_seen": 0,
        "answered_turns_included": 0,
        "unanswered_or_unattributed_turns": 0,
        "subagent_sessions_excluded": 0,
        "mixed_model_turns": 0,
        "turns_abandoned_file_error": 0,
        "symlinks_skipped": 0,
        "file_errors": 0,
    }
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "answered_human_turns": 0,
            "owned_error": {"count": 0, "by_language": {}, "by_pattern": {}},
            "conceded": {"count": 0, "by_language": {}, "by_pattern": {}},
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
    paths = list(root.glob("sessions/**/*.jsonl")) + list(
        root.glob("archived_sessions/**/*.jsonl")
    )

    for path in paths:
        diagnostics["files_seen"] += 1
        if path.is_symlink():
            diagnostics["symlinks_skipped"] += 1
            continue
        source_seen = False
        source_ok = True
        current: dict[str, Any] | None = None
        last_reasoning = 0

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
            if len(current["models"]) > 1:
                diagnostics["mixed_model_turns"] += 1
                current = None
                return
            model_id = next(iter(current["models"]))
            model_stats = stats[model_id]
            model_stats["answered_human_turns"] += 1
            diagnostics["answered_turns_included"] += 1
            event = classify("\n".join(current["texts"]), patterns)
            if event is not None:
                category, pattern_id = event
                language = pattern_id.split(".", 1)[0]
                event_stats = model_stats[category]
                event_stats["count"] += 1
                event_stats["by_language"][language] = (
                    event_stats["by_language"].get(language, 0) + 1
                )
                event_stats["by_pattern"][pattern_id] = (
                    event_stats["by_pattern"].get(pattern_id, 0) + 1
                )
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
            if current["token_seen"]:
                turn_tokens = max(
                    0, current["last_reasoning"] - current["baseline_reasoning"]
                )
                reasoning["observed_tokens"] += turn_tokens
                reasoning["tokens_in_covered_answered_turns"] += turn_tokens
                reasoning["covered_units"] += 1
                reasoning["covered_answered_turns"] += 1
            current = None

        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
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
                    kind = record.get("type")
                    payload_value = record.get("payload")
                    if payload_value is not None and not isinstance(payload_value, dict):
                        diagnostics["malformed_records"] += 1
                        continue
                    payload = payload_value or {}
                    payload_type = payload.get("type")
                    if kind == "session_meta" and not source_seen:
                        marker = json.dumps(payload.get("source"), sort_keys=True).casefold()
                        source_ok = not any(
                            token in marker for token in ("subagent", "collab", "spawn")
                        )
                        source_seen = True
                        if not source_ok:
                            diagnostics["subagent_sessions_excluded"] += 1
                    elif kind == "event_msg" and payload_type == "task_started":
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
                            "date": date,
                        }
                    elif kind == "turn_context" and current is not None:
                        model = payload.get("model")
                        if isinstance(model, str) and model and model != "<synthetic>":
                            current["models"].add(model)
                        effort = payload.get("effort")
                        current["efforts"].add(
                            effort if isinstance(effort, str) and effort else "missing"
                        )
                    elif (
                        kind == "event_msg"
                        and payload_type == "user_message"
                        and current is not None
                    ):
                        current["human"] = True
                    elif (
                        kind == "event_msg"
                        and payload_type == "agent_message"
                        and current is not None
                        and isinstance(payload.get("message"), str)
                    ):
                        current["texts"].append(payload["message"])
                    elif kind == "event_msg" and payload_type == "token_count":
                        total = (
                            ((payload.get("info") or {}).get("total_token_usage") or {}).get(
                                "reasoning_output_tokens"
                            )
                        )
                        parsed_total = nonnegative_int(total)
                        if parsed_total is not None:
                            last_reasoning = parsed_total
                            if current is not None:
                                current["last_reasoning"] = last_reasoning
                                current["token_seen"] = True
                    elif kind == "event_msg" and payload_type == "task_complete":
                        finish()
            finish()
        except OSError:
            diagnostics["file_errors"] += 1
            if current is not None and source_ok and current["human"]:
                diagnostics["human_turns_seen"] += 1
                diagnostics["turns_abandoned_file_error"] += 1
            current = None

    total_turns = sum(model["answered_human_turns"] for model in stats.values())
    models = []
    for model_id, model_stats in sorted(stats.items()):
        turns = model_stats["answered_human_turns"]
        reasoning = model_stats["reasoning"]
        eligible = reasoning["eligible_units"]
        covered = reasoning["covered_units"]
        covered_turns = reasoning["covered_answered_turns"]
        reasoning["coverage_pct"] = round(100 * covered / eligible, 2) if eligible else 0.0
        reasoning["answered_turn_coverage_pct"] = (
            round(100 * covered_turns / turns, 2) if turns else 0.0
        )
        reasoning["tokens_per_covered_answered_turn"] = (
            round(reasoning["tokens_in_covered_answered_turns"] / covered_turns, 2)
            if covered_turns
            else None
        )
        model_stats["usage_share_pct"] = round(100 * turns / total_turns, 2) if total_turns else 0.0
        for category in ("owned_error", "conceded"):
            bucket = model_stats[category]
            bucket["per_100_turns"] = round(100 * bucket["count"] / turns, 2) if turns else 0.0
        models.append({"model_id": model_id, **model_stats})
    diagnostics["turn_reconciliation_ok"] = diagnostics["human_turns_seen"] == sum(
        diagnostics[key]
        for key in (
            "answered_turns_included",
            "unanswered_or_unattributed_turns",
            "mixed_model_turns",
            "turns_abandoned_file_error",
        )
    )
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
    result = {
        "schema_version": "1.1",
        "languages": args.languages,
        "providers": providers,
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
        "provider\tmodel\tturns\tusage_pct\towned\towned_per_100\t"
        "conceded\tconceded_per_100\treasoning_unit_coverage_pct\t"
        "reasoning_turn_coverage_pct"
    )
    for provider, provider_result in result["providers"].items():
        for model in provider_result["models"]:
            print(
                f"{provider}\t{model['model_id']}\t{model['answered_human_turns']}\t"
                f"{model['usage_share_pct']:.2f}\t{model['owned_error']['count']}\t"
                f"{model['owned_error']['per_100_turns']:.2f}\t"
                f"{model['conceded']['count']}\t{model['conceded']['per_100_turns']:.2f}\t"
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
