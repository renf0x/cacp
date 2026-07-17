# Decision Log

## DEC-000 Template

- Status: example
- Date: YYYY-MM-DD
- Decision:
- Reason:
- Consequences:
- Links:

## DEC-20260717-001 Session-length control module (`ctx session`)

- Status: active
- Date: 2026-07-17
- Decision: Add a sixth pillar: session-length cost control. New `ctx session`
  trio wired to harness hooks: gauge (UserPromptSubmit; warns from real
  transcript usage at 80k/120k tok), snapshot (PreCompact; deterministic
  extract of last user asks + edited files), restore (SessionStart on
  compact/clear/resume; re-injects .ctx/session-state.md), plus agent-written
  `session save`. Version 0.1.0 -> 0.2.0.
- Reason: Measured on a real 600+ turn session: live context reached ~131k tok
  and every turn re-sent it; admission tools (guard/digest) do not touch this
  axis. No external tool can truncate the harness context -- the only lever is
  making /compact early, informed, and lossless.
- Consequences: Compaction becomes safe to do often; post-compact re-derivation
  drops to ~1k injected tokens. Hook configs load at session start -- a restart
  is required. Also found: hooks in a SUBDIR .claude/settings.json never fire;
  settings must live at the workspace root the agent was started in.
- Links: [[../README]] "Session-length control", `ctx.py` cmd_session_*
