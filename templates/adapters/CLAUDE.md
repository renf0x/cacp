<!-- CTX-AGENT-CONTEXT-STACK:START -->
## CTX Agent Context Stack

Follow `AGENT_CONTEXT.md`. At session start read only `memory/MEMORY.md`,
`handoff.md`, and `memory/project-rules.md`. Use CodeGraph for code structure,
RLM for broad semantic questions, and CTX digest/run for large inputs.

If the memory vault is missing, run:

```powershell
python ctx.py memory init --with-codegraph
python ctx.py memory open --install-obsidian
```

Do not change permanent project rules without explicit user approval. At task
completion update the universal handoff and run `python ctx.py memory check`.
Use `/compact` between substantial tasks and `/clear` for unrelated work.
<!-- CTX-AGENT-CONTEXT-STACK:END -->
