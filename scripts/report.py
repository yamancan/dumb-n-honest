#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_URL = "https://github.com/yamancan/dumb-n-honest"


class RenderError(RuntimeError):
    pass


def friendly_model(provider: str, model_id: str) -> str:
    if provider == "claude" and model_id.startswith("claude-"):
        parts = model_id.removeprefix("claude-").split("-")
        family = parts[0].title()
        version_parts = parts[1:]
        if len(version_parts) >= 2 and all(part.isdigit() for part in version_parts[:2]):
            version = f"{version_parts[0]}.{version_parts[1]}"
            suffix = " ".join(part.title() for part in version_parts[2:])
        else:
            version = version_parts[0] if version_parts else ""
            suffix = " ".join(part.title() for part in version_parts[1:])
        return " ".join(part for part in ("Claude", family, version, suffix) if part)
    if provider == "codex":
        if model_id.startswith("gpt-"):
            parts = model_id.removeprefix("gpt-").split("-")
            base = f"GPT-{parts[0]}"
            suffix = " ".join(part.title() for part in parts[1:])
            return " ".join(part for part in ("Codex", base, suffix) if part)
        return f"Codex {model_id}"
    return model_id


def acknowledgment_for(model: dict[str, Any]) -> dict[str, Any]:
    current = model.get("acknowledged_correction")
    if not isinstance(current, dict):
        raise ValueError("aggregate has no acknowledged-correction metric")
    return current


def correction_subtype_for(model: dict[str, Any], subtype: str) -> dict[str, Any]:
    current = model.get(subtype)
    if not isinstance(current, dict):
        raise ValueError(f"aggregate has no {subtype.replace('_', '-')} metric")
    return current


def model_family_and_version(provider: str, model_id: str) -> tuple[str, tuple[int, ...]]:
    if provider == "claude":
        match = re.fullmatch(r"claude-([a-z]+)-([0-9-]+)", model_id)
        if match:
            parts = match[2].split("-")
            if len(parts) > 1 and len(parts[-1]) == 8:
                parts.pop()  # A snapshot date is not a minor version.
            return match[1], tuple(int(part) for part in parts)
    elif provider == "codex":
        match = re.fullmatch(r"gpt-([0-9.]+)(?:-(.+))?", model_id)
        if match:
            return match[2] or "gpt", tuple(int(part) for part in match[1].split("."))
    return model_id, (0,)


def recent_model_ids(models: list[tuple[str, dict[str, Any]]]) -> set[str]:
    recent = set()
    for provider in ("claude", "codex"):
        versions = sorted({model_family_and_version(provider, str(model["model_id"]))[1] for p, model in models if p == provider}, reverse=True)[:3]
        recent.update(str(model["model_id"]) for p, model in models if p == provider and model_family_and_version(provider, str(model["model_id"]))[1] in versions)
    return recent


def selected_models(result: dict[str, Any], *, include_older: bool = False) -> tuple[list[tuple[str, dict[str, Any]]], int]:
    eligible: list[tuple[str, dict[str, Any]]] = []
    omitted = 0
    for provider in ("claude", "codex"):
        provider_result = result.get("providers", {}).get(provider, {})
        families: dict[str, list[dict[str, Any]]] = {}
        for model in provider_result.get("models", []):
            if model.get("answered_human_turns", 0) < 1:
                continue
            family, _ = model_family_and_version(provider, str(model["model_id"]))
            families.setdefault(family, []).append(model)
        selected = []
        for family_models in families.values():
            family_models.sort(key=lambda model: (model_family_and_version(provider, str(model["model_id"]))[1], str(model["model_id"])), reverse=True)
            selected.extend(family_models[:3])
            omitted += max(0, len(family_models) - 3)
        selected.sort(key=lambda model: (model_family_and_version(provider, str(model["model_id"]))[1], str(model["model_id"])), reverse=True)
        selected.sort(key=lambda model: float(acknowledgment_for(model)["per_100_turns"]), reverse=True)
        eligible.extend((provider, model) for model in selected)
    if not include_older:
        recent = recent_model_ids(eligible)
        omitted += sum(str(model["model_id"]) not in recent for _, model in eligible)
        eligible = [(provider, model) for provider, model in eligible if str(model["model_id"]) in recent]
    return eligible, omitted


