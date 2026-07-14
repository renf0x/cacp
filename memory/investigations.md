# Investigation Log

## INV-20260714-001 Real headless A/B: baseline vs CACP on a short task

- Status: closed
- Date: 2026-07-14
- Question: What does CACP actually change in a REAL agent session, isolated
  from the platform's automatic prompt caching?
- Method: Two identical copies of this repo's real source; B additionally got
  `ctx init --agents claude`. Same task (explain ledger dedup + RECON_OPS in
  ctx.py), same model (haiku), same tool allowlist, headless `claude -p`,
  one run each. Compared real transcripts with `ctx measure --compare`.
- Findings (real, single pair — not a statistical claim):
  - new input admitted PER TURN: −17.5% for B; output per turn: −17.0% for B —
    the ladder/digest discipline measurably reduced per-turn admission.
  - BUT B took +2 turns (9→11: reading the packet/protocol costs turns), so
    TOTAL new input was +0.8% and effective input +5.0% — net neutral-to-worse
    on a ~30-second task.
  - Answer quality: both correct, equal (both found tool_id dedup + RECON_OPS).
  - Platform cache served ~192k (A) / ~247k (B) tokens regardless of the tool —
    confirming that cache savings must never be attributed to CACP.
- Conclusion: CACP's per-turn mechanism works, but its fixed overhead (packet +
  protocol reads) eats the gain on short tasks. Expected break-even is longer
  sessions where the one-time packet cost amortizes over many turns; that is
  the next thing to measure. Mirrors caveman's honest fixed-overhead math.
- Links: [[../docs/measurement-protocol]], `ctx.py` (`cmd_measure`)

## INV-000 Template

- Status: example
- Date: YYYY-MM-DD
- Question:
- Findings:
- Conclusion:
- Links:

## INV-20260616-001 Context reduction and memory audit

- Status: closed
- Date: 2026-06-16
- Question: Does CTX/RLM/memory produce measured context reduction and useful durable agent memory on a large project?
- Findings: On a safe copy of `private-project`, deterministic `ctx digest` avoided admitting 93,888 estimated tokens of text across 10 expensive files (19.6x), but SQL/CSS recall quality is not guaranteed and `seed.sql` over-compression is a warning case. Startup routing through instructions, handoff, project context, and memory index is about 5,951 tokens versus about 354,281 tokens for the copied project (59.5x smaller than a full-read baseline). Real external RLM attempts through OpenAI OAuth and opencode free providers were blocked by execution policy because they would transmit private repository content to external providers.
- Conclusion: Deterministic CTX context reduction is real and measurable; actual provider-token/billing savings and RLM answer-quality improvement remain unproven until an A/B benchmark or permitted provider/sanitized benchmark is used. `private-project` memory is useful but not compliant with the current CTX memory schema.
- Links: [[../docs/token-memory-audit]]
