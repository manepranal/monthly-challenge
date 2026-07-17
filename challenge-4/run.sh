#!/bin/bash
# =========================================================================
# Deal Organizer — Runner (challenge-4, July "get your agents organized")
# =========================================================================
# Take a deal's inbox (emails + attachments), and let Claude file every
# document into the right folder and build a calendar of every deadline.
#
# One-shot mode (organize a pile):
#   ./run.sh                       # runs on the sample deal in examples/
#   ./run.sh examples              # same, explicit
#   ./run.sh /path/to/deal-inbox   # any folder with inbox.json + attachments/
#
# Watch mode (organize a stream — Otto-style pipeline; see CLAUDE.md):
#   ./run.sh watch                 # terminal 1: the organizer sweep loop
#   ./run.sh drip                  # terminal 2: sample emails arrive 1-by-1
#   ./run.sh status                # print the board
#   ./run.sh approve <email-id>    # clear a NEEDS REVIEW gate
#   ./run.sh resume  <email-id>    # un-park a budget-exhausted email
#
# Real inbox (Gmail/IMAP — read-only; see fetch_gmail.py for setup):
#   GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD=... \
#   ./run.sh gmail [search terms]  # pull real mail + attachments, organize it
#
#   DEAL_MODEL=claude-opus-4-8 ./run.sh        # override the model
#   OTTO_SWEEP_SEC=5 OTTO_MAX_RUNS_PER_STATE=3 # watch-mode tunables
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

case "${1:-}" in
  watch|tick|status|approve|resume)
    python3 pipeline.py "$@"
    ;;
  drip)
    shift
    python3 drip.py "$@"
    ;;
  gmail)
    shift
    DEST="$(python3 fetch_gmail.py "$@")"   # progress goes to stderr
    python3 main.py "$DEST"
    ;;
  *)
    python3 main.py "$@"
    ;;
esac
