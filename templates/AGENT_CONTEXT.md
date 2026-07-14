# Universal Agent Context Protocol (CACP)

This file is vendor-neutral. Any coding agent in this project should follow it —
Claude, Codex, Cursor, Copilot, Gemini, Cline, Roo, OpenCode, or another tool.

Goal: **answer the task while touching as few tokens as possible, and keep the
cached prompt prefix stable so repeated context is nearly free.** Reading whole
files and dumping raw command output is the expensive default. The tools below
exist so you rarely have to.

## Start Of Work

1. If `memory/MEMORY.md` is missing, run `python ctx.py memory init`.
2. Build (or refresh) the cache-stable startup packet once:
   `python ctx.py pack --out .ctx/startup-packet.md`, and read that packet.
   It contains permanent rules, the memory index, and the repo map in a fixed
   order. **Read it once; do not edit it mid-session.** Append the task and any
   handoff notes AFTER it — never in the middle — so the prompt cache stays hot.
3. For "what do we already know about X" use local retrieval, not a fresh read:
   `python ctx.py memory query "<question>"`
   (add `--scope project` to search the whole repo instead of just notes).

## The Context-Saving Ladder

Climb from cheap to expensive. Stop at the first rung that answers the question.

1. **Memory** — `python ctx.py memory query "<q>"` returns the few relevant note
   blocks. Decided facts live here; check before re-investigating.
2. **Map** — `python ctx.py map` shows where the tokens are before you open a
   file. Anything flagged EXPENSIVE should be digested, not read.
3. **Digest** — `python ctx.py digest <file>` for the structure (signatures,
   imports, classes) of any large file. Read the whole file only after the
   digest proves you need a specific part.
4. **Read (funnelled)** — when you truly must read a whole file, pull it with
   `python ctx.py read <file>` instead of a bare editor read: same bytes, but it
   logs the pull so coverage is honest. Direct `Read`/`Bash` are captured too
   when the `ctx hook` is wired.
5. **Run** — never let a noisy command dump into context. Wrap it:
   `python ctx.py run -- <command>` keeps only the salient extract and writes the
   full log to `.ctx/logs/`.

## Keep The Cache Hot (the biggest lever)

Repeated prefix tokens bill at ~0.1x on the API and keep a subscription session
alive longer. You keep the cache hot by **not churning the front of the
context**:

- Read the stable packet once; append new material at the end.
- Don't re-read files you already digested — reuse the digest or a memory note.
- Batch edits; avoid re-emitting large unchanged blocks.
- After a session, verify it actually worked with real numbers:
  `python ctx.py measure` (subscription transcript) or
  `python ctx.py measure --usage-json <file> --in-price P --out-price Q` (API).
  A low cache-read share means something is invalidating the prefix.

## Output Length (only when it pays)

Terse output saves output tokens, but only nets positive on long replies and
never on short coding answers. So: **write normally for short answers; compress
only long explanations/reviews.** For those, drop filler and use fragments, but
keep code, commands, file paths, and error text byte-for-byte exact. Do not
sacrifice correctness for brevity.

## Quality & Fewer Retry Turns

Retry turns are the most expensive tokens of all. Reduce them:

- Prefer small, anchored patches over full-file rewrites.
- After an edit, verify: `python ctx.py run -- <test/build command>`.
- Record durable findings and **decisions** in the memory journals so the next
  session (or agent) does not re-derive them or repeat a mistake.

## Obsidian Memory Vault — Write What You Learn

The `memory/` vault is the project's durable brain, browsable in Obsidian, and
how the *next* session avoids re-reading what this one understood.

- Record durable findings in the right journal: `architecture.md`,
  `decisions.md`, `bugs.md`, `investigations.md`, `operations.md`.
- Link related notes with `[[wiki-links]]`.
- Keep `MEMORY.md` a thin index — one line per note, no content.
- Never store full source files, large logs, secrets, or generated output.
  Store the conclusion, not the raw material.

## Handoff Contract

`handoff.md` is the shared queue (`Now` / `Next` / `Blocked` / `Done this
session`). It is volatile, so it is deliberately **not** part of the cached
packet — keep it at the end of context. Every task uses a stable
`TASK-YYYYMMDD-NNN` id with Status, Goal, Acceptance, and Links.

At task completion:

1. Update the relevant memory journal (durable knowledge, not chatter).
2. Move/update the task in `handoff.md`.
3. Run `python ctx.py memory check`.
4. Leave the next agent a concrete next action, not conversational history.

## Permanent Rules

Never edit `memory/project-rules.md` without explicit user instruction or
confirmation. After an approved change run:

```text
python ctx.py memory rules-approve --user-approved
```
