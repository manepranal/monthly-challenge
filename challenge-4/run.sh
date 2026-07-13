#!/bin/bash
# =========================================================================
# Deal Organizer — Runner (challenge-4, July "get your agents organized")
# =========================================================================
# Take a deal's inbox (emails + attachments), and let Claude file every
# document into the right folder and build a calendar of every deadline.
#
# Usage:
#   ./run.sh                       # runs on the sample deal in examples/
#   ./run.sh examples              # same, explicit
#   ./run.sh /path/to/deal-inbox   # any folder with inbox.json + attachments/
#
#   DEAL_MODEL=claude-opus-4-8 ./run.sh    # override the model
# =========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$ANTHROPIC_API_KEY" ] && ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: neither ANTHROPIC_API_KEY nor 'claude' CLI is available." >&2
  echo "       Either: export ANTHROPIC_API_KEY=sk-ant-..." >&2
  echo "       Or: install Claude Code (https://claude.com/claude-code) and run 'claude login'." >&2
  exit 1
fi

if ! python3 -c "import anthropic, pypdf" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt
fi

python3 main.py "$@"
