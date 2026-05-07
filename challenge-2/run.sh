#!/bin/bash
# =========================================================================
# Doc → reZen Agent — Runner (challenge-2)
# =========================================================================
# Take a contract or listing-agreement PDF/image, create the matching draft
# in reZen, and upload the source document to the checklist.
#
# Usage:
#   ./run.sh path/to/contract.pdf
#   ./run.sh path/to/listing.jpg
#   DRAFT_TX_ENV=team1 ./run.sh path/to/contract.pdf
# =========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
  echo "       export ANTHROPIC_API_KEY=sk-ant-..." >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "Usage: $0 <path-to-contract-or-listing.pdf|.png|.jpg>" >&2
  exit 1
fi

if ! python3 -c "import anthropic, requests" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt
fi

python3 main.py "$@"
