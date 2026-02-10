"""
Nami Hero World - API Server
============================
TG 和 Web 共用的後端 API

啟動: uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import json
import os
from pathlib import Path

# 資料目錄
DATA_DIR = Path(__file__).parent / "data"

app = FastAPI(
    title="Nami Hero World API",
    description="娜米的英雄世界 - 共用後端 API",
    version="0.1.0"
)

# CORS - 允許 Web 前端跨域存取
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ryansoq.github.io",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"  # 開發階段先全開
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_json(filename: str) -> dict:
    """讀取 JSON 檔案"""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(filename: str, data: dict):
    """儲存 JSON 檔案"""
    filepath = DATA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ========== API Endpoints ==========

@app.get("/", response_class=HTMLResponse)
def root():
    """首頁 - 漂亮的 Landing Page"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌲 娜米的英雄世界 API</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
        }
        h1 { font-size: 2.5em; margin-bottom: 10px; }
        .status { color: #4ade80; font-size: 1.2em; margin-bottom: 30px; }
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            margin: 10px;
            width: 100%;
            max-width: 400px;
        }
        .card h2 { margin-bottom: 15px; color: #60a5fa; }
        .hero-list { list-style: none; }
        .hero-list li {
            padding: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            display: flex;
            justify-content: space-between;
        }
        .hero-class { color: #fbbf24; }
        .stats { display: flex; gap: 20px; justify-content: center; margin: 20px 0; }
        .stat { text-align: center; }
        .stat-num { font-size: 2em; font-weight: bold; color: #4ade80; }
        .stat-label { color: #9ca3af; }
        a { color: #60a5fa; }
        .endpoints { text-align: left; font-family: monospace; font-size: 0.9em; }
        .endpoints code { color: #fbbf24; }
    </style>
</head>
<body>
    <h1>🌲 娜米的英雄世界</h1>
    <div class="status">🌊 API Running v0.1.0</div>
    
    <div class="stats" id="stats">
        <div class="stat"><div class="stat-num" id="alive">-</div><div class="stat-label">存活英雄</div></div>
        <div class="stat"><div class="stat-num" id="dead">-</div><div class="stat-label">已陣亡</div></div>
        <div class="stat"><div class="stat-num" id="total">-</div><div class="stat-label">總召喚</div></div>
    </div>
    
    <div class="card">
        <h2>⚔️ 存活英雄</h2>
        <ul class="hero-list" id="heroList">
            <li>載入中...</li>
        </ul>
    </div>
    
    <div class="card">
        <h2>📡 API Endpoints</h2>
        <div class="endpoints">
            <p><code>GET /api/heroes</code> - 所有存活英雄</p>
            <p><code>GET /api/hero/{id}</code> - 英雄詳情</p>
            <p><code>GET /api/tree</code> - 世界之樹狀態</p>
            <p><code>GET /api/leaderboard</code> - 排行榜</p>
        </div>
    </div>
    
    <script>
        fetch('/api/tree').then(r=>r.json()).then(d=>{
            document.getElementById('alive').textContent = d.stats.alive;
            document.getElementById('dead').textContent = d.stats.dead;
            document.getElementById('total').textContent = d.stats.total_summoned;
        });
        fetch('/api/heroes').then(r=>r.json()).then(d=>{
            const list = document.getElementById('heroList');
            list.innerHTML = d.heroes.map(h => 
                `<li><span>${h.name || '#'+h.card_id}</span><span class="hero-class">${h.hero_class}</span></li>`
            ).join('');
        });
    </script>
</body>
</html>
"""


@app.get("/api/heroes")
def get_all_heroes():
    """取得所有英雄（給 Web 顯示用）"""
    data = load_json("heroes.json")
    heroes_dict = data.get("heroes", {})
    
    # 整理成列表
    hero_list = []
    for card_id, hero in heroes_dict.items():
        if isinstance(hero, dict):
            hero_list.append({
                "card_id": card_id,
                **hero
            })
    
    # 只回傳存活的英雄
    alive_heroes = [h for h in hero_list if h.get("status") == "alive"]
    
    return {
        "heroes": alive_heroes,
        "total": len(alive_heroes),
        "total_all": len(hero_list)
    }


@app.get("/api/heroes/owner/{owner_id}")
def get_user_heroes(owner_id: int):
    """取得特定用戶的英雄"""
    data = load_json("heroes.json")
    heroes_dict = data.get("heroes", {})
    
    user_heroes = []
    for card_id, hero in heroes_dict.items():
        if isinstance(hero, dict) and hero.get("owner_id") == owner_id:
            user_heroes.append({
                "card_id": card_id,
                **hero
            })
    
    # 只回傳存活的
    alive = [h for h in user_heroes if h.get("status") == "alive"]
    
    return {
        "owner_id": owner_id,
        "heroes": alive,
        "total": len(alive)
    }


@app.get("/api/hero/{card_id}")
def get_hero_detail(card_id: str):
    """取得單一英雄詳情"""
    data = load_json("heroes.json")
    heroes_dict = data.get("heroes", {})
    
    hero = heroes_dict.get(card_id)
    if hero and isinstance(hero, dict):
        return {
            "hero": {
                "card_id": card_id,
                **hero
            }
        }
    
    raise HTTPException(status_code=404, detail="Hero not found")


@app.get("/api/tree")
def get_world_tree():
    """取得世界之樹狀態"""
    data = load_json("heroes.json")
    heroes_dict = data.get("heroes", {})
    
    # 計算統計
    total_heroes = 0
    alive_heroes = 0
    dead_heroes = 0
    
    for card_id, hero in heroes_dict.items():
        if isinstance(hero, dict):
            total_heroes += 1
            if hero.get("status") == "alive":
                alive_heroes += 1
            else:
                dead_heroes += 1
    
    return {
        "tree": "🌲 世界之樹",
        "stats": {
            "total_summoned": total_heroes,
            "alive": alive_heroes,
            "dead": dead_heroes
        }
    }


@app.get("/api/leaderboard")
def get_leaderboard(limit: int = 10):
    """排行榜 - 按 kills"""
    data = load_json("heroes.json")
    heroes_dict = data.get("heroes", {})
    
    # 收集所有存活英雄
    all_heroes = []
    for card_id, hero in heroes_dict.items():
        if isinstance(hero, dict) and hero.get("status") == "alive":
            all_heroes.append({
                "card_id": card_id,
                "name": hero.get("name") or f"英雄#{card_id}",
                "hero_class": hero.get("hero_class"),
                "kills": hero.get("kills", 0),
                "battles": hero.get("battles", 0),
                "atk": hero.get("atk", 0),
                "def": hero.get("def", 0),
                "spd": hero.get("spd", 0),
                "owner_id": hero.get("owner_id")
            })
    
    # 按 kills 排序
    sorted_heroes = sorted(all_heroes, key=lambda x: x["kills"], reverse=True)
    
    return {
        "leaderboard": sorted_heroes[:limit]
    }


# ========== 健康檢查 ==========

@app.get("/health")
def health_check():
    """健康檢查"""
    return {"status": "healthy", "service": "nami-hero-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
