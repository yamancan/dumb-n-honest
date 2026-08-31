#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


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


def selected_models(result: dict[str, Any]) -> tuple[list[tuple[str, dict[str, Any]]], int]:
    eligible: list[tuple[str, dict[str, Any]]] = []
    omitted = 0
    for provider in ("claude", "codex"):
        provider_result = result.get("providers", {}).get(provider, {})
        provider_models = []
        for model in provider_result.get("models", []):
            if model.get("answered_human_turns", 0) < 100:
                omitted += 1
            else:
                provider_models.append(model)
        provider_models.sort(key=lambda model: -int(model["answered_human_turns"]))
        omitted += max(0, len(provider_models) - 3)
        selected = provider_models[:3]
        if provider == "claude":
            selected.sort(
                key=lambda model: (
                    not str(model.get("model_id", "")).startswith("claude-opus-"),
                    -int(model["answered_human_turns"]),
                )
            )
        eligible.extend((provider, model) for model in selected)
    return eligible, omitted


def build_rows(models: list[tuple[str, dict[str, Any]]]) -> str:
    if not models:
        return '<p class="omitted">No exact model has at least 100 answered turns.</p>'
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
                f'<div class="provider"><div class="provider-name">{html.escape(provider.title())}</div>'
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
        label = friendly_model(provider, str(model["model_id"]))
        chunks.append(
            '<div class="model">'
            '<div>'
            f'<div class="model-name">{html.escape(label)}</div>'
            f'<div class="meta"><span class="owned-text">{owned_rate:.2f} owned</span> · '
            f'<span class="conceded-text">{conceded_rate:.2f} conceded</span> · '
            f'N={model["answered_human_turns"]:,} · total 95% CI '
            f'{float(interval.get("low", 0)):.2f}–{float(interval.get("high", 0)):.2f}'
            f'{sample_label}</div>'
            '<div class="bar">'
            f'<span class="bar-owned" style="width:{owned_width:.3f}%"></span>'
            f'<span class="bar-conceded" style="width:{conceded_width:.3f}%"></span>'
            '</div>'
            '</div>'
            '<div>'
            f'<div class="rate">{rate:.2f}</div>'
            '<div class="rate-label">total / 100</div>'
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
    opus = [
        item
        for item in models
        if item[0] == "claude" and str(item[1].get("model_id", "")).startswith("claude-opus-")
    ][:2]
    if not opus:
        opus = [item for item in models if item[0] == "claude"][:2]
    codex = [item for item in models if item[0] == "codex"][:2]
    return opus + codex


def build_tweet(
    models: list[tuple[str, dict[str, Any]]],
    github_url: str | None,
    quarantined_turns: int = 0,
) -> str:
    benchmark_url = github_url or DEFAULT_BENCHMARK_URL
    if not models:
        base = (
            "I audited my local coding-agent history for explicit correction acknowledgments. "
            "No exact model had 100 answered turns yet. Personal observational benchmark—not model error rate."
        )
    else:
        entries = []
        for provider, model in social_models(models):
            owned = correction_subtype_for(model, "owned_error")
            conceded = correction_subtype_for(model, "conceded")
            label = compact_model(provider, str(model["model_id"]))
            entries.append(
                f"{label} {owned['per_100_turns']:.2f}+{conceded['per_100_turns']:.2f}"
            )
        suffix = (
            f"Observational—not model error rate. {quarantined_turns} unattributed "
            f"{'turn' if quarantined_turns == 1 else 'turns'} excluded."
            if quarantined_turns
            else "Observational—not model error rate."
        )
        base = (
            "My correction-acknowledgment rates /100 turns (I was wrong + You’re right): "
            + "; ".join(entries)
            + f". {suffix}"
        )
    candidate = f"{base} {benchmark_url}"
    if len(candidate) <= 280:
        return candidate
    available = max(0, 278 - len(benchmark_url))
    return f"{base[:available].rstrip()}… {benchmark_url}"


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
) -> str:
    if not models:
        return "No model had at least 100 answered turns; no comparison bars are shown."
    rows = []
    for provider, model in models:
        acknowledgment = acknowledgment_for(model)
        owned = correction_subtype_for(model, "owned_error")
        conceded = correction_subtype_for(model, "conceded")
        interval = acknowledgment["wilson_95_pct"]
        rows.append(
            f"{friendly_model(provider, str(model['model_id']))}: "
            f"{owned['per_100_turns']:.2f} owned and {conceded['per_100_turns']:.2f} conceded "
            f"per 100 turns; total {acknowledgment['per_100_turns']:.2f} "
            f"({acknowledgment['count']} of {model['answered_human_turns']}; "
            f"total 95% CI {interval['low']:.2f} to {interval['high']:.2f})."
        )
    suffix = (
        f" {omitted} low-sample or overflow "
        f"{'model' if omitted == 1 else 'models'} omitted."
        if omitted
        else ""
    )
    quality_suffix = f" Data quality: {'; '.join(quality_notes)}." if quality_notes else ""
    text = (
        "Stacked bar chart grouped by provider. Black means explicit ownership such as "
        "I was wrong; orange means explicit acceptance such as You're right. "
        + " ".join(rows)
        + suffix
        + quality_suffix
        + f" Benchmark: {benchmark_url}."
    )
    return text[:1000]


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
                text=True,
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
        if 'data-overflow="true"' in measured_stdout:
            raise RenderError("Poster content exceeds 1080x1350; the HTML was preserved without PNG.")
        try:
            rendered = subprocess.run(
                [
                    *common,
                    "--run-all-compositor-stages-before-draw",
                    "--window-size=1080,1350",
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
    template = (SKILL_ROOT / "assets" / "poster.html").read_text(encoding="utf-8")
    omitted_text = (
        f'<p class="omitted">{omitted} additional low-sample '
        f'{"model" if omitted == 1 else "models"} omitted.</p>'
        if omitted
        else ""
    )
    quality_text = (
        f'<p class="omitted">Data quality — {html.escape("; ".join(quality_notes))}.</p>'
        if quality_notes
        else ""
    )
    poster = (
        template.replace("@@BENCHMARK_URL@@", html.escape(benchmark_url))
        .replace("@@ROWS@@", build_rows(models))
        .replace("@@OMITTED@@", omitted_text + quality_text)
    )

    if args.output_dir.is_symlink():
        raise SystemExit("Share-pack output directory must not be a symlink.")
    output_was_created = not args.output_dir.exists()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if output_was_created:
            args.output_dir.chmod(0o700)
    except OSError:
        pass
    targets = [
        args.output_dir / "poster.html",
        args.output_dir / "tweet.txt",
        args.output_dir / "alt-text.txt",
    ]
    if not args.no_png:
        targets.append(args.output_dir / "poster.png")
    if any(path.exists() or path.is_symlink() for path in targets):
        raise SystemExit("Share-pack output already exists; no files were overwritten.")
    write_private(args.output_dir / "poster.html", poster)
    write_private(
        args.output_dir / "tweet.txt",
        build_tweet(models, benchmark_url, quarantined_turns) + "\n",
    )
    write_private(
        args.output_dir / "alt-text.txt",
        build_alt_text(models, omitted, quality_notes, benchmark_url) + "\n",
    )

    if not args.no_png:
        try:
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
