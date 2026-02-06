#!/usr/bin/env python3
"""
🌲 娜米的英雄奇幻冒險 - TG 指令處理
===================================
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

from hero_game import (
    summon_hero, get_user_heroes, get_hero_by_id, process_battle,
    get_game_stats, format_hero_card, format_hero_list, 
    format_summon_result, format_battle_result,
    verify_hero, format_verify_result,
    SUMMON_COST, PVP_COST, load_heroes_db, save_heroes_db
)
# 統一錢包系統（支援舊輪盤 PIN fallback）
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ROULETTE_PINS_FILE = DATA_DIR / "roulette_pins.json"

def load_roulette_pins() -> dict:
    """載入舊的輪盤 PIN"""
    if ROULETTE_PINS_FILE.exists():
        with open(ROULETTE_PINS_FILE) as f:
            return json.load(f)
    return {}

try:
    import unified_wallet
    
    def verify_hero_pin(user_id: int, pin: str) -> bool:
        """驗證 PIN（統一錢包 + 舊輪盤 fallback）"""
        # 先檢查統一錢包
        if unified_wallet.verify_pin(user_id, pin):
            return True
        # 再檢查舊輪盤 PIN
        pins = load_roulette_pins()
        user_pins = pins.get(str(user_id), {})
        return pin in user_pins
    
    def get_hero_wallet(user_id: int, pin: str) -> tuple[str, str]:
        """取得錢包（統一錢包 + 舊輪盤 fallback）"""
        # 先檢查統一錢包
        if unified_wallet.verify_pin(user_id, pin):
            return unified_wallet.get_wallet(user_id, pin)
        # 再檢查舊輪盤 PIN
        pins = load_roulette_pins()
        user_pins = pins.get(str(user_id), {})
        if pin in user_pins:
            from kaspa import PrivateKey
            pk_hex = user_pins[pin]
            pk = PrivateKey(pk_hex)
            address = pk.to_address("testnet").to_string()
            return pk_hex, address
        return None, None
    
    def get_user_hero_address(user_id: int) -> str | None:
        """取得用戶地址（統一錢包 + 舊輪盤 fallback）"""
        # 先檢查統一錢包
        addr = unified_wallet.get_user_address(user_id)
        if addr:
            return addr
        # 舊輪盤沒存地址，需要從私鑰推導（但需要 PIN）
        return None
    
    set_hero_pin = unified_wallet.set_pin
    get_hero_balance = unified_wallet.get_balance
    UNIFIED_WALLET = True
    
except ImportError:
    from hero_wallet import (
        set_hero_pin, verify_hero_pin, get_user_hero_address,
        get_hero_balance, get_hero_wallet
    )
    UNIFIED_WALLET = False

logger = logging.getLogger(__name__)

# 召喚冷卻追蹤
last_summon_time = 0
SUMMON_COOLDOWN = 5  # 秒

# ═══════════════════════════════════════════════════════════════════════════════
# 工具函數
# ═══════════════════════════════════════════════════════════════════════════════

async def get_next_daa_block() -> tuple[int, str]:
    """等待下一個 DAA 的第一個區塊"""
    from kaspa import RpcClient
    
    client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
    await client.connect()
    
    try:
        # 取得當前 DAA
        info = await client.get_block_dag_info({})
        current_daa = info.get("virtualDaaScore", 0)
        target_daa = current_daa + 1
        
        logger.info(f"Waiting for DAA {target_daa}...")
        
        # 等待目標 DAA
        for _ in range(30):  # 最多等 30 秒
            await asyncio.sleep(1)
            info = await client.get_block_dag_info({})
            new_daa = info.get("virtualDaaScore", 0)
            
            if new_daa >= target_daa:
                # 找到目標 DAA 的第一個區塊
                tips = info.get("tipHashes", [])
                
                # 收集該 DAA 的區塊
                blocks_at_target = []
                for tip in tips[:20]:
                    try:
                        block_resp = await client.get_block({"hash": tip, "includeTransactions": False})
                        block = block_resp.get("block", {})
                        header = block.get("header", {})
                        block_daa = header.get("daaScore", 0)
                        blue_work = header.get("blueWork", "0")
                        
                        if block_daa == target_daa:
                            blocks_at_target.append({
                                "hash": tip,
                                "blueWork": blue_work,
                                "daaScore": block_daa
                            })
                    except:
                        continue
                
                if blocks_at_target:
                    # 官方排序：blueWork↓, hash↑
                    blocks_at_target.sort(
                        key=lambda b: (-int(b['blueWork'], 16) if isinstance(b['blueWork'], str) else -b['blueWork'], b['hash'])
                    )
                    first_block = blocks_at_target[0]
                    logger.info(f"Found block at DAA {target_daa}: {first_block['hash'][:16]}...")
                    return target_daa, first_block['hash']
                
                # 如果沒找到精確匹配，用第一個 tip
                if tips:
                    return target_daa, tips[0]
        
        raise TimeoutError("等待區塊超時")
        
    finally:
        await client.disconnect()

# ═══════════════════════════════════════════════════════════════════════════════
# 指令處理器
# ═══════════════════════════════════════════════════════════════════════════════

async def hero_summon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_hero <PIN> - 召喚英雄（消耗 10 mana）
    """
    global last_summon_time
    import time
    
    user = update.effective_user
    
    # 需要 PIN 參數
    if not context.args:
        await update.message.reply_text(
            "🌲 *召喚英雄*\n\n"
            "用法：`/nami_hero <PIN>`\n\n"
            "消耗 10 mana (tKAS) 召喚英雄\n"
            "命運由區塊 hash 決定！\n\n"
            "範例：`/nami_hero 1234`",
            parse_mode='Markdown'
        )
        return
    
    pin = context.args[0]
    
    # 驗證 PIN 格式
    if not pin.isdigit() or not (4 <= len(pin) <= 6):
        await update.message.reply_text("❌ PIN 需為 4-6 位數字")
        return
    
    # 驗證 PIN
    if not verify_hero_pin(user.id, pin):
        await update.message.reply_text(
            "❌ PIN 錯誤或尚未設定錢包\n\n"
            "請先用 `/nami_wallet <PIN>` 創建錢包",
            parse_mode='Markdown'
        )
        return
    
    # 冷卻檢查
    now = time.time()
    if now - last_summon_time < SUMMON_COOLDOWN:
        remaining = int(SUMMON_COOLDOWN - (now - last_summon_time))
        await update.message.reply_text(
            f"⏳ 大地之樹正在恢復瑪那...\n請等待 {remaining} 秒"
        )
        return
    
    # 取得錢包地址（用 PIN 推導）
    pk_hex, address = get_hero_wallet(user.id, pin)
    if not address:
        await update.message.reply_text("❌ 找不到錢包，請重新創建")
        return
    
    # 檢查餘額
    try:
        balance = await get_hero_balance(address)
        required = SUMMON_COST  # 10 tKAS = 10億 sompi
        if balance < required:
            await update.message.reply_text(
                f"❌ mana 不足！\n\n"
                f"需要：{required / 1e8:.0f} mana\n"
                f"目前：{balance / 1e8:.2f} mana\n\n"
                f"💧 用 `/nami_faucet` 領取 tKAS",
                parse_mode='Markdown'
            )
            return
    except Exception as e:
        logger.warning(f"Balance check failed: {e}, proceeding anyway")
    
    # TODO: 發送 10 mana 到大地之樹（啟用付費後取消註解）
    # await unified_wallet.send_to_tree(user.id, pin, SUMMON_COST, f"summon:{user.id}")
    
    await update.message.reply_text("🌲 正在向大地之樹祈禱...\n⏳ 等待下一個區塊...")
    
    try:
        # 取得下一個 DAA 的區塊
        daa, block_hash = await get_next_daa_block()
        
        # 召喚英雄
        hero = await summon_hero(
            user_id=user.id,
            username=user.username or str(user.id),
            address=address,
            daa=daa,
            block_hash=block_hash
        )
        
        last_summon_time = time.time()
        
        # 回覆結果
        await update.message.reply_text(format_summon_result(hero))
        
    except TimeoutError:
        await update.message.reply_text("❌ 等待區塊超時，請稍後再試")
    except Exception as e:
        logger.error(f"Hero summon error: {e}")
        await update.message.reply_text(f"❌ 召喚失敗：{e}")

