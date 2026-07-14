# CACP — the Cache-Aware Context Protocol

A working method for coding agents that reduces token cost, keeps sessions alive
longer, and improves answer quality — grounded in the levers that actually move
provider bills in 2026, and honest about the ones that don't.

## Why a new method

Two well-known tools each optimize one end of the pipe and miss the middle:

- **Input-trimming tools** (repo map / file digest / durable memory — what this
  project used to be) cut *what the agent reads*. Real and useful, but they never
  touched prompt caching and shipped only single-run synthetic benchmarks.
- **Output-shrinking tools** (e.g. caveman) cut *what the agent says* (~65% on
  long replies) but add ~1–1.5k input tokens per turn and, by their own honest
  admission, **net negative on short coding replies** — which is most coding.

Neither addresses the single biggest real lever — **prompt caching** (an
unchanged prefix bills at ~0.1x on the API and keeps a subscription window alive)
— and neither closes the loop by **measuring real provider usage**. CACP is built
around exactly those two, with input-trimming and output-shrinking kept as
*conditional* sub-levers applied only where they measurably help.

## The five pillars

Each pillar has a command or a rule, and a way to check it did something real.

### 1. Stable prefix — the cache lever (`ctx pack`)

Emit one deterministic startup packet, ordered most-stable-first:
`permanent rules → memory index → repo map → (optional) key digests`. Read it
once; **append the task and handoff after it, never edit the middle.** Volatile
state (handoff, current task) is deliberately excluded so appending it can't
invalidate the cached prefix.

- The packet is byte-stable across turns (no timestamps, deterministic ordering),
  which is what lets the model reuse the cached prefix.
- Verify with `ctx measure`: the **cache-read share of input** should be high. A
  low share means something is churning the prefix.

### 2. Tiered admission (`map` → `digest` → `read` → `run`)

Climb from cheap to expensive; stop at the first rung that answers the question.
`map` shows where the tokens are without reading; `digest` returns structure, not
bodies; `read` is the honest full-read denominator; `run` keeps only the salient
extract of noisy command output and saves the full log to disk. No full-repo
reads, ever.

### 3. Durable memory as retrieval (`memory query`)

The `memory/` vault is Markdown/Obsidian, browsable and outside chat history.
`memory query` does **local, LLM-free top-k retrieval** — it returns the few
relevant note blocks (scored by query-term frequency, normalized by length), so
the agent loads only what it needs instead of the whole vault or a sub-agent
call. Decisions and findings recorded here stop the *next* session from
re-deriving them or repeating a mistake. `--scope project` extends the same
retrieval across all repo files.

### 4. Gated output compression (rule, not always-on)

Terse output saves output tokens, but only nets positive on long replies and adds
overhead every turn. So: **write normally for short answers; compress only long
explanations/reviews** — drop filler, use fragments, but keep code, commands,
paths, and error text byte-for-byte exact. Never trade correctness for brevity,
and never claim output savings on per-request billing (some Copilot tiers), where
shorter answers cost the same.

### 5. Measured, not guessed (`measure`, and `report` for planning)

`ctx measure` reads **real** provider usage — Claude Code transcript JSONL for a
subscription, or an API usage dump for pay-per-token — and reports actual billed
tokens, cache-read share, cache hit rate, effective input in
base-token-equivalents, and (with prices) an effective dollar cost. `ctx report`
aggregates the local ledger as an input-side **planning** estimate only. Every
claimed saving is confirmed by `measure`, never assumed. See
[docs/measurement-protocol.md](measurement-protocol.md) for a reproducible A/B.

### Quality layer (spans 3–5): the turn is the unit of cost

Measured on real A/B transcripts (INV-20260714-002): a protocol that admitted
−20.5% new input still ended up +31% more expensive because it took 2.2x more
turns — every extra turn replays the whole history. Rules that follow:

- **Batch**: chain related commands into one call; pre-digest several files at
  once (`pack --digest K`) instead of one digest per turn; answer multi-part
  questions from one exploration pass.
- Prefer small anchored patches over full-file rewrites; after an edit, verify
  with `ctx run -- <tests>`; record decisions in the memory journals. Removing
  a retry turn usually beats any per-turn trimming.

## Applies to both ways you pay

| Lever | Subscription (Claude Code Max/Pro) | API (pay per token) |
|---|---|---|
| Stable prefix (`pack`) | Keeps auto-cache hot → lower latency and less effective input load per turn, so the rolling window lasts longer | Repeated prefix bills at ~0.1x input → direct dollar cut |
| Tiered admission | Fewer admitted tokens per turn → more turns before the limit | Fewer input tokens billed |
| Retrieval memory | Avoids re-reading; small loads | Avoids re-billing large context |
| Gated output | Shorter turns; faster | Cuts output tokens (priced higher than input) |
| Measurement | Read the transcript to see limit pressure | Read `usage` to see dollars |

The one thing CACP will not do is assert a fixed savings percentage. The exact
number is a property of your repo and task mix — `measure` tells you what it
actually was.

## Non-goals (deliberately removed)

- **RLM sub-agent + provider backends + OAuth login** — duplicates native agent
  subagents/Task tools in 2026, adds key-management surface, and had unproven
  answer quality.
- **CodeGraph integration** — duplicates IDE/LSP symbol graphs.
- **Shipped benchmark numbers** — replaced by a measurement harness you run on
  your own usage.

No hardcoded paths, no synthetic datasets, no infographic that isn't backed by a
number you can reproduce with `measure`.
