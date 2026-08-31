---
name: dumb-n-honest
description: Run a private local benchmark of explicit correction acknowledgments in Claude Code and Codex history.
license: MIT
metadata:
  version: "0.2.5"
---

# Dumb n Honest

Run the deterministic local audit; let the scripts read transcripts and expose only aggregates.

Requires Python 3.10+ and local Claude Code or Codex history. A Chromium-family browser is optional
for PNG export and may require explicit launch approval in a sandboxed agent. Runtime requires no
package install or network access.

## Authorization gate

Proceed only when the current user explicitly asks to run this audit. If loaded implicitly, do not
access local histories; explain how to invoke the skill explicitly and stop.

## Run

1. Resolve the directory containing this file as `SKILL_DIR`.
2. Choose a new or empty output directory outside the skill source repository when possible.
3. Optionally check availability without reading transcript content:

```bash
python3 "$SKILL_DIR/scripts/doctor.py" --provider all
```

4. Run:

```bash
python3 "$SKILL_DIR/scripts/run.py" \
  --provider all \
  --languages en,tr \
  --output-dir "<new-output-directory>"
```

The share pack links to the canonical benchmark repository. Pass `--github-url` only when the user
supplies an override. Honor provider or language restrictions the user requests. PNG is best-effort;
use `--require-png` only when the user requires it and `--no-png` when they want HTML/aggregate
output only.

5. Report the generated `results.json`, `poster.png` when available or preserved `poster.html`,
`tweet.txt`, and `alt-text.txt`. State that the rate measures explicit correction acknowledgments in
the user's observed workload, not model error rate. Explain that the share artifacts split the total
into explicit ownership (`I was wrong`) and explicit acceptance (`You're right`). Never publish
automatically.

## Privacy boundary

The scripts are the transcript boundary. They may read local JSONL; the model may read only their
aggregate stdout and generated aggregate files. Surface only the operator-selected output path.

Keep prompts, replies, transcript-derived paths, projects, session/request IDs, usernames, emails,
handles, and excerpts outside model context and output. Keep `results.json` private; suggest sharing
only the previewed poster, post draft, and alt text.

For metric interpretation, adapters, or pattern changes, read
[references/measurement.md](references/measurement.md). Ordinary runs do not require it.