async def hero_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_heroes - 查看我的英雄
    """
    user = update.effective_user
    heroes = get_user_heroes(user.id)
    await update.message.reply_text(format_hero_list(heroes))

async def hero_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_hero_info <ID> - 查看英雄詳情
    """
    if not context.args:
        await update.message.reply_text("用法：/nami_hero_info <英雄ID>")
        return
    
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 無效的英雄 ID")
        return
    
    hero = get_hero_by_id(card_id)
    if not hero:
        await update.message.reply_text(f"❌ 找不到英雄 #{card_id}")
        return
    
    await update.message.reply_text(format_hero_card(hero), parse_mode='HTML')

async def hero_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_attack @對手 [我的英雄ID] - 發起攻擊
    """
    user = update.effective_user
    
    # 解析參數
    if not context.args:
        await update.message.reply_text(
            "用法：/nami_attack @對手\n"
            "或：/nami_attack @對手 <我的英雄ID>"
        )
        return
    
    # 解析對手
    target_str = context.args[0]
    if not target_str.startswith("@"):
        await update.message.reply_text("❌ 請指定對手 @username")
        return
    
    target_username = target_str[1:]
    
    # 找到對手
    from nami_kaspa_bot import load_users
    users = load_users()
    
    target_user_id = None
    for uid, data in users.items():
        if data.get("username", "").lower() == target_username.lower():
            target_user_id = int(uid)
            break
    
    if not target_user_id:
        await update.message.reply_text(f"❌ 找不到玩家 @{target_username}")
        return
    
    if target_user_id == user.id:
        await update.message.reply_text("❌ 不能攻擊自己！")
        return
    
    # 取得攻擊方的英雄
    my_heroes = get_user_heroes(user.id, alive_only=True)
    if not my_heroes:
        await update.message.reply_text("❌ 你沒有存活的英雄！")
        return
    
    # 選擇英雄
    if len(context.args) > 1:
        try:
            my_hero_id = int(context.args[1])
            my_hero = next((h for h in my_heroes if h.card_id == my_hero_id), None)
            if not my_hero:
                await update.message.reply_text(f"❌ 找不到你的英雄 #{my_hero_id}")
                return
        except ValueError:
            await update.message.reply_text("❌ 無效的英雄 ID")
            return
    else:
        # 預設使用第一個存活英雄
        my_hero = my_heroes[0]
    
    # 取得防守方的英雄
    target_heroes = get_user_heroes(target_user_id, alive_only=True)
    if not target_heroes:
        await update.message.reply_text(f"❌ @{target_username} 沒有存活的英雄！")
        return
    
    # 預設攻擊第一個
    target_hero = target_heroes[0]
    
    # 計算費用
    pvp_cost = PVP_COST.get(my_hero.rarity, 2)
    
    await update.message.reply_text(
        f"⚔️ 發起攻擊！\n\n"
        f"你的英雄：#{my_hero.card_id} {my_hero.display_class()} {my_hero.display_rarity()}\n"
        f"對手英雄：#{target_hero.card_id} {target_hero.display_class()} {target_hero.display_rarity()}\n\n"
        f"消耗：{pvp_cost} mana\n\n"
        f"⏳ 等待命運的裁決..."
    )
    
    try:
        # 取得下一個 DAA 決定勝負
        event_daa, block_hash = await get_next_daa_block()
        result_daa = event_daa + 1
        
        # 處理戰鬥
        updated_attacker, updated_defender, attacker_wins = await process_battle(
            attacker=my_hero,
            defender=target_hero,
            event_daa=event_daa,
            result_daa=result_daa,
            block_hash=block_hash
        )
        
        # 回覆結果
        result_msg = format_battle_result(
            updated_attacker, updated_defender, attacker_wins,
            user.username or str(user.id),
            target_username
        )
        await update.message.reply_text(result_msg)
        
    except Exception as e:
        logger.error(f"Battle error: {e}")
        await update.message.reply_text(f"❌ 戰鬥失敗：{e}")

async def hero_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_history <ID> - 查看英雄歷史
    """
    if not context.args:
        await update.message.reply_text("用法：/nami_history <英雄ID>")
        return
    
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 無效的英雄 ID")
        return
    
    hero = get_hero_by_id(card_id)
    if not hero:
        await update.message.reply_text(f"❌ 找不到英雄 #{card_id}")
        return
    
    # 從鏈條中找到這個英雄的所有記錄
    from hero_game import load_hero_chain
    chain = load_hero_chain()
    
    hero_events = [e for e in chain if e.get("card") == card_id or 
                   e.get("attacker") == card_id or e.get("target") == card_id]
    
    if not hero_events:
        await update.message.reply_text(f"📜 英雄 #{card_id} 沒有歷史記錄")
        return
    
    lines = [f"📜 英雄 #{card_id} 的歷史\n"]
    
    for event in hero_events[-10:]:  # 最近 10 筆
        if event.get("type") == "hero":
            if event.get("pre_daa") == 0:
                lines.append(f"🎴 DAA {event['daa']}: 出生 - {event.get('c')} {event.get('r')}")
            else:
                lines.append(f"📊 DAA {event['daa']}: 狀態更新 - {event.get('status')}")
        elif event.get("type") == "event":
            action = event.get("action", "?")
            result = event.get("result", "?")
            if event.get("attacker") == card_id:
                lines.append(f"⚔️ DAA {event['daa']}: 攻擊 #{event.get('target')} → {result}")
            else:
                lines.append(f"🛡️ DAA {event['daa']}: 被 #{event.get('attacker')} 攻擊 → {result}")
    
    await update.message.reply_text("\n".join(lines))

