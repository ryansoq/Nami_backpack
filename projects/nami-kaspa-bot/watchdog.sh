#!/bin/bash
# 🐕 Nami Kaspa Bot Watchdog
# 每分鐘檢查 bot 是否在運行，掛了就重啟

BOT_DIR="/home/ymchang/nami-backpack/projects/nami-kaspa-bot"
LOG_FILE="/tmp/nami-kaspa-bot.log"
WATCHDOG_LOG="/tmp/nami-bot-watchdog.log"

check_and_restart() {
    if ! pgrep -f "nami_kaspa_bot.py" > /dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot 掛了，重啟中..." >> "$WATCHDOG_LOG"
        cd "$BOT_DIR"
        nohup python3 nami_kaspa_bot.py >> "$LOG_FILE" 2>&1 &
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot 已重啟 (PID: $!)" >> "$WATCHDOG_LOG"
    fi
}

check_and_restart
