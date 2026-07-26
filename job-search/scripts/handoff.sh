#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MEMORY_DIR="$ROOT/.memory"
SESSIONS_DIR="$MEMORY_DIR/sessions"
INDEX_FILE="$MEMORY_DIR/index.md"

TIMESTAMP="$(date '+%Y-%m-%d %H:%M')"
FILENAME="$(date '+%Y-%m-%d-%H%M')"

GOAL="${GOAL:?usage: GOAL=... DONE=... make handoff}"
DONE_LIST="${DONE:-}"
NEXT_LIST="${NEXT:-}"
BLOCKER_LIST="${BLOCKERS:-}"

mkdir -p "$SESSIONS_DIR"

{
  echo "# Session $TIMESTAMP"
  echo
  echo "**Goal:** $GOAL"
  echo
  echo "**Done:**"
  if [ -n "$DONE_LIST" ]; then
    echo "$DONE_LIST" | tr '|' '\n' | while IFS= read -r item; do
      echo "- $item"
    done
  else
    echo "- (not specified)"
  fi
  echo
  echo "**Next:**"
  if [ -n "$NEXT_LIST" ]; then
    echo "$NEXT_LIST" | tr '|' '\n' | while IFS= read -r item; do
      echo "1. $item"
    done
  else
    echo "1. (not specified)"
  fi
  echo
  echo "**Blockers:**"
  if [ -n "$BLOCKER_LIST" ]; then
    echo "$BLOCKER_LIST" | tr '|' '\n' | while IFS= read -r item; do
      echo "- $item"
    done
  else
    echo "- None"
  fi
} > "$SESSIONS_DIR/$FILENAME.md"

if ! grep -q "sessions/$FILENAME" "$INDEX_FILE" 2>/dev/null; then
  echo "- [[sessions/$FILENAME]] — $TIMESTAMP: $GOAL" >> "$INDEX_FILE"
fi

echo "handoff written to .memory/sessions/$FILENAME.md"