def build_rows(models: list[tuple[str, dict[str, Any]]], visible_ids: set[str] | None = None) -> str:
    if not models:
        return '<p class="omitted">No answered turns were attributed to an exact model.</p>'
    max_signal = max(
        100 * int(acknowledgment_for(model)["count"]) / int(model["answered_human_turns"])
        for _, model in models
    ) or 1.0
    chunks: list[str] = []
    previous_provider = None
    for provider, model in models:
        if provider != previous_provider:
            if previous_provider is not None:
                chunks.append("</div>")
            chunks.append(
                f'<div class="provider" data-provider="{provider}"><div class="provider-name">{html.escape(provider.title())}</div>'
            )
            previous_provider = provider
        acknowledgment = acknowledgment_for(model)
        rate = float(acknowledgment["per_100_turns"])
        owned = correction_subtype_for(model, "owned_error")
        conceded = correction_subtype_for(model, "conceded")
        owned_rate = float(owned["per_100_turns"])
        conceded_rate = float(conceded["per_100_turns"])
        denominator = int(model["answered_human_turns"])
        owned_width = 100 * (100 * int(owned["count"]) / denominator) / max_signal
        conceded_width = 100 * (100 * int(conceded["count"]) / denominator) / max_signal
        interval = acknowledgment.get("wilson_95_pct") or {"low": 0, "high": 0}
        sample_status = str(acknowledgment.get("sample_status") or "exploratory")
        sample_label = f" · {html.escape(sample_status)}" if sample_status != "sample-sufficient" else ""
        if denominator < 100:
            sample_label = " · <strong class=\"low-sample\">Low sample</strong>" + sample_label
        label = friendly_model(provider, str(model["model_id"]))
        model_id = str(model["model_id"])
        family, _ = model_family_and_version(provider, model_id)
        recent = visible_ids is None or model_id in visible_ids
        owned_signal = 100 * int(owned["count"]) / denominator
        conceded_signal = 100 * int(conceded["count"]) / denominator
        chunks.append(
            f'<div class="model" data-model-id="{html.escape(model_id, quote=True)}" data-family="{html.escape(family, quote=True)}" data-recent="{int(recent)}" data-owned-rate="{owned_signal}" data-conceded-rate="{conceded_signal}"{" hidden" if not recent else ""}>'
            '<div>'
            f'<div class="model-name">{html.escape(label)}</div>'
            f'<div class="model-usage">Usage: {model["answered_human_turns"]:,} answered turns · {int(acknowledgment["count"])} acknowledgments</div>'
            f'<div class="meta"><span class="owned-text">{owned_rate:.2f} owned</span> · '
            f'<span class="conceded-text">{conceded_rate:.2f} conceded</span> · '
            'total 95% CI '
            f'{float(interval.get("low", 0)):.2f}–{float(interval.get("high", 0)):.2f}'
            f'{sample_label}</div>'
            '<div class="bar">'
            f'<span class="bar-owned" style="width:{owned_width:.3f}%"></span>'
            f'<span class="bar-conceded" style="width:{conceded_width:.3f}%"></span>'
            '</div>'
            '</div>'
            '<div>'
            f'<div class="rate">{rate:.2f}</div>'
            '<div class="rate-label">acks /100 turns</div>'
            '</div>'
            '</div>'
        )
    chunks.append("</div>")
    return "".join(chunks)


def compact_model(provider: str, model_id: str) -> str:
    label = friendly_model(provider, model_id)
    if provider == "claude":
        parts = label.split()
        return " ".join(parts[1:3]) if len(parts) >= 3 else label
    if provider == "codex":
        return label.replace("Codex GPT-", "Codex ", 1)
    return label


