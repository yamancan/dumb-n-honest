# Measurement contract

Read this when interpreting results, changing language patterns, or reviewing provider adapters.

## Question answered

The audit asks:

> On this user's actual workload, how often did each exact coding-agent model explicitly own an
> error, and how much observable reasoning did it use?

It is a local observational audit, not a model benchmark. It cannot detect errors the agent never
acknowledged and cannot establish why rates differ.

## Denominator and attribution

The denominator is an answered top-level human turn. Assistant streaming fragments, tool calls, and
tool results remain part of that turn. Sidechains, subagents, collaboration rollouts, injected
messages, and synthetic messages do not create turns.

Read every real model ID within the turn. Assign the turn only when exactly one real model appears.
Report and exclude a turn containing multiple real models rather than assigning its first message.
Keep raw exact IDs separate, including Opus versions and Codex Sol, Terra, and Luna variants.

## Categories

`OWNED_ERROR` is the primary metric. It requires explicit first-person ownership, for example:

- English: `I was wrong`, `my mistake`, `I misread`, `I overlooked`, `I need to correct...`.
- Turkish: `yanıldım`, `ben hatalıydım`, `hata yaptım`, `yanlış okudum`, `gözden kaçırdım`.

`CONCEDED` is secondary because agreement can occur without an error:

- English: `you're right`, `good catch`, `thanks for correcting me`.
- Turkish: `haklısın`, `doğru söylüyorsun`, `iyi yakaladın`, `uyarın yerinde`.

Apply all selected language packs to every visible assistant reply; do not infer one language for a
whole session. If a turn matches both categories, count `OWNED_ERROR` once and do not also count
`CONCEDED`. Repeated matches still produce one event per turn.

Strip code, inline code, blockquotes, and quoted examples before matching. Exclude conditionals,
uncertainty, questions, retracted statements, negation, third-party mistakes, and phrase/classifier
discussion. An apology alone is neither category. Turkish diacritics are folded for matching so
native and ASCII spellings use the same pattern IDs. Pattern IDs and worked synthetic examples live
only in `patterns/en.json` and `patterns/tr.json`.

## Rates and reasoning

Report counts and rates per 100 answered turns. Usage share is within each provider because Claude
Code and Codex stores may cover different periods and products.

Reasoning is diagnostic and never part of the admission-rate denominator:

- Claude: final observed `thinking_tokens` per request ID, deduplicated by request. A turn is fully
  covered only when every observed request ID in that turn has a token value.
- Codex: per-turn delta of session-cumulative `reasoning_output_tokens`.

Missing observations remain missing, never zero. Report observed tokens, covered units, eligible
units, fully covered answered turns, request/unit coverage, and answered-turn coverage. Token averages
use only fully covered turns. Below 95% on either coverage measure, the poster shows a
partial-coverage label rather than a comparable token value. Never rank Claude against Codex by
token count because their schemas, tokenizers, and reasoning modes differ.

## Reconciliation diagnostics

Provider diagnostics report roots found, files seen/read, malformed records, excluded symlinks or
subagent sessions, mixed-model turns, unanswered/unattributed turns, and file errors. For eligible
top-level human turns, `turn_reconciliation_ok` confirms that included, mixed, unanswered, and
file-abandoned buckets add back to the observed total.

## Output boundary

Aggregate output may contain provider names, exact model IDs, dates, effort values, named pattern
IDs, counts, rates, token observations, and diagnostics. It must not contain transcript text,
excerpts, transcript-derived paths, projects, sessions, request IDs, usernames, emails, handles, or
hashes. The operator-selected aggregate output path may be printed so the artifacts can be found.
