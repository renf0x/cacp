# Universal Agent Context Protocol

This file is vendor-neutral. Any coding agent working in this project should
follow it, whether it is Claude, Codex, Cursor, Copilot, Gemini, Cline, Roo,
OpenCode, or another tool.

## Start Of Work

1. If `memory/MEMORY.md` is missing, run:
   `python ctx.py memory init --with-codegraph`.
2. After first-time initialization, run:
   `python ctx.py memory open --install-obsidian`.
3. Read only:
   - `memory/MEMORY.md`
   - `handoff.md`
   - `memory/project-rules.md`
4. Use `codegraph context "<task>"` for code relationships.
5. Use `python ctx.py memory query "<question>"` for broad memory questions.
6. Add `--scope project` only when the answer requires the whole codebase.

## Context Budget

- Start with `python ctx.py map`.
- Digest files over 300 lines before reading them fully.
- Run noisy commands through `python ctx.py run -- <command>`.
- Do not put full source files, large logs, secrets, or generated output in memory.
- Use RLM for large semantic questions, not for small targeted edits.

## Handoff Contract

`handoff.md` is the shared queue for every agent. It contains only:

- `Now`: task currently being executed.
- `Next`: ordered future tasks.
- `Blocked`: blockers requiring user or external action.
- `Done this session`: completed work, checks, and important file changes.

Every task uses a stable `TASK-YYYYMMDD-NNN` identifier and includes:

- Status
- Goal
- Acceptance criteria
- Relevant links

At task completion:

1. Update the relevant memory journal.
2. Move/update the task in `handoff.md`.
3. Run `python ctx.py memory check`.
4. Leave the next agent a concrete next action rather than conversational history.

## Permanent Rules

Never edit `memory/project-rules.md` without explicit user instruction or
confirmation. After an approved change run:

```text
python ctx.py memory rules-approve --user-approved
```