def social_models(models: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    selected = []
    for provider in ("claude", "codex"):
        provider_models = [item for item in models if item[0] == provider and int(item[1]["answered_human_turns"]) >= 100]
        if provider == "claude":
            opus = [
                item
                for item in provider_models
                if str(item[1].get("model_id", "")).startswith("claude-opus-")
            ]
            if opus:
                provider_models = opus
        if provider_models:
            selected.append(provider_models[0])
    return selected


def build_tweet(
    models: list[tuple[str, dict[str, Any]]],
    github_url: str | None,
    quarantined_turns: int = 0,
    total_answered_turns: int | None = None,
) -> str:
    benchmark_url = github_url or DEFAULT_BENCHMARK_URL
    cta = "▶ Run yours locally: npx dumb-n-honest"
    featured = social_models(models)
    if not featured:
        disclosure = f" {quarantined_turns} unattributed turns excluded." if quarantined_turns else ""
        base = (
            "🤖 I audited my local coding-agent history for explicit correction acknowledgments. "
            "No exact model had 100 answered turns yet. "
            f"⚠️ Personal workload, not error rate.{disclosure}"
        )
        candidate = f"{base}\n\n{cta}\n\n{benchmark_url}"
        if len(candidate) <= 280:
            return candidate
        available = max(0, 278 - len(cta) - len(benchmark_url))
        return f"{base[:available].rstrip()}…\n\n{cta}\n\n{benchmark_url}"

    providers = {provider for provider, _ in featured}
    history = " + ".join(
        label for provider, label in (("claude", "Claude Code"), ("codex", "Codex"))
        if provider in providers
    ) or "coding-agent"
    turns = total_answered_turns
    if turns is None:
        turns = sum(int(model.get("answered_human_turns") or 0) for _, model in models)
    entries = []
    for provider, model in featured:
        acknowledgment = acknowledgment_for(model)
        entries.append(
            f"{compact_model(provider, str(model['model_id']))} · "
            f"{float(acknowledgment['per_100_turns']):.2f}"
        )
    result_lines = "\n".join(entries)
    disclosure = (
        f" {quarantined_turns} unattributed "
        f"{'turn was' if quarantined_turns == 1 else 'turns were'} excluded."
        if quarantined_turns
        else ""
    )
    candidates = [
        (
            f"🤖 I counted “you're right” across {turns:,} turns of {history} history.\n\n"
            f"{result_lines}\n\n"
            f"🖤 owned + 🟠 conceded: correction acknowledgments /100 turns. "
            f"⚠️ Personal workload, not error rate.{disclosure}\n\n"
            f"{cta}\n\n"
            f"{benchmark_url}"
        ),
        (
            f"🤖 I counted “you're right” across {turns:,} turns.\n\n"
            f"{result_lines}\n\n"
            f"🖤 owned + 🟠 conceded, per 100 turns. "
            f"⚠️ Personal workload, not error rate.{disclosure}\n\n"
            f"{cta}\n\n"
            f"{benchmark_url}"
        ),
        (
            f"🤖 How often does a coding agent admit being wrong?\n\n"
            f"{result_lines}\n\n"
            f"🖤 owned + 🟠 conceded, per 100 turns. "
            f"⚠️ Personal, not error rate.{disclosure}\n\n"
            f"{cta}\n\n"
            f"{benchmark_url}"
        ),
    ]
    for candidate in candidates:
        if len(candidate) <= 280:
            return candidate
    available = max(0, 278 - len(cta) - len(benchmark_url))
    base = candidates[-1].rsplit("\n\n", 1)[0]
    return f"{base[:available].rstrip()}…\n\n{cta}\n\n{benchmark_url}"


def quarantine_notes(result: dict[str, Any]) -> tuple[list[str], int]:
    notes = []
    total = 0
    for provider in ("claude", "codex"):
        diagnostics = result.get("providers", {}).get(provider, {}).get("diagnostics", {})
        turns = int(diagnostics.get("quarantined_model_turns") or 0)
        if not turns:
            continue
        share = float(diagnostics.get("quarantined_model_turn_share_pct") or 0)
        total += turns
        notes.append(
            f"{provider.title()}: {turns} {'turn' if turns == 1 else 'turns'} "
            f"excluded (unknown model, {share:.2f}%)"
        )
    return notes, total


def quality_failure_summary(result: dict[str, Any]) -> str:
    summaries = []
    statuses = (result.get("quality") or {}).get("provider_status") or {}
    for provider in ("claude", "codex"):
        status = statuses.get(provider)
        if not status or status in ("OK", "OK_WITH_WARNINGS"):
            continue
        diagnostics = result.get("providers", {}).get(provider, {}).get("diagnostics", {})
        counters = []
        for key in (
            "malformed_records",
            "file_errors",
            "files_vanished",
            "invalid_model_ids",
            "invalid_effort_values",
            "quarantined_model_turns",
        ):
            value = int(diagnostics.get(key) or 0)
            if value:
                counters.append(f"{key}={value}")
        if diagnostics.get("turn_reconciliation_ok") is False:
            counters.append("turn_reconciliation_ok=false")
        detail = f" ({', '.join(counters)})" if counters else ""
        summaries.append(f"{provider}={status}{detail}")
    return "; ".join(summaries) or "quality status unavailable"


def build_alt_text(
    models: list[tuple[str, dict[str, Any]]],
    omitted: int,
    quality_notes: list[str] | None = None,
    benchmark_url: str = DEFAULT_BENCHMARK_URL,
    max_length: int | None = 1000,
) -> str:
    if not models:
        return "No answered turns were attributed to an exact model; no comparison bars are shown."
    rows = []
    for provider, model in models:
        acknowledgment = acknowledgment_for(model)
        owned = correction_subtype_for(model, "owned_error")
        conceded = correction_subtype_for(model, "conceded")
        interval = acknowledgment["wilson_95_pct"]
        sample_label = " Low sample." if int(model["answered_human_turns"]) < 100 else ""
        rows.append(
            f"{friendly_model(provider, str(model['model_id']))}: "
            f"{owned['per_100_turns']:.2f} owned and {conceded['per_100_turns']:.2f} conceded "
            f"per 100 turns; total {acknowledgment['per_100_turns']:.2f} "
            f"({acknowledgment['count']} of {model['answered_human_turns']}; "
            f"total 95% CI {interval['low']:.2f} to {interval['high']:.2f}).{sample_label}"
        )
    suffix = (
        f" {omitted} older "
        f"{'version' if omitted == 1 else 'versions'} omitted (recent generations; at most three per model family)."
        if omitted
        else ""
    )
    quality_suffix = f" Data quality: {'; '.join(quality_notes)}." if quality_notes else ""
    text = (
        "Stacked bar chart grouped by provider. Black means explicit ownership such as "
        "I was wrong; orange means explicit acceptance such as You're right. "
        "Higher is not worse; personal workload, not error rate. "
        + " ".join(rows)
        + suffix + quality_suffix
        + f" Run yours locally with npx dumb-n-honest. Benchmark: {benchmark_url}."
    )
    if max_length is None or len(text) <= max_length:
        return text
    # Keep every model in the shorter image description instead of silently
    # cutting off the models at the end of a large chart.
    compact = (
        "Correction acknowledgments per 100 answered turns; black owned, orange conceded. "
        "Higher is not worse; this is not error rate. "
        + " ".join(
            f"{friendly_model(provider, str(model['model_id']))}: "
            f"{correction_subtype_for(model, 'owned_error')['per_100_turns']:.2f} owned and "
            f"{correction_subtype_for(model, 'conceded')['per_100_turns']:.2f} conceded per 100 turns; "
            f"total {acknowledgment_for(model)['per_100_turns']:.2f} "
            f"({acknowledgment_for(model)['count']}/{model['answered_human_turns']})"
            + (", low sample." if int(model["answered_human_turns"]) < 100 else ".")
            for provider, model in models
        )
        + suffix + quality_suffix
        + f" Run yours locally with npx dumb-n-honest. Benchmark: {benchmark_url}."
    )
    if len(compact) <= max_length:
        return compact
    return (
        f"Chart of {len(models)} exact models, grouped by provider. Correction acknowledgments "
        "per 100 answered turns; black is explicit ownership, orange explicit acceptance. "
        "Up to three latest versions per model family; fewer than 100 turns are marked low sample. "
        "Higher is not worse; personal workload, not error rate. "
        "Full model counts, rates and confidence intervals are in the local report."
        + suffix + quality_suffix
    )[:max_length]


def build_chart_svg(models: list[tuple[str, dict[str, Any]]], description: str, quality_notes: list[str], benchmark_url: str) -> str:
    """A browser-independent image export of the complete chart."""
    provider_count = len({provider for provider, _ in models})
    height = max(1350, 350 + provider_count * 44 + len(models) * 110 + 140 + len(quality_notes) * 24)
    ink, muted, orange = "#111111", "#676767", "#c4512d"
    font = "system-ui, -apple-system, sans-serif"
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="{height}" viewBox="0 0 1080 {height}" role="img" aria-labelledby="title description" data-quality-lines="{len(quality_notes)}">',
        '<title id="title">Dumb n Honest — correction acknowledgments</title>',
        f'<desc id="description">{html.escape(description)}</desc>',
        f'<rect width="1080" height="{height}" fill="#f6f4ef"/>',
        f'<g font-family="{font}" fill="{ink}">',
    ]

    def text(x: int, y: int, value: str, size: int = 14, color: str = ink, extra: str = "") -> None:
        chunks.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" {extra}>{html.escape(value)}</text>')

    text(72, 90, "LOCAL CODING-AGENT AUDIT", 18, muted)
    text(72, 182, "Dumb n Honest", 84, extra='font-weight="750" letter-spacing="-4"')
    text(72, 232, "Correction acknowledgments / 100 answered turns.", 25)
    chunks.extend([
        '<rect x="72" y="275" width="24" height="10" fill="#111111"/>',
        f'<rect x="460" y="275" width="24" height="10" fill="{orange}"/>',
        '<path d="M72 258H1008M72 312H1008" stroke="#d8d8d8"/>',
    ])
    text(108, 286, "“I was wrong” · owned error", 18)
    text(496, 286, "“You’re right” · conceded", 18)
    max_rate = max((100 * int(acknowledgment_for(model)["count"]) / int(model["answered_human_turns"]) for _, model in models), default=0) or 1
    y = 350
    previous_provider = None
    for provider, model in models:
        if provider != previous_provider:
            chunks.append(f'<g data-provider-header="{provider}" data-base-y="{y}">')
            text(72, y, provider.upper(), 16, muted)
            chunks.append("</g>")
            y += 44
            previous_provider = provider
        ack = acknowledgment_for(model)
        owned = correction_subtype_for(model, "owned_error")
        conceded = correction_subtype_for(model, "conceded")
        n = int(model["answered_human_turns"])
        interval = ack["wilson_95_pct"]
        status = "Low sample · " if n < 100 else ""
        status += str(ack.get("sample_status") or "exploratory")
        label = friendly_model(provider, str(model["model_id"]))
        row_description = f'{label}: {float(owned["per_100_turns"]):.2f} owned and {float(conceded["per_100_turns"]):.2f} conceded per 100 turns; total {float(ack["per_100_turns"]):.2f}; {int(ack["count"])} of {n}; 95% CI {float(interval["low"]):.2f}–{float(interval["high"]):.2f}; {status}.'
        chunks.append(f'<g data-model-id="{html.escape(str(model["model_id"]), quote=True)}" data-provider="{provider}" data-base-y="{y}" data-owned-rate="{100 * int(owned["count"]) / n}" data-conceded-rate="{100 * int(conceded["count"]) / n}" data-description="{html.escape(row_description, quote=True)}">')
        text(72, y, friendly_model(provider, str(model["model_id"])), 23, extra='font-weight="700"')
        text(1008, y + 4, f'{float(ack["per_100_turns"]):.2f}', 34, extra='text-anchor="end" font-weight="750"')
        text(72, y + 25, f'Usage: {n:,} answered turns · {int(ack["count"])} acknowledgments', 15)
        text(72, y + 47, f'{float(owned["per_100_turns"]):.2f} owned · {float(conceded["per_100_turns"]):.2f} conceded · 95% CI {float(interval["low"]):.2f}–{float(interval["high"]):.2f} · {status}', 14, muted)
        text(1008, y + 27, "acks /100 turns", 13, muted, 'text-anchor="end"')
        owned_width = 748 * (100 * int(owned["count"]) / n) / max_rate
        conceded_width = 748 * (100 * int(conceded["count"]) / n) / max_rate
        chunks.extend([
            f'<rect x="72" y="{y + 63}" width="748" height="11" fill="#e5e2db"/>',
            f'<rect class="bar-owned" x="72" y="{y + 63}" width="{owned_width:.3f}" height="11" fill="{ink}"/>',
            f'<rect class="bar-conceded" x="{72 + owned_width:.3f}" y="{y + 63}" width="{conceded_width:.3f}" height="11" fill="{orange}"/>',
            f'<path d="M72 {y + 91}H1008" stroke="#d8d8d8"/>',
            '</g>',
        ])
        y += 110
    footer_y = height - 110 - len(quality_notes) * 24
    chunks.append(f'<g id="chart-footer" data-base-y="{footer_y}">')
    text(72, footer_y, "Higher ≠ worse. Acknowledgment rate, not model error rate.", 18)
    text(72, footer_y + 30, "Up to 3 versions per family · Sorted by acknowledgment rate within providers.", 15, muted)
    text(72, footer_y + 60, "Run yours locally: npx dumb-n-honest", 18)
    text(72, footer_y + 83, benchmark_url, 13, muted)
    for index, note in enumerate(quality_notes):
        text(72, footer_y + 107 + index * 24, note, 13, muted)
    chunks.append("</g></g></svg>")
    return "".join(chunks)


