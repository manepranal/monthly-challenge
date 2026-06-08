#!/bin/bash
# =========================================================================
# Open House Flyer Agent — Runner (challenge-3, June "Agents for Agents")
# =========================================================================
# Turn a listing (JSON file, arrakis listing id, or flags) into a polished,
# Fair-Housing-reviewed open-house flyer PNG + a social caption.
#
# Usage:
#   ./run.sh examples/listing.json
#   ./run.sh <arrakis-listing-uuid> --beds 4 --baths 3 --sqft 2450 --photo hero.jpg
#   ./run.sh --street "12 Oak Ln" --city Rye --state NY --zip 10580 \
#            --price 1250000 --beds 4 --baths 3 --photo hero.jpg
#
#   FLYER_FORMAT=social ./run.sh examples/listing.json   # 1080x1350 IG size
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

if [ $# -lt 1 ]; then
  echo "Usage: $0 <listing.json | arrakis-listing-id | --street ... --price ...>" >&2
  exit 1
fi

if ! python3 -c "import anthropic, requests" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt
fi

python3 main.py "$@"
