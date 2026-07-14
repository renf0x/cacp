# CACP — Cache-Aware Context Protocol

**A working method to cut token cost, extend agent sessions, and improve answer
quality — built on the levers that actually move provider bills in 2026, and
honest about the ones that don't.**

**Version: 0.1.0**

CACP is a small, portable toolkit (`ctx.py`) plus a durable memory vault and
vendor-neutral agent adapters. It stops coding agents from re-reading the whole
repo and long histories every turn, keeps the cached prompt prefix stable so
repeated context is nearly free, and measures the result against **real** provider
usage instead of estimates.

Works with Claude Code, Codex, Cursor, Copilot, Gemini, Cline, Roo, OpenCode, and
any agent that can read files or run shell commands.

> Full method write-up: [METHOD.md](METHOD.md). Reproducible measurement:
> [docs/measurement-protocol.md](docs/measurement-protocol.md).

## The five pillars

| Pillar | Command / rule | What it does |
|---|---|---|
| **1. Stable prefix** | `ctx pack` | One deterministic startup packet (rules → memory index → repo map → optional digests). A byte-stable prefix keeps the prompt cache hot: ~0.1x input on the API, a longer window on a subscription. |
| **2. Tiered admission** | `map` → `digest` → `read` → `run` | Climb cheap→expensive; stop at the first rung that answers. No full-repo reads. |
| **3. Durable memory** | `memory query` | Local, LLM-free top-k retrieval — load only the relevant note blocks, not the whole vault. |
| **4. Gated output** | adapter rule | Terse output only when it nets positive (long replies); never on short coding answers; code/commands/errors byte-exact. |
| **5. Measured** | `measure` (+ `report`) | Real billed tokens and cache-read share from provider usage logs. Confirm every saving; never assume. |

Retry turns are the most expensive tokens: prefer small patches, verify with
`ctx run -- <tests>`, and record decisions in memory so the next session doesn't
re-derive them.

## Why it saves tokens — both ways you pay

- **Subscription (Claude Code Max/Pro):** fewer admitted tokens per turn + no
  re-reads + a hot auto-cache → the rolling window lasts longer.
- **API (pay per token):** a repeated cached prefix bills at ~0.1x input; trimmed
  admission cuts billed input; gated output cuts the higher-priced output tokens.

CACP will **not** quote a fixed savings percentage — the real number depends on
your repo and task mix. `ctx measure` tells you what it actually was.

## Quick start

### Requirements

- Python 3.10+
- Optional: Obsidian (a human-facing viewer for the memory vault)

### Install into any project

```powershell
git clone https://github.com/renf0x/ctx-agent-context-stack.git
cd ctx-agent-context-stack
python install.py C:\path\to\your-project --agents all --open-obsidian
```

The installer drops the portable toolkit into the **root of the target project**:

```text
your-project/
  ctx.py
  AGENT_CONTEXT.md
  AGENTS.md
  CLAUDE.md
  handoff.md
  memory/
```

It never overwrites existing `AGENTS.md` / `CLAUDE.md` — it appends one marked,
idempotent adapter block. Pick the agents you use:

| Option | Wires the protocol into |
|---|---|
| `generic` | `AGENT_CONTEXT.md` — the vendor-neutral protocol every agent follows |
| `codex` | `AGENTS.md` — read by Codex, Cursor, Copilot, Gemini, Cline, Roo, … |
| `claude` | `CLAUDE.md` — read by Claude Code |
| `all` (default) | all of the above |

### Global install (optional)

`install.py` drops a local `ctx.py` invoked as `python ctx.py <cmd>`. For a global
`ctx` command that resolves from any folder:

```powershell
pip install .
```

A local `ctx.py` still takes priority when present, so per-project pinning works.

### Everyday use

Install once; the agent then applies the protocol automatically (its instruction
file points at `AGENT_CONTEXT.md`). At session start:

```powershell
python ctx.py pack --out .ctx/startup-packet.md   # cache-stable startup packet; read it once
```

The commands that cover almost everything:

