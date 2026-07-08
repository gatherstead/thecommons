#!/usr/bin/env bash
# PostToolUse lint hook — invoked by Claude Code after Edit/Write.
# Reads a JSON payload from stdin, extracts the edited file path, and
# runs Ruff (Python) or ESLint (TS/TSX) if the file lives inside the
# linted tree.  Files outside those trees are skipped cleanly (exit 0).

set -euo pipefail

# --- 1. Extract file path from stdin JSON -----------------------------------
file=$(python3 -c '
import json, sys
payload = json.load(sys.stdin)
print(payload.get("tool_input", {}).get("file_path", ""))
')

# Nothing to lint.
if [[ -z "$file" ]]; then
  exit 0
fi

# File no longer exists (e.g. a delete-then-recreate race).
if [[ ! -f "$file" ]]; then
  exit 0
fi

# --- 2. Resolve repo root ---------------------------------------------------
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backendServer"
FRONTEND_DIR="$REPO_ROOT/theCommonsWeb"

# --- 3. Determine extension -------------------------------------------------
ext="${file##*.}"

# --- 4. Branch on extension + directory -------------------------------------
case "$ext" in
  py)
    # Only lint files inside backendServer/.
    if [[ "$file" != "$BACKEND_DIR/"* ]]; then
      exit 0
    fi
    cd "$BACKEND_DIR"
    output=$(uv run ruff check "$file" 2>&1) && exit 0
    echo "==> ruff lint failed: $file"
    echo "$output"
    exit 1
    ;;
  ts|tsx)
    # Only lint files inside theCommonsWeb/.
    if [[ "$file" != "$FRONTEND_DIR/"* ]]; then
      exit 0
    fi
    cd "$FRONTEND_DIR"
    output=$(pnpm exec eslint "$file" 2>&1) && exit 0
    echo "==> eslint lint failed: $file"
    echo "$output"
    exit 1
    ;;
  *)
    # Unknown extension — skip cleanly.
    exit 0
    ;;
esac
