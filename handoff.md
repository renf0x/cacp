# Handoff

## Now

- Migrated the toolkit to **CACP (Cache-Aware Context Protocol), v0.1.0**. Trimmed
  to the deterministic core and added the two levers the old stack missed:
  cache-stable layout (`ctx pack`) and real provider-usage measurement
  (`ctx measure`). See [[../METHOD]] and `docs/measurement-protocol.md`.
- Removed RLM (`rlm.py`, 9 provider backends, `gemini-login`) and the CodeGraph
  integration: both now duplicate native agent subagents/Task tools and IDE/LSP
  symbol graphs in 2026, and RLM answer quality was never proven.
- Removed shipped/synthetic benchmark numbers (old `docs/claude-code-ab-benchmark.md`,
  `docs/token-memory-audit.md`, and the hardcoded `scripts/create_benchmark_lab.py`).
  Savings are now something you prove on your own usage with `ctx measure`.
- `ctx memory query` is now local, LLM-free top-k retrieval (no provider/keys).

## Next

### TASK-20260714-001 Real A/B on provider usage

- Status: next
- Goal: Prove or disprove end-to-end token impact of the CACP packet + ladder.
- Acceptance: Run the same real task twice (baseline vs CACP) in a real agent,
  then compare with `ctx measure` on the actual transcripts / API usage; report
  measured deltas only (input, output, cache-read share). No synthetic numbers.
- Links: `docs/measurement-protocol.md`, `ctx.py` (`cmd_measure`)

### TASK-20260714-002 SQL/CSS-aware digest quality

- Status: next
- Goal: Replace misleading high-compression cases with file-type-aware digests.
- Acceptance: SQL digest preserves schema objects, table/column names, insert
  targets, representative values, policies/indexes/constraints; CSS digest keeps
  selectors, custom properties, media queries, and layout-critical properties.
  Extreme compression is flagged unless recall is validated.
- Links: `ctx.py` (`_digest_text`)

### TASK-20260714-003 Memory schema migration for existing projects

- Status: next
- Goal: Normalize older project memories without overwriting user notes.
- Acceptance: `ctx memory init` preserves existing files, creates missing schema
  files/templates/checksums, and documents how to split durable facts from
  task-only handoff.
- Links: `memory/`

## Blocked

(none)

## Done this session

### 2026-07-14 CACP migration (v0.1.0)

- `ctx.py`: added `pack` (deterministic cache-stable startup packet) and `measure`
  (real billed tokens + cache-read share from Claude Code transcripts or an API
  usage dump). Refactored `map` into reusable `_scan_repo`/`_render_map`; added a
  shared `_digest_text`; rewrote `memory query` as local `_retrieve` top-k.
- Removed `rlm.py`, `cmd_rlm`, `cmd_gemini_login`, the CodeGraph integration, the
  RLM provider breakdown in `report`, and the synthetic benchmark script.
- Renamed the package `tvl-rlm` → `ctx-cacp`; scripts now expose only `ctx`.
- Rewrote `templates/`, `docs/design.md`, `README.md`; added `METHOD.md` and
  `docs/measurement-protocol.md`. Updated tests for the new surface.

### Superseded from the previous stack

- RLM quality benchmark, private-repo RLM run, and the CodeGraph project-mismatch
  guard are dropped: RLM and CodeGraph were removed from the toolkit.

---

_Older history (pre-CACP) intentionally trimmed from this queue; see
`memory/changelog.md` and `memory/investigations.md` for the full record._
