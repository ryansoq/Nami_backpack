#!/usr/bin/env python3
"""
同步英雄資料到 pixel-hero-stage
從 nami-kaspa-bot 的 heroes.json 匯出存活英雄到 alive.json
"""
import json
from pathlib import Path

# 路徑
BOT_DATA = Path.home() / "nami-backpack/projects/nami-kaspa-bot/data/heroes.json"
STAGE_DATA = Path.home() / "nami-backpack/projects/pixel-hero-stage/heroes/alive.json"

def sync_heroes():
    # 讀取 bot 資料
    with open(BOT_DATA, "r") as f:
        db = json.load(f)
    
    heroes = []
    protected_count = 0
    
    for card_id, data in db.get("heroes", {}).items():
        if data.get("status") == "alive":
            hero = {
                "id": int(card_id),
                "class": data.get("class", "knight"),
                "name": data.get("name", ""),
                "rarity": data.get("rarity", "N"),
                "kills": data.get("kills", 0),
                "protected": data.get("protected", False)
            }
            heroes.append(hero)
            if hero["protected"]:
                protected_count += 1
    
    # 寫入 stage 資料
    output = {
        "heroes": heroes,
        "count": len(heroes),
        "protected_count": protected_count
    }
    
    STAGE_DATA.parent.mkdir(parents=True, exist_ok=True)
    with open(STAGE_DATA, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 同步完成！")
    print(f"   👥 英雄：{len(heroes)}")
    print(f"   🛡️ 保護英雄：{protected_count}")

if __name__ == "__main__":
    sync_heroes()