```powershell
ctx pack --out .ctx/startup-packet.md   # pillar 1: stable prefix (read once, append after)
ctx map                                 # see what is expensive before opening files
ctx digest src/large-file.ts            # structure instead of the whole file
ctx read src/config.json                # full read when unavoidable (logged honestly)
ctx run -- npm test                     # filter a noisy command; full log saved locally
ctx memory query "how does X work?"     # local top-k retrieval (no LLM); --scope project for repo-wide
ctx report                              # input-side planning estimate from the ledger
ctx measure                             # REAL billed tokens + cache-read share
```

## Measuring for real

`ctx measure` reads actual provider usage — it never estimates.

```powershell
# Subscription: auto-detects ~/.claude/projects/<slug>/, or pass a transcript file
ctx measure --transcript path\to\session.jsonl

# API: feed the response usage objects and your prices
ctx measure --usage-json usage.json --in-price 5 --out-price 25
```

It reports uncached input, cache read (0.1x), cache write (1.25x), output, the
**cache-read share of input**, hit rate, effective input, and (with prices) an
effective dollar cost. A low cache-read share means something is invalidating the
prefix — rebuild it with `ctx pack` and stop editing context mid-session.

`ctx report` aggregates the local ledger (admitted-vs-avoided, input-side,
heuristic `chars/3.5`). Treat it as a **planning** signal for climbing the ladder;
confirm dollars/limit impact with `ctx measure`. See
[docs/measurement-protocol.md](docs/measurement-protocol.md) for a reproducible
A/B you run on your own usage.

## Coverage hook (Claude Code)

To capture reads that bypass `ctx` so the ledger reflects real coverage, wire a
`PostToolUse` hook:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Read|Bash",
        "hooks": [ { "type": "command", "command": "ctx hook", "async": true } ] }
    ]
  }
}
```

The hook is silent, always exits 0, never blocks the agent, skips `ctx`'s own
commands (so they are not double-counted), and de-duplicates a tool call by its
`tool_use_id`.

> **Permissions.** Allow only the *installed* command — `Bash(ctx *)` — never
> `Bash(python ctx.py *)`. A local `ctx.py` takes priority over the global
> install, so auto-allowing `python ctx.py` would let any cloned repo's `ctx.py`
> run without a prompt.

## Durable memory (Obsidian vault)

`memory/` is a plugin-free Obsidian vault living **in the repository**, so it is
shared: clone the project and the memory comes with it, readable by every agent.

- Record durable findings in the right journal: `architecture.md`, `decisions.md`,
  `bugs.md`, `investigations.md`, `operations.md`. Link with `[[wiki-links]]`.
- Keep `MEMORY.md` a thin index. Never store source files, large logs, or secrets.
- `ctx memory query "<q>"` retrieves the relevant blocks; `ctx memory check`
  validates links, size limits, and protected rules; `ctx memory rotate` archives
  closed journal entries.

```powershell
ctx memory open --install-obsidian
```

`memory/project-rules.md` belongs to the user — agents must not weaken it without
approval. After an approved change: `ctx memory rules-approve --user-approved`.

`handoff.md` carries only tasks (`Now` / `Next` / `Blocked` / `Done this
session`). It is volatile, so it is kept **out** of the cached packet — append it
after the packet. This lets another agent continue from verified state without the
previous agent's full conversation.

## What was removed (and why)

Earlier versions bundled an RLM sub-agent (9 provider backends + OAuth) and a
CodeGraph integration. By 2026 those duplicate native agent subagents/Task tools
and IDE/LSP symbol graphs, while adding maintenance, key-management surface, and
unproven answer quality — so they were removed, along with all shipped benchmark
numbers. What remains is the deterministic, self-hostable core plus the two levers
those tools missed: cache-stable layout and measurement against real usage.

## Files not to commit

```text
.ctx/
__pycache__/
node_modules/
dist/
build/
```

Commit the whole `memory/` vault (notes + `.obsidian/app.json` /
`templates.json`) — it is the shared, cross-agent durable knowledge. Only
`memory/.obsidian/workspace.json` and `cache` stay machine-local.

## Status

CACP is a method, not a guarantee of lower billing or better answers in every
session. It is designed so you can **prove or disprove** each lever on your own
repositories and providers with `ctx measure`. If a lever doesn't help your
workload, turn it off.

## License

MIT
