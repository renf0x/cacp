#!/usr/bin/env python3
"""ctx.py - CACP: the Cache-Aware Context Protocol for coding agents.

Cross-harness (Claude Code / Codex / any agent). Stdlib only; the `anthropic`
package is used opportunistically for exact token counts when available.

The method has five pillars; the commands below implement them:
  1. Stable prefix .... `pack`     -- one ordered, cache-friendly startup packet
  2. Tiered admission . `map`/`digest`/`read`/`run` -- climb cheap->expensive
  3. Durable memory ... `memory`   -- load-on-demand top-k notes, not the whole vault
  4. Gated output ..... (template)  -- terse output only when it nets positive
  5. Measured .........  `measure`/`report` -- real provider usage, not estimates

Subcommands:
  init [path]         scaffold CACP into a project (memory + agent adapters + packet)
  pack [path]         build a deterministic, cache-stable startup packet
  map [path]          repo map with per-file token estimates (what is expensive to read)
  digest <file>       structural digest of a file instead of a full read
  run -- <command>    run a noisy command, print only the salient extract; full log saved
  read <file>         print a file verbatim and log it as uncompressed context
  count <file|->      token count of a file or stdin (exact via API if key present)
  rawcount <path|->   token count of unsqueezed text with no compression or ledger savings
  memory ...          durable memory vault (init/check/context/query/rotate/...)
  report              admitted-vs-avoided tokens from the local ledger (planning estimate)
  measure             REAL billed tokens + cache-hit rate from provider usage logs
"""

from __future__ import annotations

__version__ = "0.1.0"

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Rough chars-per-token for code/mixed text. Real tokenizers vary (Fable 5
# tokenizes ~30% denser input into ~30% MORE tokens than Opus-tier), so this
# is a planning estimate, not a billing number.
CHARS_PER_TOKEN = 3.5

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".ctx", "dist", "build", ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
    "target", "vendor", ".next", "coverage", "release", ".codegraph", ".obsidian",
    ".claude",
}
SKIP_FILES = {"package-lock.json", "src/assets/manifest.json"}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf",
    ".mp3", ".mp4", ".sqlite", ".db", ".pyc", ".class", ".jar", ".lock",
}

ERROR_RE = re.compile(
    r"(error|exception|traceback|failed|failure|fatal|panic|assert"
    r"|FAIL|ERROR|E\d{3,4}\b|warning C\d+|\bnpm ERR!)",
    re.IGNORECASE,
)

MEMORY_REQUIRED = (
    "MEMORY.md",
    "project-rules.md",
    "architecture.md",
    "decisions.md",
    "bugs.md",
    "investigations.md",
    "operations.md",
    "changelog.md",
    "archive/tasks",
    "archive/bugs",
    "archive/decisions",
    "archive/investigations",
    "templates/task.md",
    "templates/bug.md",
    "templates/decision.md",
    "templates/investigation.md",
    ".obsidian/app.json",
    ".obsidian/templates.json",
    ".gitignore",
    ".rules.sha256",
)
MEMORY_DIRECTORIES = {
    "archive/tasks",
    "archive/bugs",
    "archive/decisions",
    "archive/investigations",
}
MEMORY_LINE_LIMIT = 120
JOURNAL_MAX_TOKENS = 8000
JOURNAL_TARGET_TOKENS = 5000
MEMORY_JOURNALS = {
    "bugs.md": "bugs",
    "decisions.md": "decisions",
    "investigations.md": "investigations",
}
WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
ENTRY_RE = re.compile(r"(?m)^##\s+((?:BUG|DEC|INV)-[^\n]+)\n")

MEMORY_TEMPLATES = {
    "MEMORY.md": """# Project Memory

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
- Rebuild the cache-stable startup packet: `python ctx.py pack`
- First bootstrap: `python ctx.py memory open --install-obsidian`
""",
    "project-rules.md": """# Permanent Project Rules

> Agents must not edit or delete these rules without explicit user instruction
> or confirmation. After an approved change, run
> `python ctx.py memory rules-approve --user-approved`.

## RULE-001

- Status: active
- Rule: Preserve existing behavior unless the task explicitly requires a change.

## RULE-002

- Status: active
- Rule: After memory initialization, run
  `python ctx.py memory open --install-obsidian` once for project bootstrap.
""",
    "architecture.md": "# Architecture\n\nProject architecture and stable component boundaries.\n",
    "decisions.md": "# Decision Log\n\n## DEC-000 Template\n\n- Status: example\n- Date: YYYY-MM-DD\n- Decision:\n- Reason:\n- Consequences:\n- Links:\n",
    "bugs.md": "# Bug Log\n\n## BUG-000 Template\n\n- Status: example\n- Date: YYYY-MM-DD\n- Symptom:\n- Cause:\n- Resolution:\n- Regression test:\n- Links:\n",
    "investigations.md": "# Investigation Log\n\n## INV-000 Template\n\n- Status: example\n- Date: YYYY-MM-DD\n- Question:\n- Findings:\n- Conclusion:\n- Links:\n",
    "operations.md": "# Operations\n\nCommands, verification steps, and operational constraints.\n",
    "changelog.md": "# Memory Changelog\n\nRecord meaningful changes to the memory system.\n",
    "templates/task.md": """## TASK-YYYYMMDD-NNN

- Status: next
- Goal:
- Acceptance:
- Links:
""",
    "templates/bug.md": """## BUG-YYYYMMDD-NNN

- Status: open
- Date: YYYY-MM-DD
- Symptom:
- Cause:
- Resolution:
- Regression test:
- Links:
""",
    "templates/decision.md": """## DEC-YYYYMMDD-NNN

- Status: active
- Date: YYYY-MM-DD
- Decision:
- Reason:
- Consequences:
- Links:
""",
    "templates/investigation.md": """## INV-YYYYMMDD-NNN

- Status: open
- Date: YYYY-MM-DD
- Question:
- Findings:
- Conclusion:
- Links:
""",
    ".obsidian/app.json": json.dumps({
        "newFileLocation": "folder",
        "newFileFolderPath": "memory",
        "useMarkdownLinks": False,
        "alwaysUpdateLinks": True,
    }, indent=2) + "\n",
    ".obsidian/templates.json": json.dumps({
        "folder": "templates",
        "dateFormat": "YYYY-MM-DD",
        "timeFormat": "HH:mm",
    }, indent=2) + "\n",
    ".gitignore": "workspace.json\nworkspace-mobile.json\ncache\n",
}
ROOT_GITIGNORE_TEMPLATE = """.ctx/
__pycache__/
node_modules/
dist/
build/
coverage/
.env
.env.*
"""


def est_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def exact_tokens(text: str) -> tuple[int, str]:
    """Return (tokens, method). Uses the Anthropic count_tokens endpoint when
    the SDK and ANTHROPIC_API_KEY are available; falls back to the heuristic."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # type: ignore

            client = anthropic.Anthropic()
            resp = client.messages.count_tokens(
                model="claude-opus-4-8",
                messages=[{"role": "user", "content": text or " "}],
            )
            return resp.input_tokens, "api:claude-opus-4-8"
        except Exception as exc:  # network/SDK issues must never break the tool
            sys.stderr.write(f"[ctx] count_tokens unavailable ({exc}); using heuristic\n")
    return est_tokens(text), "heuristic(chars/3.5)"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


LEDGER_PATH = Path(".ctx") / "ledger.jsonl"


# Ops that pull full, uncompressed content into the agent's context. They are
# the denominator for the honest savings percentage: every token a `read`
# admits is context that ctx did NOT compress, so it dilutes the headline ratio
# instead of being silently excluded like a direct Read would be.
RAW_OPS = frozenset({"read", "direct"})

# Orientation ops whose "raw" side is a hypothetical read-everything cost rather
# than a real 1:1 content substitution. They stay in the per-op table for
# visibility but are kept out of the headline savings % so it cannot be inflated
# by a denominator the agent would never actually have paid.
RECON_OPS = frozenset({"map", "pack"})


def ledger_log(op: str, raw_tok: int, kept_tok: int, detail: str,
               **extra: object) -> None:
    """Append a savings record to the ledger.

    Written exclusively by this tool (deterministic code) — the model never
    computes or edits these numbers, so `ctx.py report` measures the effect
    independently of the agent's own claims. `extra` carries optional, schema-v2
    fields (provider/model/calls/path/exit_code); None values are dropped so old
    readers and aggregates keep working."""
    try:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec: dict[str, object] = {
            "v": 2,
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "op": op,
            "raw_tokens": raw_tok,
            "kept_tokens": kept_tok,
            "saved_tokens": max(0, raw_tok - kept_tok),
            "detail": detail,
        }
        rec.update({k: v for k, v in extra.items() if v is not None})
        with LEDGER_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:
        sys.stderr.write(f"[ctx] ledger write failed: {exc}\n")


# ----------------------------------------------------------------- map ----

def _scan_repo(root: Path) -> tuple[list[tuple[int, int, str]], int, int]:
    """Walk the repo once. Return (rows, total_tokens, skipped) where each row is
    (tokens, lines, relpath), sorted most-expensive first. Deterministic: the
    same tree always yields the same order, which is what keeps `pack` output
    byte-stable across turns so the agent's prompt cache stays hot."""
    rows: list[tuple[int, int, str]] = []
    total_tokens = 0
    skipped = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            relpath = p.relative_to(root).as_posix()
            if name in SKIP_FILES or relpath in SKIP_FILES:
                skipped += 1
                continue
            if p.suffix.lower() in BINARY_EXT:
                skipped += 1
                continue
            try:
                text = read_text(p)
            except OSError:
                skipped += 1
                continue
            tok = est_tokens(text)
            total_tokens += tok
            rows.append((tok, text.count("\n") + 1, relpath))
    rows.sort(reverse=True)
    return rows, total_tokens, skipped


