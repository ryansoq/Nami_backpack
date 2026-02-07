#!/bin/bash
#
# 🌲 重啟 Bot 並運行測試
# 
# 用法：./scripts/restart_with_test.sh [--full]
#

set -e

cd "$(dirname "$0")/.."

echo "=================================="
echo "🌲 Nami Kaspa Bot - 重啟 + 測試"
echo "=================================="

# 1. 語法檢查
echo ""
echo "[1/4] 🔍 語法檢查..."
python3 -m py_compile hero_game.py hero_commands.py reward_system.py nami_kaspa_bot.py
echo "      ✅ 語法正確"

# 2. 運行測試
echo ""
echo "[2/4] 🧪 運行測試..."
if python3 tests/test_summon.py "$@"; then
    echo "      ✅ 測試通過"
else
    echo "      ❌ 測試失敗，中止重啟"
    exit 1
fi

# 3. 停止舊的 bot
echo ""
echo "[3/4] 🛑 停止舊 bot..."
pkill -f nami_kaspa_bot.py 2>/dev/null || true
sleep 2
echo "      ✅ 已停止"

# 4. 啟動新的 bot
echo ""
echo "[4/4] 🚀 啟動新 bot..."
nohup python3 nami_kaspa_bot.py > /tmp/nami-kaspa-bot.log 2>&1 &
sleep 3

if pgrep -f nami_kaspa_bot.py > /dev/null; then
    echo "      ✅ Bot 已啟動 (PID: $(pgrep -f nami_kaspa_bot.py))"
else
    echo "      ❌ Bot 啟動失敗"
    tail -20 /tmp/nami-kaspa-bot.log
    exit 1
fi

echo ""
echo "=================================="
echo "🎉 重啟完成！"
echo "=================================="