async def hero_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_rules - 查看遊戲規則
    """
    rules = """🌲 *娜米的英雄奇幻冒險*
_Nami's Hero Fantasy Adventure_

━━━━━━━━━━━━━━━━

*⚡ 基本規則*
• tKAS = Mana（瑪那）
• 召喚英雄：10 mana
• PvP 攻擊：2-8 mana（依稀有度）

*🃏 稀有度*
🪨 普通 60% - ×1.0 屬性
✨ 稀有 25% - ×1.2 屬性
💎 英雄 12% - ×1.4 屬性
👑 傳說 3% - ×1.8 屬性

*⚔️ 戰鬥*
• 高稀有度打低稀有度幾乎必勝
• 但低稀有度有翻盤機會！
• 敗者英雄永久死亡 ☠️

*🌲 大地之樹*
• 定期發放 mana 給存活英雄
• 稀有度越高，祝福越多

*🔗 公平機制*
• 所有結果由區塊 hash 決定
• 鏈上記錄，任何人可驗證

━━━━━━━━━━━━━━━━
_Built on Kaspa TestNet_"""
    
    await update.message.reply_text(rules, parse_mode='Markdown')

async def hero_burn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_burn <ID> - 銷毀英雄（測試用）
    """
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("用法：/nami_burn <英雄ID>")
        return
    
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 無效的英雄 ID")
        return
    
    # 檢查是否是自己的英雄
    from hero_game import get_hero_by_id, load_heroes_db, save_heroes_db, load_hero_chain, save_hero_chain
    
    hero = get_hero_by_id(card_id)
    if not hero:
        await update.message.reply_text(f"❌ 找不到英雄 #{card_id}")
        return
    
    if hero.owner_id != user.id:
        await update.message.reply_text("❌ 這不是你的英雄！")
        return
    
    if hero.status == "dead":
        await update.message.reply_text(f"❌ 英雄 #{card_id} 已經死亡了")
        return
    
    await update.message.reply_text(f"🔥 正在銷毀英雄 #{card_id}...\n⏳ 等待區塊確認...")
    
    # 取得下一個 DAA 和區塊 hash
    try:
        daa, block_hash = await get_next_daa_block()
    except Exception as e:
        await update.message.reply_text(f"❌ 銷毀失敗：{e}")
        return
    
    # 更新狀態
    hero.status = "dead"
    hero.latest_daa = daa
    
    db = load_heroes_db()
    db["heroes"][str(card_id)] = hero.to_dict()
    save_heroes_db(db)
    
    # 建立 payload
    event_payload = {
        "g": "nami_hero",
        "type": "event",
        "daa": daa,
        "pre_daa": hero.card_id,
        "action": "burn",
        "card": card_id,
        "block_hash": block_hash,
        "result": "destroyed"
    }
    
    state_payload = {
        "g": "nami_hero",
        "type": "hero",
        "daa": daa + 1,
        "pre_daa": daa,
        "card": card_id,
        "status": "dead"
    }
    
    # 記錄銷毀事件
    chain = load_hero_chain()
    chain.append(event_payload)
    chain.append(state_payload)
    save_hero_chain(chain)
    
    # 區塊瀏覽器連結
    explorer_url = f"https://explorer-tn10.kaspa.org/blocks/{block_hash}"
    
    # 格式化 payload 顯示
    import json
    payload_str = json.dumps(event_payload, indent=2, ensure_ascii=False)
    
    await update.message.reply_text(
        f"🔥 英雄已銷毀！\n\n"
        f"#{card_id} {hero.display_class()} {hero.display_rarity()}\n"
        f"→ 回歸大地之樹 🌲\n\n"
        f"📍 銷毀 DAA: #{daa}\n"
        f"🔗 [區塊瀏覽器]({explorer_url})\n\n"
        f"📦 *Payload:*\n```json\n{payload_str}\n```",
        parse_mode='Markdown'
    )

