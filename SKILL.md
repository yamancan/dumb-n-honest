---
name: dumb-n-honest
description: Run a private local benchmark of explicit correction acknowledgments in Claude Code and Codex history.
license: MIT
metadata:
  version: "0.2.11"
---

# Dumb n Honest

Run the deterministic local audit; let the scripts read transcripts and expose only aggregates.

Requires Python 3.10+ and local Claude Code or Codex history. Optional `rsvg-convert` exports PNG
directly; the offline HTML also offers a browser PNG download. Runtime requires no
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

The report links to the canonical benchmark repository. Pass `--github-url` only when the user
supplies an override. Honor provider or language restrictions the user requests. The default is one
offline workspace, a best-effort `chart.png`, and private aggregates. Use `--export-share-pack` when
separate poster, draft and alt-text files are requested. `--no-png` skips PNG files and
`--require-png` implies the exports and requires a successful PNG render.

5. Link the generated `report.html` as the primary output; keep `results.json` private. The workspace
contains the chart, editable draft, full description, copy controls, provider/family/model filters and
PNG/SVG downloads. Link `chart.png` when generated. Save page preserves draft edits and selections.
The chart offers at most three latest numeric versions per family, sorted by acknowledgment rate
within each provider. By default it shows the three newest observed version numbers per provider;
Include older generations reveals earlier models. Models below 100 turns retain a Low sample label.
State that the rate measures explicit correction acknowledgments in the user's observed workload,
not model error rate. The total combines ownership (`I was wrong`) and acceptance (`You're right`).
Report separate exports when requested. Never publish automatically.

## Privacy boundary

The scripts are the transcript boundary. They may read local JSONL; the model may read only their
aggregate stdout and generated aggregate files. Surface only the operator-selected output path.

Keep prompts, replies, transcript-derived paths, projects, session/request IDs, usernames, emails,
handles, and excerpts outside model context and output. Keep `results.json` private; suggest sharing
only the previewed poster, post draft, and alt text.

For metric interpretation, adapters, or pattern changes, read
[references/measurement.md](references/measurement.md). Ordinary runs do not require it.
