#!/usr/bin/env python3
"""
Nami TG ↔ OpenClaw World Bridge
當 Nami 在 TG 講話時，同步到 OpenClaw World
"""

import httpx
import asyncio
from typing import Optional

OPENCLAW_WORLD_URL = "http://127.0.0.1:18800/ipc"
AGENT_ID = "nami"  # Use "nami" prefix to get cylinder person avatar

async def register_nami():
    """註冊 Nami 到 OpenClaw World"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(OPENCLAW_WORLD_URL, json={
            "command": "register",
            "args": {
                "agentId": AGENT_ID,
                "name": "Nami 🌊",
                "bio": "CTO 技術長 - Kaspa 專家",
                "skills": [
                    {"skillId": "coding", "name": "寫程式", "description": "Python, TypeScript"},
                    {"skillId": "blockchain", "name": "區塊鏈", "description": "Kaspa"},
                    {"skillId": "architecture", "name": "系統架構"}
                ],
                "color": "#00CED1"
            }
        })
        return resp.json()

async def send_chat(text: str):
    """發送聊天訊息到 OpenClaw World"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(OPENCLAW_WORLD_URL, json={
            "command": "world-chat",
            "args": {
                "agentId": AGENT_ID,
                "text": text[:500]  # 最多 500 字
            }
        })
        return resp.json()

async def do_action(action: str):
    """執行動作 (wave, dance, idle, walk, etc.)"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(OPENCLAW_WORLD_URL, json={
            "command": "world-action",
            "args": {
                "agentId": AGENT_ID,
                "action": action
            }
        })
        return resp.json()

async def move_to(x: float, z: float):
    """移動到指定位置"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(OPENCLAW_WORLD_URL, json={
            "command": "world-move",
            "args": {
                "agentId": AGENT_ID,
                "x": x,
                "y": 0,
                "z": z
            }
        })
        return resp.json()

async def get_room_events(limit: int = 20):
    """取得房間最近的事件"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(OPENCLAW_WORLD_URL, json={
            "command": "room-events",
            "args": {"limit": limit}
        })
        return resp.json()

async def is_server_running() -> bool:
    """檢查 OpenClaw World 是否在運行"""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://127.0.0.1:18800/health")
            return resp.status_code == 200
    except:
        return False

# === 同步函數（給非 async 環境用）===

def sync_chat(text: str):
    """同步版發送聊天"""
    return asyncio.run(send_chat(text))

def sync_action(action: str):
    """同步版執行動作"""
    return asyncio.run(do_action(action))

def sync_register():
    """同步版註冊"""
    return asyncio.run(register_nami())

if __name__ == "__main__":
    import sys
    
    async def main():
        # 檢查服務
        if not await is_server_running():
            print("❌ OpenClaw World 服務未啟動")
            return
        
        # 註冊
        result = await register_nami()
        print(f"✅ 註冊: {result}")
        
        # 測試訊息
        if len(sys.argv) > 1:
            text = " ".join(sys.argv[1:])
            result = await send_chat(text)
            print(f"✅ 發送: {result}")
        else:
            result = await send_chat("Nami Bridge 測試訊息 🌊")
            print(f"✅ 發送: {result}")
        
        # 揮手
        await do_action("wave")
        print("✅ 揮手!")
    
    asyncio.run(main())
