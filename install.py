#!/usr/bin/env python3
"""Install CTX Agent Context Stack into the root of another project."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANAGED_START = "<!-- CTX-AGENT-CONTEXT-STACK:START -->"
MANAGED_END = "<!-- CTX-AGENT-CONTEXT-STACK:END -->"
GENERIC_CONTEXT = """# Universal Agent Context Protocol

This project uses CTX Agent Context Stack. Any coding agent should follow this
vendor-neutral protocol.

## Start

1. If `memory/MEMORY.md` is missing, run
   `python ctx.py memory init --with-codegraph`.
2. After first-time initialization run
   `python ctx.py memory open --install-obsidian`.
3. Read only `memory/MEMORY.md`, `handoff.md`, and
   `memory/project-rules.md`.
4. Use CodeGraph for code relationships, RLM for broad semantic questions,
   and CTX digest/run for large files and noisy output.

## Handoff

`handoff.md` is shared by every agent and contains only `Now`, `Next`,
`Blocked`, and `Done this session`. Tasks use stable `TASK-YYYYMMDD-NNN`
identifiers with status, goal, acceptance criteria, and links.

At task completion update handoff and the relevant memory journal, then run
`python ctx.py memory check`.

Never edit `memory/project-rules.md` without explicit user approval. After an
approved change run `python ctx.py memory rules-approve --user-approved`.
"""
CODEX_ADAPTER = f"""{MANAGED_START}
## CTX Agent Context Stack

Follow `AGENT_CONTEXT.md`. Use the universal handoff for collaboration with
Codex, Claude, Cursor, Copilot, Gemini, Cline, Roo, OpenCode, and other agents.
Initialize missing memory with `python ctx.py memory init --with-codegraph`,
then run `python ctx.py memory open --install-obsidian`.
{MANAGED_END}
"""
CLAUDE_ADAPTER = f"""{MANAGED_START}
## CTX Agent Context Stack

Follow `AGENT_CONTEXT.md`. Use the universal handoff for collaboration with
Codex, Claude, Cursor, Copilot, Gemini, Cline, Roo, OpenCode, and other agents.
Initialize missing memory with `python ctx.py memory init --with-codegraph`,
then run `python ctx.py memory open --install-obsidian`. Use `/compact` between
substantial tasks and `/clear` for unrelated work.
{MANAGED_END}
"""


def copy_file(source: Path, target: Path, force: bool) -> str:
    if target.exists() and not force:
        return "kept"
    existed = target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return "updated" if existed else "created"


def append_managed_block(target: Path, block: str) -> str:
    block = block.strip()
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if MANAGED_START in current:
        return "kept"
    target.parent.mkdir(parents=True, exist_ok=True)
    separator = "\n\n" if current.strip() else ""
    target.write_text(current.rstrip() + separator + block + "\n", encoding="utf-8")
    return "appended"


def run(command: list[str], cwd: Path) -> int:
    print("+", subprocess.list2cmdline(command))
    return subprocess.run(command, cwd=cwd).returncode


def parse_agents(value: str) -> list[str]:
    if value == "all":
        return ["generic", "codex", "claude"]
    agents = [part.strip().lower() for part in value.split(",") if part.strip()]
    valid = {"generic", "codex", "claude"}
    invalid = sorted(set(agents) - valid)
    if invalid:
        raise argparse.ArgumentTypeError(f"unknown agents: {', '.join(invalid)}")
    return agents or ["generic"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install CTX, RLM, memory, CodeGraph bootstrap, and handoff files."
    )
    parser.add_argument("project", nargs="?", default=".", help="target project root")
    parser.add_argument(
        "--agents",
        type=parse_agents,
        default=parse_agents("all"),
        help="all or comma-separated: generic,codex,claude (default: all)",
    )
    parser.add_argument(
        "--force-toolkit",
        action="store_true",
        help="replace existing ctx.py and rlm.py",
    )
    parser.add_argument(
        "--no-codegraph",
        action="store_true",
        help="do not initialize CodeGraph",
    )
    parser.add_argument(
        "--open-obsidian",
        action="store_true",
        help="install Obsidian when needed and open the memory vault",
    )
    args = parser.parse_args(argv)

    project = Path(args.project).resolve()
    project.mkdir(parents=True, exist_ok=True)

    results = {
        "ctx.py": copy_file(ROOT / "ctx.py", project / "ctx.py", args.force_toolkit),
        "rlm.py": copy_file(ROOT / "rlm.py", project / "rlm.py", args.force_toolkit),
    }
    if "generic" in args.agents:
        context = project / "AGENT_CONTEXT.md"
        if context.exists():
            results["AGENT_CONTEXT.md"] = "kept"
        else:
            context.write_text(GENERIC_CONTEXT, encoding="utf-8")
            results["AGENT_CONTEXT.md"] = "created"
    if "codex" in args.agents:
        results["AGENTS.md"] = append_managed_block(
            project / "AGENTS.md",
            CODEX_ADAPTER,
        )
    if "claude" in args.agents:
        results["CLAUDE.md"] = append_managed_block(
            project / "CLAUDE.md",
            CLAUDE_ADAPTER,
        )

    python = sys.executable
    init = [python, "ctx.py", "memory", "init"]
    if not args.no_codegraph:
        init.append("--with-codegraph")
    if run(init, project) != 0:
        return 1
    if args.open_obsidian:
        if run([python, "ctx.py", "memory", "open", "--install-obsidian"], project) != 0:
            return 1
    if run([python, "ctx.py", "memory", "check"], project) != 0:
        return 1

    print("\nInstalled:")
    for name, result in results.items():
        print(f"- {name}: {result}")
    print("\nNext: open the project with any coding agent and describe the task normally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
