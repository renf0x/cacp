<!-- CTX-AGENT-CONTEXT-STACK:START -->
## CACP — Cache-Aware Context Protocol

Follow `AGENT_CONTEXT.md`. Answer tasks while touching as few tokens as possible
AND keeping the cached prompt prefix stable so repeated context is nearly free.

At session start, build/read the stable packet:
`python ctx.py pack --out .ctx/startup-packet.md` (permanent rules + memory index
+ repo map, in a fixed order). Read it once; append the task/handoff AFTER it —
never edit the middle, or the prompt cache is invalidated.

- **Retrieve, don't re-read**: `python ctx.py memory query "<q>"` returns the few
  relevant note blocks (local, no LLM). Add `--scope project` for repo-wide.
- **Climb the ladder** for bulk: `ctx map` before opening files, `ctx digest
  <file>` for big files, `ctx read <file>` when a full read is unavoidable,
  `ctx run -- <cmd>` for noisy commands.
- **Verify to avoid retry turns**: after edits run `ctx run -- <tests>`; prefer
  small patches over full rewrites; record decisions in the memory journals.
- **Compress output only when it pays**: normal length for short answers; terse
  (fragments, no filler) only for long explanations — keep code/commands/errors
  byte-exact.
- **Measure for real**: after a session run `python ctx.py measure` to see actual
  billed tokens and cache-read share. A low share means the prefix is churning.

If the memory vault is missing, run:

```powershell
python ctx.py memory init
python ctx.py pack --out .ctx/startup-packet.md
```

Do not change permanent project rules without explicit user approval. At task
completion update the handoff, record durable findings in the memory journals,
and run `python ctx.py memory check`.
<!-- CTX-AGENT-CONTEXT-STACK:END -->