async def hero_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_verify <ID> - 驗證英雄（檢查鏈上資料）
    """
    if not context.args:
        await update.message.reply_text("用法：/nami_verify <英雄ID>")
        return
    
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 無效的英雄 ID")
        return
    
    await update.message.reply_text(f"🔍 正在驗證英雄 #{card_id}...")
    
    try:
        result = await verify_hero(card_id)
        await update.message.reply_text(
            format_verify_result(result),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Verify error: {e}")
        await update.message.reply_text(f"❌ 驗證失敗：{e}")

async def hero_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_game_status - 查看遊戲統計
    """
    stats = get_game_stats()
    
    msg = f"""🌲 *大地之樹狀態*

👥 玩家數：{stats['total_players']}
🎴 總英雄：{stats['total_heroes']}
├ 🟢 存活：{stats['alive_heroes']}
└ ☠️ 陣亡：{stats['dead_heroes']}

*稀有度分布：*
🪨 普通：{stats['rarity_counts']['common']}
✨ 稀有：{stats['rarity_counts']['rare']}
💎 英雄：{stats['rarity_counts']['epic']}
👑 傳說：{stats['rarity_counts']['legendary']}

💰 Mana 池：{stats['mana_pool']} tKAS"""
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def hero_payload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_payload <ID> - 查看英雄的鏈上 payload
    """
    if not context.args:
        await update.message.reply_text("用法：/nami_payload <英雄ID>")
        return
    
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 無效的英雄 ID")
        return
    
    hero = get_hero_by_id(card_id)
    if not hero:
        await update.message.reply_text(f"❌ 找不到英雄 #{card_id}")
        return
    
    # 生成 payload
    payload = {
        "g": "nami_hero",
        "type": "hero",
        "daa": hero.card_id,
        "card": hero.card_id,
        "c": hero.hero_class[:3],
        "r": hero.rarity[:3],
        "a": hero.atk,
        "d": hero.def_,
        "s": hero.spd,
        "status": hero.status
    }
    
    import json
    payload_json = json.dumps(payload, separators=(',', ':'))
    
    msg = f"""📦 英雄 #{card_id} Payload

