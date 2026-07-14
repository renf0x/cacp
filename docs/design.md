# Design — CACP (Cache-Aware Context Protocol)

CACP is one portable Python file (`ctx.py`) plus an installer, a memory vault,
and vendor-neutral agent adapters. It combines five levers behind a single
project-root workflow, each applied only where it measurably nets positive.

## Pillars → commands

1. **Stable prefix** — `ctx pack` emits one deterministic, cache-friendly startup
   packet (permanent rules → memory index → repo map → optional digests), ordered
   most-stable-first. A byte-stable prefix keeps the model's prompt cache hot:
   ~0.1x input on the API, and a longer-lived window on a subscription. Volatile
   state (handoff, current task) is deliberately excluded so it can be appended
   without invalidating the cache.
2. **Tiered admission** — `map` → `digest` → `read` → `run`. Deterministic input
   filtering; stop at the first rung that answers the question. No full-repo reads.
3. **Durable memory** — `memory` manages a Markdown/Obsidian vault. `memory query`
   is local, LLM-free top-k retrieval so the agent loads only the relevant note
   blocks instead of the whole vault or a sub-agent call.
4. **Gated output** — the agent adapters instruct terse output only when it nets
   positive (long explanations), never on short coding replies, and always keep
   code/commands/errors byte-exact.
5. **Measured** — `report` gives an input-side planning estimate from the local
   ledger; `measure` reads REAL provider usage (Claude Code transcript JSONL, or
   an API usage dump) and reports actual billed tokens and cache-read share. All
   claimed savings must be confirmed here, not assumed.

## Why this shape

Earlier versions bundled an RLM sub-agent (9 provider backends + OAuth) and a
CodeGraph integration. By 2026 those duplicate native agent capabilities
(built-in subagents/Task tools, IDE/LSP symbol graphs) while adding maintenance,
key-management surface, and unproven answer quality — so they were removed. What
remains is the deterministic, self-hostable core plus the two levers those tools
missed: cache-stable layout and measurement against real usage.

## Boundaries

`ctx.py` is stdlib-only (the `anthropic` package is optional, used only for exact
token counting in `ctx count`). Agent-specific files are thin adapters;
`AGENT_CONTEXT.md`, `handoff.md`, and `memory/` are the universal protocol.
