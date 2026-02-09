"""
🎬 Battle Canvas Export
把 ATB 戰鬥結果轉換成 Canvas 可播放的 JSON 格式

用途：讓網頁版英雄舞台可以即時播放戰鬥動畫
"""

import json
import os
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Canvas 戰鬥記錄輸出路徑
CANVAS_BATTLE_PATH = os.path.expanduser(
    "~/nami-backpack/projects/pixel-hero-stage/battles/latest.json"
)
NAMI_BACKPACK_PATH = os.path.expanduser("~/nami-backpack")

# 🔧 開關：是否推送到 GitHub（避免一直 push）
ENABLE_WEB_PUSH = False


def hero_to_canvas_format(hero) -> Dict[str, Any]:
    """把 Hero 物件轉換成 Canvas 格式"""
    return {
        "card_id": hero.card_id,
        "name": hero.name or f"英雄#{hero.card_id}",
        "class": hero.hero_class,
        "rarity": hero.rarity,
        "atk": hero.atk,
        "def": hero.def_,
        "spd": hero.spd
    }


def generate_battle_events(attacker, defender, battle_detail: Dict, attacker_wins: bool) -> list:
    """
    從戰鬥結果生成 Canvas 事件序列
    
    因為目前 ATB 戰鬥引擎只輸出文字 log，
    這裡我們根據統計數據重建一個合理的事件序列
    """
    events = []
    tick = 0
    
    # 開始
    events.append({
        "tick": tick,
        "type": "battle_start",
        "msg": "⚔️ ATB 戰鬥開始！"
    })
    
    # 取得戰鬥統計
    stats = battle_detail.get("stats", {})
    p1_attacks = stats.get("p1_attacks", 2)
    p2_attacks = stats.get("p2_attacks", 2)
    p1_skills = stats.get("p1_skills", 0)
    p2_skills = stats.get("p2_skills", 0)
    p1_damage = stats.get("p1_damage_dealt", 50)
    p2_damage = stats.get("p2_damage_dealt", 40)
    loops = stats.get("loops", 20)
    
    # 計算平均傷害
    p1_avg_atk_dmg = p1_damage // max(1, p1_attacks + p1_skills) if p1_attacks > 0 else 20
    p2_avg_atk_dmg = p2_damage // max(1, p2_attacks + p2_skills) if p2_attacks > 0 else 18
    
    # 根據 loops 和攻擊次數分配 tick
    total_actions = p1_attacks + p2_attacks + p1_skills + p2_skills
    if total_actions == 0:
        total_actions = 4
    
    tick_per_action = max(20, (loops * 2) // total_actions)
    
    # 交替生成事件
    p1_atk_left = p1_attacks
    p2_atk_left = p2_attacks
    p1_skill_left = p1_skills
    p2_skill_left = p2_skills
    
    attacker_name = attacker.name or f"英雄#{attacker.card_id}"
    defender_name = defender.name or f"英雄#{defender.card_id}"
    
    # 技能名稱對應
    skill_names = {
        "knight": "烈焰斬",
        "mage": "流星雨",
        "archer": "穿透射擊",
        "knight": "聖光護盾",
        "rogue": "幻影突襲"
    }
    
    action_order = []
    
    # 建立行動順序（根據 SPD 決定誰先手比較多）
    p1_first = attacker.spd >= defender.spd
    
    while p1_atk_left > 0 or p2_atk_left > 0 or p1_skill_left > 0 or p2_skill_left > 0:
        # P1 行動
        if p1_first and (p1_atk_left > 0 or p1_skill_left > 0):
            if p1_skill_left > 0 and (p1_atk_left == 0 or len(action_order) % 3 == 2):
                action_order.append(("attacker", "skill"))
                p1_skill_left -= 1
            elif p1_atk_left > 0:
                action_order.append(("attacker", "attack"))
                p1_atk_left -= 1
        
        # P2 行動
        if p2_atk_left > 0 or p2_skill_left > 0:
            if p2_skill_left > 0 and (p2_atk_left == 0 or len(action_order) % 3 == 2):
                action_order.append(("defender", "skill"))
                p2_skill_left -= 1
            elif p2_atk_left > 0:
                action_order.append(("defender", "attack"))
                p2_atk_left -= 1
        
        # P1 行動（如果不是先手）
        if not p1_first and (p1_atk_left > 0 or p1_skill_left > 0):
            if p1_skill_left > 0 and (p1_atk_left == 0 or len(action_order) % 3 == 2):
                action_order.append(("attacker", "skill"))
                p1_skill_left -= 1
            elif p1_atk_left > 0:
                action_order.append(("attacker", "attack"))
                p1_atk_left -= 1
        
        # 防止無限迴圈
        if len(action_order) > 20:
            break
    
    # 生成事件
    tick = 30
    for who, action_type in action_order:
        is_attacker = who == "attacker"
        actor_name = attacker_name if is_attacker else defender_name
        actor_class = attacker.hero_class if is_attacker else defender.hero_class
        avg_dmg = p1_avg_atk_dmg if is_attacker else p2_avg_atk_dmg
        
        # 加點隨機變化
        import random
        damage = max(1, avg_dmg + random.randint(-5, 5))
        
        if action_type == "attack":
            events.append({
                "tick": tick,
                "type": "attack",
                "who": who,
                "target": "defender" if is_attacker else "attacker",
                "damage": damage,
                "msg": f"{actor_name} 發動普攻！造成 {damage} 傷害"
            })
        else:  # skill
            skill_name = skill_names.get(actor_class, "必殺技")
            skill_damage = int(damage * 1.8)
            events.append({
                "tick": tick,
                "type": "skill",
                "who": who,
                "skill_name": skill_name,
                "target": "defender" if is_attacker else "attacker",
                "damage": skill_damage,
                "msg": f"{actor_name} 發動【{skill_name}】！造成 {skill_damage} 傷害"
            })
        
        tick += tick_per_action
    
    # 結束事件
    if attacker_wins:
        events.append({
            "tick": tick,
            "type": "death",
            "who": "defender",
            "msg": f"💀 {defender_name} 倒下了..."
        })
        events.append({
            "tick": tick,
            "type": "battle_end",
            "winner": "attacker",
            "msg": f"🏆 {attacker_name} 獲得勝利！"
        })
    else:
        events.append({
            "tick": tick,
            "type": "death",
            "who": "attacker",
            "msg": f"💀 {attacker_name} 倒下了..."
        })
        events.append({
            "tick": tick,
            "type": "battle_end",
            "winner": "defender",
            "msg": f"🏆 {defender_name} 獲得勝利！"
        })
    
    return events


def export_battle_to_canvas(
    attacker,
    defender,
    battle_detail: Dict,
    attacker_wins: bool,
    battle_id: Optional[str] = None
) -> bool:
    """
    輸出戰鬥結果到 Canvas JSON 並推送到 GitHub
    
    Returns:
        bool: 是否成功
    """
    try:
        # 生成戰鬥 ID
        if not battle_id:
            battle_id = f"pvp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # v0.5: 優先使用 ATB 引擎產生的真實事件
        events = battle_detail.get("events", [])
        if not events:
            # 後備：用統計數據重建事件
            events = generate_battle_events(attacker, defender, battle_detail, attacker_wins)
        
        # 建立 Canvas 格式的戰鬥記錄
        canvas_battle = {
            "id": battle_id,
            "timestamp": datetime.now().isoformat(),
            "attacker": hero_to_canvas_format(attacker),
            "defender": hero_to_canvas_format(defender),
            "events": events,
            "result": {
                "winner": "attacker" if attacker_wins else "defender",
                "winner_name": attacker.name if attacker_wins else defender.name,
                "loser_name": defender.name if attacker_wins else attacker.name,
                "winner_card_id": attacker.card_id if attacker_wins else defender.card_id,
                "loser_card_id": defender.card_id if attacker_wins else attacker.card_id
            },
            "stats": battle_detail.get("stats", {})
        }
        
        # 確保目錄存在
        os.makedirs(os.path.dirname(CANVAS_BATTLE_PATH), exist_ok=True)
        
        # 寫入 JSON
        with open(CANVAS_BATTLE_PATH, "w", encoding="utf-8") as f:
            json.dump(canvas_battle, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📝 Canvas 戰鬥記錄已寫入: {CANVAS_BATTLE_PATH}")
        
        # 推送到 GitHub
        push_result = push_to_github(battle_id)
        
        return push_result
        
    except Exception as e:
        logger.error(f"❌ Canvas 輸出失敗: {e}")
        return False


def push_to_github(battle_id: str) -> bool:
    """推送到 GitHub"""
    if not ENABLE_WEB_PUSH:
        logger.info(f"⏸️ Web push 已禁用，跳過 GitHub 推送")
        return True
    
    try:
        os.chdir(NAMI_BACKPACK_PATH)
        
        # Git add
        subprocess.run(
            ["git", "add", "projects/pixel-hero-stage/battles/latest.json"],
            check=True,
            capture_output=True
        )
        
        # Git commit
        subprocess.run(
            ["git", "commit", "-m", f"⚔️ PvP 戰鬥: {battle_id}"],
            check=True,
            capture_output=True
        )
        
        # Git push
        subprocess.run(
            ["git", "push"],
            check=True,
            capture_output=True
        )
        
        logger.info(f"✅ GitHub 推送成功: {battle_id}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.warning(f"⚠️ GitHub 推送失敗: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ GitHub 推送錯誤: {e}")
        return False
