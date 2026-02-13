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
BASE_REWARD_MANA = 500  # 大地之母每回合提供的起始 mana
REWARD_POOL_RATIO = 0.7  # 70% 進獎勵池
MIN_REWARD = 100000  # 最小發放金額 0.001 tKAS

# 🐲 哥布林入侵設定
GOBLIN_THREAT_PER = 50  # 每隻魔物威脅 50 mana
GOBLIN_SPAWN_PER_WAVE = 2  # 每波生成 2 隻
GOBLIN_MAX_COUNT = 10  # 哥布林存活上限

# 稀有度積分加成
RARITY_BONUS = {
    # v0.3+ Rank 系統 - 6階手遊風格 (Thanks Bob for catching this bug! 🔍)
    "N":   1,         # 普通 55%
    "R":   2,         # 稀有 28%
    "SR":  3,         # 超稀 13%
    "SSR": 5,         # 極稀 3.5%
    "UR":  8,         # 傳說 0.4%
    "LR": 13,         # 神話 0.1%
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
    
    v0.5: 魔物威脅機制
    - 結算時扣除存活哥布林數 × 50 mana
    - 結算後生成新一波哥布林（+2 隻，上限 10 隻）
    
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
        "error": None,
        "goblin_threat": 0,
        "new_goblins": []
    }
    
    # 獎勵池 = 驅動費累積 + 大地之母起始 mana
    db = load_heroes_db()
    accumulated_mana = db.get("total_mana_pool", 0)
    total_mana = accumulated_mana + BASE_REWARD_MANA  # 加入大地之母提供的起始 mana
    
    # 🐲 計算魔物威脅
    alive_goblins = [
        (gid, g) for gid, g in db.get("heroes", {}).items()
        if g.get("status") == "alive" and g.get("owner_id") == 0
    ]
    goblin_count = len(alive_goblins)
    goblin_threat = goblin_count * GOBLIN_THREAT_PER
    result["goblin_count"] = goblin_count
    result["goblin_threat"] = goblin_threat
    
    logger.info(f"🐲 魔物威脅: {goblin_count} 隻 × {GOBLIN_THREAT_PER} = -{goblin_threat} mana")
    
    # 扣除魔物威脅
    actual_mana = max(0, total_mana - goblin_threat)
    reward_pool = int(actual_mana * 1e8)  # 轉換為 sompi
    
    result["total_pool"] = int(total_mana * 1e8)  # 原始獎勵池
    result["actual_pool"] = reward_pool  # 扣除威脅後
    result["mana_pool_before"] = accumulated_mana
    result["base_reward"] = BASE_REWARD_MANA
    
    logger.info(f"🌲 獎勵池: 累積 {accumulated_mana} + 起始 {BASE_REWARD_MANA} = {total_mana} mana")
    logger.info(f"🌲 扣除魔物威脅後: {actual_mana} mana")
    
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
    logger.info(f"🌲 驅動費池已清空（已發放 {accumulated_mana} mana）")
    
    # 🐲 生成下一波哥布林（發放後）
    try:
        new_goblins = await spawn_goblins_wave(daa)
        result["new_goblins"] = new_goblins
        logger.info(f"🐲 新一波哥布林已生成: {len(new_goblins)} 隻")
    except Exception as e:
        logger.error(f"❌ 生成哥布林失敗: {e}")
        result["goblin_spawn_error"] = str(e)
    
    return result