<code>{payload_json}</code>

📍 命運: DAA {hero.card_id}
📦 公告: DAA {hero.card_id + 1} (待上鏈)

Size: {len(payload_json)} bytes"""
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def hero_decode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_decode <TX_ID> - 解碼鏈上交易的 payload
    """
    if not context.args:
        await update.message.reply_text("用法：/nami_decode <TX_ID>")
        return
    
    tx_id = context.args[0]
    
    # 驗證 TX ID 格式（64 hex 字符）
    if len(tx_id) != 64 or not all(c in '0123456789abcdef' for c in tx_id.lower()):
        await update.message.reply_text("❌ 無效的 TX ID（需要 64 個十六進位字符）")
        return
    
    await update.message.reply_text(f"🔍 正在查詢交易 {tx_id[:16]}...")
    
    try:
        from kaspa import RpcClient
        
        client = RpcClient(url="ws://127.0.0.1:17210", network_id="testnet-10")
        await client.connect()
        
        try:
            # 查詢交易
            # 注意：kaspad 可能不支援直接查詢 TX，需要用其他方式
            # 先嘗試從 mempool 查詢
            result = await client.get_mempool_entry({"txId": tx_id})
            tx_data = result.get('transaction', {})
            payload_hex = tx_data.get('payload', '')
        except Exception as e:
            # 如果不在 mempool，交易可能已經被確認
            # 需要用區塊瀏覽器 API 或其他方式查詢
            await update.message.reply_text(
                f"⚠️ 交易不在 mempool（可能已確認）\n\n"
                f"請手動複製 explorer 的 payload hex，然後用：\n"
                f"/nami_decode_hex <payload_hex>"
            )
            return
        finally:
            await client.disconnect()
        
        if not payload_hex:
            await update.message.reply_text("❌ 交易沒有 payload")
            return
        
        # 解碼 payload
        import json
        payload_bytes = bytes.fromhex(payload_hex)
        payload_str = payload_bytes.decode('utf-8')
        payload_json = json.loads(payload_str)
        
        formatted = json.dumps(payload_json, indent=2, ensure_ascii=False)
        
        msg = f"""🔍 交易 Payload 解碼

TX: <code>{tx_id[:32]}...</code>

📦 Payload:
<pre>{formatted}</pre>

🔗 <a href="https://explorer-tn10.kaspa.org/txs/{tx_id}">區塊瀏覽器</a>"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Decode error: {e}")
        await update.message.reply_text(f"❌ 解碼失敗：{e}")

async def hero_decode_hex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_decode_hex <payload_hex> - 直接解碼 hex payload
    """
    if not context.args:
        await update.message.reply_text("用法：/nami_decode_hex <payload_hex>")
        return
    
    payload_hex = context.args[0]
    
    try:
        import json
        payload_bytes = bytes.fromhex(payload_hex)
        payload_str = payload_bytes.decode('utf-8')
        payload_json = json.loads(payload_str)
        
        formatted = json.dumps(payload_json, indent=2, ensure_ascii=False)
        
        msg = f"""🔍 Payload 解碼成功！

<pre>{formatted}</pre>

Size: {len(payload_hex) // 2} bytes"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ 解碼失敗：{e}")

async def hero_pin_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_hero_pin <PIN> - 設定英雄遊戲 PIN（私聊）
    """
    user = update.effective_user
    
    # 只允許私聊
    if update.effective_chat.type != 'private':
        await update.message.reply_text("⚠️ 請私聊我設定 PIN！")
        return
    
    if not context.args:
        # 顯示當前狀態
        address = get_user_hero_address(user.id)
        if address:
            try:
                balance = await get_hero_balance(address)
                msg = f"""🎴 你的英雄錢包

📍 地址：
<code>{address}</code>

💰 餘額：{balance / 1e8:.4f} tKAS

存入 tKAS 到這個地址就可以召喚英雄！
召喚費用：10 tKAS"""
            except:
                msg = f"""🎴 你的英雄錢包

📍 地址：
<code>{address}</code>

（無法查詢餘額）"""
        else:
            msg = """🎴 英雄錢包設定

用法：/nami_hero_pin <PIN>

PIN 為 4-6 位數字，會產生你專屬的英雄錢包地址。

⚠️ 重要：記住你的 PIN！忘記 PIN = 失去錢包！"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        return
    
    pin = context.args[0]
    
    # 驗證 PIN 格式
    if not pin.isdigit() or not (4 <= len(pin) <= 6):
        await update.message.reply_text("❌ PIN 需為 4-6 位數字")
        return
    
    # 設定 PIN
    address = set_hero_pin(user.id, pin)
    
    # 查餘額
    try:
        balance = await get_hero_balance(address)
        balance_str = f"{balance / 1e8:.4f} tKAS"
    except:
        balance_str = "（無法查詢）"
    
    msg = f"""✅ PIN 設定成功！

