#!/usr/bin/env python3
"""
🌲 大地之樹獎勵系統
==================

觸發條件：DAA 結尾 66666
分配方式：獎勵池 70% 按積分比例發放給存活英雄
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from hero_game import (
    load_heroes_db, save_heroes_db, get_hero_by_id, Hero,
    TREE_ADDRESS
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

REWARD_TRIGGER_SUFFIX = "66666"  # DAA 結尾 66666 觸發（約每 2.78 小時）
BASE_REWARD_MANA = 100  # 大地之母每回合提供的起始 mana
REWARD_POOL_RATIO = 0.7  # 70% 進獎勵池
MIN_REWARD = 100000  # 最小發放金額 0.001 tKAS

# 稀有度積分加成
RARITY_BONUS = {
    "common": 1,      # 普通
    "uncommon": 2,    # 優秀
    "rare": 3,        # 稀有
    "epic": 5,        # 史詩
    "legendary": 8,   # 傳說
    "mythic": 13      # 神話
}

# ═══════════════════════════════════════════════════════════════════════════════
# 獎勵計算
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_hero_score(hero: Hero) -> int:
    """
    計算英雄積分
    
    積分 = 存活天數 + 稀有度加成 + 擊殺數 × 2
    """
    # 存活天數
    try:
        created = datetime.fromisoformat(hero.created_at)
        days_alive = (datetime.now() - created).days + 1  # 至少 1 天
    except:
        days_alive = 1
    
    # 稀有度加成
    rarity_bonus = RARITY_BONUS.get(hero.rarity, 1)
    
    # 擊殺數
    kills = hero.kills or 0
    
    score = days_alive + rarity_bonus + (kills * 2)
    return max(score, 1)


def get_alive_heroes() -> list[tuple[Hero, str]]:
    """
    取得所有存活英雄及其創建者地址
    
    Returns:
        [(hero, owner_address), ...]
    """
    db = load_heroes_db()
    alive_heroes = []
    
    for card_id, hero_data in db.get("heroes", {}).items():
        if hero_data.get("status") == "alive":
            hero = Hero.from_dict(hero_data)
            owner_address = hero_data.get("owner_address", "")
            if owner_address:
                alive_heroes.append((hero, owner_address))
    
    return alive_heroes


def calculate_rewards(total_pool: int, heroes: list[tuple[Hero, str]]) -> list[dict]:
    """
    計算每個英雄的獎勵金額
    
    Args:
        total_pool: 總獎勵池（sompi）
        heroes: [(hero, owner_address), ...]
    
    Returns:
        [{"hero": hero, "address": addr, "score": score, "reward": amount}, ...]
    """
    if not heroes:
        return []
    
    # 計算所有積分
    results = []
    total_score = 0
    
    for hero, address in heroes:
        score = calculate_hero_score(hero)
        total_score += score
        results.append({
            "hero": hero,
            "address": address,
            "score": score,
            "reward": 0
        })
    
    if total_score == 0:
        return results
    
    # 按比例分配
    for r in results:
        r["reward"] = int(total_pool * r["score"] / total_score)
    
    # 過濾太小的獎勵
    results = [r for r in results if r["reward"] >= MIN_REWARD]
    
    # 按獎勵排序
    results.sort(key=lambda x: x["reward"], reverse=True)
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 發放獎勵
# ═══════════════════════════════════════════════════════════════════════════════

async def distribute_rewards(daa: int, tree_balance: int, queue_lock=None) -> dict:
    """
    發放獎勵（發放期間暫停服務）
    
    獎勵來源：驅動費池（召喚、PvP 等費用累積）
    不是挖礦收入！
    
    Args:
        daa: 當前 DAA（觸發高度）
        tree_balance: 大地之樹當前餘額（sompi）- 僅供參考
        queue_lock: 排隊鎖（可選，用於暫停服務）
    
    Returns:
        發放結果
    """
    logger.info(f"🌲 大地之樹關門發放獎勵！DAA: {daa}")
    result = {
        "daa": daa,
        "success": False,
        "total_pool": 0,
        "distributed": 0,
        "recipients": [],
        "error": None
    }
    
    # 獎勵池 = 驅動費累積 + 大地之母起始 mana
    db = load_heroes_db()
    accumulated_mana = db.get("total_mana_pool", 0)
    total_mana = accumulated_mana + BASE_REWARD_MANA  # 加入大地之母提供的起始 mana
    reward_pool = int(total_mana * 1e8)  # 轉換為 sompi
    result["total_pool"] = reward_pool
    result["mana_pool_before"] = accumulated_mana
    result["base_reward"] = BASE_REWARD_MANA
    
    logger.info(f"🌲 獎勵池: 累積 {accumulated_mana} + 起始 {BASE_REWARD_MANA} = {total_mana} mana")
    
    if reward_pool < MIN_REWARD * 10:
        result["error"] = "獎勵池太小"
        return result
    
    # 取得存活英雄
    heroes = get_alive_heroes()
    if not heroes:
        result["error"] = "沒有存活英雄"
        return result
    
    # 計算獎勵分配
    rewards = calculate_rewards(reward_pool, heroes)
    if not rewards:
        result["error"] = "沒有符合條件的英雄"
        return result
    
    # 發放獎勵（使用大地之樹錢包）
    import unified_wallet
    
    for i, r in enumerate(rewards):
        hero = r["hero"]
        address = r["address"]
        amount = r["reward"]
        
        try:
            # 從大地之樹發送獎勵
            tx_id = await unified_wallet.send_from_tree(
                to_address=address,
                amount=amount,
                memo=f"reward:{daa}:{hero.card_id}"
            )
            
            r["tx_id"] = tx_id
            r["status"] = "success"
            result["distributed"] += amount
            
            logger.info(f"🎁 獎勵發放 | #{hero.card_id} → {address[:20]}... | {amount/1e8:.4f} tKAS")
            
            # 等待 UTXO 更新（避免衝突），最後一筆不用等
            if i < len(rewards) - 1:
                await asyncio.sleep(1.5)
            
        except Exception as e:
            r["status"] = "failed"
            r["error"] = str(e)
            logger.error(f"❌ 獎勵發放失敗 | #{hero.card_id} | {e}")
            # 發送失敗也等一下，避免連續失敗
            await asyncio.sleep(1.0)
    
    result["recipients"] = rewards
    result["success"] = True
    
    # 清空驅動費池（已發放）
    db = load_heroes_db()
    db["total_mana_pool"] = 0
    save_heroes_db(db)
    logger.info(f"🌲 驅動費池已清空（已發放 {mana_pool} mana）")
    
    return result


def format_reward_announcement(result: dict) -> str:
    """格式化獎勵公告"""
    daa = result["daa"]
    total_pool = result["total_pool"]
    distributed = result["distributed"]
    recipients = result["recipients"]
    
    if not result["success"]:
        return f"""🌲 *大地之樹獎勵發放* #{daa}

