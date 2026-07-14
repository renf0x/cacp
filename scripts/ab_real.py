#!/usr/bin/env python3
"""Reproducible A/B on a REAL repo. No invented numbers: every token figure is
computed by ctx.py from the real file bytes on disk (heuristic chars/3.5 -- the
same estimator the tool uses everywhere). Cache multipliers are the real
Anthropic ones (read 0.1x, write 1.25x).

Usage:
    python scripts/ab_real.py [path-to-repo]   # defaults to this repo

What it shows:
  1. digest vs full read on the real N biggest files  (pillar 2, measured)
  2. pack packet size vs reading the whole repo         (pillar 1, orientation)
  3. an N-turn cache model using the real multipliers   (pillar 1, modeled)

Only #3 makes an assumption (baseline churns the prefix / cold cache; CACP keeps
it cached) -- that is the mechanism under test. #1 and #2 are direct measurements
of real files. For a fully live number, compare `ctx measure` on two real agent
transcripts (see docs/measurement-protocol.md).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ctx  # noqa: E402

N = 6
rows, repo_tokens, _ = ctx._scan_repo(ROOT)
targets = [ROOT / rel for _t, _l, rel in rows[:N]]

print(f"repo: {ROOT}")
print(f"real files scanned: {len(rows)}  |  full-repo est tokens: {repo_tokens:,}\n")

print(f"{'file':40} {'full read':>10} {'digest':>10} {'reduction':>10}")
full_sum = dig_sum = 0
per_full, per_dig = [], []
for p in targets:
    full = ctx.est_tokens(ctx.read_text(p))
    dig = ctx.est_tokens(ctx._digest_text(p))
    per_full.append(full)
    per_dig.append(dig)
    full_sum += full
    dig_sum += dig
    print(f"{p.relative_to(ROOT).as_posix():40} {full:>10,} {dig:>10,} "
          f"{100 * (full - dig) / max(full, 1):>9.1f}%")
print(f"{'TOTAL (inspect top-' + str(N) + ' files)':40} {full_sum:>10,} {dig_sum:>10,} "
      f"{100 * (full_sum - dig_sum) / max(full_sum, 1):>9.1f}%\n")

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ctx.cmd_pack(argparse.Namespace(path=str(ROOT), top=40, warn=4000,
                                    digest=0, out=None, quiet=False))
packet_tok = ctx.est_tokens(buf.getvalue().split("# packet")[0])
print(f"orientation: pack packet = {packet_tok:,} est tokens "
      f"(vs {repo_tokens:,} to read the whole repo)\n")

T = N
READ, WRITE = ctx.CACHE_READ_MULT, ctx.CACHE_WRITE_MULT
orient = full_sum // N * 2  # a realistic orientation ~= two big files
base = sum(orient + per_full[i] for i in range(T))                 # cold, full reads
cacp = orient * WRITE + sum(orient * READ + per_dig[i] for i in range(T))  # cached, digests
print(f"{T}-turn model (orientation re-sent each turn + 1 file/turn):")
print(f"  baseline (cold prefix, full reads) : {base:>12,.0f} input-equiv")
print(f"  CACP (cached prefix, digests)      : {cacp:>12,.0f} input-equiv")
print(f"  reduction                          : {100 * (base - cacp) / max(base, 1):>11.1f}%")
