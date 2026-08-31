# dumb-n-honest

A private, bilingual personal observational benchmark for local Claude Code and Codex history.

It answers one narrow question:

> How often did each exact model explicitly acknowledge a correction in my local coding-agent
> history?

`I was wrong`, `You're right`, and their supported English and Turkish variants belong to the same
headline event: `ACKNOWLEDGED_CORRECTION`. A turn counts at most once. The share artifacts decompose
that total into explicit ownership (`OWNED_ERROR`) and explicit acceptance (`CONCEDED`). The audit
reports events per 100 answered top-level human turns, Wilson 95% confidence intervals, sample
status, and available thinking/reasoning coverage.

This is not model error rate, accuracy, or a universal leaderboard. A higher rate can reflect more
mistakes, more user corrections, more explicit ownership, or more willingness to agree.

## Privacy

- Transcript parsing is deterministic and local.
- The scanner makes no network requests.
- Raw prompts and replies are never written to output.
- Output excludes paths, projects, session/request IDs, usernames, emails, excerpts, and hashes.
- Untrusted model and effort strings are constrained before they can enter aggregate output.
- Nothing is posted automatically.

The repository uses no runtime packages so the transcript-reading boundary can be audited directly.
Keep `results.json` private. Preview `poster.png`, `tweet.txt`, and `alt-text.txt` before sharing.

## Requirements

- Python 3.10 or newer; standard library only.
- Local Claude Code and/or Codex transcript history.
- Chrome, Chromium, Edge, or Brave for PNG export.

HTML, aggregate JSON, the English post draft, and alt text do not require a browser. PNG generation
is best-effort by default; use `--require-png` only when PNG is mandatory.

Agent sandboxes may ask for permission to read `~/.claude` or `~/.codex`.

## Agent smoke test from this repository

Giving an agent the repository URL does not by itself authorize access to local history. Ask it
explicitly to run the audit. A source checkout can be tested directly; installation and a tagged
release are not required for this smoke test.

```bash
git clone https://github.com/yamancan/dumb-n-honest.git
cd dumb-n-honest
python3 scripts/doctor.py --provider all
smoke_output_dir="$(mktemp -d)"
python3 scripts/run.py \
  --provider all \
  --languages en,tr \
  --output-dir "$smoke_output_dir" \
  --no-png
```

Use a new or empty output directory outside the repository. For a safe agent dogfood run, give the
agent this instruction together with the repository URL:

> Clone this repository and smoke-test it as a new user. You are explicitly authorized to let its
> scripts scan my local Claude Code and Codex histories. Do not open, grep, or quote raw JSONL.
> Run `doctor.py`, then run both providers with `en,tr`, a new output directory outside the
> repository, and `--no-png`. Inspect only aggregate stdout and generated aggregate artifacts.
> Report provider status, `shareable`, quality counters, turn reconciliation, model denominators,
> and the artifact list. Do not modify the repository or commit, tag, push, publish, or share
> anything. Stop after reporting the smoke-test result.

## Install

For normal installation, download, extract, and inspect a tagged release. From the extracted
directory run one installer:

```bash
python3 scripts/install.py --target codex
python3 scripts/install.py --target claude
```

The installers refuse to overwrite an existing installation. Codex receives
`agents/openai.yaml` with implicit invocation disabled. The Claude installer adds Claude Code's
`disable-model-invocation: true` field to the installed copy while the release source remains valid
portable Agent Skills frontmatter. A script-level authorization gate is retained in both variants.

Invoke `$dumb-n-honest` in Codex or `/dumb-n-honest` in Claude Code. On native Windows, use `py -3`
instead of `python3` when needed.

## Check the environment

The doctor checks Python, local history presence, and whether an optional browser is installed
without reading transcript content. `detected-may-require-approval` means the executable exists;
a sandboxed agent may still request permission before launching it:

```bash
python3 scripts/doctor.py --provider all
```

## Run

```bash
python3 scripts/run.py --output-dir ./dumb-n-honest-output
```

Defaults: both providers and both language packs (`en,tr`). Examples:

```bash
python3 scripts/run.py --provider claude --languages en,tr --output-dir ./audit-claude
python3 scripts/run.py --provider codex --languages tr --output-dir ./audit-codex
python3 scripts/run.py --output-dir ./audit-html --no-png
python3 scripts/run.py --output-dir ./audit-strict --require-png
```