async def spawn_goblins_wave(daa: int) -> list[dict]:
    """
    生成新一波哥布林
    
    Args:
        daa: 當前 DAA（用於生成屬性的 hash 來源）
    
    Returns:
        新生成的哥布林列表
    """
    from hero_game import create_goblin_hero, load_heroes_db
    
    db = load_heroes_db()
    
    # 計算當前存活哥布林數
    alive_goblins = [
        g for g in db.get("heroes", {}).values()
        if g.get("status") == "alive" and g.get("owner_id") == 0
    ]
    current_count = len(alive_goblins)
    
    # 檢查上限
    if current_count >= GOBLIN_MAX_COUNT:
        logger.info(f"🐲 哥布林已達上限 ({current_count}/{GOBLIN_MAX_COUNT})，不生成新的")
        return []
    
    # 計算可生成數量
    spawn_count = min(GOBLIN_SPAWN_PER_WAVE, GOBLIN_MAX_COUNT - current_count)
    
    logger.info(f"🐲 生成 {spawn_count} 隻哥布林 (當前 {current_count}/{GOBLIN_MAX_COUNT})")
    
    new_goblins = []
    for i in range(spawn_count):
        try:
            # 用 DAA + 序號生成不同的哥布林
            goblin = await create_goblin_hero(daa, seed_offset=i)
            new_goblins.append(goblin)
            logger.info(f"🐲 生成哥布林: {goblin.get('name')} #{goblin.get('card_id')}")
        except Exception as e:
            logger.error(f"❌ 生成哥布林 #{i} 失敗: {e}")
    
    return new_goblins


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
    goblin_count = result.get("goblin_count", 0)
    goblin_threat = result.get("goblin_threat", 0)
    actual_pool = result.get("actual_pool", total_pool)
    new_goblins = result.get("new_goblins", [])
    
    lines = [
        f"🌲 *大地之樹獎勵發放* #{daa}",
        "",
        f"💰 獎勵池：{total_pool/1e8:.2f} mana",
        f"   ├ 累積：{accumulated:.2f}",
        f"   └ 起始：{base_reward:.2f} (大地之母)",
    ]
    
    # 魔物威脅
    if goblin_count > 0:
        lines.extend([
            f"🐲 魔物威脅：{goblin_count} 隻 → *-{goblin_threat} mana*",
            f"📊 實際發放：{actual_pool/1e8:.2f} mana",
        ])
    
    lines.extend([
        f"📤 已發放：{distributed/1e8:.2f} mana",
        f"👥 受益者：{len(recipients)} 位英雄",
        "",
        "🏆 *排名：*"
    ])
    
    for i, r in enumerate(recipients[:10], 1):  # 只顯示前 10 名
        hero = r["hero"]
        reward = r["reward"]
        score = r["score"]
        address = r["address"]
        
        # v0.3: 用 rank (N/R/SR/SSR/UR/LR)
        rank_emoji = {
            "N": "⚪", "R": "🔵", "SR": "🟣", 
            "SSR": "🟡", "UR": "🔴", "LR": "✨"
        }.get(hero.rank, "⚪")
        
        class_emoji = {
            "warrior": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"
        }.get(hero.hero_class, "")
        
        status = "✓" if r.get("status") == "success" else "✗"
        
        # 有別名優先顯示別名，沒有就顯示 card_id
        hero_display = f"「{hero.name}」" if hero.name else f"#{hero.card_id}"
        
        lines.append(
            f"{i}. {status} {hero_display} {rank_emoji}{hero.rank} {class_emoji}\n"
            f"   → {reward/1e8:.4f} mana (積分:{score})\n"
            f"   `{address[:25]}...`"
        )
    
    if len(recipients) > 10:
        lines.append(f"\n...還有 {len(recipients) - 10} 位英雄")
    
    # 🐲 新一波魔物來襲
    if new_goblins:
        lines.append("")
        lines.append("🐲 *新一波魔物來襲！*")
        for g in new_goblins:
            rank_emoji = {"N": "⚪", "R": "🔵", "SR": "🟣", "SSR": "🟡", "UR": "🔴", "LR": "✨"}.get(g.get("rank"), "⚪")
            class_emoji = {"knight": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}.get(g.get("hero_class"), "")
            lines.append(f"   👹 {g.get('name')} {rank_emoji}{class_emoji}")
        lines.append("")
        lines.append("⚔️ 下次結算前消滅牠們！")
    
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
    
    # 檢查區間內是否有觸發點（先不更新 last_checked_daa）
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
    
    # 只在成功發放後才更新記錄
    if result.get("success"):
        db = load_heroes_db()  # 重新載入（distribute_rewards 可能有修改）
        db["last_reward_daa"] = trigger_daa
        db["last_checked_daa"] = current_daa  # 只在成功發放後才更新
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
        logger.info(f"✅ 獎勵記錄已保存 | DAA: {trigger_daa}")
    else:
        # 發放失敗，記錄錯誤但不更新 last_checked_daa（下次會重試）
        logger.warning(f"⚠️ 獎勵發放失敗 | DAA: {trigger_daa} | 原因: {result.get('error')}")
    
    return result