def render_svg_png(chart: str) -> bytes:
    renderer = shutil.which("rsvg-convert")
    if renderer is None:
        raise RenderError("PNG file export needs rsvg-convert; Download PNG in report.html still works in your browser.")
    try:
        rendered = subprocess.run([renderer, "--format", "png"], input=chart.encode("utf-8"), capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise RenderError("The chart PNG could not be exported; use Download PNG in report.html.") from None
    if rendered.returncode != 0 or not rendered.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RenderError("The chart PNG could not be exported; use Download PNG in report.html.")
    return rendered.stdout


def build_workspace(
    result: dict[str, Any], models: list[tuple[str, dict[str, Any]]],
    draft: str, description: str, quality_notes: list[str], benchmark_url: str, omitted: int,
    png: bytes | None = None,
) -> str:
    template = (SKILL_ROOT / "assets" / "workspace.html").read_text(encoding="utf-8")
    script = (SKILL_ROOT / "assets" / "workspace.js").read_text(encoding="utf-8")
    status = (result.get("quality") or {}).get("provider_status") or {}
    quality_html = "".join(
        f'<li>{html.escape(provider.title())}: {html.escape(str(status.get(provider, "unavailable")))}</li>'
        for provider in ("claude", "codex")
    ) + "".join(f"<li>{html.escape(note)}</li>" for note in quality_notes)
    all_models, family_omitted = selected_models(result, include_older=True)
    visible_ids = {str(model["model_id"]) for _, model in models}
    chart = build_chart_svg(models, description, quality_notes, benchmark_url)
    all_description = build_alt_text(all_models, family_omitted, quality_notes, benchmark_url, max_length=None)
    full_chart = build_chart_svg(all_models, all_description, quality_notes, benchmark_url)
    options = []
    for provider, model in all_models:
        model_id = str(model["model_id"])
        family, _ = model_family_and_version(provider, model_id)
        recent = model_id in visible_ids
        options.append(
            f'<label class="model-option" data-provider="{provider}" data-family="{html.escape(family, quote=True)}" data-recent="{int(recent)}"{" hidden" if not recent else ""}>'
            f'<input class="model-toggle" type="checkbox" value="{html.escape(model_id, quote=True)}"{" checked" if recent else ""}>'
            f'{html.escape(friendly_model(provider, model_id))} <span class="hint">N={model["answered_human_turns"]:,}</span></label>'
        )
    families = sorted({model_family_and_version(provider, str(model["model_id"]))[0] for provider, model in all_models})
    family_options = ''.join(f'<option value="{html.escape(family, quote=True)}">{html.escape(family.replace("-", " ").title())}</option>' for family in families)
    png_download = (
        f'<button class="lead" id="download-png" type="button" data-default-models="{html.escape(json.dumps(sorted(visible_ids)), quote=True)}" data-default-png="data:image/png;base64,{base64.b64encode(png).decode("ascii")}">Download PNG</button>'
        if png else '<button class="lead" id="download-png" type="button">Download PNG</button>'
    )
    values = {
        "ROWS": build_rows(all_models, visible_ids),
        "MODEL_COUNT": str(len(models)),
        "TURN_COUNT": f'{sum(int(model.get("answered_human_turns") or 0) for provider in result.get("providers", {}).values() for model in provider.get("models", [])):,}',
        "PROVIDER_COUNT": str(len({provider for provider, _ in models})),
        "DRAFT": html.escape(draft),
        "DESCRIPTION": html.escape(description),
        "QUALITY": quality_html,
        "CHART_DATA": base64.b64encode(chart.encode("utf-8")).decode("ascii"),
        "FULL_CHART_DATA": base64.b64encode(full_chart.encode("utf-8")).decode("ascii"),
        "MODEL_OPTIONS": "".join(options),
        "FAMILY_OPTIONS": family_options,
        "PNG_DOWNLOAD": png_download,
        "BENCHMARK_URL": html.escape(benchmark_url, quote=True),
        "SCRIPT": script,
        "SELECTION_NOTE": f"{omitted} older {'version is' if omitted == 1 else 'versions are'} hidden by default." if omitted else "Every observed version is shown.",
    }
    return re.sub(r"@@([A-Z_]+)@@", lambda match: values[match.group(1)], template)


def write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def find_browser() -> Path | None:
    fixed_candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
    ]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            fixed_candidates.extend(
                [
                    Path(base) / "Google/Chrome/Application/chrome.exe",
                    Path(base) / "Microsoft/Edge/Application/msedge.exe",
                    Path(base) / "BraveSoftware/Brave-Browser/Application/brave.exe",
                ]
            )
    for candidate in fixed_candidates:
        if candidate.is_file():
            return candidate
    for command in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "msedge",
        "msedge.exe",
        "chrome",
        "chrome.exe",
        "brave-browser",
        "brave.exe",
    ):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)
    return None


