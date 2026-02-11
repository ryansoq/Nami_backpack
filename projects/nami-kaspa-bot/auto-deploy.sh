#!/bin/bash
# 🚀 Auto-deploy: 檢查 git 更新，沒人用時才重啟 bot
# 用 cron 每小時跑一次: 0 * * * * /path/to/auto-deploy.sh

set -e
cd "$(dirname "$0")"

LOG_FILE="/tmp/nami-bot-deploy.log"
LOCK_FILE="/tmp/nami-bot-deploy.lock"

# 避免同時跑多個
exec 200>"$LOCK_FILE"
flock -n 200 || exit 0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# 檢查遠端更新
git fetch origin main --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    # 沒有更新
    exit 0
fi

log "🔄 發現更新: $LOCAL -> $REMOTE"

# 檢查最近 5 分鐘有沒有活動（bot.log 有新內容）
if [ -f "bot.log" ]; then
    LAST_MOD=$(stat -c %Y bot.log 2>/dev/null || echo 0)
    NOW=$(date +%s)
    DIFF=$((NOW - LAST_MOD))
    
    if [ "$DIFF" -lt 300 ]; then
        log "⏳ 有人在用 (${DIFF}s ago)，延後部署"
        exit 0
    fi
fi

# Pull 更新
git pull origin main --quiet
log "✅ Git pull 完成"

# 重啟 bot
BOT_PID=$(pgrep -f "python3 nami_kaspa_bot.py" || true)
if [ -n "$BOT_PID" ]; then
    kill "$BOT_PID" 2>/dev/null || true
    sleep 2
    log "🛑 舊 bot 已停止 (PID: $BOT_PID)"
fi

nohup python3 nami_kaspa_bot.py > bot.log 2>&1 &
NEW_PID=$!
log "🚀 新 bot 已啟動 (PID: $NEW_PID)"

# 保留最近 100 行 log
tail -100 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
