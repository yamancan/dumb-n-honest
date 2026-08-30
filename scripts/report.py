#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]


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


def language_label(languages: list[str]) -> str:
    names = {"en": "English", "tr": "Turkish"}
    return " + ".join(names.get(language, language.upper()) for language in languages)


def selected_models(result: dict[str, Any]) -> tuple[list[tuple[str, dict[str, Any]]], int]:
    eligible: list[tuple[str, dict[str, Any]]] = []
    omitted = 0
    for provider in ("claude", "codex"):
        provider_result = result.get("providers", {}).get(provider, {})
        for model in provider_result.get("models", []):
            if model.get("answered_human_turns", 0) < 100:
                omitted += 1
            else:
                eligible.append((provider, model))
    eligible.sort(key=lambda item: ((0 if item[0] == "claude" else 1), -item[1]["answered_human_turns"]))
    if len(eligible) > 6:
        omitted += len(eligible) - 6
        eligible = eligible[:6]
    return eligible, omitted


def reasoning_label(reasoning: dict[str, Any]) -> str:
    unit_coverage = float(reasoning.get("coverage_pct") or 0)
    turn_coverage = float(
        reasoning.get("answered_turn_coverage_pct")
        if reasoning.get("answered_turn_coverage_pct") is not None
        else unit_coverage
    )
    if min(unit_coverage, turn_coverage) < 95:
        if round(unit_coverage) != round(turn_coverage):
            return (
                "reasoning n/a — partial coverage "
                f"({unit_coverage:.0f}% units · {turn_coverage:.0f}% turns)"
            )
        return f"reasoning n/a — partial coverage ({unit_coverage:.0f}%)"
    tokens = reasoning.get("tokens_per_covered_answered_turn")
    if tokens is None:
        return f"reasoning n/a · {turn_coverage:.0f}% turn coverage"
    return f"{tokens:,.0f} reasoning tokens / covered turn · {turn_coverage:.0f}% coverage"


def build_rows(models: list[tuple[str, dict[str, Any]]]) -> str:
    if not models:
        return '<p class="omitted">No exact model has at least 100 answered turns.</p>'
    max_signal = max(
        float(model["owned_error"]["per_100_turns"])
        + float(model["conceded"]["per_100_turns"])
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
        owned = float(model["owned_error"]["per_100_turns"])
        conceded = float(model["conceded"]["per_100_turns"])
        owned_width = 100 * owned / max_signal
        conceded_width = 100 * conceded / max_signal
        date_range = model.get("date_range") or {}
        first = date_range.get("first") or "unknown"
        last = date_range.get("last") or "unknown"
        label = friendly_model(provider, str(model["model_id"]))
        chunks.append(
            '<div class="model">'
            '<div>'
            f'<div class="model-name">{html.escape(label)}</div>'
            f'<div class="meta">N={model["answered_human_turns"]:,} · {model.get("usage_share_pct", 0):.2f}% provider usage · {html.escape(str(first))}–{html.escape(str(last))}</div>'
            '<div class="bar">'
            f'<span class="bar-owned" style="width:{owned_width:.3f}%"></span>'
            f'<span class="bar-conceded" style="width:{conceded_width:.3f}%"></span>'
            '</div>'
            f'<div class="reasoning">{html.escape(reasoning_label(model.get("reasoning") or {}))}</div>'
            '</div>'
            '<div>'
            f'<div class="rate">{owned:.2f}</div>'
            f'<div class="rate-label">owned / 100<br>{model["owned_error"]["count"]} owned · {model["conceded"]["count"]} conceded</div>'
            '</div>'
            '</div>'
        )
    chunks.append("</div>")
    return "".join(chunks)


def build_tweet(models: list[tuple[str, dict[str, Any]]], github_url: str | None) -> str:
    if not models:
        base = "I audited my local coding-agent history. No exact model had 100 answered turns yet."
    else:
        provider, model = max(
            models, key=lambda item: float(item[1]["owned_error"]["per_100_turns"])
        )
        label = friendly_model(provider, str(model["model_id"]))
        base = (
            f"{label} explicitly admitted {model['owned_error']['count']} errors in "
            f"{model['answered_human_turns']:,} answered turns "
            f"({model['owned_error']['per_100_turns']:.2f}/100). "
            "This counts admissions, not all mistakes. Local audit; not a benchmark."
        )
    if github_url:
        candidate = f"{base} {github_url}"
        if len(candidate) <= 280:
            base = candidate
    if len(base) > 280:
        base = base[:277].rstrip() + "…"
    return base


def build_alt_text(models: list[tuple[str, dict[str, Any]]], omitted: int) -> str:
    rows = []
    for provider, model in models:
        rows.append(
            f"{friendly_model(provider, str(model['model_id']))}: "
            f"{model['owned_error']['per_100_turns']:.2f} owned errors per 100 turns "
            f"({model['owned_error']['count']} of {model['answered_human_turns']}), "
            f"plus {model['conceded']['count']} concessions."
        )
    suffix = f" {omitted} low-sample or overflow model omitted." if omitted else ""
    text = "Bar chart grouped by provider. " + " ".join(rows) + suffix
    return text[:1000]


def write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def find_browser() -> Path | None:
    fixed_candidates = (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
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
        "brave-browser",
    ):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)
    return None


def render_png(poster_html: Path, output: Path) -> None:
    browser = find_browser()
    if browser is None:
        raise SystemExit(
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
            raise SystemExit("Local browser could not measure poster.html; the HTML was preserved.")
        if 'data-overflow="true"' in measured_stdout:
            raise SystemExit("Poster content exceeds 1080x1350; the HTML was preserved without PNG.")
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
            raise SystemExit("Local browser could not render poster.png; poster.html was preserved.")
    try:
        output.chmod(0o600)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Render aggregate dumb-n-honest results.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-url")
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args()

    result = json.loads(args.input.read_text(encoding="utf-8"))
    models, omitted = selected_models(result)
    template = (SKILL_ROOT / "assets" / "poster.html").read_text(encoding="utf-8")
    omitted_text = (
        f'<p class="omitted">{omitted} low-sample model omitted from the poster; retained in results.json.</p>'
        if omitted == 1
        else (
            f'<p class="omitted">{omitted} low-sample or overflow models omitted from the poster; retained in results.json.</p>'
            if omitted
            else ""
        )
    )
    poster = (
        template.replace("@@LANGUAGES@@", html.escape(language_label(result.get("languages", []))))
        .replace("@@ROWS@@", build_rows(models))
        .replace("@@OMITTED@@", omitted_text)
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
    write_private(args.output_dir / "tweet.txt", build_tweet(models, args.github_url) + "\n")
    write_private(args.output_dir / "alt-text.txt", build_alt_text(models, omitted) + "\n")

    if not args.no_png:
        render_png(args.output_dir / "poster.html", args.output_dir / "poster.png")
    print(args.output_dir / "poster.html")
    if not args.no_png:
        print(args.output_dir / "poster.png")
    print(args.output_dir / "tweet.txt")
    print(args.output_dir / "alt-text.txt")


if __name__ == "__main__":
    try:
        main()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise SystemExit("Aggregate results could not be read or rendered.") from None