🔑 PIN：{pin}
📍 地址：
<code>{address}</code>

💰 餘額：{balance_str}

存入 tKAS 到這個地址，就可以用 PIN 召喚英雄！

⚠️ 重要：記住你的 PIN！
（同一個 PIN 永遠對應同一個地址）"""
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def hero_wallet_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_hero_balance - 查看英雄錢包餘額
    """
    user = update.effective_user
    address = get_user_hero_address(user.id)
    
    if not address:
        await update.message.reply_text(
            "❌ 你還沒設定英雄錢包！\n\n"
            "請私聊我用 /nami_hero_pin 設定 PIN"
        )
        return
    
    try:
        balance = await get_hero_balance(address)
        
        msg = f"""💰 英雄錢包餘額

📍 地址：<code>{address[:30]}...</code>
💰 餘額：{balance / 1e8:.4f} tKAS

召喚費用：10 tKAS
PvP 費用：2-8 tKAS"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ 查詢失敗：{e}")

# ═══════════════════════════════════════════════════════════════════════════════
# 註冊指令
# ═══════════════════════════════════════════════════════════════════════════════

def register_hero_commands(app):
    """註冊英雄遊戲指令到 Bot"""
    from telegram.ext import CommandHandler
    
    # 主要指令
    app.add_handler(CommandHandler("nami_hero", hero_summon))
    app.add_handler(CommandHandler("nami_heroes", hero_list))
    app.add_handler(CommandHandler("nami_attack", hero_attack))
    app.add_handler(CommandHandler("nami_burn", hero_burn))
    
    # 輔助指令
    app.add_handler(CommandHandler("nami_hero_info", hero_info))
    app.add_handler(CommandHandler("nami_history", hero_history))
    app.add_handler(CommandHandler("nami_verify", hero_verify))
    app.add_handler(CommandHandler("nami_rules", hero_rules))
    app.add_handler(CommandHandler("nami_game_status", hero_stats))
    app.add_handler(CommandHandler("nami_payload", hero_payload))
    app.add_handler(CommandHandler("nami_decode", hero_decode))
    app.add_handler(CommandHandler("nami_decode_hex", hero_decode_hex))
    app.add_handler(CommandHandler("nami_hero_pin", hero_pin_setup))
    app.add_handler(CommandHandler("nami_hero_balance", hero_wallet_balance))
    
    logger.info("🌲 英雄遊戲指令已註冊")
