#!/usr/bin/env python3
"""
🌲 娜米的英雄奇幻冒險 - TG 指令處理
===================================
"""

import asyncio
import logging
import time
from telegram import Update
from telegram.ext import ContextTypes

# ═══════════════════════════════════════════════════════════════════════════════
# 🙏 大地之樹排隊系統
# ═══════════════════════════════════════════════════════════════════════════════

class TreeQueue:
    """大地之樹服務排隊系統"""
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._queue = []  # [(user_id, timestamp)]
        self._current_user = None
    
    def queue_size(self) -> int:
        """目前排隊人數"""
        return len(self._queue)
    
    def add_to_queue(self, user_id: int):
        """加入排隊"""
        if user_id not in [u for u, _ in self._queue]:
            self._queue.append((user_id, time.time()))
    
    def remove_from_queue(self, user_id: int):
        """離開排隊"""
        self._queue = [(u, t) for u, t in self._queue if u != user_id]
    
    async def acquire(self, user_id: int) -> bool:
        """嘗試獲取服務"""
        self.add_to_queue(user_id)
        await self._lock.acquire()
        self._current_user = user_id
        self.remove_from_queue(user_id)
        return True
    
    def release(self):
        """釋放服務"""
        self._current_user = None
        if self._lock.locked():
            self._lock.release()
    
    def get_queue_message(self, user_id: int) -> str:
        """取得排隊訊息"""
        pos = next((i for i, (u, _) in enumerate(self._queue) if u == user_id), -1)
        if pos > 0:
            return f"⏳ 排隊等候 {pos} 人..."
        return ""


# 全局排隊實例
tree_queue = TreeQueue()

# ═══════════════════════════════════════════════════════════════════════════════
# 📢 公告系統
# ═══════════════════════════════════════════════════════════════════════════════

def get_announcement_chat_id() -> int | None:
    """從檔案載入公告群組 ID"""
    announce_file = DATA_DIR / "announce_group.json"
    if announce_file.exists():
        with open(announce_file, 'r') as f:
            data = json.load(f)
            return data.get("chat_id")
    return None

async def send_announcement(bot, message: str, parse_mode: str = 'Markdown'):
    """發送公告到群組"""
    chat_id = get_announcement_chat_id()
    if not chat_id:
        return
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"公告發送失敗: {e}")

