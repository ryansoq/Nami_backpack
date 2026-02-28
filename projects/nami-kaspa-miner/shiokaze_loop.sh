#!/bin/bash
# ShioKaze 自動重啟 wrapper
while true; do
    echo "[$(date '+%H:%M:%S')] 🌊 啟動 ShioKaze v4..."
    python3 -u shiokaze_v4.py "$@"
    echo "[$(date '+%H:%M:%S')] ⚠️ ShioKaze 退出，3 秒後重啟..."
    sleep 3
done
