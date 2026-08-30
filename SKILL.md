---
name: dumb-n-honest
description: Run only when the user explicitly asks to audit local Claude Code or Codex self-corrections; keep transcript content private and return aggregate results plus a share pack.
license: MIT
metadata:
  version: "0.1.0"
---

# Dumb n Honest

Run the deterministic local audit; never inspect transcript files directly.

Requires Python 3.10+ and local Claude Code or Codex history. A Chromium-family browser is optional
for PNG export. No network access is required.

## Authorization gate

Proceed only when the current user request explicitly asks to run this audit. If this skill was
loaded implicitly, do not access local histories; explain how the user can invoke it and stop.

## Run

1. Resolve the directory containing this `SKILL.md` as `SKILL_DIR`.
2. Choose a new or empty output directory outside the skill source repository when possible. The
   command refuses to overwrite an earlier run.
3. Run:

```bash
python3 "$SKILL_DIR/scripts/run.py" \
  --provider all \
  --languages en,tr \
  --output-dir "<new-output-directory>"
```

Pass `--github-url` only when the user supplies one. Use `--provider claude` or `--provider codex`
when requested. Use `--no-png` only when the user wants aggregate/HTML output or no supported local
browser is available.

4. Report the paths to `results.json`, `poster.png` or preserved `poster.html`, `tweet.txt`, and
   `alt-text.txt`.
5. State: this measures explicit self-corrections in visible replies, not every mistake or model
   accuracy.

## Privacy boundary

The scripts are the transcript boundary. They may read local JSONL; the model may read only their
aggregate stdout and generated aggregate files. Never print, search, quote, summarize, or attach
prompts, replies, transcript-derived paths, session IDs, request IDs, projects, usernames, emails,
or excerpts. The chosen aggregate output directory is the only path that may be surfaced.

The scripts perform no network requests and never post automatically. A generated tweet is a draft;
leave publication to the user.

For metric interpretation or language-pattern changes, read
[references/measurement.md](references/measurement.md). Ordinary runs do not require loading it.
