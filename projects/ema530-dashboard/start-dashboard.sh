#!/bin/bash
# EMA530 Dashboard watchdog + data refresh
# Idempotent: safe to run repeatedly. Refreshes data, ensures http.server + cloudflared running.

set -u
cd "$(dirname "$0")"

LOG=/home/ymchang/clawd/logs/dashboard-watchdog.log
PORT=18806
PYTHON=/usr/bin/python3
CLOUDFLARED=/home/ymchang/bin/cloudflared
TUNNEL_TOKEN=eyJhIjoiOTI1YjcwNWUyMDJhYmQyMDFkMmI0NzRmYWVjOTRkM2MiLCJ0IjoiNzg2ZjhkMWYtZDE0ZS00NDVjLWFjNGItNGE2ODM3ZDgxZjUyIiwicyI6Ik5UUXpOMkZpT1dVdFpXUm1ZUzAwTlRGaExXSm1ZbUl0TlRGak5tTmpNV0prTUdKaSJ9

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

mkdir -p "$(dirname "$LOG")"

# 1. Refresh data
log "=== watchdog start ==="
if "$PYTHON" generate_data.py >> "$LOG" 2>&1; then
    log "data.json refreshed OK"
else
    log "WARN: generate_data.py failed (exit $?)"
fi

# 2. Ensure http.server on $PORT
if ss -tln 2>/dev/null | grep -q ":$PORT "; then
    log "http.server :$PORT already listening"
else
    log "http.server :$PORT down, starting..."
    nohup "$PYTHON" -m http.server "$PORT" > /tmp/dashboard-$PORT.log 2>&1 &
    disown
    sleep 2
    if ss -tln 2>/dev/null | grep -q ":$PORT "; then
        log "http.server :$PORT started OK"
    else
        log "ERROR: http.server :$PORT failed to start"
    fi
fi

# 3. Ensure cloudflared running
if pgrep -f "cloudflared tunnel run" > /dev/null; then
    log "cloudflared already running"
else
    log "cloudflared down, starting..."
    nohup "$CLOUDFLARED" tunnel run --token "$TUNNEL_TOKEN" > /tmp/cloudflared.log 2>&1 &
    disown
    sleep 5
    if pgrep -f "cloudflared tunnel run" > /dev/null; then
        log "cloudflared started OK"
    else
        log "ERROR: cloudflared failed to start"
    fi
fi

log "=== watchdog done ==="
