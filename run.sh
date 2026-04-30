#!/bin/bash
# =========================================================================
# Draft Transaction Agent — Runner
# =========================================================================
# Take an English description of a real-estate deal, create a draft
# transaction in bolt, and print the link.
#
# Usage:
#   ./run.sh                                       # interactive (paste prompt)
#   ./run.sh "Create a transaction with $20k..."   # one-shot
#   cat examples/prompt.txt | ./run.sh             # via stdin
# =========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
  echo "       export ANTHROPIC_API_KEY=sk-ant-..." >&2
  exit 1
fi

if ! python3 -c "import anthropic, requests" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt
fi

python3 main.py "$@"