The output directory must be new or empty. Existing results are never overwritten. Optional GitHub
URL override for the generated post and poster:

```bash
python3 scripts/run.py --output-dir ./audit-share \
  --github-url https://github.com/OWNER/dumb-n-honest
```

Without an override, share artifacts link to
`https://github.com/yamancan/dumb-n-honest`, the canonical benchmark repository.

## Outputs

- `results.json`: private aggregate results, versions, quality status, and diagnostics.
- `poster.html`: self-contained, network-free 1080×1350 poster source.
- `poster.png`: share image when a compatible browser can render it.
- `tweet.txt`: English post draft of at most 280 characters.
- `alt-text.txt`: objective chart description.

The lean poster reserves up to three rows per provider. Each stacked bar uses black for explicit
ownership such as `I was wrong` and orange for explicit acceptance such as `You're right`; the
number at right is their deduplicated total per 100 turns. The row also shows the subtype rates,
denominator, total confidence interval, and sample status. The post summarizes the same split for up
to two Opus models and two Codex models by answered-turn volume without declaring the highest total
a winner. Both include the benchmark link. Nothing is published automatically.

## Measurement contract

The denominator is one answered top-level human turn attributed to exactly one raw model ID.
Streaming fragments and tool activity stay inside that turn. Sidechains, subagents, collaboration
rollouts, injected messages, tool results, unanswered turns, and mixed-model turns do not enter an
exact-model denominator.

Headline:

```text
ACKNOWLEDGED_CORRECTION = OWNED_ERROR OR CONCEDED
```

`OWNED_ERROR` and `CONCEDED` remain diagnostic subtypes. Ambiguous phrases such as `fair point`,
`that's right`, `good catch`, and `iyi yakaladın` are `SOFT_CONCESSION` diagnostics and do not enter
the headline rate.

Every rate includes its numerator, denominator, Wilson 95% confidence interval, and sample status:

- fewer than 500 turns or 10 events: `exploratory`;
- 10–19 events: `sample-limited`;
- at least 20 events: `sample-sufficient`.

These labels describe turn-level sample size only. Wilson intervals treat turns as independent;
sessions and projects may be clustered. Different tasks, periods, tools, effort, context length,
and user behavior still confound model comparisons.

Thinking/reasoning tokens are a separate resource-use diagnostic in private `results.json`.
Missing observations stay missing. The social poster omits token metrics so partial coverage and
provider-specific tokenization cannot be mistaken for a model ranking. Claude and Codex token
counts are never ranked against each other.

See [`references/measurement.md`](references/measurement.md) for the full contract.

## Quality gates

The scanner records adapter and pattern versions plus provider status. A missing optional provider
is allowed when another provider is valid. Unknown model IDs are never emitted: affected turns are
quarantined from exact-model denominators. Up to 1% of observed top-level human turns may be
quarantined under `OK_WITH_WARNINGS`, with the omission disclosed in the poster, post, and alt text.
More than 1%, malformed data, unsupported/empty schema, unknown effort metadata, file errors, or
failed turn reconciliation mark results unshareable; private `results.json` is preserved but the
share pack is refused. Excluded subagent and duplicate-session files do not contribute metadata or
turns to quality gates. Claude subagent transcripts under `subagents/` are excluded by path; Claude
meta/compaction records and their associated assistant output are excluded from turns. If a top-level transcript disappears while the
scan runs (an active agent session), the result is `INCOMPLETE`; re-run when nothing is writing. The renderer requires schema 2.0 with an explicit passing quality status.

All eligible local records found in the selected roots are scanned. The tool cannot prove that
deleted, remote, retained-out, or unsupported conversations do not exist.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Fixtures are invented and test deterministic behavior, adversarial phrase cases, turn
reconstruction, exact-model attribution, schema drift, reasoning coverage, privacy canaries,
best-effort rendering, and extracted-package execution. Synthetic tests do not establish real-world
classifier precision or recall; a labeled EN/TR gold set is required before claiming that.

Not affiliated with or endorsed by Anthropic or OpenAI. Claude, Claude Code, Codex, Opus, Fable, and
GPT model names identify locally recorded products and models only.
