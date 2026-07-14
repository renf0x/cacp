# Measurement Protocol — prove it on YOUR usage, not on ours

This project ships **no benchmark numbers**. Token savings depend on your repo,
your task mix, and whether you are on a subscription or paying per token, so the
only honest number is the one you measure. `ctx measure` reads **real** provider
usage; nothing here is estimated or synthetic.

## What actually moves the numbers

- **Input:** admitted context (what the ladder trims) and cache-read share (what a
  stable `pack` prefix raises). On the API a cache read bills at ~0.1x and a cache
  write at ~1.25x of the base input price; on a subscription, fewer admitted
  tokens and a hot cache extend the rolling window.
- **Output:** length. Only worth compressing on long replies (see the gated-output
  rule in `AGENT_CONTEXT.md`); short coding answers are already cheap.
- **Retry turns:** the most expensive tokens. Verifying edits and recording
  decisions removes whole turns — usually a bigger win than either of the above.

## A/B you can reproduce

Run the **same real task twice** in your agent, on the same starting commit.

- **Run A (baseline):** work normally — open files directly, no packet.
- **Run B (CACP):** `python ctx.py pack --out .ctx/startup-packet.md`, read that
  packet once, then climb the ladder (`map`/`digest`/`read`/`run`) and retrieve
  from memory instead of re-reading.

Then compare real usage:

```bash
# Subscription (Claude Code): auto-detects ~/.claude/projects/<slug>/, or pass a file
python ctx.py measure --transcript <path-to-run-A.jsonl>
python ctx.py measure --transcript <path-to-run-B.jsonl>

# API (pay per token): feed the response usage objects and your prices
python ctx.py measure --usage-json runA-usage.json --in-price 5 --out-price 25
python ctx.py measure --usage-json runB-usage.json --in-price 5 --out-price 25
```

`measure` reports, per run: uncached input, cache read (0.1x), cache write
(1.25x), output, **cache-read share of input**, cache hit rate, effective input
in base-token-equivalents, and (with prices) an effective dollar cost. Compare B
to A on the metric that matches how you pay.

## Reading the result honestly

- A **higher cache-read share in B** means the stable prefix is working. A low
  share means something is invalidating it — you edited context mid-session or the
  packet is being rebuilt too often.
- On **per-request billing** (e.g. some Copilot tiers), shorter output does not
  reduce the charge — do not claim output savings there.
- If B is not clearly better than A on your metric, say so and turn that lever
  off. Wanting a technique to help does not make it help.

## Note on `ctx report`

`ctx report` aggregates the local ledger (admitted-vs-avoided, input-side,
heuristic `chars/3.5`). It is a **planning** signal for climbing the ladder — not
a billing number. Always confirm dollars/limit impact with `ctx measure`.