❌ 發放失敗：{result.get('error', '未知錯誤')}"""
    
    base_reward = result.get("base_reward", 0)
    accumulated = result.get("mana_pool_before", 0)
    
    lines = [
        f"🌲 *大地之樹獎勵發放* #{daa}",
        "",
        f"💰 獎勵池：{total_pool/1e8:.2f} mana",
        f"   ├ 累積：{accumulated:.2f}",
        f"   └ 起始：{base_reward:.2f} (大地之母)",
        f"📤 已發放：{distributed/1e8:.2f} mana",
        f"👥 受益者：{len(recipients)} 位英雄",
        "",
        "🏆 *排名：*"
    ]
    
    for i, r in enumerate(recipients[:10], 1):  # 只顯示前 10 名
        hero = r["hero"]
        reward = r["reward"]
        score = r["score"]
        address = r["address"]
        
        rarity_emoji = {
            "common": "⚪", "uncommon": "🟢", "rare": "🔵",
            "epic": "🟣", "legendary": "🟡", "mythic": "🔴"
        }.get(hero.rarity, "⚪")
        
        class_emoji = {
            "warrior": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"
        }.get(hero.hero_class, "")
        
        status = "✓" if r.get("status") == "success" else "✗"
        
        lines.append(
            f"{i}. {status} `#{hero.card_id}` {rarity_emoji}{hero.rarity} {class_emoji}\n"
            f"   → {reward/1e8:.4f} mana (積分:{score})\n"
            f"   `{address[:25]}...`"
        )
    
    if len(recipients) > 10:
        lines.append(f"\n...還有 {len(recipients) - 10} 位英雄")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 觸發檢查
# ═══════════════════════════════════════════════════════════════════════════════

def should_trigger_reward(daa: int) -> bool:
    """檢查是否應該觸發獎勵發放（精確匹配當前 DAA）"""
    return str(daa).endswith(REWARD_TRIGGER_SUFFIX)


def find_trigger_daa_in_range(start_daa: int, end_daa: int) -> Optional[int]:
    """
    檢查 (start_daa, end_daa] 區間內是否有觸發點
    
    DAA 變化速度 ~10/秒，檢查間隔 60 秒 ≈ 600 DAA
    不能只看當前 DAA，要檢查整個區間
    
    Returns:
        觸發的 DAA，或 None
    """
    if start_daa >= end_daa:
        return None
    
    # 找區間內最近的 66666 結尾 DAA
    # 例如 start=380560000, end=380560700
    # 要找 380566666（如果在區間內）
    
    suffix = int(REWARD_TRIGGER_SUFFIX)  # 66666
    suffix_len = len(REWARD_TRIGGER_SUFFIX)  # 5 位數
    divisor = 10 ** suffix_len  # 100000
    
    # 計算 start_daa 之後最近的 66666 結尾 DAA
    base = (start_daa // divisor) * divisor + suffix
    if base <= start_daa:
        base += divisor  # 跳到下一個 66666
    
    # 檢查是否在區間內
    if base <= end_daa:
        return base
    
    return None


async def check_and_distribute(current_daa: int, tree_balance: int) -> Optional[dict]:
    """
    檢查並發放獎勵
    
    改進：檢查從上次檢查到現在的區間，而不是精確匹配當前 DAA
    （DAA 變化 ~10/秒，60 秒間隔會錯過精確匹配）
    
    Args:
        current_daa: 當前 DAA
        tree_balance: 大地之樹餘額
    
    Returns:
        發放結果，如果沒觸發則返回 None
    """
    db = load_heroes_db()
    last_reward_daa = db.get("last_reward_daa") or 0  # 處理 None
    last_checked_daa = db.get("last_checked_daa") or (last_reward_daa or current_daa - 100000)
    
    # 更新檢查點
    db["last_checked_daa"] = current_daa
    save_heroes_db(db)
    
    # 檢查區間內是否有觸發點
    trigger_daa = find_trigger_daa_in_range(last_checked_daa, current_daa)
    
    if trigger_daa is None:
        return None
    
    # 檢查是否已經發放過（避免重複）
    if trigger_daa <= last_reward_daa:
        logger.info(f"🌲 DAA {trigger_daa} 已發放過，跳過")
        return None
    
    logger.info(f"🎉 觸發獎勵發放！區間 [{last_checked_daa}, {current_daa}] 包含 DAA: {trigger_daa}")
    
    # 發放獎勵（用觸發點 DAA，不是當前 DAA）
    result = await distribute_rewards(trigger_daa, tree_balance)
    
    # 記錄已發放
    db = load_heroes_db()  # 重新載入（distribute_rewards 可能有修改）
    db["last_reward_daa"] = trigger_daa
    db["reward_history"] = db.get("reward_history", [])
    db["reward_history"].append({
        "daa": trigger_daa,
        "checked_at_daa": current_daa,
        "timestamp": datetime.now().isoformat(),
        "total_pool": result["total_pool"],
        "distributed": result["distributed"],
        "recipients_count": len(result["recipients"])
    })
    save_heroes_db(db)
    
    return result