def _render_map(root: Path, rows: list[tuple[int, int, str]], total_tokens: int,
                skipped: int, top: int, warn: int, show_all: bool) -> str:
    out: list[str] = []
    out.append(f"# repo map: {root}")
    out.append(f"# files: {len(rows)} (skipped {skipped} binary/unreadable), "
               f"~{total_tokens:,} tokens total to read everything")
    out.append(f"{'~tokens':>9}  {'lines':>6}  path")
    shown = rows if show_all else rows[:top]
    for tok, lines, rel in shown:
        flag = "  <- EXPENSIVE, prefer `ctx.py digest`" if tok >= warn else ""
        out.append(f"{tok:>9,}  {lines:>6}  {rel}{flag}")
    if not show_all and len(rows) > top:
        rest = sum(t for t, _, _ in rows[top:])
        out.append(f"      ...   {len(rows) - top} more files, ~{rest:,} tokens (use --all)")
    return "\n".join(out)


def cmd_map(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    rows, total_tokens, skipped = _scan_repo(root)
    rendered = _render_map(root, rows, total_tokens, skipped,
                           args.top, args.warn, args.all)
    # Orienting via the map costs the printed listing instead of reading every
    # file; log that gap so recon shows up in the savings report too.
    ledger_log("map", total_tokens, est_tokens(rendered), str(root),
               files=len(rows))
    print(rendered)
    return 0


# ----------------------------------------------------------------- pack ----

SQL_STMT_RE = re.compile(
    r"^\s*(create|alter|drop|truncate|comment on|grant|revoke|insert into|copy"
    r"|create policy|enable row level security|--)", re.IGNORECASE)
SQL_CREATE_BLOCK_RE = re.compile(
    r"^\s*create\s+(table|type|view|materialized view|index|function|trigger|policy)",
    re.IGNORECASE)


def digest_sql(text: str) -> list[str]:
    """SQL-aware digest: keep schema (CREATE blocks with their column lists),
    statement headers (INSERT INTO names table+columns), policies/grants and
    comments; drop the data rows, reporting how many were omitted. The generic
    digest used to crush seed files to near-nothing and lose the schema."""
    out: list[str] = []
    in_block = False
    omitted = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if in_block:
            out.append(ln.rstrip())
            if s.endswith((");", ")")) or s == ");":
                in_block = False
            continue
        if SQL_CREATE_BLOCK_RE.match(ln):
            out.append(ln.rstrip())
            # a CREATE ... ( that does not close on the same line opens a block
            # whose body (columns/constraints) is schema, not data -- keep it
            if "(" in ln and ");" not in ln:
                in_block = True
            continue
        if SQL_STMT_RE.match(ln):
            out.append(ln.rstrip())
        else:
            omitted += 1
    if omitted:
        out.append(f"-- [{omitted} data/detail lines omitted by digest]")
    return out


CSS_PROP_RE = re.compile(r"^\s*--[\w-]+\s*:")


def digest_css(text: str) -> list[str]:
    """CSS-aware digest: keep the structure that answers layout questions --
    selectors, @media/@supports/@keyframes, custom properties -- and drop
    individual declarations, reporting how many were omitted."""
    out: list[str] = []
    omitted = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(("/*", "*")):
            continue
        if (s.startswith("@") or "{" in s or s == "}" or CSS_PROP_RE.match(ln)):
            out.append(ln.rstrip())
        else:
            omitted += 1
    if omitted:
        out.append(f"/* [{omitted} declaration lines omitted by digest] */")
    return out


def _digest_text(p: Path) -> str:
    """Structural digest of a single file, shared by `digest` and `pack`.
    File-type aware: Python via AST, SQL keeps schema not data, CSS keeps
    selectors not declarations, everything else via the generic keep-list."""
    text = read_text(p)
    suf = p.suffix.lower()
    if suf == ".py":
        kept = digest_python(text)
    elif suf == ".sql":
        kept = digest_sql(text)
    elif suf in {".css", ".scss", ".less"}:
        kept = digest_css(text)
    else:
        kept = [ln.rstrip() for ln in text.splitlines() if GENERIC_KEEP.match(ln)]
        if not kept:
            ls = text.splitlines()
            kept = ls[:15] + (["..."] + ls[-5:] if len(ls) > 20 else [])
    return "\n".join(kept)


def cmd_pack(args: argparse.Namespace) -> int:
    """Pillar 1: emit ONE deterministic, cache-stable startup packet.

    Order is most-stable first so the agent's cacheable prompt prefix stays
    byte-identical across turns (rules rarely change; the map changes only when
    files are added; digests change with code). Volatile state (handoff, the
    current task) is deliberately excluded -- append that AFTER this packet so it
    never invalidates the cached prefix. On the API this bills the repeated
    prefix at 0.1x; on a subscription it keeps the auto-cache hot and shrinks the
    admitted context. There are no timestamps in the body on purpose."""
    root = Path(args.path).resolve()
    memory = root / "memory"
    sections: list[str] = []

    # 1. Durable rules (most stable).
    rules = memory / "project-rules.md"
    if rules.is_file():
        sections.append(f"===== PERMANENT RULES (memory/project-rules.md) =====\n"
                        f"{read_text(rules).strip()}")

    # 2. Memory index (thin, fairly stable).
    index = memory / "MEMORY.md"
    if index.is_file():
        sections.append(f"===== MEMORY INDEX (memory/MEMORY.md) =====\n"
                        f"{read_text(index).strip()}")

    # 3. Repo map (changes only when files are added/removed).
    rows, total_tokens, skipped = _scan_repo(root)
    map_text = _render_map(root, rows, total_tokens, skipped,
                           args.top, args.warn, show_all=False)
    sections.append(f"===== REPO MAP =====\n{map_text}")

    # 4. Optional digests of the top-K most expensive files.
    for _tok, _lines, rel in rows[: max(0, args.digest)]:
        p = root / rel
        try:
            sections.append(f"===== DIGEST: {rel} =====\n{_digest_text(p)}")
        except OSError:
            continue

    header = ("# CACP startup packet -- cache-stable prefix.\n"
              "# Read this ONCE at session start. Append the task/handoff AFTER it;\n"
              "# do NOT edit this block mid-session or the prompt cache is invalidated.")
    packet = header + "\n\n" + "\n\n".join(sections) + "\n"
    packet_tok = est_tokens(packet)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(packet, encoding="utf-8")

    # Recon-style ledger record: the packet stands in for reading the whole repo.
    ledger_log("pack", total_tokens, packet_tok, str(root),
               files=len(rows), digests=max(0, args.digest))
    if args.quiet and args.out:
        print(f"# wrote {args.out}: ~{packet_tok:,} tokens "
              f"(vs ~{total_tokens:,} to read the whole repo)")
    else:
        sys.stdout.write(packet)
        print(f"# packet ~{packet_tok:,} tokens vs ~{total_tokens:,} to read everything "
              f"({total_tokens / max(packet_tok, 1):.1f}x smaller startup baseline)"
              + (f"; written to {args.out}" if args.out else ""))
    return 0


# -------------------------------------------------------------- digest ----

PY_KEEP = re.compile(r"^\s*(def |class |async def |import |from |@)")
GENERIC_KEEP = re.compile(
    r"^\s*(def |class |function |func |fn |interface |struct |enum |type "
    r"|import |from |export |const [A-Z_]+|public |private |protected "
    r"|#{1,3} |// ---|/\*\*|describe\(|it\(|test\()"
)


def digest_python(text: str) -> list[str]:
    """AST-based digest: imports, class/def signatures, first docstring lines."""
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [ln for ln in text.splitlines() if PY_KEEP.match(ln)]

    lines = text.splitlines()
    out: list[str] = []
    doc = ast.get_docstring(tree)
    if doc:
        out.append('"""' + doc.splitlines()[0] + '"""')
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            ln = lines[node.lineno - 1].rstrip()
            indent = len(ln) - len(ln.lstrip())
            out.append((indent, node.lineno, ln))  # type: ignore[arg-type]
    # keep source order for tuple entries, strings (docstring) stay first
    sigs = sorted((e for e in out if isinstance(e, tuple)), key=lambda t: t[1])
    head = [e for e in out if isinstance(e, str)]
    return head + [t[2] for t in sigs]


def cmd_digest(args: argparse.Namespace) -> int:
    p = Path(args.file)
    if not p.is_file():
        sys.stderr.write(f"[ctx] not a file: {p}\n")
        return 2
    full_tok = est_tokens(read_text(p))
    digest = _digest_text(p)
    dig_tok = est_tokens(digest)
    ledger_log("digest", full_tok, dig_tok, str(p))
    print(f"# digest of {p} -- ~{dig_tok:,} tokens instead of ~{full_tok:,} "
          f"({full_tok / max(dig_tok, 1):.1f}x saving); read the full file only if needed")
    print(digest)
    return 0


# ----------------------------------------------------------------- run ----

def cmd_run(args: argparse.Namespace) -> int:
    if not args.command:
        sys.stderr.write("[ctx] usage: ctx.py run -- <command...>\n")
        return 2
    cmdline = subprocess.list2cmdline(args.command) if os.name == "nt" else " ".join(args.command)
    proc = subprocess.run(cmdline, shell=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    raw = (proc.stdout or "") + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
    raw_lines = raw.splitlines()

    log_dir = Path(".ctx") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"{stamp}.log"
    log_path.write_text(f"$ {cmdline}\nexit={proc.returncode}\n\n{raw}",
                        encoding="utf-8")

    # extract: every error-ish line (capped) + the tail
    err_idx = [i for i, ln in enumerate(raw_lines) if ERROR_RE.search(ln)]
    keep: dict[int, str] = {}
    for i in err_idx[: args.max_errors]:
        for j in range(max(0, i - args.ctx_lines), min(len(raw_lines), i + args.ctx_lines + 1)):
            keep[j] = raw_lines[j]
    for j in range(max(0, len(raw_lines) - args.tail), len(raw_lines)):
        keep[j] = raw_lines[j]

    shown_lines: list[str] = []
    prev = None
    for j in sorted(keep):
        if prev is not None and j > prev + 1:
            shown_lines.append(f"  ... [{j - prev - 1} lines omitted, see {log_path}]")
        shown_lines.append(keep[j])
        prev = j
    shown = "\n".join(shown_lines)

    raw_tok, shown_tok = est_tokens(raw), est_tokens(shown) if shown else 0
    ledger_log("run", raw_tok, shown_tok, cmdline)
    print(shown)
    print(f"\n# exit={proc.returncode} | {len(raw_lines)} lines -> {len(keep)} shown "
          f"| ~{raw_tok:,} -> ~{shown_tok:,} tokens "
          f"({raw_tok / max(shown_tok, 1):.1f}x saving) | full log: {log_path}")
    return proc.returncode


# --------------------------------------------------------------- count ----

def cmd_count(args: argparse.Namespace) -> int:
    if args.file == "-":
        text = sys.stdin.read()
        label = "<stdin>"
    else:
        p = Path(args.file)
        if not p.is_file():
            sys.stderr.write(f"[ctx] not a file: {p}\n")
            return 2
        text = read_text(p)
        label = str(p)
    tok, method = exact_tokens(text)
    print(f"{label}: {tok:,} tokens ({method}), {len(text):,} chars")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    """Print a file verbatim and record it as uncompressed context pulled in.

    Use this instead of a plain editor read when you genuinely need the whole
    file: it gives the agent the same bytes, but logs the pull so `ctx report`
    can show what fraction of context actually went through a compressor versus
    being admitted raw. Raw reads have no saving — they are the honest
    denominator of the savings percentage."""
    p = Path(args.file)
    if not p.is_file():
        sys.stderr.write(f"[ctx] not a file: {p}\n")
        return 2
    text = read_text(p)
    tok = est_tokens(text)
    ledger_log("read", tok, tok, str(p))
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    print(f"# read {p} verbatim -- ~{tok:,} tokens admitted uncompressed "
          f"(prefer `ctx.py digest` for structure, or `ctx.py memory query` to reuse a note)")
    return 0


# A Bash call that itself invokes ctx already writes its own ledger record
# (digest/run/read/pack). Counting the Bash tool_response on top would double-count
# the same content as a raw "direct" pull, so the hook skips these.
_CTX_SELFCALL_RE = re.compile(
    r"(^|[|&;(\n]\s*)ctx\b|(^|[|&;(\n]\s*)(python\d?|py)\s+\S*ctx\.py\b")


def _is_ctx_selfcall(command: str) -> bool:
    return bool(_CTX_SELFCALL_RE.search(command or ""))


def _hook_tokens_and_label(event: dict) -> tuple[int, str]:
    """Estimate the context tokens an agent tool call admitted, plus a label.

    Reads the Claude Code PostToolUse payload. We count the tool RESPONSE (what
    actually entered the agent's context), falling back to the read target's
    size. Returns (0, ...) when there is nothing to charge."""
    tool = str(event.get("tool_name", "") or "")
    resp = event.get("tool_response")
    text = ""
    if isinstance(resp, str):
        text = resp
    elif isinstance(resp, dict):
        # Read returns {"file": {"content": ...}}; Bash returns stdout/stderr.
        for key in ("content", "stdout", "output", "stderr"):
            val = resp.get(key)
            if isinstance(val, str):
                text += val
        if not text:
            inner = resp.get("file")
            if isinstance(inner, dict) and isinstance(inner.get("content"), str):
                text = inner["content"]
    if not text:
        # Pre-run or content-less event: fall back to the file being read.
        fp = (event.get("tool_input") or {}).get("file_path")
        if isinstance(fp, str) and Path(fp).is_file():
            try:
                text = read_text(Path(fp))
            except OSError:
                text = ""
    return est_tokens(text), tool or "tool"


def cmd_hook(args: argparse.Namespace) -> int:
    """Passively record context pulled by a direct agent tool call (Read/Bash).

    Wire this as a Claude Code PostToolUse hook so reads that bypass ctx still
    land in the savings denominator -- otherwise `ctx report` coverage only
    reflects pulls the agent voluntarily routed through `ctx read`. Always exits
    0 and prints nothing: a hook must never break or slow the agent loop."""
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            return 0
        # Skip ctx's own Bash invocations: those already self-log, so
        # counting their output here would double-count the same content.
        if str(event.get("tool_name", "")) == "Bash":
            cmd = (event.get("tool_input") or {}).get("command", "")
            if isinstance(cmd, str) and _is_ctx_selfcall(cmd):
                return 0
        tok, label = _hook_tokens_and_label(event)
        if tok >= args.min_tokens:
            # tool_use_id lets `report` de-duplicate a tool call that fires the
            # hook more than once (retries / parallel hook execution).
            tid = event.get("tool_use_id") or event.get("toolUseID")
            ledger_log("direct", tok, tok, f"{label} (bypassed ctx)",
                       session=event.get("session_id"), tool_id=tid)
    except Exception:  # a hook must be silent and harmless on any malformed input
        pass
    return 0


def cmd_rawcount(args: argparse.Namespace) -> int:
    """Report the full unsqueezed context size for a file, directory, or stdin.

    Unlike digest/run this does not compress, summarize, or write savings
    records. It is a baseline meter for A/B comparisons.
    """
    skipped_secrets: list[str] = []
    if args.path == "-":
        text = sys.stdin.read()
        label = "<stdin>"
        files = 1
    else:
        p = Path(args.path)
        label = str(p)
        if p.is_dir():
            text, files, skipped_secrets = collect_context(
                p, include_secrets=args.include_secrets)
        elif p.is_file():
            text = read_text(p)
            files = 1
        else:
            sys.stderr.write(f"[ctx] not a file or directory: {p}\n")
            return 2

    tokens = est_tokens(text)
    result = {
        "path": label,
        "files": files,
        "chars": len(text),
        "tokens": tokens,
        "method": "heuristic(chars/3.5)",
        "compression": "none",
        "ledger": "not written",
        "skipped_secret_files": skipped_secrets,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"# raw context: {label}")
    print("# compression: none; ledger: not written")
    print(f"files: {files:,}")
    print(f"chars: {len(text):,}")
    print(f"tokens: ~{tokens:,} ({result['method']})")
    if skipped_secrets:
        print(f"secret-looking files skipped: {len(skipped_secrets):,} "
              f"(e.g. {', '.join(skipped_secrets[:3])}); "
              "use --include-secrets to count them")
    return 0


# -------------------------------------------------------------- memory ----

def _project_root(path: str | os.PathLike[str]) -> Path:
    return Path(path).resolve()


def _memory_root(path: str | os.PathLike[str]) -> Path:
    return _project_root(path) / "memory"


def _rules_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_rules_digest(memory: Path) -> None:
    rules = memory / "project-rules.md"
    (memory / ".rules.sha256").write_text(_rules_digest(rules) + "\n", encoding="utf-8")


def cmd_memory_init(args: argparse.Namespace) -> int:
    root = _project_root(args.path)
    memory = root / "memory"
    created: list[str] = []
    memory.mkdir(parents=True, exist_ok=True)
    for rel in MEMORY_REQUIRED:
        target = memory / rel
        if rel in MEMORY_DIRECTORIES:
            if not target.exists():
                target.mkdir(parents=True)
                created.append(f"memory/{rel}/")
            continue
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel == ".rules.sha256":
            continue
        target.write_text(MEMORY_TEMPLATES[rel], encoding="utf-8")
        created.append(f"memory/{rel}")

    handoff = root / "handoff.md"
    if not handoff.exists():
        handoff.write_text(
            "# Handoff\n\n## Now\n\n## Next\n\n## Blocked\n\n## Done this session\n",
            encoding="utf-8",
        )
        created.append("handoff.md")

    root_gitignore = root / ".gitignore"
    if not root_gitignore.exists():
        root_gitignore.write_text(ROOT_GITIGNORE_TEMPLATE, encoding="utf-8")
        created.append(".gitignore")

    checksum = memory / ".rules.sha256"
    if not checksum.exists():
        _write_rules_digest(memory)
        created.append("memory/.rules.sha256")

    print(f"# memory initialized at {memory}")
    print("# created: " + (", ".join(created) if created else "nothing (already initialized)"))
    return 0


def _resolve_wiki_link(source: Path, memory: Path, raw: str) -> Path | None:
    target = raw.split("|", 1)[0].split("#", 1)[0].strip()
    if not target or "://" in target:
        return None
    candidate = (source.parent / target)
    if not candidate.suffix:
        candidate = candidate.with_suffix(".md")
    if candidate.exists():
        return candidate
    # Obsidian also resolves note names anywhere in the vault.
    matches = list(memory.rglob(candidate.name))
    return matches[0] if len(matches) == 1 else candidate


def memory_check(root: Path) -> list[dict[str, str]]:
    memory = root / "memory"
    issues: list[dict[str, str]] = []
    for rel in MEMORY_REQUIRED:
        target = memory / rel
        if not target.exists():
            issues.append({"code": "missing", "path": f"memory/{rel}",
                           "message": "required path is missing"})

    index = memory / "MEMORY.md"
    if index.is_file():
        lines = read_text(index).count("\n") + 1
        if lines > MEMORY_LINE_LIMIT:
            issues.append({"code": "index-too-long", "path": "memory/MEMORY.md",
                           "message": f"{lines} lines; limit is {MEMORY_LINE_LIMIT}"})

    for name in MEMORY_JOURNALS:
        journal = memory / name
        if journal.is_file() and est_tokens(read_text(journal)) > JOURNAL_MAX_TOKENS:
            issues.append({"code": "journal-too-large", "path": f"memory/{name}",
                           "message": f"over {JOURNAL_MAX_TOKENS} estimated tokens; rotate it"})

    for note in memory.rglob("*.md"):
        if "archive" in note.relative_to(memory).parts:
            continue
        for raw in WIKI_LINK_RE.findall(read_text(note)):
            resolved = _resolve_wiki_link(note, memory, raw)
            if resolved is not None and not resolved.exists():
                issues.append({"code": "broken-link",
                               "path": note.relative_to(root).as_posix(),
                               "message": f"[[{raw}]] does not resolve"})

    rules = memory / "project-rules.md"
    checksum = memory / ".rules.sha256"
    if rules.is_file() and checksum.is_file():
        expected = read_text(checksum).strip()
        actual = _rules_digest(rules)
        if expected != actual:
            issues.append({"code": "rules-changed", "path": "memory/project-rules.md",
                           "message": "rules changed without approved checksum update"})
    return issues


def cmd_memory_check(args: argparse.Namespace) -> int:
    root = _project_root(args.path)
    issues = memory_check(root)
    if args.json:
        print(json.dumps({"ok": not issues, "issues": issues}, ensure_ascii=False, indent=2))
    elif issues:
        print("# memory check failed")
        for issue in issues:
            print(f"- [{issue['code']}] {issue['path']}: {issue['message']}")
    else:
        print("# memory check: OK")
    return 1 if issues else 0


# ------------------------------------------------------ local retrieval ----
# Pillar 3: LLM-free, network-free top-k retrieval over durable notes (and,
# on demand, the whole project). It replaces the old RLM sub-agent call for the
# common "what do we already know about X" question: no provider, no keys, no
# extra token spend -- the agent loads only the few blocks it needs.

# \w is Unicode-aware in Python: Cyrillic/CJK/accented notes are searchable too,
# not only ASCII identifiers.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _split_blocks(text: str) -> list[tuple[str, str]]:
    """Split a note into (heading, block) chunks on markdown headers so a hit
    points the agent at a section, not a whole file."""
    blocks: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.*)", line)
        if m:
            if any(b.strip() for b in buf):
                blocks.append((heading, "\n".join(buf).strip()))
            heading = m.group(1).strip()
            buf = [line]
        else:
            buf.append(line)
    if any(b.strip() for b in buf):
        blocks.append((heading, "\n".join(buf).strip()))
    return blocks


def _iter_search_files(root: Path, memory_only: bool):
    if memory_only:
        base = root / "memory" if (root / "memory").is_dir() else root
        for note in sorted(base.rglob("*.md")):
            if "archive" in note.relative_to(base).parts:
                continue
            yield note
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.suffix.lower() in BINARY_EXT or _looks_secret(name):
                continue
            yield p


def _retrieve(root: Path, query: str, top: int,
              memory_only: bool) -> list[tuple[float, str, str, str]]:
    """Return the top-k (score, relpath, heading, block) matches for a query.

    Scoring is query-term frequency normalized by sqrt(block length): a short,
    on-topic block outranks a long one that mentions the term once. Deterministic
    and cheap -- no model, no network."""
    qterms = set(_tokenize(query))
    if not qterms:
        return []
    scored: list[tuple[float, str, str, str]] = []
    for path in _iter_search_files(root, memory_only):
        rel = path.relative_to(root).as_posix()
        try:
            text = read_text(path)
        except OSError:
            continue
        for heading, block in _split_blocks(text):
            words = _tokenize(block)
            hits = sum(1 for w in words if w in qterms)
            if not hits:
                continue
            # A query term in the section heading is a stronger relevance signal
            # than one buried in the body -- count heading hits twice.
            head_hits = sum(1 for w in _tokenize(heading) if w in qterms)
            score = (hits + head_hits) / (len(words) ** 0.5)
            scored.append((score, rel, heading, block))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[:top]


def _render_hits(hits: list[tuple[float, str, str, str]]) -> str:
    out: list[str] = []
    for _score, rel, heading, block in hits:
        loc = rel + (f" # {heading}" if heading else "")
        snippet = block if len(block) <= 800 else block[:800].rstrip() + " ..."
        out.append(f"----- {loc} -----\n{snippet}")
    return "\n\n".join(out)


def _memory_context(root: Path, task: str) -> str:
    memory = root / "memory"
    parts = [f"# Task\n\n{task}"]
    for path in (memory / "MEMORY.md", root / "handoff.md", memory / "project-rules.md"):
        if path.is_file():
            parts.append(f"# {path.relative_to(root).as_posix()}\n\n{read_text(path)}")

    hits = _retrieve(root, task, top=5, memory_only=True)
    if hits:
        parts.append("# Relevant durable notes (top-k retrieval)\n\n" + _render_hits(hits))
    return "\n\n".join(parts).strip() + "\n"


def _memory_vault_tokens(root: Path) -> int:
    """Token cost of reading the whole memory vault + handoff at session start —
    the corpus a focused `memory context` is meant to stand in for."""
    total = 0
    memory = root / "memory"
    if memory.is_dir():
        for note in memory.rglob("*.md"):
            # Archived notes are not part of the session-start corpus, so they
            # must not inflate the denominator (matches memory_check's scope).
            if "archive" in note.relative_to(memory).parts:
                continue
            try:
                total += est_tokens(read_text(note))
            except OSError:
                continue
    handoff = root / "handoff.md"
    if handoff.is_file():
        total += est_tokens(read_text(handoff))
    return total


def cmd_memory_context(args: argparse.Namespace) -> int:
    root = _project_root(args.path)
    text = _memory_context(root, args.task)
    kept = est_tokens(text)
    # Conservative denominator: the memory vault, not the whole repo — distilling
    # a task context beats re-reading every note at session start.
    ledger_log("mem-context", max(_memory_vault_tokens(root), kept), kept,
               args.task[:60])
    print(text, end="")
    print(f"\n# memory context: ~{kept:,} estimated tokens")
    return 0


def cmd_memory_query(args: argparse.Namespace) -> int:
    """Pillar 3: local, LLM-free top-k retrieval over durable notes.

    Returns the most relevant note blocks (or, with --scope project, the most
    relevant file blocks across the repo) so the agent loads only what it needs
    instead of re-reading the whole vault or spending a sub-agent call. No
    network, no provider, no API keys."""
    root = _project_root(args.path)
    hits = _retrieve(root, args.question, top=args.top,
                     memory_only=(args.scope == "memory"))
    if args.json:
        print(json.dumps({
            "query": args.question,
            "scope": args.scope,
            "hits": [{"score": round(s, 4), "path": rel, "heading": h,
                      "snippet": b[:800]} for s, rel, h, b in hits],
        }, ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print(f"# no matching {'notes' if args.scope == 'memory' else 'files'} "
              f"for: {args.question!r}")
        return 0
    rendered = _render_hits(hits)
    print(rendered)
    print(f"\n# {len(hits)} block(s), ~{est_tokens(rendered):,} tokens "
          f"(local retrieval, no LLM)")
    return 0


def _entry_is_closed(entry: str) -> bool:
    match = re.search(r"(?mi)^-\s*Status:\s*([^\n]+)", entry)
    if not match:
        return False
    status = match.group(1).strip().lower()
    return status in {"closed", "done", "resolved", "superseded", "archived", "example"}


def _rotate_journal(memory: Path, name: str, category: str) -> int:
    path = memory / name
    if not path.is_file():
        return 0
    text = read_text(path)
    if est_tokens(text) <= JOURNAL_MAX_TOKENS:
        return 0
    matches = list(ENTRY_RE.finditer(text))
    if not matches:
        return 0
    header = text[:matches[0].start()]
    entries = [
        text[m.start():(matches[i + 1].start() if i + 1 < len(matches) else len(text))]
        for i, m in enumerate(matches)
    ]
    moved: list[str] = []
    kept: list[str] = []
    current = est_tokens(text)
    for entry in entries:
        if current > JOURNAL_TARGET_TOKENS and _entry_is_closed(entry):
            moved.append(entry.strip())
            current -= est_tokens(entry)
        else:
            kept.append(entry.strip())
    if not moved:
        return 0
    path.write_text(header.rstrip() + "\n\n" + "\n\n".join(kept).rstrip() + "\n",
                    encoding="utf-8")
    month = datetime.date.today().strftime("%Y-%m")
    archive = memory / "archive" / category / f"{month}.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    existing = read_text(archive).rstrip() if archive.exists() else f"# {category.title()} Archive {month}"
    archive.write_text(existing + "\n\n" + "\n\n".join(moved) + "\n", encoding="utf-8")
    return len(moved)


def cmd_memory_rotate(args: argparse.Namespace) -> int:
    memory = _memory_root(args.path)
    total = sum(_rotate_journal(memory, name, category)
                for name, category in MEMORY_JOURNALS.items())
    print(f"# memory rotation: moved {total} closed entr{'y' if total == 1 else 'ies'}")
    return 0


def cmd_memory_rules_approve(args: argparse.Namespace) -> int:
    if not args.user_approved:
        sys.stderr.write("[ctx] refusing to approve rules without --user-approved\n")
        return 2
    memory = _memory_root(args.path)
    rules = memory / "project-rules.md"
    if not rules.is_file():
        sys.stderr.write(f"[ctx] missing rules file: {rules}\n")
        return 2
    _write_rules_digest(memory)
    print("# permanent rules checksum updated after explicit user approval")
    return 0


def _find_obsidian() -> str | None:
    found = shutil.which("obsidian")
    if found:
        return found
    if os.name != "nt":
        return None
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = (
        local / "Obsidian" / "Obsidian.exe",
        local / "Programs" / "Obsidian" / "Obsidian.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Obsidian" / "Obsidian.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Obsidian" / "Obsidian.exe",
    )
    return str(next((path for path in candidates if path.is_file()), "")) or None


def _install_obsidian_from_official_release() -> int:
    if os.name != "nt":
        sys.stderr.write("[ctx] automatic fallback install is currently supported on Windows only\n")
        return 1
    api = "https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest"
    try:
        request = urllib.request.Request(
            api,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "ctx-memory"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
        assets = release.get("assets", [])
        asset = next(
            item for item in assets
            if re.fullmatch(r"Obsidian-\d+(?:\.\d+)+\.exe", item.get("name", ""))
        )
        url = asset["browser_download_url"]
        if not url.startswith(
            "https://github.com/obsidianmd/obsidian-releases/releases/download/"
        ):
            raise RuntimeError("release asset is not hosted by the official Obsidian repository")
        with tempfile.TemporaryDirectory(prefix="ctx-obsidian-") as temp:
            installer = Path(temp) / asset["name"]
            urllib.request.urlretrieve(url, installer)
            proc = subprocess.run([str(installer), "/S"])
            return proc.returncode
    except (OSError, KeyError, StopIteration, ValueError, RuntimeError) as exc:
        sys.stderr.write(f"[ctx] official Obsidian install failed: {exc}\n")
        return 1


def _register_obsidian_vault(memory: Path) -> tuple[str | None, bool]:
    if os.name != "nt":
        return None, False
    appdata = Path(os.environ.get("APPDATA", ""))
    if not appdata:
        return None, False
    config = appdata / "obsidian" / "obsidian.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"vaults": {}}
    if config.is_file():
        try:
            loaded = json.loads(read_text(config))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            backup = config.with_suffix(".json.invalid")
            shutil.copy2(config, backup)
    vaults = data.setdefault("vaults", {})
    if not isinstance(vaults, dict):
        vaults = {}
        data["vaults"] = vaults
    normalized = str(memory.resolve())
    existing = next(
        (key for key, value in vaults.items()
         if isinstance(value, dict)
         and os.path.normcase(value.get("path", "")) == os.path.normcase(normalized)),
        None,
    )
    key = existing or hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    created = existing is None
    vaults[key] = {
        **(vaults.get(key, {}) if isinstance(vaults.get(key), dict) else {}),
        "path": normalized,
        "ts": round(datetime.datetime.now().timestamp() * 1000),
        "open": True,
    }
    config.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return key, created


def _restart_obsidian_if_running() -> None:
    if os.name != "nt":
        return
    check = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Obsidian.exe", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if "Obsidian.exe" not in check.stdout:
        return
    subprocess.run(
        ["taskkill", "/IM", "Obsidian.exe", "/T"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    import time
    time.sleep(2)


def cmd_memory_open(args: argparse.Namespace) -> int:
    memory = _memory_root(args.path)
    if not memory.is_dir():
        sys.stderr.write(f"[ctx] memory vault not found: {memory}\n")
        return 2
    obsidian = _find_obsidian()
    if not obsidian and args.install_obsidian:
        winget = shutil.which("winget")
        if winget:
            proc = subprocess.run([
                winget, "install", "--id", "Obsidian.Obsidian", "-e",
                "--accept-package-agreements", "--accept-source-agreements",
            ], text=True)
            if proc.returncode != 0:
                return proc.returncode
        else:
            result = _install_obsidian_from_official_release()
            if result != 0:
                return result
        obsidian = _find_obsidian()
    if not obsidian:
        sys.stderr.write("[ctx] Obsidian not found. Re-run with --install-obsidian or open "
                         f"this folder manually: {memory}\n")
        return 1
    _, created = _register_obsidian_vault(memory)
    if created:
        _restart_obsidian_if_running()
    # Obsidian assigns the real vault ID internally. The stable public reference
    # after registering the path is the folder/vault name, not our config key.
    vault_uri = "obsidian://open?vault=" + urllib.parse.quote(memory.name, safe="")
    subprocess.Popen([obsidian, vault_uri])
    print(f"# opened Obsidian vault: {memory}")
    return 0


# ------------------------------------------------------------- rawcount ----

# Files that usually hold secrets - excluded from directory scans by default.
SECRET_RE = re.compile(
    r"(^\.env($|\.)|(^|\.)(pem|key|p12|pfx)$|id_rsa|id_ed25519|^\.npmrc$|"
    r"credentials.*\.json$|oauth_creds\.json$|secret|\.pem$)",
    re.IGNORECASE)


def _looks_secret(name: str) -> bool:
    return bool(SECRET_RE.search(name))


def collect_context(root: Path, include_secrets: bool = False) -> tuple[int, int, list[str]]:
    """Concatenate every text file under a directory (same skip rules as `map`)
    into one big context string with per-file headers. Returns (context_text,
    nfiles, skipped_secret_names). Secret-looking files are excluded by default so
    the project's .env/keys are never shipped to an LLM."""
    parts: list[str] = []
    nfiles = 0
    skipped_secrets: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if not include_secrets and _looks_secret(name):
                skipped_secrets.append(rel)
                continue
            if name.startswith("."):
                continue
            if name in SKIP_FILES or rel in SKIP_FILES:
                continue
            if p.suffix.lower() in BINARY_EXT:
                continue
            try:
                text = read_text(p)
            except OSError:
                continue
            parts.append(f"\n===== FILE: {rel} =====\n{text}")
            nfiles += 1
    return "".join(parts), nfiles, skipped_secrets


# -------------------------------------------------------------- report ----

def cmd_report(args: argparse.Namespace) -> int:
    if args.reset:
        if LEDGER_PATH.is_file():
            LEDGER_PATH.unlink()
        print("# ledger reset")
        return 0
    if not LEDGER_PATH.is_file():
        print("# ledger is empty: no ctx.py digest/run operations recorded yet")
        return 0

    # Optional settle window: an async PostToolUse hook may still be flushing its
    # last record when the agent calls report right after a task. Waiting a beat
    # lets those writes land before we read.
    if getattr(args, "settle", 0):
        time.sleep(max(0, args.settle) / 1000.0)

    by_op: dict[str, dict[str, int]] = {}
    seen_ids: set[str] = set()
    bad = dup = 0
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            raw, kept = int(rec["raw_tokens"]), int(rec["kept_tokens"])
            # De-duplicate a single tool call that fired the hook more than once
            # (retries / parallel hook execution) by its tool_use_id.
            tid = rec.get("tool_id")
            if tid:
                if tid in seen_ids:
                    dup += 1
                    continue
                seen_ids.add(str(tid))
            agg = by_op.setdefault(rec["op"], {"n": 0, "raw": 0, "kept": 0})
            agg["n"] += 1
            agg["raw"] += raw
            agg["kept"] += kept
        except (json.JSONDecodeError, KeyError, ValueError):
            bad += 1

    content = {op: a for op, a in by_op.items() if op not in RECON_OPS}
    recon = {op: a for op, a in by_op.items() if op in RECON_OPS}

    print("# ledger report -- computed by ctx.py from .ctx/ledger.jsonl,")
    print("# NOT model-estimated. Heuristic token counts (chars/3.5) -- this is an")
    print("# input-side PLANNING estimate. For REAL billed tokens run `ctx measure`.")

    # --- CONTENT FLOW: real file content pulled for the task --------------
    # This is the honest, headline result. `read`/`direct` ops (raw == kept)
    # are the denominator of integrity: they admit content in full and pull the
    # percentage down, instead of vanishing the way an untracked editor read
    # would. Recon (map) is reported separately so it cannot inflate this.
    c_raw = sum(a["raw"] for a in content.values())
    c_kept = sum(a["kept"] for a in content.values())
    c_saved = c_raw - c_kept
    print("\nCONTENT FLOW  (real file content pulled for the task)")
    print(f"  {'op':<10} {'calls':>6} {'raw':>12} {'admitted':>12} {'saved':>12} {'ratio':>7}")
    for op in sorted(content):
        a = content[op]
        print(f"  {op:<10} {a['n']:>6} {a['raw']:>12,} {a['kept']:>12,} "
              f"{a['raw'] - a['kept']:>12,} {a['raw'] / max(a['kept'], 1):>6.1f}x")
    if content:
        pct = 100.0 * c_saved / max(c_raw, 1)
        print(f"  {'TOTAL':<10} {sum(a['n'] for a in content.values()):>6} {c_raw:>12,} "
              f"{c_kept:>12,} {c_saved:>12,} {c_raw / max(c_kept, 1):>6.1f}x")
        print(f"  reduction: {pct:.1f}%   ({c_raw / max(c_kept, 1):.2f}x)")
        # Tracked file-content coverage: of the bulk content the hook/funnel SAW,
        # how much went through a compressor vs was admitted raw. It covers only
        # Read/Bash; Grep/Glob/MCP/sub-agent outputs are not yet counted.
        raw_via_compressor = sum(a["raw"] for op, a in content.items() if op not in RAW_OPS)
        raw_via_read = sum(a["raw"] for op, a in content.items() if op in RAW_OPS)
        engaged = raw_via_compressor + raw_via_read
        if raw_via_read:
            cov = 100.0 * raw_via_compressor / max(engaged, 1)
            print(f"  tracked file-content coverage: {cov:.1f}% compressed "
                  f"({raw_via_read:,} of {engaged:,} tok read raw/direct)")
        else:
            print("  tracked file-content coverage: no raw reads logged -- route full")
            print("    reads through `ctx read` or wire the `ctx hook` for true coverage.")
        usd = c_saved / 1e6 * args.price
        print(f"  dollar value: ~${usd:.2f} at ${args.price}/MTok (single pass; in an agent")
        print("    loop the effect compounds as admitted tokens are re-sent each turn).")
    else:
        print("  (no content pulls logged yet)")

    # --- RECONNAISSANCE: orientation only, excluded from savings ----------
    if recon:
        print("\nRECONNAISSANCE  (orientation only -- excluded from savings)")
        for op in sorted(recon):
            a = recon[op]
            print(f"  {op:<10} repo estimate {a['raw']:>12,} -> output {a['kept']:>8,} "
                  f"({a['n']} call{'s' if a['n'] != 1 else ''})")
        print("  note: map/pack list the repo without reading it; their huge ratio is")
        print("        not a real saving and is kept out of the CONTENT FLOW headline.")

    print("\n# coverage tracks Read/Bash via the ctx hook; Grep/Glob/MCP/sub-agent")
    print("# outputs are not yet counted, so true total context may be higher.")
    print("# these are planning estimates -- confirm dollars/limits with `ctx measure`.")
    if dup:
        print(f"# de-duplicated {dup} repeated tool_use_id record(s)")
    if bad:
        print(f"# warning: {bad} malformed ledger line(s) skipped")
    return 0


# ------------------------------------------------------------- measure ----

# Real per-turn input multipliers on the Anthropic API, relative to the base
# input price: a cache READ bills at 0.1x and a 5-minute cache WRITE at 1.25x.
# Output bills at the separate output price. These are the levers a stable
# prefix (`pack`) pulls on; `measure` reports what they actually did.
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25
USAGE_KEYS = ("input_tokens", "output_tokens",
              "cache_read_input_tokens", "cache_creation_input_tokens")


def _usage_from_transcript(path: Path) -> list[dict]:
    """Pull per-message usage dicts out of a Claude Code transcript JSONL file.
    Each assistant message carries `message.usage` with the input/output and the
    two cache fields. Non-JSON / non-usage lines are skipped."""
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        msg = obj.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) else obj.get("usage")
        if isinstance(usage, dict) and any(k in usage for k in USAGE_KEYS):
            records.append(usage)
    return records


def _default_transcript_dir() -> Path:
    """Claude Code stores transcripts under ~/.claude/projects/<slug>/, where the
    slug is the absolute project path with non-alphanumerics replaced by '-'."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(Path.cwd().resolve()))
    return Path.home() / ".claude" / "projects" / slug


def _collect_usage(args: argparse.Namespace) -> tuple[list[dict], str]:
    if args.usage_json:
        raw = (sys.stdin.read() if args.usage_json == "-"
               else Path(args.usage_json).read_text(encoding="utf-8"))
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("usage", data)
        items = data if isinstance(data, list) else [data]
        return [u for u in items if isinstance(u, dict)], f"usage-json:{args.usage_json}"
    src = Path(args.transcript) if args.transcript else _default_transcript_dir()
    if src.is_file():
        files = [src]
    elif src.is_dir():
        files = sorted(src.glob("*.jsonl"))
    else:
        return [], f"transcript:{src} (not found)"
    recs: list[dict] = []
    for f in files:
        recs.extend(_usage_from_transcript(f))
    return recs, f"transcript:{src}"


def _usage_stats(recs: list[dict]) -> dict[str, float]:
    """Aggregate raw usage records into the metrics `measure` reports.

    The split matters: `cache_read` is history the PLATFORM re-serves at a
    discount regardless of any tool -- crediting it to ctx would be dishonest.
    What a context tool actually controls is the NEW tokens admitted each turn
    (uncached input + cache_creation: file reads, tool output, instructions),
    the output length, and how many turns the task takes."""
    def total(key: str) -> int:
        return sum(int(u.get(key, 0) or 0) for u in recs)

    inp, out = total("input_tokens"), total("output_tokens")
    c_read, c_write = total("cache_read_input_tokens"), total("cache_creation_input_tokens")
    turns = len(recs)
    new_input = inp + c_write  # tokens entering context for the first time
    return {
        "turns": turns,
        "input_uncached": inp,
        "cache_read": c_read,
        "cache_write": c_write,
        "output": out,
        "new_input": new_input,
        "new_per_turn": new_input / max(turns, 1),
        "out_per_turn": out / max(turns, 1),
        "input_total": inp + c_read + c_write,
        "eff_input": inp + c_read * CACHE_READ_MULT + c_write * CACHE_WRITE_MULT,
    }


def _print_stats(s: dict[str, float], source: str,
                 in_price: float, out_price: float) -> None:
    print(f"# REAL usage from {source} -- {s['turns']:.0f} assistant turn(s)")
    print("\nTOOL-CONTROLLABLE  (what CACP/agent discipline can change)")
    print(f"  new input admitted (uncached + cache-write) : {s['new_input']:>12,.0f}")
    print(f"    per turn                                   : {s['new_per_turn']:>12,.0f}")
    print(f"  output                                       : {s['output']:>12,.0f}")
    print(f"    per turn                                   : {s['out_per_turn']:>12,.0f}")
    print(f"  turns                                        : {s['turns']:>12,.0f}")
    print("\nPLATFORM CACHE  (informational -- NOT this tool's saving)")
    cache_share = 100.0 * s["cache_read"] / max(s["input_total"], 1)
    print(f"  cache read (0.1x)  : {s['cache_read']:>14,.0f}   "
          f"share of input: {cache_share:.1f}%")
    print(f"  effective input    : {s['eff_input']:>14,.0f} base-token-equiv "
          f"(caching off: {s['input_total']:,.0f})")
    print("  the cache discount is applied by the provider automatically; a tool")
    print("  only influences it indirectly by keeping the prefix stable.")
    if in_price or out_price:
        cost = s["eff_input"] / 1e6 * in_price + s["output"] / 1e6 * out_price
        print(f"  $ at ${in_price}/MTok in + ${out_price}/MTok out : ${cost:.4f}")


def _collect_from_path(path: str) -> tuple[list[dict], str]:
    """Load usage records from a path for --compare: .jsonl transcript (file or
    dir) or a .json usage dump."""
    if path.endswith(".json"):
        return _collect_usage(argparse.Namespace(usage_json=path, transcript=None))
    return _collect_usage(argparse.Namespace(usage_json=None, transcript=path))


def cmd_measure(args: argparse.Namespace) -> int:
    """Pillar 5: report REAL billed tokens from provider usage, separating the
    platform's automatic cache discount from what the tool actually controls.

    Single mode: stats for one transcript/usage dump. Compare mode
    (`--compare A B`): baseline vs CACP run -- the honest tool-effect deltas are
    new-input-per-turn, output, and turns; the platform cache is reported but
    never claimed as the tool's saving."""
    if getattr(args, "compare", None):
        a_path, b_path = args.compare
        try:
            a_recs, a_src = _collect_from_path(a_path)
            b_recs, b_src = _collect_from_path(b_path)
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"[ctx] measure: could not read usage ({exc})\n")
            return 1
        if not a_recs or not b_recs:
            sys.stderr.write(f"[ctx] measure: no usage records in "
                             f"{'A' if not a_recs else 'B'}\n")
            return 1
        a, b = _usage_stats(a_recs), _usage_stats(b_recs)
        print(f"# A/B compare -- A(baseline): {a_src}")
        print(f"#               B(candidate): {b_src}")
        print(f"\n{'metric':<28} {'A':>12} {'B':>12} {'delta':>9}")

        def row(label: str, key: str) -> None:
            av, bv = a[key], b[key]
            pct = 100.0 * (bv - av) / max(av, 1)
            print(f"{label:<28} {av:>12,.0f} {bv:>12,.0f} {pct:>+8.1f}%")

        print("-- tool-controllable " + "-" * 42)
        row("new input admitted", "new_input")
        row("  new input / turn", "new_per_turn")
        row("output", "output")
        row("  output / turn", "out_per_turn")
        row("turns", "turns")
        print("-- platform cache (informational) " + "-" * 29)
        row("cache read", "cache_read")
        row("effective input", "eff_input")
        print("\n# negative delta = B used less. Only the tool-controllable block is")
        print("# attributable to the workflow under test; cache-read volume mostly")
        print("# tracks session length and the provider's automatic caching.")
        return 0

    try:
        recs, source = _collect_usage(args)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"[ctx] measure: could not read usage ({exc})\n")
        return 1
    if not recs:
        sys.stderr.write(
            f"[ctx] measure: no usage records found ({source}).\n"
            "  subscription: pass --transcript <file.jsonl>, or run inside the\n"
            "    project dir so ~/.claude/projects/<slug>/ is auto-detected.\n"
            "  API: pipe response usage JSON with `--usage-json -` or `--usage-json <file>`.\n")
        return 1
    _print_stats(_usage_stats(recs), source, args.in_price, args.out_price)
    return 0


# ---------------------------------------------------------------- init ----
# Embedded agent-facing templates so a single downloaded ctx.py can scaffold a
# project by itself (no clone, no templates/ dir). The files under templates/
# are the human-readable mirror of these; keep them in sync.

MANAGED_START = "<!-- CTX-AGENT-CONTEXT-STACK:START -->"
MANAGED_END = "<!-- CTX-AGENT-CONTEXT-STACK:END -->"

AGENT_CONTEXT_MD = """# Universal Agent Context Protocol (CACP)

This file is vendor-neutral. Any coding agent in this project should follow it.

Goal: answer the task while touching as few tokens as possible, and keep the
cached prompt prefix stable so repeated context is nearly free.

## Start of work

1. If `memory/MEMORY.md` is missing, run `python ctx.py memory init`.
2. Build/read the cache-stable startup packet once:
   `python ctx.py pack --out .ctx/startup-packet.md`. Read it once; append the
   task and handoff AFTER it, never edit the middle, so the prompt cache stays hot.
3. For "what do we already know about X" use local retrieval, not a fresh read:
   `python ctx.py memory query "<question>"` (add `--scope project` for repo-wide).

## The context-saving ladder

Climb cheap -> expensive; stop at the first rung that answers the question:
`memory query` -> `map` -> `digest` -> `read` (funnelled full read) -> `run`.
No full-repo reads.

## Keep the cache hot

Repeated prefix tokens bill at ~0.1x on the API and extend a subscription window.
Read the stable packet once; append new material at the end; don't re-read files
you already digested. After a session, verify with real numbers: `python ctx.py
measure`. A low cache-read share means the prefix is being invalidated.

## Output length (only when it pays)

Write normally for short answers; compress only long explanations/reviews (drop
filler, use fragments) and keep code, commands, paths, and errors byte-exact.

## Quality & fewer retry turns

Prefer small anchored patches over full rewrites; after an edit verify with
`python ctx.py run -- <test/build>`; record durable findings and decisions in the
memory journals so the next session does not re-derive them.

## Memory & permanent rules

Record durable findings in `memory/*.md`, link with `[[wiki-links]]`, keep
`MEMORY.md` a thin index, never store source/logs/secrets. `handoff.md` is
volatile (Now/Next/Blocked/Done) and stays OUT of the cached packet. Never edit
`memory/project-rules.md` without user approval; after an approved change run
`python ctx.py memory rules-approve --user-approved`.
"""

_ADAPTER_BODY = """## CACP - Cache-Aware Context Protocol

Follow `AGENT_CONTEXT.md`. Answer tasks while touching as few tokens as possible
AND keeping the cached prompt prefix stable so repeated context is nearly free.

At session start build/read the stable packet:
`python ctx.py pack --out .ctx/startup-packet.md` (rules + memory index + repo
map, fixed order). Read it once; append the task/handoff AFTER it, never edit the
middle or the prompt cache is invalidated.

- Retrieve, don't re-read: `python ctx.py memory query "<q>"` (local, no LLM;
  `--scope project` for repo-wide).
- Climb the ladder for bulk: `ctx map`, `ctx digest <file>`, `ctx read <file>`,
  `ctx run -- <cmd>`.
- Verify to avoid retry turns: after edits run `ctx run -- <tests>`; prefer small
  patches; record decisions in the memory journals.
- Compress output only when it pays; keep code/commands/errors byte-exact.
- Measure for real: `python ctx.py measure` shows actual billed tokens and
  cache-read share.

Do not change permanent project rules without explicit user approval. At task
completion update the handoff, record durable findings, run `python ctx.py memory
check`."""

ADAPTER_CLAUDE = (f"{MANAGED_START}\n{_ADAPTER_BODY} Use `/compact` between "
                  f"substantial tasks and `/clear` for unrelated work.\n{MANAGED_END}\n")
ADAPTER_AGENTS = f"{MANAGED_START}\n{_ADAPTER_BODY}\n{MANAGED_END}\n"

VALID_AGENTS = ("generic", "codex", "claude")


def _parse_agents(value: str) -> list[str]:
    if value == "all":
        return list(VALID_AGENTS)
    agents = [p.strip().lower() for p in value.split(",") if p.strip()]
    bad = sorted(set(agents) - set(VALID_AGENTS))
    if bad:
        raise argparse.ArgumentTypeError(f"unknown agents: {', '.join(bad)}")
    return agents or ["generic"]


def _write_if_absent(path: Path, content: str) -> str:
    if path.exists():
        return "kept"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "created"


def _append_managed_block(path: Path, block: str) -> str:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if MANAGED_START in current:
        return "kept"
    path.parent.mkdir(parents=True, exist_ok=True)
    sep = "\n\n" if current.strip() else ""
    path.write_text(current.rstrip() + sep + block.strip() + "\n", encoding="utf-8")
    return "appended"


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold CACP into a project from this single file: memory vault, agent
    adapters, and a first cache-stable packet. Idempotent and non-destructive --
    existing files and rules are preserved. This is what makes `ctx.py` drop-in:
    download the one file, run `python ctx.py init`, done."""
    root = _project_root(args.path)
    agents = args.agents if isinstance(args.agents, list) else _parse_agents(args.agents)
    results: dict[str, str] = {}

    # 1. memory vault + handoff + gitignore (reuses the tested initializer).
    cmd_memory_init(argparse.Namespace(path=str(root)))

    # 2. agent-facing instruction files.
    if "generic" in agents:
        results["AGENT_CONTEXT.md"] = _write_if_absent(root / "AGENT_CONTEXT.md",
                                                       AGENT_CONTEXT_MD)
    if "codex" in agents:
        results["AGENTS.md"] = _append_managed_block(root / "AGENTS.md", ADAPTER_AGENTS)
    if "claude" in agents:
        results["CLAUDE.md"] = _append_managed_block(root / "CLAUDE.md", ADAPTER_CLAUDE)

    # 3. build the first cache-stable startup packet.
    packet = root / ".ctx" / "startup-packet.md"
    cmd_pack(argparse.Namespace(path=str(root), top=40, warn=4000, digest=0,
                                out=str(packet), quiet=True))

    print(f"\n# CACP initialized in {root}")
    for name, res in results.items():
        print(f"- {name}: {res}")
    print("- memory/: ready   - .ctx/startup-packet.md: built")
    print("\nNext: open the project with your agent and describe the task. It will")
    print("read .ctx/startup-packet.md, climb the ladder, and you can check real")
    print("savings any time with `python ctx.py measure`.")
    return 0


# ---------------------------------------------------------------- main ----

def main(argv: list[str] | None = None) -> int:
    # Legacy Windows consoles default to cp1251/cp866, which cannot encode
    # characters that routinely appear in answers (arrows, em dashes, etc.).
    # Force UTF-8 so output never crashes with UnicodeEncodeError.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(prog="ctx.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ini = sub.add_parser(
        "init",
        help="scaffold CACP into a project (memory + agent adapters + first packet)")
    ini.add_argument("path", nargs="?", default=".")
    ini.add_argument("--agents", type=_parse_agents, default=_parse_agents("all"),
                     help="all or comma list: generic,codex,claude (default: all)")
    ini.set_defaults(fn=cmd_init)

    m = sub.add_parser("map", help="repo map with token estimates")
    m.add_argument("path", nargs="?", default=".")
    m.add_argument("--top", type=int, default=40, help="show N most expensive files")
    m.add_argument("--all", action="store_true", help="show every file")
    m.add_argument("--warn", type=int, default=4000, help="flag files above N tokens")
    m.set_defaults(fn=cmd_map)

    pk = sub.add_parser(
        "pack",
        help="build a deterministic, cache-stable startup packet (pillar 1)")
    pk.add_argument("path", nargs="?", default=".")
    pk.add_argument("--top", type=int, default=40, help="files listed in the repo map")
    pk.add_argument("--warn", type=int, default=4000, help="flag files above N tokens")
    pk.add_argument("--digest", type=int, default=0, metavar="K",
                    help="also append structural digests of the K most expensive files")
    pk.add_argument("--out", metavar="PATH",
                    help="also write the packet to PATH (e.g. .ctx/startup-packet.md)")
    pk.add_argument("--quiet", action="store_true",
                    help="with --out, print only a one-line summary instead of the packet")
    pk.set_defaults(fn=cmd_pack)

    d = sub.add_parser("digest", help="structural digest of a file")
    d.add_argument("file")
    d.set_defaults(fn=cmd_digest)

    r = sub.add_parser("run", help="run a command, show only the salient extract")
    r.add_argument("--tail", type=int, default=20, help="always keep last N lines")
    r.add_argument("--max-errors", type=int, default=30, help="cap on error sites kept")
    r.add_argument("--ctx-lines", type=int, default=2, help="context lines around an error")
    r.add_argument("command", nargs=argparse.REMAINDER,
                   help="command after `--`, e.g. ctx.py run -- pytest -q")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("count", help="token count of a file or stdin (-)")
    c.add_argument("file")
    c.set_defaults(fn=cmd_count)

    rd = sub.add_parser(
        "read",
        help="print a file verbatim and log it as uncompressed context (savings denominator)")
    rd.add_argument("file")
    rd.set_defaults(fn=cmd_read)

    hk = sub.add_parser(
        "hook",
        help="PostToolUse hook: log context pulled by direct Read/Bash (reads JSON on stdin)")
    hk.add_argument("--min-tokens", type=int, default=200,
                    help="ignore tool calls smaller than this (default 200)")
    hk.set_defaults(fn=cmd_hook)

    rc = sub.add_parser(
        "rawcount",
        help="token count of unsqueezed text with no compression or ledger savings")
    rc.add_argument("path", help="file, directory, or - for stdin")
    rc.add_argument("--include-secrets", action="store_true",
                    help="when scanning a directory, include .env/keys/secrets")
    rc.add_argument("--json", action="store_true", help="emit machine-readable metrics")
    rc.set_defaults(fn=cmd_rawcount)

    mem = sub.add_parser("memory", help="manage the project memory vault")
    mem_sub = mem.add_subparsers(dest="memory_cmd", required=True)

    mem_init = mem_sub.add_parser("init", help="create missing memory vault files")
    mem_init.add_argument("path", nargs="?", default=".")
    mem_init.set_defaults(fn=cmd_memory_init)

    mem_check = mem_sub.add_parser("check", help="validate memory structure and rules")
    mem_check.add_argument("path", nargs="?", default=".")
    mem_check.add_argument("--json", action="store_true")
    mem_check.set_defaults(fn=cmd_memory_check)

    mem_context = mem_sub.add_parser("context", help="build a small task context")
    mem_context.add_argument("task")
    mem_context.add_argument("--path", default=".")
    mem_context.set_defaults(fn=cmd_memory_context)

    mem_query = mem_sub.add_parser(
        "query", help="local top-k retrieval over durable notes (no LLM, no keys)")
    mem_query.add_argument("question")
    mem_query.add_argument("--path", default=".")
    mem_query.add_argument("--scope", choices=["memory", "project"], default="memory",
                           help="memory=durable notes only; project=all repo files")
    mem_query.add_argument("--top", type=int, default=5, help="number of blocks to return")
    mem_query.add_argument("--json", action="store_true")
    mem_query.set_defaults(fn=cmd_memory_query)

    mem_rotate = mem_sub.add_parser("rotate", help="archive closed journal entries")
    mem_rotate.add_argument("path", nargs="?", default=".")
    mem_rotate.set_defaults(fn=cmd_memory_rotate)

    mem_rules = mem_sub.add_parser("rules-approve",
                                   help="approve the current permanent-rules checksum")
    mem_rules.add_argument("path", nargs="?", default=".")
    mem_rules.add_argument("--user-approved", action="store_true", required=True)
    mem_rules.set_defaults(fn=cmd_memory_rules_approve)

    mem_open = mem_sub.add_parser("open", help="open the memory folder in Obsidian")
    mem_open.add_argument("path", nargs="?", default=".")
    mem_open.add_argument("--install-obsidian", action="store_true")
    mem_open.set_defaults(fn=cmd_memory_open)

    rep = sub.add_parser(
        "report",
        help="ledger estimate from .ctx/ledger.jsonl (input-side planning number)")
    rep.add_argument("--price", type=float, default=5.0,
                     help="input price $/MTok for the cost estimate (default 5.0)")
    rep.add_argument("--reset", action="store_true", help="clear the ledger")
    rep.add_argument("--settle", type=int, default=0, metavar="MS",
                     help="wait MS milliseconds before reading, so a trailing async "
                          "hook write can land (default 0)")
    rep.set_defaults(fn=cmd_report)

    ms = sub.add_parser(
        "measure",
        help="REAL billed tokens + cache-hit rate from provider usage logs (pillar 5)")
    ms.add_argument("--transcript", metavar="PATH",
                    help="Claude Code transcript .jsonl file or dir "
                         "(default: auto-detect ~/.claude/projects/<slug>/)")
    ms.add_argument("--usage-json", metavar="PATH",
                    help="API-mode usage: a JSON file (or - for stdin) of response "
                         "usage objects")
    ms.add_argument("--compare", nargs=2, metavar=("A", "B"),
                    help="A/B diff of two runs (baseline vs candidate); each arg is a "
                         "transcript .jsonl file/dir or a .json usage dump")
    ms.add_argument("--in-price", type=float, default=0.0,
                    help="input $/MTok, to also print an effective dollar cost")
    ms.add_argument("--out-price", type=float, default=0.0,
                    help="output $/MTok, to also print an effective dollar cost")
    ms.set_defaults(fn=cmd_measure)

    args = ap.parse_args(argv)
    if getattr(args, "command", None) and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
