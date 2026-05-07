#!/bin/bash
# =========================================================================
# Demo recorder — captures a clean end-to-end run for video submission.
#
# Records the full screen for the duration of the demo (contract + listing),
# saves an .mov, and opens it when done.
#
# Usage:
#   export ANTHROPIC_API_KEY=sk-ant-...
#   ./record-demo.sh
# =========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
  exit 1
fi

OUT="$HOME/Desktop/may-challenge-demo.mov"
DURATION=180  # 3 minutes — enough headroom for extract+submit+upload x2

echo
echo "▶ Recording to $OUT for up to ${DURATION}s"
echo "  Bring this terminal to the front; the agent will start in 3s..."
sleep 3

# Start screen recording in background.
/usr/sbin/screencapture -V "$DURATION" -v "$OUT" &
REC_PID=$!

# Give the recorder a moment to initialise.
sleep 2

clear
echo "════════════════════════════════════════════════════════════════"
echo "  May Challenge — Contract & Listing → reZen"
echo "════════════════════════════════════════════════════════════════"
echo
echo "▶ Step 1/2 — Contract (PDF)"
echo
sleep 1
./run.sh examples/sample-contract.pdf
sleep 3

echo
echo "════════════════════════════════════════════════════════════════"
echo "▶ Step 2/2 — Listing Agreement (PDF)"
echo "════════════════════════════════════════════════════════════════"
echo
sleep 1
./run.sh examples/sample-listing.pdf
sleep 3

echo
echo "✓ Demo complete. Stopping recording..."
# Stop screencapture early by killing it; macOS will finalize the .mov.
kill -INT "$REC_PID" 2>/dev/null || true
wait "$REC_PID" 2>/dev/null || true

if [ -f "$OUT" ]; then
  echo
  echo "✓ Saved to: $OUT"
  open "$OUT"
else
  echo "WARN: recording file not found at $OUT — check screencapture output."
fi
