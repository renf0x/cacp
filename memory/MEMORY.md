# Project Memory

> Read this index at session start. Open linked notes only when needed.

## Project

- Goal:
- Current state:
- Primary stack:
- User overview:

## Start Here

- Active tasks: [[../handoff]]
- Permanent rules: [[project-rules]]
- Architecture: [[architecture]]
- Operations: [[operations]]

## Logs

- Decisions: [[decisions]]
- Bugs: [[bugs]]
- Investigations: [[investigations]]
- Changes: [[changelog]]

## Retrieval

- Relevant durable notes (local, no LLM): `python ctx.py memory query "<question>"`
- Broaden into project files: `python ctx.py memory query "<question>" --scope project`
- Rebuild the cache-stable startup packet: `python ctx.py pack --out .ctx/startup-packet.md`
- First bootstrap: `python ctx.py memory open --install-obsidian`
