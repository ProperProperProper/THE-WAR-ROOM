#!/bin/bash
set -e

LOG_DIR="/tmp"
OMLX_LOG="$LOG_DIR/omlx.log"
WARROOM_LOG="$LOG_DIR/war-room.log"

# Remove old logs
rm -f "$OMLX_LOG" "$WARROOM_LOG"

echo "[$(date)] Starting War Room startup sequence..." | tee -a "$WARROOM_LOG"

# 1. Start oMLX
echo "[$(date)] Starting oMLX on port 8000..." | tee -a "$WARROOM_LOG"
/Users/local.local/.omlx/bin/omlx serve --port 8000 > "$OMLX_LOG" 2>&1 &
OMLX_PID=$!
echo "[$(date)] oMLX PID: $OMLX_PID" | tee -a "$WARROOM_LOG"

# Wait for oMLX to be ready
echo "[$(date)] Waiting for oMLX to be ready..." | tee -a "$WARROOM_LOG"
for i in {1..30}; do
  if nc -z localhost 8000 2>/dev/null; then
    echo "[$(date)] oMLX is ready!" | tee -a "$WARROOM_LOG"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "[$(date)] WARNING: oMLX didn't respond in time, continuing anyway..." | tee -a "$WARROOM_LOG"
  fi
  sleep 1
done

sleep 2

# Ollama/Mistral removed - using Claude instead (freed 4.8GB memory)

# Start War Room
echo "[$(date)] Starting War Room on port 8765..." | tee -a "$WARROOM_LOG"
cd /Users/local.local/Documents/Codex/2026-09-20/i-x20/outputs/war-room
python3 server.py --no-browser > "$WARROOM_LOG" 2>&1 &
WARROOM_PID=$!
echo "[$(date)] War Room PID: $WARROOM_PID" | tee -a "$WARROOM_LOG"

# Wait for War Room to be ready
echo "[$(date)] Waiting for War Room to be ready..." | tee -a "$WARROOM_LOG"
for i in {1..30}; do
  if nc -z localhost 8765 2>/dev/null; then
    echo "[$(date)] War Room is ready at http://127.0.0.1:8765" | tee -a "$WARROOM_LOG"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "[$(date)] WARNING: War Room didn't respond in time" | tee -a "$WARROOM_LOG"
  fi
  sleep 1
done

echo "[$(date)] Startup complete! Services running." | tee -a "$WARROOM_LOG"
echo "  oMLX:     http://127.0.0.1:8000 (PID: $OMLX_PID)"
echo "  War Room: http://127.0.0.1:8765 (PID: $WARROOM_PID)" | tee -a "$WARROOM_LOG"
echo "  Note: Mistral/Ollama removed to free 4.8GB - use Claude instead" | tee -a "$WARROOM_LOG"
