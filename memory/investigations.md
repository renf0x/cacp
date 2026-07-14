# Investigation Log

## INV-20260714-004 Session splitting (handoff pattern) is MORE expensive than history replay

- Status: closed
- Date: 2026-07-14
- Question: Instead of letting one session replay its history every turn, is it
  cheaper to split work into fresh short sessions with durable state (handoff/
  memory) — and does a digest packet fix the re-exploration cost?
- Method: the same 8 audit questions as INV-002, run as 8 separate fresh
  headless sessions. C = pure split (no CACP), D = split + `pack --digest 6`
  packet loaded via CLAUDE.md. Same model/tools. Compared against A (one
  continuous 24-turn session) by aggregating each variant's 8 real transcripts.
- Findings (real):
  - C (pure split): new input +328% (124k -> 531k), effective input +198.5%,
    wall time 3m09s vs A's 1m52s. Every fresh session re-pays the full system
    prompt as a cache WRITE and re-explores the repo at full price.
  - D (split + packet): better than C (packet cut ~190k of re-exploration; new
    input/turn even −8.4% vs A) but still effective input +124% vs A.
  - Quality: comparable (7/8 answers cite code in both variants).
  - Final measured cost ranking for this task class (effective input):
    A continuous 269k < B1 CACP-instructions 353k < B2 464k < D 604k < C 805k.
- Conclusion: history replay inside ONE session is the CHEAP mode — the platform
  serves it at 0.1x; a session restart pays 1.25x cache-writes of the whole
  system prompt plus full-price re-orientation. Splitting is justified only
  when the replayed history exceeds the restart cost (context pollution, window
  limits, task switch) — NOT as a per-turn economy. Handoff/memory are for
  continuity and quality across necessary restarts. This vindicates pillar 1
  (one continuous session, stable cached prefix) as the cheapest base mode.
- Links: INV-20260714-002, INV-20260714-003, [[../docs/measurement-protocol]]

## INV-20260714-003 Validation run: the turn-batching INSTRUCTION did not hold

- Status: closed
- Date: 2026-07-14
- Question: Does adding an explicit turn-batching rule to the adapter fix the
  turn multiplication found in INV-002?
- Method: same audit task/model/tools; B re-initialized with the updated adapter
  (rule verified present in CLAUDE.md before the run). One run.
- Findings (real):
  - Turns did NOT drop: 58 (vs 53 old-protocol, 24 baseline). The model again
    ignored ctx commands (grep + 12 windowed reads of ctx.py) and additionally
    made 2 Write calls (drafting the audit to disk), exploding output to 42,176
    (vs 16,015 old-protocol, 12,449 baseline). Effective input +72% vs baseline.
  - New-input-per-turn stayed down (−44% vs baseline) — that effect repeats
    across all three CACP runs (−17.5%, −64%, −44%).
  - Between two near-identical CACP runs, output varied 16k ↔ 42k: single-pair
    A/B at this variance cannot establish small effects.
- Conclusion: instruction-only protocols are WEAK, unstable enforcement on a
  small model. The repeatable win is deterministic admission pressure (read
  less per step); the repeatable loss is turn multiplication, and a written
  rule does not fix it. Next real lever must be deterministic, not advisory:
  richer `pack --digest K` packets that pre-answer exploration, and/or a
  PreToolUse hook that rewrites full reads into digests. More single runs will
  not settle small deltas — variance dominates.
- Links: INV-20260714-002, [[../docs/measurement-protocol]]

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
