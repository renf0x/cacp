#!/usr/bin/env bash
# CACP one-line installer (macOS / Linux / WSL / Git Bash).
#
#   curl -fsSL https://raw.githubusercontent.com/renf0x/ctx-agent-context-stack/main/install.sh | bash
#
# Downloads the single self-contained ctx.py into the current project and runs
# `python ctx.py init` to scaffold the memory vault, agent adapters, and a first
# cache-stable startup packet. Non-destructive: existing files are kept.
set -euo pipefail

RAW="https://raw.githubusercontent.com/renf0x/ctx-agent-context-stack/main/ctx.py"
TARGET="${1:-.}"
AGENTS="${CACP_AGENTS:-all}"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "error: Python 3.10+ is required but was not found on PATH." >&2
  exit 1
fi

mkdir -p "$TARGET"
echo "Downloading ctx.py -> $TARGET/ctx.py"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$RAW" -o "$TARGET/ctx.py"
else
  wget -qO "$TARGET/ctx.py" "$RAW"
fi

echo "Scaffolding CACP (agents: $AGENTS)"
( cd "$TARGET" && "$PY" ctx.py init --agents "$AGENTS" )

echo
echo "Done. Open the project with your coding agent; it will read"
echo ".ctx/startup-packet.md. Check real savings any time: python ctx.py measure"