async def announce_hero_birth(bot, hero, username: str):
    """公告英雄誕生"""
    rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", 
                    "epic": "🟣👑", "legendary": "🟡✨", "mythic": "🔴🔱"}.get(hero.rarity, "⚪")
    rarity_name = {"common": "普通", "uncommon": "優秀", "rare": "稀有",
                   "epic": "史詩", "legendary": "傳說", "mythic": "神話"}.get(hero.rarity, "普通")
    class_name = {"warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}.get(hero.hero_class, "")
    class_emoji = {"warrior": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}.get(hero.hero_class, "")
    
    # 取得區塊和銘文連結
    block_link = ""
    if hero.source_hash:
        block_link = f"🔗 命運區塊:\nhttps://explorer-tn10.kaspa.org/blocks/{hero.source_hash}"
    
    tx_link = ""
    if hero.tx_id and not hero.tx_id.startswith('daa_'):
        tx_link = f"📝 銘文:\nhttps://explorer-tn10.kaspa.org/txs/{hero.tx_id}"
    
    msg = f"""🎴 <b>召喚成功！</b>

{rarity_emoji} {rarity_name} - {class_name} {class_emoji}
⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}

📍 命運: DAA <code>{hero.card_id}</code>
{block_link}
{tx_link}

👤 召喚者: @{username}
英雄 ID: <code>#{hero.card_id}</code>

快速指令：
<code>/nami_verify {hero.card_id}</code>"""
    
    await send_announcement(bot, msg, parse_mode='HTML')

async def announce_hero_death(bot, hero, reason: str, killer_name: str = None, death_tx: str = None):
    """公告英雄死亡"""
    rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵",
                    "epic": "🟣👑", "legendary": "🟡✨", "mythic": "🔴🔱"}.get(hero.rarity, "⚪")
    rarity_name = {"common": "普通", "uncommon": "優秀", "rare": "稀有",
                   "epic": "史詩", "legendary": "傳說", "mythic": "神話"}.get(hero.rarity, "普通")
    class_name = {"warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}.get(hero.hero_class, "")
    class_emoji = {"warrior": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}.get(hero.hero_class, "")
    
    if reason == "burn":
        cause = "🔥 自焚銷毀"
    elif reason == "pvp_loss" and killer_name:
        cause = f"⚔️ 被 @{killer_name} 擊殺"
    else:
        cause = f"☠️ {reason}"
    
    tx_link = ""
    if death_tx:
        tx_link = f"📝 死亡銘文:\nhttps://explorer-tn10.kaspa.org/txs/{death_tx}"
    
    msg = f"""☠️ <b>英雄陣亡</b>

{rarity_emoji} {rarity_name} - {class_name} {class_emoji}
⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}

💀 死因: {cause}
⚔️ 戰績: {hero.battles}戰 {hero.kills}殺
{tx_link}

英雄 ID: <code>#{hero.card_id}</code>

快速指令：
<code>/nami_verify {hero.card_id}</code>

<i>願靈魂回歸大地之樹...</i> 🌲"""
    
    await send_announcement(bot, msg, parse_mode='HTML')

async def announce_pvp_result(bot, result: dict, my_hero, target_hero, 
                               attacker_name: str, defender_name: str):
    """公告完整 PvP 戰報到群聊"""
    
    # 稀有度名稱
    rarity_names = {
        "common": "普通", "uncommon": "優秀", "rare": "稀有",
        "epic": "史詩", "legendary": "傳說", "mythic": "神話"
    }
    class_names = {
        "warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"
    }
    rarity_mult = {
        "common": "x1.0", "uncommon": "x1.2", "rare": "x1.5",
        "epic": "x1.5", "legendary": "x2.0", "mythic": "x3.0"
    }
    
    my_rarity = rarity_names.get(my_hero.rarity, "普通")
    target_rarity = rarity_names.get(target_hero.rarity, "普通")
    my_mult = rarity_mult.get(my_hero.rarity, "x1.0")
    target_mult = rarity_mult.get(target_hero.rarity, "x1.0")
    
    # 檢查是否命運逆轉
    detail = result.get("battle_detail", {})
    is_reversal = detail.get("reversal", False)
    
    # 確定勝負
    if result["attacker_wins"]:
        if is_reversal:
            result_emoji = "⚡"
            result_text = "命運逆轉！！！"
        else:
            result_emoji = "🏆"
            result_text = "攻方獲勝！"
        winner = my_hero
        loser = target_hero
        winner_name = attacker_name
        loser_name = defender_name
    else:
        result_emoji = "🛡️"
        result_text = "守方反殺！"
        winner = target_hero
        loser = my_hero
        winner_name = defender_name
        loser_name = attacker_name
    
    winner_class = class_names.get(winner.hero_class, winner.hero_class)
    loser_class = class_names.get(loser.hero_class, loser.hero_class)
    
    # 格式化戰鬥詳情
    detail = result.get("battle_detail", {})
    rounds_text = ""
    for i, r in enumerate(detail.get("rounds", []), 1):
        if r["winner"] == "atk":
            r_result = "🔵"
        elif r["winner"] == "def":
            r_result = "🔴"
        else:
            r_result = "⚪"
        rounds_text += f"R{i} {r['name']}: {r['atk_val']} vs {r['def_val']} {r_result}\n"
    
    score = f"{detail.get('atk_wins', 0)}:{detail.get('def_wins', 0)}"
    
    msg = f"""{result_emoji} <b>PvP 結果：{result_text}</b>

🔵 <b>攻方</b> #{my_hero.card_id} ({my_rarity} {my_mult})
⚔️{my_hero.atk} 🛡️{my_hero.def_} ⚡{my_hero.spd}

🔴 <b>守方</b> #{target_hero.card_id} ({target_rarity} {target_mult})
⚔️{target_hero.atk} 🛡️{target_hero.def_} ⚡{target_hero.spd}

📊 <b>對決</b> (數值已含加成)
{rounds_text}
<b>比分: {score}</b> → {detail.get('final_reason', '')}

---

🏆 <b>勝者</b>：#{winner.card_id} {winner_class}
   @{winner_name} | 擊殺：{winner.kills}

☠️ <b>敗者</b>：#{loser.card_id} {loser_class}
   @{loser_name} | 永久死亡

📝 <b>鏈上記錄</b>：
付費: <code>{result['payment_tx'][:16]}...</code>"""
    
    if result.get("win_tx"):
        msg += f"\n勝利: <code>{result['win_tx'][:20]}...</code>"
    msg += f"\n死亡: <code>{result['death_tx'][:20]}...</code>"
    
    msg += f"\n\n🔗 <a href='https://explorer-tn10.kaspa.org/txs/{result['death_tx']}'>區塊瀏覽器</a>"
    
    msg += "\n\n<i>願靈魂回歸大地之樹...</i> 🌲"
    
    await send_announcement(bot, msg, parse_mode='HTML')

async def announce_reward(bot, result: dict):
    """公告獎勵發放"""
    from reward_system import format_reward_announcement
    msg = format_reward_announcement(result)
    await send_announcement(bot, msg)

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
                
                # 如果沒找到精確匹配，用第一個 tip 並取其實際 DAA
                if tips:
                    try:
                        block_resp = await client.get_block({"hash": tips[0], "includeTransactions": False})
                        actual_daa = block_resp.get("block", {}).get("header", {}).get("daaScore", new_daa)
                        logger.warning(f"No block at target DAA {target_daa}, using tip with DAA {actual_daa}")
                        return actual_daa, tips[0]
                    except:
                        return new_daa, tips[0]
        
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
    chat = update.effective_chat
    
    # Log: 誰在哪裡做了什麼
    chat_info = f"[{chat.type}:{chat.id}]" if chat.type != "private" else "[私聊]"
    logger.info(f"🎮 召喚請求 | {chat_info} @{user.username or user.id}")
    
    # 需要 PIN 參數
    if not context.args:
        await update.message.reply_text(
            "🌲 *召喚英雄*\n\n"
            "消耗 10 mana (tKAS) 召喚英雄\n"
            "命運由區塊 hash 決定！\n\n"
            "用法：\n"
            "```\n/nami_hero <PIN>\n```",
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
    
    # 檢查英雄上限（在排隊前檢查，避免浪費等待時間）
    from hero_game import MAX_HEROES_PER_USER, load_heroes_db
    db = load_heroes_db()
    user_alive_heroes = [h for h in db.get("heroes", {}).values() 
                         if h.get("owner_id") == user.id and h.get("status") == "alive"]
    
    if len(user_alive_heroes) >= MAX_HEROES_PER_USER:
        # 列出玩家的英雄，引導燒掉
        rarity_names = {"common": "⚪普通", "uncommon": "🟢優秀", "rare": "🔵稀有",
                        "epic": "🟣史詩", "legendary": "🟡傳說", "mythic": "🔴神話"}
        class_names = {"warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}
        
        hero_list = []
        for h in user_alive_heroes:
            r = rarity_names.get(h["rarity"], h["rarity"])
            c = class_names.get(h["hero_class"], h["hero_class"])
            hero_list.append(f"  `#{h['card_id']}` {r} {c} - {h.get('kills', 0)}殺")
        
        msg = f"""⚠️ <b>英雄數量已達上限！</b>

你目前有 <b>{len(user_alive_heroes)}/{MAX_HEROES_PER_USER}</b> 隻存活英雄。

📜 <b>你的英雄：</b>
{chr(10).join(hero_list)}

💡 請先燒掉不需要的英雄再召喚：
<pre>/nami_burn &lt;英雄ID&gt; &lt;PIN&gt;</pre>

例如：
<code>/nami_burn {user_alive_heroes[0]['card_id']} {pin}</code>

🔥 燒掉英雄會退還 5 mana！"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        return
    
    # 排隊系統
    queue_size = tree_queue.queue_size()
    if queue_size > 0:
        await update.message.reply_text(
            f"🙏 正在向大地之樹祈禱...\n"
            f"⏳ 排隊等候 {queue_size} 人..."
        )
    else:
        await update.message.reply_text("🙏 正在向大地之樹祈禱...\n⏳ 等待下一個區塊...")
    
    # 等待輪到自己
    await tree_queue.acquire(user.id)
    
    try:
        # 取得下一個 DAA 的區塊
        daa, block_hash = await get_next_daa_block()
        
        # 召喚英雄（玩家自己簽名 inscription！）
        hero = await summon_hero(
            user_id=user.id,
            username=user.username or str(user.id),
            address=address,
            daa=daa,
            block_hash=block_hash,
            pin=pin  # 傳入 PIN 讓玩家自己簽名
        )
        
        last_summon_time = time.time()
        
        # Log: 召喚成功
        logger.info(f"✅ 召喚成功 | @{user.username or user.id} | #{hero.card_id} {hero.display_rarity()} {hero.display_class()}")
        if hero.tx_id:
            logger.info(f"   📦 TX: {hero.tx_id}")
        
        # 回覆結果
        await update.message.reply_text(format_summon_result(hero), parse_mode='Markdown')
        
        # 群組公告
        await announce_hero_birth(context.bot, hero, user.username or str(user.id))
        
    except TimeoutError:
        logger.warning(f"⏰ 召喚超時 | @{user.username or user.id}")
        await update.message.reply_text("❌ 等待區塊超時，請稍後再試")
    except Exception as e:
        logger.error(f"❌ 召喚失敗 | @{user.username or user.id} | {e}")
        await update.message.reply_text(f"❌ 召喚失敗：{e}")
    finally:
        # 釋放排隊
        tree_queue.release()

async def hero_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_heroes - 查看我的英雄
    """
    user = update.effective_user
    heroes = get_user_heroes(user.id)
    await update.message.reply_text(format_hero_list(heroes), parse_mode='Markdown')

SCOUT_COST = 10_00000000  # 偵查費用 10 mana

async def hero_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_hero_info <ID> [PIN] - 查看英雄詳情
    
    - 查看自己的英雄：免費
    - 查看別人的英雄：需要 10 mana + PIN（偵查費）
    """
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📜 *查看英雄詳情*\n\n"
            "查看自己的英雄（免費）：\n"
            "```\n/nami_hero_info <ID>\n```\n\n"
            "偵查敵方英雄（10 mana）：\n"
            "```\n/nami_hero_info <ID> <PIN>\n```",
            parse_mode='Markdown'
        )
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
    
    # 檢查是否為自己的英雄
    is_own_hero = hero.owner_id == user.id
    
    if is_own_hero:
        # 自己的英雄：免費查看
        await update.message.reply_text(format_hero_card(hero), parse_mode='HTML')
    else:
        # 別人的英雄：需要付費偵查
        if len(context.args) < 2:
            await update.message.reply_text(
                f"🔍 *偵查敵方英雄*\n\n"
                f"英雄 `#{card_id}` 屬於其他玩家\n"
                f"偵查需要消耗 *10 mana*\n\n"
                f"確認偵查：\n"
                f"```\n/nami_hero_info {card_id} <你的PIN>\n```",
                parse_mode='Markdown'
            )
            return
        
        pin = context.args[1]
        
        # 驗證 PIN 並取得地址
        if not verify_hero_pin(user.id, pin):
            await update.message.reply_text("❌ PIN 錯誤")
            return
        
        # 取得使用者地址
        try:
            _, address = get_hero_wallet(user.id, pin)
        except Exception as e:
            await update.message.reply_text(f"❌ 錢包錯誤：{e}")
            return
        
        # 檢查餘額
        try:
            balance = await get_hero_balance(address)
            if balance < SCOUT_COST:
                need = (SCOUT_COST - balance) / 1e8
                await update.message.reply_text(f"❌ 餘額不足！需要 10 mana，還差 {need:.2f}")
                return
        except Exception as e:
            await update.message.reply_text(f"❌ 餘額查詢失敗：{e}")
            return
        
        # 扣款
        try:
            import unified_wallet
            tx_id = await unified_wallet.send_to_tree(user.id, pin, SCOUT_COST, f"scout:{card_id}")
            await update.message.reply_text(
                f"🔍 *偵查成功！*\n\n"
                f"💰 消耗 10 mana\n"
                f"📝 TX: `{tx_id[:16]}...`\n\n"
                f"──────────────\n",
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 付款失敗：{e}")
            return
        
        # 顯示英雄資訊
        await update.message.reply_text(format_hero_card(hero), parse_mode='HTML')

async def hero_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_search <@username> [PIN] - 搜尋玩家的英雄
    
    - 免費看存活數量
    - 10 mana 看詳細列表
    """
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔍 *搜尋玩家英雄*\n\n"
            "查看玩家英雄數量（免費）：\n"
            "```\n/nami_search @username\n```\n\n"
            "查看詳細列表（10 mana）：\n"
            "```\n/nami_search @username <PIN>\n```",
            parse_mode='Markdown'
        )
        return
    
    target_username = context.args[0].lstrip('@').lower()
    
    # 從 users.json 找 user_id
    import json
    with open(DATA_DIR / "users.json", 'r') as f:
        users = json.load(f)
    
    target_user_id = None
    for uid, udata in users.items():
        if udata.get("username", "").lower() == target_username:
            target_user_id = int(uid)
            break
    
    if not target_user_id:
        await update.message.reply_text(f"❌ 找不到玩家 @{target_username}")
        return
    
    # 取得該玩家的英雄
    from hero_game import load_heroes_db
    db = load_heroes_db()
    
    target_heroes = [h for h in db.get("heroes", {}).values() 
                     if h.get("owner_id") == target_user_id]
    alive_heroes = [h for h in target_heroes if h.get("status") == "alive"]
    dead_heroes = [h for h in target_heroes if h.get("status") == "dead"]
    
    # 免費資訊：只顯示數量
    if len(context.args) < 2:
        await update.message.reply_text(
            f"🔍 *玩家偵查：@{target_username}*\n\n"
            f"🟢 存活英雄：{len(alive_heroes)} 隻\n"
            f"☠️ 陣亡英雄：{len(dead_heroes)} 隻\n\n"
            f"💡 查看詳細列表需要 10 mana：\n"
            f"```\n/nami_search @{target_username} <PIN>\n```",
            parse_mode='Markdown'
        )
        return
    
    # 付費偵查：顯示詳細列表
    pin = context.args[1]
    
    # 驗證 PIN 並取得地址
    if not verify_hero_pin(user.id, pin):
        await update.message.reply_text("❌ PIN 錯誤")
        return
    
    # 取得使用者地址
    try:
        _, address = get_hero_wallet(user.id, pin)
    except Exception as e:
        await update.message.reply_text(f"❌ 錢包錯誤：{e}")
        return
    
    # 檢查餘額
    try:
        balance = await get_hero_balance(address)
        if balance < SCOUT_COST:
            need = (SCOUT_COST - balance) / 1e8
            await update.message.reply_text(f"❌ 餘額不足！需要 10 mana，還差 {need:.2f}")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ 餘額查詢失敗：{e}")
        return
    
    # 扣款
    try:
        import unified_wallet
        tx_id = await unified_wallet.send_to_tree(user.id, pin, SCOUT_COST, f"search:{target_username}")
    except Exception as e:
        await update.message.reply_text(f"❌ 付款失敗：{e}")
        return
    
    # 格式化英雄列表
    rarity_names = {"common": "⚪", "uncommon": "🟢", "rare": "🔵",
                    "epic": "🟣👑", "legendary": "🟡✨", "mythic": "🔴🔱"}
    class_emojis = {"warrior": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}
    
    lines = [f"🔍 *@{target_username} 的英雄*\n"]
    lines.append(f"💰 偵查費：10 mana | TX: `{tx_id[:12]}...`\n")
    
    if alive_heroes:
        lines.append("🟢 *存活：*")
        for h in alive_heroes:
            r = rarity_names.get(h["rarity"], "⚪")
            c = class_emojis.get(h["hero_class"], "")
            lines.append(f"  `#{h['card_id']}` {r}{c} ⚔️{h['atk']} 🛡️{h['def']} ⚡{h['spd']}")
    
    if dead_heroes:
        lines.append("\n☠️ *陣亡：*")
        for h in dead_heroes[:5]:  # 最多顯示 5 隻
            r = rarity_names.get(h["rarity"], "⚪")
            c = class_emojis.get(h["hero_class"], "")
            lines.append(f"  `#{h['card_id']}` {r}{c}")
        if len(dead_heroes) > 5:
            lines.append(f"  _...還有 {len(dead_heroes)-5} 隻_")
    
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

async def hero_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_pvp <我的ID> <對手ID> <PIN> - 發起 PvP 攻擊
    
    鏈上 PvP 流程：
    1. 驗證雙方英雄存活
    2. 付費給大地之樹
    3. 等待命運區塊決定勝負
    4. 發送鏈上事件
    """
    user = update.effective_user
    chat = update.effective_chat
    
    chat_info = f"[{chat.type}:{chat.id}]" if chat.type != "private" else "[私聊]"
    logger.info(f"⚔️ PvP 請求 | {chat_info} @{user.username or user.id} | args: {len(context.args or [])}")
    
    # 解析參數
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "⚔️ *PvP 攻擊*\n\n"
            "用法：\n"
            "```\n/nami_pvp <我的英雄ID> <對手英雄ID> <PIN>\n```\n\n"
            "例如：\n"
            "`/nami_pvp 380079718 380067645 1234`\n\n"
            "⚠️ 敗者永久死亡！",
            parse_mode='Markdown'
        )
        return
    
    try:
        my_hero_id = int(context.args[0])
        target_hero_id = int(context.args[1])
        pin = context.args[2]
    except (ValueError, IndexError):
        await update.message.reply_text("❌ 用法：`/nami_pvp <我的ID> <對手ID> <PIN>`", parse_mode='Markdown')
        return
    
    # 不能攻擊自己的英雄
    if my_hero_id == target_hero_id:
        await update.message.reply_text("❌ 不能攻擊自己的英雄！")
        return
    
    # 取得雙方英雄
    from hero_game import load_heroes_db, Hero, PVP_COST, process_pvp_onchain, format_battle_result
    
    db = load_heroes_db()
    my_hero_data = db.get("heroes", {}).get(str(my_hero_id))
    target_hero_data = db.get("heroes", {}).get(str(target_hero_id))
    
    if not my_hero_data:
        await update.message.reply_text(f"❌ 找不到英雄 #{my_hero_id}")
        return
    if not target_hero_data:
        await update.message.reply_text(f"❌ 找不到英雄 #{target_hero_id}")
        return
    
    # 驗證擁有權
    if my_hero_data.get("owner_id") != user.id:
        await update.message.reply_text(f"❌ #{my_hero_id} 不是你的英雄！")
        return
    
    # 不能攻擊自己的英雄
    if target_hero_data.get("owner_id") == user.id:
        await update.message.reply_text("❌ 不能攻擊自己的英雄！")
        return
    
    # 驗證雙方都活著
    if my_hero_data.get("status") != "alive":
        await update.message.reply_text(f"❌ 你的英雄 #{my_hero_id} 已死亡！")
        return
    if target_hero_data.get("status") != "alive":
        await update.message.reply_text(f"❌ 對手英雄 #{target_hero_id} 已死亡！")
        return
    
    # 驗證 PIN
    import unified_wallet
    if not unified_wallet.verify_pin(user.id, pin):
        await update.message.reply_text("❌ PIN 錯誤")
        return
    
    # 建立 Hero 物件
    my_hero = Hero(
        card_id=my_hero_data["card_id"],
        owner_id=my_hero_data["owner_id"],
        owner_address=my_hero_data["owner_address"],
        hero_class=my_hero_data["hero_class"],
        rarity=my_hero_data["rarity"],
        atk=my_hero_data["atk"],
        def_=my_hero_data["def"],
        spd=my_hero_data["spd"],
        status=my_hero_data["status"],
        latest_daa=my_hero_data.get("latest_daa", my_hero_data["card_id"]),
        kills=my_hero_data.get("kills", 0),
        battles=my_hero_data.get("battles", 0),
        tx_id=my_hero_data.get("tx_id", ""),
        latest_tx=my_hero_data.get("latest_tx", "")
    )
    
    target_hero = Hero(
        card_id=target_hero_data["card_id"],
        owner_id=target_hero_data["owner_id"],
        owner_address=target_hero_data["owner_address"],
        hero_class=target_hero_data["hero_class"],
        rarity=target_hero_data["rarity"],
        atk=target_hero_data["atk"],
        def_=target_hero_data["def"],
        spd=target_hero_data["spd"],
        status=target_hero_data["status"],
        latest_daa=target_hero_data.get("latest_daa", target_hero_data["card_id"]),
        kills=target_hero_data.get("kills", 0),
        battles=target_hero_data.get("battles", 0),
        tx_id=target_hero_data.get("tx_id", ""),
        latest_tx=target_hero_data.get("latest_tx", "")
    )
    
    # 計算費用
    pvp_cost = PVP_COST
    
    # 中文翻譯
    class_names = {"warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}
    rarity_names = {"common": "普通", "uncommon": "優秀", "rare": "稀有",
                    "epic": "史詩", "legendary": "傳說", "mythic": "神話"}
    
    my_class = class_names.get(my_hero.hero_class, my_hero.hero_class)
    my_rarity = rarity_names.get(my_hero.rarity, my_hero.rarity)
    target_class = class_names.get(target_hero.hero_class, target_hero.hero_class)
    target_rarity = rarity_names.get(target_hero.rarity, target_hero.rarity)
    
    await update.message.reply_text(
        f"⚔️ *發起 PvP 攻擊！*\n\n"
        f"🔵 你的英雄：#{my_hero.card_id}\n"
        f"   {my_rarity} {my_class}\n"
        f"   ⚔️{my_hero.atk} 🛡️{my_hero.def_} ⚡{my_hero.spd}\n\n"
        f"🔴 對手英雄：#{target_hero.card_id}\n"
        f"   {target_rarity} {target_class}\n"
        f"   ⚔️{target_hero.atk} 🛡️{target_hero.def_} ⚡{target_hero.spd}\n\n"
        f"💰 消耗：{pvp_cost} mana\n\n"
        f"⏳ 付費中...",
        parse_mode='Markdown'
    )
    
    try:
        # 取得下一個 DAA 決定勝負
        from hero_commands import get_next_daa_block
        event_daa, block_hash = await get_next_daa_block()
        
        await update.message.reply_text(
            f"🎲 命運區塊：`{block_hash[:16]}...`\n"
            f"📍 DAA: {event_daa}\n\n"
            f"⏳ 計算結果並發送鏈上事件...",
            parse_mode='Markdown'
        )
        
        # 處理鏈上 PvP
        result = await process_pvp_onchain(
            attacker=my_hero,
            defender=target_hero,
            attacker_user_id=user.id,
            attacker_pin=pin,
            block_hash=block_hash
        )
        
        # 取得對手用戶名
        from nami_kaspa_bot import load_users
        users = load_users()
        target_username = users.get(str(target_hero_data["owner_id"]), {}).get("username", "???")
        
        # 格式化結果
        if result["attacker_wins"]:
            result_emoji = "🏆"
            result_text = "勝利！"
            winner = my_hero
            loser = target_hero
            winner_name = user.username or str(user.id)
            loser_name = target_username
        else:
            result_emoji = "☠️"
            result_text = "落敗..."
            winner = target_hero
            loser = my_hero
            winner_name = target_username
            loser_name = user.username or str(user.id)
        
        winner_class = class_names.get(winner.hero_class, winner.hero_class)
        loser_class = class_names.get(loser.hero_class, loser.hero_class)
        
        # 格式化戰鬥詳情
        detail = result.get("battle_detail", {})
        
        # 稀有度加成說明
        rarity_mult = {
            "common": "x1.0", "uncommon": "x1.2", "rare": "x1.5",
            "epic": "x1.5", "legendary": "x2.0", "mythic": "x3.0"
        }
        my_mult = rarity_mult.get(my_hero.rarity, "x1.0")
        target_mult = rarity_mult.get(target_hero.rarity, "x1.0")
        
        rounds_text = ""
        for i, r in enumerate(detail.get("rounds", []), 1):
            if r["winner"] == "atk":
                r_result = "🔵"
            elif r["winner"] == "def":
                r_result = "🔴"
            else:
                r_result = "⚪"
            rounds_text += f"R{i} {r['name']}: {r['atk_val']} vs {r['def_val']} {r_result}\n"
        
        score = f"{detail.get('atk_wins', 0)}:{detail.get('def_wins', 0)}"
        
        msg = f"""{result_emoji} <b>PvP 結果：{result_text}</b>

🔵 <b>攻方</b> #{my_hero.card_id} ({my_rarity} {my_mult})
⚔️{my_hero.atk} 🛡️{my_hero.def_} ⚡{my_hero.spd}

🔴 <b>守方</b> #{target_hero.card_id} ({target_rarity} {target_mult})
⚔️{target_hero.atk} 🛡️{target_hero.def_} ⚡{target_hero.spd}

📊 <b>對決</b> (數值已含加成)
{rounds_text}
<b>比分: {score}</b> → {detail.get('final_reason', '')}

---

🏆 <b>勝者</b>：#{winner.card_id} {winner_class}
   @{winner_name} | 擊殺：{winner.kills}

☠️ <b>敗者</b>：#{loser.card_id} {loser_class}
   @{loser_name} | 永久死亡

📝 <b>鏈上記錄</b>：
付費: <code>{result['payment_tx'][:16]}...</code>"""
        
        if result.get("win_tx"):
            msg += f"\n勝利: <code>{result['win_tx'][:20]}...</code>"
        msg += f"\n死亡: <code>{result['death_tx'][:20]}...</code>"
        
        msg += f"\n\n🔗 <a href='https://explorer-tn10.kaspa.org/txs/{result['death_tx']}'>區塊瀏覽器</a>"
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
        # 群組公告（完整戰報）
        await announce_pvp_result(
            context.bot,
            result,
            my_hero,
            target_hero,
            attacker_name=user.username or str(user.id),
            defender_name=target_username
        )
        
        logger.info(f"⚔️ PvP 完成 | @{user.username} #{my_hero.card_id} vs #{target_hero.card_id} | {'勝利' if result['attacker_wins'] else '落敗'}")
        
    except Exception as e:
        logger.error(f"PvP error: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ PvP 失敗：{e}")

async def hero_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_history <ID> - 查看英雄歷史
    """
    if not context.args:
        await update.message.reply_text("用法：\n```\n/nami_history <英雄ID>\n```", parse_mode='Markdown')
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
        await update.message.reply_text("用法：\n```\n/nami_burn <英雄ID>\n```", parse_mode='Markdown')
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

async def hero_burn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_burn <ID> <PIN> - 銷毀英雄（不可逆！）
    """
    user = update.effective_user
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "🔥 *銷毀英雄*\n\n"
            "⚠️ 注意：銷毀不可逆！\n\n"
            "用法：\n"
            "```\n/nami_burn <英雄ID> <PIN>\n```",
            parse_mode='Markdown'
        )
        return
    
    try:
        hero_id = int(context.args[0])
        pin = context.args[1]
    except ValueError:
        await update.message.reply_text("❌ 無效的英雄 ID")
        return
    
    # 確認擁有權
    hero = get_hero_by_id(hero_id)
    if not hero:
        await update.message.reply_text("❌ 找不到此英雄")
        return
    
    if hero.owner_id != user.id:
        await update.message.reply_text("❌ 這不是你的英雄")
        return
    
    if hero.status == "dead":
        await update.message.reply_text("❌ 英雄已經死亡")
        return
    
    # 排隊系統
    queue_size = tree_queue.queue_size()
    if queue_size > 0:
        await update.message.reply_text(
            f"🔥 正在銷毀英雄 #{hero_id}...\n"
            f"⏳ 排隊等候 {queue_size} 人..."
        )
    else:
        await update.message.reply_text(
            f"🔥 正在銷毀英雄 #{hero_id}...\n"
            f"📝 建立死亡銘文中..."
        )
    
    await tree_queue.acquire(user.id)
    
    try:
        from hero_game import burn_hero
        result = await burn_hero(user.id, hero_id, pin)
        
        if result["success"]:
            tx_id = result["tx_id"]
            await update.message.reply_text(
                f"🔥 *英雄已銷毀*\n\n"
                f"英雄 ID: `#{hero_id}`\n"
                f"狀態: ☠️ 已死亡\n"
                f"原因: 銷毀 (burn)\n\n"
                f"📝 死亡銘文:\n"
                f"https://explorer-tn10.kaspa.org/txs/{tx_id}\n\n"
                f"驗證指令：\n"
                f"```\n/nami_verify {tx_id}\n```",
                parse_mode='Markdown'
            )
            logger.info(f"🔥 Burn 成功 | @{user.username or user.id} | #{hero_id}")
            
            # 群組公告
            await announce_hero_death(context.bot, hero, "burn", death_tx=tx_id)
        else:
            await update.message.reply_text(f"❌ 銷毀失敗：{result['error']}")
            
    except Exception as e:
        logger.error(f"Burn error: {e}")
        await update.message.reply_text(f"❌ 銷毀失敗：{e}")
    finally:
        tree_queue.release()


async def hero_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_verify <ID|TX> - 驗證英雄
    
    支援：
    - 英雄 ID (數字) → 本地驗證
    - TX ID (64 hex) → 鏈上完整驗證
    """
    if not context.args:
        await update.message.reply_text(
            "用法：\n"
            "```\n"
            "/nami_verify <英雄ID>  # 本地驗證\n"
            "/nami_verify <TX_ID>   # 鏈上完整驗證\n"
            "```",
            parse_mode='Markdown'
        )
        return
    
    arg = context.args[0]
    
    # 判斷是 TX ID 還是英雄 ID
    is_tx_id = len(arg) == 64 and all(c in '0123456789abcdef' for c in arg.lower())
    
    if is_tx_id:
        # 鏈上完整驗證
        await update.message.reply_text(f"🔍 正在從鏈上驗證...")
        
        try:
            from hero_game import verify_from_tx, format_tx_verify_result
            result = await verify_from_tx(arg.lower())
            await update.message.reply_text(
                format_tx_verify_result(result),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"TX verify error: {e}")
            await update.message.reply_text(f"❌ 驗證失敗：{e}")
    else:
        # 本地驗證（用英雄 ID）
        try:
            card_id = int(arg)
        except ValueError:
            await update.message.reply_text("❌ 無效的 ID（數字 = 英雄 ID，64 hex = TX ID）")
            return
        
        await update.message.reply_text(f"🔍 正在驗證英雄 #{card_id}...\n⏳ 追蹤鏈上記錄中...")
        
        try:
            from hero_game import verify_hero_by_id, format_hero_verify_result
            result = await verify_hero_by_id(card_id)
            await update.message.reply_text(
                format_hero_verify_result(result),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Verify error: {e}")
            await update.message.reply_text(f"❌ 驗證失敗：{e}")


async def hero_remint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_remint <ID> <PIN> - 補發鏈上銘文（給沒上鏈的英雄）
    
    只有卡主可以 remint 自己的卡
    """
    user = update.effective_user
    args = context.args
    
    if not args or len(args) < 2:
        await update.message.reply_text(
            "❌ 用法：`/nami_remint <英雄ID> <PIN>`\n\n"
            "為沒有鏈上記錄的英雄補發銘文",
            parse_mode='Markdown'
        )
        return
    
    try:
        hero_id = int(args[0])
        pin = args[1]
    except ValueError:
        await update.message.reply_text("❌ 英雄 ID 必須是數字")
        return
    
    try:
        from hero_game import load_heroes_db, save_heroes_db, create_birth_payload, Hero
        import unified_wallet
        
        db = load_heroes_db()
        hero_data = db.get("heroes", {}).get(str(hero_id))
        
        if not hero_data:
            await update.message.reply_text(f"❌ 找不到英雄 #{hero_id}")
            return
        
        # 檢查是否為卡主
        if hero_data.get("owner_id") != user.id:
            await update.message.reply_text("❌ 只有卡主可以 remint 自己的英雄")
            return
        
        # 檢查是否已有鏈上記錄
        if hero_data.get("tx_id") and hero_data.get("latest_tx"):
            await update.message.reply_text(
                f"✅ 英雄 #{hero_id} 已經有鏈上記錄了！\n"
                f"TX: `{hero_data['tx_id'][:32]}...`",
                parse_mode='Markdown'
            )
            return
        
        # 驗證 PIN
        if not unified_wallet.verify_pin(user.id, pin):
            await update.message.reply_text("❌ PIN 錯誤")
            return
        
        await update.message.reply_text(f"🔄 正在為英雄 #{hero_id} 補發鏈上銘文...")
        
        # 重建 Hero 物件
        hero = Hero(
            card_id=hero_data["card_id"],
            owner_id=hero_data["owner_id"],
            owner_address=hero_data["owner_address"],
            hero_class=hero_data["hero_class"],
            rarity=hero_data["rarity"],
            atk=hero_data["atk"],
            def_=hero_data["def"],
            spd=hero_data["spd"],
            status=hero_data.get("status", "alive"),
            latest_daa=hero_data.get("latest_daa", hero_data["card_id"])
        )
        
        # 建立 birth payload
        birth_payload = create_birth_payload(
            daa=hero_id,
            hero=hero,
            source_hash=hero_data.get("source_hash", "")
        )
        
        # 發送 inscription（不需要再付款，用 skip_payment）
        payment_tx_id, inscription_tx_id = await unified_wallet.mint_hero_inscription(
            user_id=user.id,
            pin=pin,
            hero_payload=birth_payload,
            skip_payment=True  # 已經付過了
        )
        
        # 更新資料庫
        db["heroes"][str(hero_id)]["tx_id"] = inscription_tx_id
        db["heroes"][str(hero_id)]["latest_tx"] = inscription_tx_id
        if payment_tx_id:
            db["heroes"][str(hero_id)]["payment_tx"] = payment_tx_id
        save_heroes_db(db)
        
        # 中文翻譯
        class_names = {"warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}
        rarity_names = {"common": "普通", "uncommon": "優秀", "rare": "稀有",
                        "epic": "史詩", "legendary": "傳說", "mythic": "神話"}
        class_zh = class_names.get(hero.hero_class, hero.hero_class)
        rarity_zh = rarity_names.get(hero.rarity, hero.rarity)
        
        await update.message.reply_text(
            f"✅ *Remint 成功！*\n\n"
            f"🎴 英雄 #{hero_id}\n"
            f"• 職業: {class_zh}\n"
            f"• 稀有度: {rarity_zh}\n\n"
            f"📝 Inscription TX:\n`{inscription_tx_id}`\n\n"
            f"現在可以用 `/nami_verify {hero_id}` 驗證了！",
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Remint 成功 | @{user.username} | #{hero_id} | TX: {inscription_tx_id[:16]}...")
        
    except Exception as e:
        logger.error(f"Remint error: {e}")
        await update.message.reply_text(f"❌ Remint 失敗：{e}")


async def next_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_next_reward - 查看下次獎勵發放時間
    """
    try:
        from kaspa import RpcClient
        import unified_wallet
        from hero_game import load_heroes_db
        
        # 取得當前 DAA
        client = RpcClient(url="ws://127.0.0.1:17210", network_id="testnet-10")
        await client.connect()
        try:
            info = await client.get_block_dag_info({})
            current_daa = info.get("virtualDaaScore", 0)
        finally:
            await client.disconnect()
        
        # 計算下一個 66666
        current_suffix = current_daa % 100000
        if current_suffix < 66666:
            next_trigger = current_daa - current_suffix + 66666
        else:
            next_trigger = current_daa - current_suffix + 166666
        
        remaining_daa = next_trigger - current_daa
        remaining_seconds = remaining_daa // 10  # ~10 DAA/秒
        remaining_minutes = remaining_seconds // 60
        remaining_hours = remaining_minutes // 60
        
        # 取得資料
        db = load_heroes_db()
        
        # 🌲 大地的祝福（召喚、PvP 等費用累積）
        mana_pool = db.get("total_mana_pool", 0)
        
        # 取得存活英雄數
        alive_count = sum(1 for h in db.get("heroes", {}).values() if h.get("status") == "alive")
        
        # 上次發放
        last_reward_daa = db.get("last_reward_daa", 0)
        
        if remaining_hours > 0:
            time_str = f"{remaining_hours}h {remaining_minutes % 60}m"
        else:
            time_str = f"{remaining_minutes}m"
        
        # 預估每位英雄獎勵
        per_hero = mana_pool / alive_count if alive_count > 0 else 0
        
        msg = f"""🌲 *下次獎勵發放*

📍 目前 DAA: `{current_daa}`
🎯 下次觸發: `{next_trigger}`
⏳ 剩餘: ~{time_str} ({remaining_daa:,} DAA)

💰 *🌲 大地的祝福*
累積: {mana_pool} mana
預估每位: ~{per_hero:.1f} mana

👥 存活英雄: {alive_count} 位
📊 上次發放: #{last_reward_daa or '尚未發放'}

*獎勵按積分分配給存活英雄！*
積分 = 存活天數 + 稀有度 + 擊殺×2"""

        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Next reward error: {e}")
        await update.message.reply_text(f"❌ 查詢失敗：{e}")


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
        await update.message.reply_text("用法：\n```\n/nami_payload <英雄ID>\n```", parse_mode='Markdown')
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
        await update.message.reply_text("用法：\n```\n/nami_decode <TX_ID>\n```", parse_mode='Markdown')
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
        await update.message.reply_text("用法：\n```\n/nami_decode_hex <payload_hex>\n```", parse_mode='Markdown')
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

PIN 為 4-6 位數字，會產生你專屬的英雄錢包地址。

⚠️ 重要：記住你的 PIN！忘記 PIN = 失去錢包！

用法：
<pre>/nami_hero_pin 1234</pre>"""
        
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
    app.add_handler(CommandHandler("nami_pvp", hero_attack))
    app.add_handler(CommandHandler("nami_burn", hero_burn))
    
    # 輔助指令
    app.add_handler(CommandHandler("nami_hero_info", hero_info))
    app.add_handler(CommandHandler("nami_search", hero_search))
    app.add_handler(CommandHandler("nami_history", hero_history))
    app.add_handler(CommandHandler("nami_verify", hero_verify))
    app.add_handler(CommandHandler("nami_remint", hero_remint))
    app.add_handler(CommandHandler("nami_rules", hero_rules))
    app.add_handler(CommandHandler("nami_game_status", hero_stats))
    app.add_handler(CommandHandler("nami_next_reward", next_reward))
    app.add_handler(CommandHandler("nami_payload", hero_payload))
    app.add_handler(CommandHandler("nami_decode", hero_decode))
    app.add_handler(CommandHandler("nami_decode_hex", hero_decode_hex))
    app.add_handler(CommandHandler("nami_hero_pin", hero_pin_setup))
    app.add_handler(CommandHandler("nami_hero_balance", hero_wallet_balance))
    
    logger.info("🌲 英雄遊戲指令已註冊")
