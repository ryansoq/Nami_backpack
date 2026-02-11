#!/bin/bash
# API Server 自動重啟守護腳本

cd ~/nami-backpack/projects/nami-kaspa-bot

while true; do
    echo "$(date): 啟動 API Server..."
    python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000
    echo "$(date): API Server 停止，5秒後重啟..."
    sleep 5
done
