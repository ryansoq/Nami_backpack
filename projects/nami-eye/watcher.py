#!/usr/bin/env python3
"""
Nami Eye Watcher — 監看 frames，用 vision 分析後回傳 caption + 發 TG
用法: python3 watcher.py [--interval 5]

流程:
  1. 監看 /tmp/nami-eye-frames/ 有新 frame
  2. 讀取最新 frame + speech text
  3. 呼叫 OpenClaw wake API 讓 Nami 分析（或直接用本地 vision）
  4. POST caption 到 Nami Eye 畫面
  5. 發到 TG
"""

import os, sys, time, json, base64, glob, argparse, httpx

FRAME_DIR = "/tmp/nami-eye-frames"
LATEST_FRAME = "/tmp/nami-eye-latest.jpg"
CAPTION_URL = "http://localhost:18805/api/caption"

# OpenClaw Gateway hooks
OPENCLAW_CONFIG = "/home/ymchang/.openclaw/openclaw.json"
GATEWAY_URL = "http://127.0.0.1:18789"

def get_hook_token():
    try:
        with open(OPENCLAW_CONFIG) as f:
            return json.load(f)["hooks"]["token"]
    except:
        return None

def get_tg_bot_token():
    try:
        with open("/home/ymchang/clawd/.secrets/nami-kaspa-bot.json") as f:
            return json.load(f)["token"]
    except:
        return None

def send_caption(text):
    """送 caption 到 Nami Eye 畫面"""
    try:
        r = httpx.post(CAPTION_URL, json={"text": text}, timeout=5)
        return r.status_code == 200
    except:
        return False

def send_tg(text, chat_id="5168530096"):
    """送訊息到 TG（用主 bot）"""
    token = get_hook_token()
    if not token:
        return
    try:
        # 用 Gateway wake 讓 Nami 發訊息
        # 或直接用 bot token
        pass  # TG 發送由 OpenClaw 處理
    except:
        pass

def analyze_frame(frame_path, speech_text=None):
    """
    分析 frame — 回傳簡短描述
    這裡用簡單的方式：把圖片+語音文字透過 wake 傳給 OpenClaw
    讓 Nami 在主 session 裡分析並回傳 caption
    """
    # 讀圖片 base64
    with open(frame_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    prompt = "[Nami Eye Frame]"
    if speech_text:
        prompt += f" 語音: {speech_text}"
    prompt += " 請用一句話描述你看到的畫面，然後 POST 到 http://localhost:18805/api/caption"
    
    # Wake OpenClaw
    token = get_hook_token()
    if token:
        try:
            httpx.post(
                f"{GATEWAY_URL}/hooks/wake",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"text": prompt, "mode": "now"},
                timeout=5
            )
        except Exception as e:
            print(f"Wake failed: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=8, help="檢查間隔（秒）")
    args = parser.parse_args()

    print(f"👁️ Nami Eye Watcher 啟動 (每 {args.interval} 秒)")
    
    seen_frames = set()
    # 先標記已存在的 frames
    for f in glob.glob(f"{FRAME_DIR}/frame_*.jpg"):
        seen_frames.add(os.path.basename(f))

    while True:
        time.sleep(args.interval)
        
        # 找新 frames
        current = set()
        for f in glob.glob(f"{FRAME_DIR}/frame_*.jpg"):
            current.add(os.path.basename(f))
        
        new_frames = sorted(current - seen_frames)
        if not new_frames:
            continue
        
        # 只處理最新的那張
        latest = new_frames[-1]
        frame_path = os.path.join(FRAME_DIR, latest)
        
        # 看有沒有對應的 speech
        num = latest.replace("frame_", "").replace(".jpg", "")
        speech_path = os.path.join(FRAME_DIR, f"speech_{num}.txt")
        speech = None
        if os.path.exists(speech_path):
            with open(speech_path) as f:
                speech = f.read().strip()
        
        print(f"🖼️ 新 frame: {latest}" + (f" 🎤 {speech}" if speech else ""))
        
        # 分析並回傳
        analyze_frame(frame_path, speech)
        
        seen_frames = current

if __name__ == "__main__":
    main()
