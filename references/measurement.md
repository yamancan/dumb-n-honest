# Measurement contract

Read this when interpreting results, changing language patterns, or reviewing provider adapters.

## Question answered

The audit asks:

> In this user's eligible local history, how often did each exact coding-agent model explicitly
> acknowledge a correction, and how much observable reasoning did it use?

This is a personal observational benchmark. It is not model error rate, accuracy, or a universal
leaderboard. It cannot detect errors the model never acknowledged or establish why rates differ.
Model choice, task difficulty, date, tools, effort, context length, and user correction behavior may
all confound a comparison.

## Unit, denominator, and attribution

The denominator is one answered top-level human turn. Assistant streaming fragments, tool calls,
and tool results remain part of that turn. Sidechains, subagents, collaboration rollouts, injected
messages, meta and compaction records, their associated assistant output, and synthetic messages do
not create turns.

Read every real model ID within the turn. Assign the turn only when exactly one real model appears.
Report and exclude a turn containing multiple real models. Keep exact IDs separate, including Opus
versions and Codex Sol, Terra, and Luna variants. `answered_turn_share_pct` is the model's share of
included answered turns within its provider; it is not token or billing usage.

All eligible records found in the selected local roots are scanned. Local history cannot prove that
deleted, remote, retained-out, or unsupported records do not exist.

## Headline event

`ACKNOWLEDGED_CORRECTION` is the deduplicated union:

```text
ACKNOWLEDGED_CORRECTION = OWNED_ERROR OR CONCEDED
```

A turn counts at most once. If a reply says both `You're right` and `I was wrong`, the diagnostic
subtype is `OWNED_ERROR` and the headline count is one.

Diagnostic subtypes:

- `OWNED_ERROR`: explicit first-person ownership such as `I was wrong`, `my mistake`, `yanıldım`,
  `benim hatam`, or `hata bende`.
- `CONCEDED`: explicit acceptance such as `You're right`, `you are correct`, `haklısın`, or
  `dediğin doğru`.
- `SOFT_CONCESSION`: ambiguous agreement such as `fair point`, `that's right`, `good catch`, or
  `iyi yakaladın`. It is reported for diagnostics and excluded from the headline rate.

Apply all selected language packs to each visible assistant reply. Strip code, inline code,
blockquotes, Markdown tables, HTML code, and quoted examples before matching. Exclude conditionals,
uncertainty, questions, retractions, negation, third-party mistakes, and phrase/classifier
discussion. An apology alone is not an event. Turkish diacritics are folded so native and common
ASCII spellings share pattern IDs.

The deterministic pattern packs favor precision over recall. Synthetic fixtures prove the code's
contract, not real-world classifier quality. A public precision/recall claim requires an
independently labeled English/Turkish gold set with hard negatives.

## Rates and sample status

Report counts and rates per 100 answered turns with a Wilson 95% confidence interval.

- fewer than 500 turns or 10 headline events: `exploratory`;
- 10–19 events: `sample-limited`;
- at least 20 events: `sample-sufficient`.

The final label is a turn-level sampling gate, not proof that tasks or time are comparable. Wilson
intervals treat turns as independent even though sessions and projects may be clustered. If
intervals overlap, describe the observed rates without declaring a clear difference. Never turn the
highest observed rate into an automatic winner.

## Thinking and reasoning

Reasoning is diagnostic and never part of the acknowledgment denominator:

- Claude: final observed `thinking_tokens` per request ID, deduplicated by request. An assistant
  unit without a request ID remains an uncovered eligible unit.
- Codex: per-turn delta of session-cumulative `reasoning_output_tokens`. A counter reset makes that
  turn uncovered rather than a zero-token observation.

Missing observations remain missing. Report observed tokens, covered units, eligible units, fully
covered answered turns, unit coverage, and turn coverage in private aggregate results. Token
averages use fully covered turns only. The social poster omits token metrics so partial coverage and
provider-specific tokenization cannot be mistaken for a ranking. Never rank Claude against Codex
by token count because their schemas, tokenizers, and reasoning modes differ.

## Quality and reconciliation

Each provider reports roots found, files seen/read, records seen/recognized, malformed records,
excluded symlinks, subagent files or sessions, duplicate sessions, files that vanished mid-scan, mixed-model turns, unanswered or
unattributed turns, quarantined unknown-model turns, metadata validation failures, reasoning
resets, and file errors. Metadata inside excluded sessions does not enter validation counters.
Duplicate session files are skipped before turn aggregation, so their counter can prove exclusion
rather than duplicate denominator entries. Files are visited in sorted path order, so attribution
never depends on filesystem enumeration order. A top-level file that disappears between listing and
reading is retried once, then counted as a file error: the snapshot is incomplete and unshareable.

For eligible top-level human turns, included, mixed, unanswered, and file-abandoned buckets must add
back to the observed total. Provider status is one of:

- `OK`
- `OK_WITH_WARNINGS`
- `MISSING_ROOT`
- `NO_FILES`
- `NO_ANSWERED_TURNS`
- `UNSUPPORTED_OR_EMPTY_SCHEMA`
- `INCOMPLETE`

A missing optional provider is allowed when another provider is valid. An unknown model ID is never
emitted: its affected top-level turn is quarantined from the exact-model denominator. At most 1%
of observed top-level human turns may be quarantined under `OK_WITH_WARNINGS`; every share artifact
discloses the omitted count. More than 1%, unsupported schema, malformed input, file errors, invalid
effort metadata, or failed reconciliation make the aggregate unshareable. Preserve private
`results.json`; refuse poster/post generation.

## Output boundary

Aggregate output may contain provider names, provider-allowlisted exact model IDs, dates,
allowlisted effort values, named pattern IDs, counts, rates, confidence intervals, token
observations, versions, and diagnostics. Unknown model metadata is redacted and its turn is
quarantined under the threshold above; unknown effort metadata is redacted and blocks sharing.
Output must not contain transcript text, excerpts, transcript-derived paths, projects, sessions,
request IDs, usernames, emails, handles, or hashes.

`results.json` is private by default. Share only a previewed poster, the generated English post
draft, and alt text. The poster and post split the deduplicated headline total into `OWNED_ERROR`
and `CONCEDED` so agreement is not presented as error ownership. Each share artifact names the
benchmark repository; `--github-url` may override the canonical link. Nothing posts automatically.

## Controlled challenge benchmark

A universal model comparison is a separate future mode. It must run the same frozen tasks, system
prompt, tools, effort, and correction sequence across randomized repeated model runs. It should
score initial error, acceptance of true corrections, acceptance of intentionally false corrections
(sycophancy), and correctness of the repair. Local-history rates must remain separate from that
controlled result.
