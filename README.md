# dumb-n-honest

A private, bilingual audit of explicit self-corrections in local Claude Code and Codex history.

It answers a narrow question: how often did each exact model visibly own an error on your actual
workload? It also reports available thinking/reasoning usage and its coverage.

This is not an error-rate benchmark. It cannot find mistakes the agent did not acknowledge.

## Privacy

- Transcript parsing is deterministic and local.
- The scanner makes no network requests.
- Raw prompts and replies are never written to output.
- Output excludes paths, projects, session/request IDs, usernames, emails, excerpts, and hashes.
- Nothing is posted automatically.

The repository is intentionally small and uses no runtime packages, so the transcript-reading code
can be audited directly.

## Requirements

- Python 3.10 or newer; standard library only.
- Claude Code and/or Codex local transcript history.
- Chrome, Chromium, Edge, or Brave for PNG export. Without one, use `--no-png`; HTML is still
  generated.

No `pip install`, `npm install`, remote font, or network connection is required at runtime.

## Skill invocation safety

The portable `SKILL.md` follows the open Agent Skills format and contains an explicit-authorization
gate. Codex also reads `agents/openai.yaml`, which disables implicit invocation.

For a personal Claude Code installation, set the skill to `user-invocable-only` in `/skills` before
running it. This keeps it hidden from Claude until you invoke `/dumb-n-honest`. Do not install this
privacy-sensitive workflow as an auto-invoked skill.

## Run

```bash
python3 scripts/run.py --output-dir ./dumb-n-honest-output
```

Defaults: both providers and both language packs (`en,tr`). Examples:

```bash
python3 scripts/run.py --provider claude --languages en,tr --output-dir ./dumb-n-honest-output-claude
python3 scripts/run.py --provider codex --languages tr --output-dir ./dumb-n-honest-output-codex
python3 scripts/run.py --output-dir ./dumb-n-honest-output-html --no-png
```

The output directory must be new or empty. Existing results are never overwritten.
Repository-local directories beginning with `dumb-n-honest-output` are ignored by Git; keep personal
aggregate results and share packs out of version control.

An optional repository URL can be included in the post draft:

```bash
python3 scripts/run.py --output-dir ./dumb-n-honest-output-share --github-url https://github.com/OWNER/dumb-n-honest
```

## Outputs

- `results.json`: complete aggregate results and diagnostics.
- `poster.html`: network-free 1080×1350 poster source.
- `poster.png`: share image when a supported browser is available.
- `tweet.txt`: English post draft of at most 280 characters.
- `alt-text.txt`: objective chart description.

The poster uses `OWNED_ERROR` as its headline metric. `CONCEDED` remains separate because phrases
such as “you're right” and “haklısın” may be ordinary agreement.

## Supported language signals

English and Turkish are enabled by default and applied turn by turn. Turkish matching accepts both
native spelling (`yanıldım`, `haklısın`) and common ASCII spelling (`yanildim`, `haklisin`). Pattern
packs include explicit ownership, concessions, uncertainty/meta exclusions, and worked synthetic examples. See
[`patterns/en.json`](patterns/en.json) and [`patterns/tr.json`](patterns/tr.json).

## Development

```bash
python3 -m unittest discover -s tests -v
```

All fixtures are invented. The tests cover phrase families, false positives, turn reconstruction,
mixed-model attribution, Claude/Codex parity, reasoning coverage, privacy canaries, one-command
output, and exact PNG dimensions.

Not affiliated with or endorsed by Anthropic or OpenAI. Claude, Claude Code, Codex, Opus, Fable, and
GPT model names are used only to identify locally recorded products and models.
