"""
Nami TG Group Listener 🌊

監聽群組中的 @nami / @NamiElf_bot mention，
偵測到後透過 DM 觸發 OpenClaw 喚醒。

Usage:
  python3 listener.py
"""
import asyncio
import json
import os
import time
import httpx

# Nami_kaspa_bot token (用這個做 polling，不跟 OpenClaw Gateway 衝突)
BOT_TOKEN = "7031382774:AAFCkbE2j8Jbj9b_dw6tia5qCr-5P1Dtvak"
# 監聽的群組
GROUP_ID = -1003753194248
# Ryan 的 chat ID（用來發 DM 喚醒 OpenClaw）
RYAN_CHAT_ID = 5168530096
# 監聽的關鍵字
TRIGGERS = ["@nami", "@namielf_bot"]
# Cooldown（避免重複喚醒）
COOLDOWN_SEC = 30

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 用 NamiElf_bot 發 DM 喚醒 OpenClaw（因為 OpenClaw 聽的是這個 bot）
WAKE_BOT_TOKEN = "8488217070:AAHzaYy1MKr-T58LHwTH6SbYQmVx3q27vMY"
WAKE_URL = f"https://api.telegram.org/bot{WAKE_BOT_TOKEN}"

last_wake = 0
last_update_id = 0


async def send_dm(text: str):
    """發 DM 給 Ryan 觸發 OpenClaw 喚醒"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{WAKE_URL}/sendMessage", json={
            "chat_id": RYAN_CHAT_ID,
            "text": text,
        })
        if resp.status_code == 200:
            print(f"[wake] DM sent to Ryan ✅")
        else:
            print(f"[wake] DM failed: {resp.text}")


async def poll_updates():
    """Long polling for group messages"""
    global last_update_id, last_wake
    
    async with httpx.AsyncClient(timeout=35) as client:
        while True:
            try:
                params = {"offset": last_update_id + 1, "timeout": 30, "allowed_updates": ["message"]}
                resp = await client.get(f"{BASE_URL}/getUpdates", params=params)
                
                if resp.status_code != 200:
                    print(f"[poll] Error {resp.status_code}: {resp.text[:100]}")
                    await asyncio.sleep(5)
                    continue
                
                data = resp.json()
                updates = data.get("result", [])
                
                for update in updates:
                    last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    text = (msg.get("text") or "").lower()
                    from_user = msg.get("from", {}).get("first_name", "?")
                    from_id = msg.get("from", {}).get("id", 0)
                    
                    # 只看目標群組
                    if chat_id != GROUP_ID:
                        continue
                    
                    # 忽略自己發的
                    if from_id == int(BOT_TOKEN.split(":")[0]):
                        continue
                    
                    # 檢查 mention
                    triggered = any(t in text for t in TRIGGERS)
                    
                    # 也檢查 entities 裡的 mention
                    if not triggered:
                        for ent in msg.get("entities", []):
                            if ent.get("type") == "mention":
                                mention_text = (msg.get("text") or "")[ent["offset"]:ent["offset"]+ent["length"]].lower()
                                if mention_text in TRIGGERS:
                                    triggered = True
                                    break
                    
                    if triggered:
                        now = time.time()
                        if now - last_wake < COOLDOWN_SEC:
                            print(f"[skip] Cooldown ({int(COOLDOWN_SEC - (now - last_wake))}s left)")
                            continue
                        
                        last_wake = now
                        print(f"[mention] {from_user}: {msg.get('text', '')[:100]}")
                        
                        # 發 DM 喚醒 OpenClaw
                        wake_text = f"[GROUP-MENTION] (untrusted external content)\n👤 {from_user} 在群組 @nami\n💬 {msg.get('text', '')[:200]}"
                        await send_dm(wake_text)
                    
            except httpx.TimeoutException:
                continue  # Long poll timeout, normal
            except Exception as e:
                print(f"[error] {e}")
                await asyncio.sleep(5)


async def main():
    # 先清掉舊的 updates
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/getUpdates", params={"offset": -1})
        if resp.status_code == 200:
            updates = resp.json().get("result", [])
            if updates:
                global last_update_id
                last_update_id = updates[-1]["update_id"]
    
    print(f"🌊 Nami TG Listener started")
    print(f"   Group: {GROUP_ID}")
    print(f"   Triggers: {TRIGGERS}")
    print(f"   Cooldown: {COOLDOWN_SEC}s")
    print(f"   Wake via DM to: {RYAN_CHAT_ID}")
    print()
    
    await poll_updates()


if __name__ == "__main__":
    asyncio.run(main())
