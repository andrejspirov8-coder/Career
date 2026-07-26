#!/usr/bin/env bash
set -euo pipefail

MEMORY_DIR="$(cd "$(dirname "$0")/.." && pwd)/.memory"
TOPIC="${1:?usage: remember.sh <topic> [message]}"
TOPIC_FILE="$MEMORY_DIR/topics/$TOPIC.md"
INDEX_FILE="$MEMORY_DIR/index.md"
TIMESTAMP="$(date '+%Y-%m-%d')"

# Read message from arg or stdin
if [ -n "${2-}" ]; then
  MESSAGE="$2"
else
  MESSAGE="$(cat)"
fi

if [ -z "$MESSAGE" ]; then
  echo "error: no message provided" >&2
  exit 1
fi

mkdir -p "$MEMORY_DIR/topics"

# Append to topic file
echo "- $TIMESTAMP — $MESSAGE" >> "$TOPIC_FILE"

# If topic is new, add to index
if ! grep -q "[[$TOPIC]]" "$INDEX_FILE" 2>/dev/null; then
  first_message="$(head -1 <<< "$MESSAGE")"
  echo "- [[$TOPIC]] — $TIMESTAMP: $first_message" >> "$INDEX_FILE"
fi

echo "saved to memory: [$TOPIC] $MESSAGE"
