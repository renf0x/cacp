# Investigation Log

## INV-20260714-002 Real headless A/B: long 8-part audit task (the honest КПД)

- Status: closed
- Date: 2026-07-14
- Question: Does CACP's per-turn saving amortize on a longer real task, and what
  is the true net effect isolated from platform caching?
- Method: same repos as INV-001, 8-part audit task forcing broad file coverage,
  same model (haiku), same tools, max 40 turns, one pair. Real transcripts
  compared with `measure --compare`; behavior diffed from tool_use records.
- Findings (real, single pair):
  - TOTAL new input admitted: −20.5% for B (124,111 → 98,708) — the admission
    discipline DID amortize (per-turn −64%). Output/turn −41.7%.
  - BUT turns 24 → 53 (+120%): B worked in many small steps. Every extra turn
    replays the whole history, so cache-read volume doubled (1.15M → 2.30M) and
    EFFECTIVE input rose +31% — B was net MORE expensive despite admitting less.
    Wall time +16% (1m52s → 2m10s). Quality: both audits complete and correct.
  - Behavior: B mostly IGNORED ctx commands (no digest/map/query calls; it used
    grep + windowed reads instead) — instruction adherence of a small model is
    weak; the admission gain came from the protocol's "read less" pressure, not
    from the tools themselves.
- Conclusion: the dominant cost unit of a session is the TURN, not the file
  read. A context protocol only nets positive if it does NOT multiply turns:
  batch exploration into few calls, pre-digest via `pack --digest K` instead of
  per-file digest turns. Adapter rules updated accordingly (turn-batching rule).
- Links: [[../docs/measurement-protocol]], INV-20260714-001

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