def render_png(poster_html: Path, output: Path) -> None:
    browser = find_browser()
    if browser is None:
        raise RenderError(
            "PNG rendering requires an installed Chrome, Chromium, Edge, or Brave browser; "
            "poster.html was preserved."
        )
    uri = poster_html.resolve().as_uri()
    with tempfile.TemporaryDirectory(prefix="dnh-browser-") as profile_dir:
        common = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile_dir}",
        ]
        try:
            measured = subprocess.run(
                [*common, "--dump-dom", uri],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=10,
            )
            measured_stdout = measured.stdout
            measured_ok = measured.returncode == 0
        except subprocess.TimeoutExpired as error:
            measured_stdout = error.stdout or ""
            if isinstance(measured_stdout, bytes):
                measured_stdout = measured_stdout.decode("utf-8", errors="replace")
            measured_ok = "<html" in measured_stdout.casefold()
        if not measured_ok:
            raise RenderError("Local browser could not measure poster.html; the HTML was preserved.")
        height_match = re.search(r'data-poster-height="(\d+)"', measured_stdout)
        if height_match is None:
            raise RenderError("Local browser could not measure poster height; the HTML was preserved.")
        poster_height = max(1350, int(height_match.group(1)))
        try:
            rendered = subprocess.run(
                [
                    *common,
                    "--run-all-compositor-stages-before-draw",
                    f"--window-size=1080,{poster_height}",
                    f"--screenshot={output}",
                    uri,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
            rendered_ok = rendered.returncode == 0
        except subprocess.TimeoutExpired:
            rendered_ok = output.is_file()
        if not rendered_ok or not output.is_file():
            raise RenderError("Local browser could not render poster.png; poster.html was preserved.")
    try:
        output.chmod(0o600)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Render aggregate dumb-n-honest results.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--github-url",
        help=f"Override the benchmark link (default: {DEFAULT_BENCHMARK_URL}).",
    )
    parser.add_argument("--no-png", action="store_true")
    parser.add_argument("--require-png", action="store_true")
    parser.add_argument("--export-share-pack", action="store_true", help="Also export separate poster, draft and alt-text files (PNG is best-effort).")
    args = parser.parse_args()

    if args.no_png and args.require_png:
        parser.error("--no-png and --require-png cannot be combined")

    result = json.loads(args.input.read_text(encoding="utf-8"))
    quality = result.get("quality") or {}
    if result.get("schema_version") != "2.0" or quality.get("shareable") is not True:
        raise SystemExit(
            f"Aggregate quality checks failed: {quality_failure_summary(result)}. "
            "No share pack was generated."
        )
    models, omitted = selected_models(result)
    quality_notes, quarantined_turns = quarantine_notes(result)
    benchmark_url = args.github_url or DEFAULT_BENCHMARK_URL
    parsed_url = urlsplit(benchmark_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        parser.error("--github-url must be an HTTP or HTTPS URL")
    template = (SKILL_ROOT / "assets" / "poster.html").read_text(encoding="utf-8")
    omitted_text = (
        f'<p class="omitted">{omitted} older '
        f'{"version" if omitted == 1 else "versions"} omitted (recent generations; at most three per model family).</p>'
        if omitted
        else ""
    )
    quality_text = (
        f'<p class="omitted">Data quality: {html.escape("; ".join(quality_notes))}.</p>'
        if quality_notes
        else ""
    )
    poster = (
        template.replace("@@BENCHMARK_URL@@", html.escape(benchmark_url))
        .replace("@@ROWS@@", build_rows(models))
        .replace("@@OMITTED@@", omitted_text + quality_text)
    )
    total_turns = sum(
        int(model.get("answered_human_turns") or 0)
        for provider in result.get("providers", {}).values()
        for model in provider.get("models", [])
    )
    draft = build_tweet(models, benchmark_url, quarantined_turns, total_turns)
    description = build_alt_text(models, omitted, quality_notes, benchmark_url, max_length=None)
    export_share_pack = args.export_share_pack or args.require_png

    if args.output_dir.is_symlink():
        raise SystemExit("Share-pack output directory must not be a symlink.")
    output_was_created = not args.output_dir.exists()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if output_was_created:
            args.output_dir.chmod(0o700)
    except OSError:
        pass
    targets = [args.output_dir / "report.html"]
    if not args.no_png:
        targets.append(args.output_dir / "chart.png")
    if export_share_pack:
        targets.extend(args.output_dir / name for name in ("poster.html", "tweet.txt", "alt-text.txt"))
    if export_share_pack and not args.no_png:
        targets.append(args.output_dir / "poster.png")
    if any(path.exists() or path.is_symlink() for path in targets):
        raise SystemExit("Share-pack output already exists; no files were overwritten.")
    png = None
    if not args.no_png:
        try:
            png = render_svg_png(build_chart_svg(models, description, quality_notes, benchmark_url))
        except RenderError as error:
            print(f"warning: {error}", file=sys.stderr)
    workspace = build_workspace(result, models, draft, description, quality_notes, benchmark_url, omitted, png)
    write_private(args.output_dir / "report.html", workspace)
    print(args.output_dir / "report.html")
    if png:
        png_path = args.output_dir / "chart.png"
        png_path.write_bytes(png)
        png_path.chmod(0o600)
        print(png_path)
    if not export_share_pack:
        return
    write_private(args.output_dir / "poster.html", poster)
    write_private(args.output_dir / "tweet.txt", draft + "\n")
    write_private(args.output_dir / "alt-text.txt", build_alt_text(models, omitted, quality_notes, benchmark_url) + "\n")

    if not args.no_png:
        try:
            if png:
                (args.output_dir / "poster.png").write_bytes(png)
                (args.output_dir / "poster.png").chmod(0o600)
            else:
                render_png(args.output_dir / "poster.html", args.output_dir / "poster.png")
        except RenderError as error:
            if args.require_png:
                raise SystemExit(str(error)) from None
            print(f"warning: {error}", file=sys.stderr)
    print(args.output_dir / "poster.html")
    if (args.output_dir / "poster.png").is_file():
        print(args.output_dir / "poster.png")
    print(args.output_dir / "tweet.txt")
    print(args.output_dir / "alt-text.txt")


if __name__ == "__main__":
    try:
        main()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise SystemExit("Aggregate results could not be read or rendered.") from None
