#!/usr/bin/env python3
"""
🌲 娜米的英雄奇幻冒險 - TG 指令處理
===================================
"""

import asyncio
import logging
import re
import time
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ═══════════════════════════════════════════════════════════════════════════════
# 🔒 v0.4 安全機制
# ═══════════════════════════════════════════════════════════════════════════════

# 管理員 ID（可以在維護模式下操作）
ADMIN_IDS = [5168530096]  # Ryan

# 維護模式（開啟時只有管理員能執行操作）
MAINTENANCE_MODE = False

# 全局錢包鎖（防止 UTXO 衝突）
WALLET_LOCK = asyncio.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# 🎛️ v0.4 待確認操作暫存（Inline Button 確認機制）
# ═══════════════════════════════════════════════════════════════════════════════

# 暫存待確認的操作，60 秒後過期
# 格式: {action_id: {user_id, action, hero_id, pin, created_at}}
PENDING_ACTIONS: dict[str, dict] = {}
PENDING_TIMEOUT = 60  # 秒


def create_pending_action(user_id: int, action: str, hero_id: int, pin: str) -> str:
    """建立待確認操作，返回 action_id"""
    action_id = uuid.uuid4().hex[:8]
    PENDING_ACTIONS[action_id] = {
        "user_id": user_id,
        "action": action,
        "hero_id": hero_id,
        "pin": pin,
        "created_at": time.time()
    }
    return action_id


def get_pending_action(action_id: str, user_id: int) -> dict | None:
    """取得待確認操作（驗證 user_id 和過期時間）"""
    action = PENDING_ACTIONS.get(action_id)
    if not action:
        return None
    
    # 驗證 user_id
    if action["user_id"] != user_id:
        return None
    
    # 檢查過期
    if time.time() - action["created_at"] > PENDING_TIMEOUT:
        del PENDING_ACTIONS[action_id]
        return None
    
    return action


def consume_pending_action(action_id: str) -> dict | None:
    """取出並刪除待確認操作"""
    return PENDING_ACTIONS.pop(action_id, None)


def cleanup_expired_actions():
    """清理過期的待確認操作"""
    now = time.time()
    expired = [k for k, v in PENDING_ACTIONS.items() 
               if now - v["created_at"] > PENDING_TIMEOUT]
    for k in expired:
        del PENDING_ACTIONS[k]

def is_admin(user_id: int) -> bool:
    """檢查是否為管理員"""
    return user_id in ADMIN_IDS

def check_maintenance(user_id: int) -> str | None:
    """
    檢查維護模式
    Returns: 錯誤訊息（如果被阻擋），None（如果可以繼續）
    """
    if MAINTENANCE_MODE and not is_admin(user_id):
        return "🛠️ 系統維護中，請稍後再試～"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 📲 回覆即操作 - 從回覆訊息中提取英雄 ID
# ═══════════════════════════════════════════════════════════════════════════════

def extract_hero_id_from_reply(update: Update) -> int | None:
    """
    從回覆的訊息中提取英雄 ID
    
    支援格式：
    - 🎴 英雄 #380849450
    - 英雄 ID: `#380849450`
    - /nami_verify 380849450
    
    Returns: 英雄 ID (int) 或 None
    """
    if not update.message or not update.message.reply_to_message:
        return None
    
    reply_text = update.message.reply_to_message.text or ""
    
    # 嘗試匹配 #xxxxxxxx 格式（最常見）
    match = re.search(r'#(\d{6,12})', reply_text)
    if match:
        return int(match.group(1))
    
    # 嘗試匹配純數字格式（如 /nami_verify 380849450）
    match = re.search(r'/nami_(?:verify|hero_info|burn|payload)\s+(\d{6,12})', reply_text)
    if match:
        return int(match.group(1))
    
    return None

async def with_wallet_lock(coro):
    """
    使用錢包鎖執行協程
    確保同一時間只有一個錢包操作
    """
    async with WALLET_LOCK:
        return await coro

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


async def send_announcement_photo(bot, photo, caption: str, parse_mode: str = 'Markdown'):
    """發送帶圖片的公告到群組"""
    chat_id = get_announcement_chat_id()
    if not chat_id:
        return
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"公告圖片發送失敗: {e}")

async def announce_hero_birth(bot, hero, username: str):
    """v0.3: 公告英雄誕生（星星格式）"""
    # v0.3 Rank 顯示
    rank = getattr(hero, 'rank', hero.rarity)
    rank_display = {
        "N": "⭐ N 普通", "R": "⭐⭐ R 稀有", "SR": "⭐⭐⭐ SR 超稀",
        "SSR": "💎⭐⭐⭐⭐ SSR 極稀", "UR": "✨⭐⭐⭐⭐⭐ UR 傳說", "LR": "🔱⭐⭐⭐⭐⭐⭐ LR 神話",
        # 向後相容
        "common": "⭐ N 普通", "uncommon": "⭐⭐ R 稀有", "rare": "⭐⭐⭐ SR 超稀",
        "epic": "💎⭐⭐⭐⭐ SSR 極稀", "legendary": "✨⭐⭐⭐⭐⭐ UR 傳說", "mythic": "🔱⭐⭐⭐⭐⭐⭐ LR 神話"
    }.get(rank, f"⭐ {rank}")
    
    class_name = {"knight": "騎士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}.get(hero.hero_class, "")
    class_emoji = {"knight": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}.get(hero.hero_class, "")
    
    # v0.3 特效標題
    header = ""
    if rank in ["LR", "mythic"]:
        header = "🔱🔱🔱 ⚡ 神話降世！⚡ 🔱🔱🔱\n\n"
    elif rank in ["UR", "legendary"]:
        header = "✨✨✨ 傳說降臨！✨✨✨\n\n"
    elif rank in ["SSR", "epic"]:
        header = "💎💎 極稀出現！💎💎\n\n"
    
    # 保護狀態
    protected_note = ""
    if getattr(hero, 'protected', False):
        protected_note = "🛡️ <b>已受大地之母保護</b>\n\n"
    
    # 取得區塊和銘文連結
    block_link = ""
    if hero.source_hash:
        block_link = f"🔗 命運區塊:\nhttps://explorer-tn10.kaspa.org/blocks/{hero.source_hash}"
    
    tx_link = ""
    if hero.tx_id and not hero.tx_id.startswith('daa_'):
        tx_link = f"📝 銘文:\nhttps://explorer-tn10.kaspa.org/txs/{hero.tx_id}"
    
    msg = f"""🎴 <b>召喚成功！</b>

{header}{rank_display} - {class_name} {class_emoji}
⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}

{protected_note}📍 命運: DAA <code>{hero.card_id}</code>
{block_link}
{tx_link}

👤 召喚者: @{username}
英雄 ID: <code>#{hero.card_id}</code>

快速指令：
<code>/nami_verify {hero.card_id}</code>"""
    
    await send_announcement(bot, msg, parse_mode='HTML')

async def announce_hero_death(bot, hero, reason: str, killer_name: str = None, death_tx: str = None):
    """v0.3: 公告英雄死亡（星星格式）"""
    # v0.3 Rank 顯示
    rank = getattr(hero, 'rank', hero.rarity)
    rank_display = {
        "N": "⭐ N", "R": "⭐⭐ R", "SR": "⭐⭐⭐ SR",
        "SSR": "💎 SSR", "UR": "✨ UR", "LR": "🔱 LR",
        "common": "⭐ N", "uncommon": "⭐⭐ R", "rare": "⭐⭐⭐ SR",
        "epic": "💎 SSR", "legendary": "✨ UR", "mythic": "🔱 LR"
    }.get(rank, f"⭐ {rank}")
    
    class_name = {"knight": "騎士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}.get(hero.hero_class, "")
    class_emoji = {"knight": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}.get(hero.hero_class, "")
    
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

{rank_display} - {class_name} {class_emoji}
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
    """v0.3: 公告完整 PvP 戰報到群聊（星星格式）"""
    
    # v0.3 Rank 顯示
    def get_rank_short(hero):
        rank = getattr(hero, 'rank', getattr(hero, 'rarity', 'N'))
        return {
            "N": "⭐N", "R": "⭐⭐R", "SR": "⭐⭐⭐SR",
            "SSR": "💎SSR", "UR": "✨UR", "LR": "🔱LR",
            "common": "⭐N", "uncommon": "⭐⭐R", "rare": "⭐⭐⭐SR",
            "epic": "💎SSR", "legendary": "✨UR", "mythic": "🔱LR"
        }.get(rank, f"⭐{rank}")
    
    class_names = {
        "knight": "騎士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"
    }
    rarity_mult = {
        "common": "x1.0", "uncommon": "x1.2", "rare": "x1.5",
        "epic": "x1.5", "legendary": "x2.0", "mythic": "x3.0"
    }
    
    # v0.3: 使用 Rank 顯示
    my_rank = get_rank_short(my_hero)
    target_rank = get_rank_short(target_hero)
    
    # Rank 加成倍率
    rank_mult = {
        "N": "x1.0", "R": "x1.2", "SR": "x1.5", "SSR": "x2.0", "UR": "x3.0", "LR": "x5.0",
        "common": "x1.0", "uncommon": "x1.1", "rare": "x1.2", "epic": "x1.5", "legendary": "x2.0", "mythic": "x3.0"
    }
    my_mult = rank_mult.get(getattr(my_hero, 'rank', my_hero.rarity), "x1.0")
    target_mult = rank_mult.get(getattr(target_hero, 'rank', target_hero.rarity), "x1.0")
    
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
    
    # 判斷敗者是否有保護
    loser_protected = result.get("defender_protected") if result["attacker_wins"] else result.get("attacker_protected")
    loser_fate = "🛡️ 受保護（免死）" if loser_protected else "永久死亡"
    loser_emoji = "🛡️" if loser_protected else "☠️"
    
    # 格式化戰鬥詳情（v0.4 ATB 系統）
    detail = result.get("battle_detail", {})
    
    # 檢查是否是 ATB 版本
    if detail.get("atb_version"):
        # v0.4 ATB 戰報
        battle_log = detail.get("battle_log", "")
        stats = detail.get("stats", {})
        loops = detail.get("loops", 0)
        is_draw = detail.get("draw", False)
        
        # 取戰報的最後幾行（精華部分）
        log_lines = battle_log.split("\n")
        # v0.4.1: 新格式以 🔵⚡ 或 🔴⚡ 開頭，也要抓樹枝行 ├─ └─
        battle_lines = [l for l in log_lines if 
                        l.startswith("🔵") or l.startswith("🔴") or 
                        l.startswith("├─") or l.startswith("└─") or
                        l.startswith("⚡") or l.startswith("🗡️") or 
                        l.startswith("🧙") or l.startswith("⚔️") or 
                        l.startswith("🏹") or l.startswith("💨") or l.startswith("🔥")]
        
        # v0.4.1: 完整戰報（純文字，4096 字元限制夠用）
        battle_summary = "\n".join(battle_lines)
        
        rounds_text = f"<pre>{battle_summary}</pre>" if battle_summary else ""
        score = f"回合:{loops} | 閃避:{stats.get('p1_evades',0)+stats.get('p2_evades',0)} | 大招:{stats.get('p1_skills',0)+stats.get('p2_skills',0)}"
    else:
        # 舊版三回合格式
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

🔵 <b>攻方</b> #{my_hero.card_id} ({my_rank} {my_mult})
HP:{getattr(my_hero, 'max_hp', 500)} ⚔️{my_hero.atk} 🛡️{my_hero.def_} ⚡{my_hero.spd}

🔴 <b>守方</b> #{target_hero.card_id} ({target_rank} {target_mult})
HP:{getattr(target_hero, 'max_hp', 500)} ⚔️{target_hero.atk} 🛡️{target_hero.def_} ⚡{target_hero.spd}

📊 <b>ATB 戰報</b>
{rounds_text}
<b>{score}</b>

---

🏆 <b>勝者</b>：#{winner.card_id} {winner_class}
   @{winner_name} | 擊殺：{winner.kills}

{loser_emoji} <b>敗者</b>：#{loser.card_id} {loser_class}
   @{loser_name} | {loser_fate}

📝 <b>鏈上記錄</b>：
付費: <code>{result['payment_tx'][:16]}...</code>"""
    
    if result.get("win_tx"):
        msg += f"\n勝利: <code>{result['win_tx'][:20]}...</code>"
    
    # 只有敗者真的死了才顯示死亡 TX
    if result.get("death_tx"):
        msg += f"\n死亡: <code>{result['death_tx'][:20]}...</code>"
        msg += f"\n\n🔗 <a href='https://explorer-tn10.kaspa.org/txs/{result['death_tx']}'>區塊瀏覽器</a>"
        msg += "\n\n<i>願靈魂回歸大地之樹...</i> 🌲"
    else:
        # 敗者有保護，沒死
        msg += "\n\n🛡️ <i>敗者受保護，免於死亡</i>"
    
    # v0.4.1: 暫時關閉圖片，純文字發送完整戰報（避免 caption 1024 字元限制）
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
    """
    等待下一個 DAA 的第一個官方區塊
    
    注意：DAA 不一定連續有區塊，所以找的是「大於 min_daa 的第一個區塊」
    """
    from kaspa import RpcClient
    
    client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
    await client.connect()
    
    try:
        # 取得當前 DAA
        info = await client.get_block_dag_info({})
        current_daa = info.get("virtualDaaScore", 0)
        target_daa = current_daa + 1
        
        logger.info(f"Waiting for DAA > {current_daa}...")
        
        # 等待新區塊
        for _ in range(30):  # 最多等 30 秒
            await asyncio.sleep(1)
            info = await client.get_block_dag_info({})
            new_daa = info.get("virtualDaaScore", 0)
            
            if new_daa > current_daa:
                return await _get_first_official_block(client, current_daa)
        
        raise TimeoutError("等待區塊超時")
        
    finally:
        await client.disconnect()


async def get_first_block_after_daa(min_daa: int, max_retries: int = 3) -> tuple[int, str]:
    """
    找到 DAA > min_daa 的第一個官方區塊
    
    用於驗證流程：payment_tx 確認後，找命運區塊
    包含重試機制：如果找不到區塊，等幾秒再試
    """
    from kaspa import RpcClient
    
    last_error = None
    
    for retry in range(max_retries):
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            # 等待 DAA 超過 min_daa
            for _ in range(60):  # 最多等 60 秒
                info = await client.get_block_dag_info({})
                current_daa = info.get("virtualDaaScore", 0)
                
                if current_daa > min_daa:
                    try:
                        return await _get_first_official_block(client, min_daa)
                    except Exception as e:
                        if "找不到 DAA" in str(e):
                            last_error = e
                            logger.warning(f"重試 {retry + 1}/{max_retries}: {e}")
                            break  # 跳出內層迴圈，進入重試
                        raise  # 其他錯誤直接拋出
                
                await asyncio.sleep(1)
            else:
                raise TimeoutError(f"等待 DAA > {min_daa} 超時")
            
            # 等 5 秒後重試
            await asyncio.sleep(5)
            
        finally:
            await client.disconnect()
    
    # 所有重試都失敗
    raise last_error or Exception(f"多次重試後仍找不到 DAA > {min_daa} 的區塊")


async def _get_first_official_block(client, min_daa: int) -> tuple[int, str]:
    """
    內部函數：找到 DAA > min_daa 的第一個官方區塊
    
    官方排序規則（來自 rusty-kaspa）：
    1. blueWork 大的優先
    2. blueWork 相同 → hash 字典序小的優先
    """
    info = await client.get_block_dag_info({})
    tips = info.get("tipHashes", [])
    
    # 收集所有 DAA > min_daa 的區塊
    candidate_blocks = []
    
    for tip in tips[:30]:
        try:
            block_resp = await client.get_block({"hash": tip, "includeTransactions": False})
            block = block_resp.get("block", {})
            header = block.get("header", {})
            block_daa = header.get("daaScore", 0)
            blue_work = header.get("blueWork", "0")
            
            if block_daa > min_daa:
                candidate_blocks.append({
                    "hash": tip,
                    "blueWork": blue_work,
                    "daaScore": block_daa
                })
        except:
            continue
    
    if not candidate_blocks:
        raise Exception(f"找不到 DAA > {min_daa} 的區塊")
    
    # 找最小 DAA 的區塊們（第一批）
    min_block_daa = min(b["daaScore"] for b in candidate_blocks)
    first_daa_blocks = [b for b in candidate_blocks if b["daaScore"] == min_block_daa]
    
    # 官方排序：blueWork↓, hash↑
    first_daa_blocks.sort(
        key=lambda b: (
            -int(b['blueWork'], 16) if isinstance(b['blueWork'], str) else -b['blueWork'],
            b['hash']
        )
    )
    
    first_block = first_daa_blocks[0]
    logger.info(f"Found first official block after DAA {min_daa}: DAA={first_block['daaScore']}, hash={first_block['hash'][:16]}...")
    
    return first_block['daaScore'], first_block['hash']


async def get_tx_confirmed_daa(tx_id: str, timeout: int = 60) -> int:
    """
    查詢 TX 被確認時的 DAA
    
    等待 TX 出現在區塊中，返回該區塊的 DAA
    """
    from kaspa import RpcClient
    
    client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
    await client.connect()
    
    try:
        for _ in range(timeout):
            try:
                # 嘗試取得 TX 所在的區塊
                # 注意：這需要 TX 已被包含在區塊中
                # Kaspa 的 get_transaction 會返回包含該 TX 的區塊資訊
                
                # 暫時用 virtual chain 的方式：等待幾秒後假設已確認
                # TODO: 用更精確的方式查詢 TX 所在區塊
                await asyncio.sleep(3)
                
                info = await client.get_block_dag_info({})
                current_daa = info.get("virtualDaaScore", 0)
                
                logger.info(f"TX {tx_id[:16]}... 假設已確認於 DAA ~{current_daa}")
                return current_daa
                
            except Exception as e:
                logger.warning(f"查詢 TX DAA 失敗: {e}")
                await asyncio.sleep(1)
        
        raise TimeoutError(f"等待 TX {tx_id} 確認超時")
        
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
    
    # v0.3: 維護模式檢查
    if msg := check_maintenance(user.id):
        await update.message.reply_text(msg)
        return
    
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
        class_names = {"knight": "騎士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}
        
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
    
    payment_tx_id = None  # 追蹤是否已付款（用於退款判斷）
    
    try:
        # ═══════════════════════════════════════════════════════════════════
        # 新流程：先付款，後取命運區塊（形成閉環驗證）
        # ═══════════════════════════════════════════════════════════════════
        
        # Step 1: 發送 payment_tx
        await update.message.reply_text("💰 發送付款交易...")
        
        import unified_wallet
        payment_tx_id = await unified_wallet.send_summon_payment(
            user_id=user.id,
            pin=pin
        )
        
        logger.info(f"Payment TX sent: {payment_tx_id}")
        
        # Step 2: 等待確認，取得 DAA
        await update.message.reply_text("⏳ 等待交易確認...")
        payment_daa = await get_tx_confirmed_daa(payment_tx_id)
        
        logger.info(f"Payment confirmed at DAA ~{payment_daa}")
        
        # Step 3: 找 payment_daa 之後的第一個官方區塊
        await update.message.reply_text("🎲 等待命運區塊...")
        daa, block_hash = await get_first_block_after_daa(payment_daa)
        
        logger.info(f"Fate block: DAA={daa}, hash={block_hash[:16]}...")
        
        # Step 4: 召喚英雄（用命運區塊計算屬性，發 inscription）
        hero = await summon_hero(
            user_id=user.id,
            username=user.username or str(user.id),
            address=address,
            daa=daa,
            block_hash=block_hash,
            pin=pin,
            payment_tx_id=payment_tx_id  # 傳入已完成的 payment_tx
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # Step 5: 驗證出生證明閉環（安全機制）
        # ═══════════════════════════════════════════════════════════════════
        await update.message.reply_text("🔍 驗證出生證明...")
        
        # 從 DB 讀取完整資料（包含 payment_tx）
        from hero_game import load_heroes_db
        db = load_heroes_db()
        hero_data = db.get("heroes", {}).get(str(hero.card_id), {})
        
        # 檢查必要欄位
        verification_ok = True
        verification_errors = []
        
        if not hero.source_hash:
            verification_ok = False
            verification_errors.append("缺少命運區塊 (source_hash)")
        if not hero_data.get("payment_tx"):
            verification_ok = False
            verification_errors.append("缺少付費證明 (payment_tx)")
        if not hero.tx_id:
            verification_ok = False
            verification_errors.append("缺少銘文交易 (inscription tx)")
        
        if not verification_ok:
            # 驗證失敗 - 刪除英雄並退款
            logger.error(f"❌ 出生驗證失敗 | #{hero.card_id} | {verification_errors}")
            
            # 從 DB 刪除這隻英雄
            from hero_game import save_heroes_db
            if str(hero.card_id) in db.get("heroes", {}):
                del db["heroes"][str(hero.card_id)]
                save_heroes_db(db)
            
            # 退款
            import unified_wallet
            try:
                refund_tx = await unified_wallet.refund_to_player(address, 10_00000000)
                await update.message.reply_text(
                    f"❌ 出生驗證失敗！\n"
                    f"原因：{', '.join(verification_errors)}\n\n"
                    f"💸 已退還 10 tKAS\n"
                    f"📦 退款 TX: `{refund_tx[:16]}...`",
                    parse_mode='Markdown'
                )
            except Exception as refund_err:
                await update.message.reply_text(
                    f"❌ 出生驗證失敗，退款也失敗了 😭\n"
                    f"請聯繫管理員處理\n"
                    f"Payment TX: `{payment_tx_id}`",
                    parse_mode='Markdown'
                )
            return
        
        # 驗證成功！
        last_summon_time = time.time()
        
        # Log: 召喚成功
        logger.info(f"✅ 召喚成功（已驗證）| @{user.username or user.id} | #{hero.card_id} {hero.display_rarity()} {hero.display_class()}")
        if hero.tx_id:
            logger.info(f"   📦 TX: {hero.tx_id}")
        
        # 回覆結果（帶職業圖片）
        try:
            from pathlib import Path
            
            # 使用 Ryan 的像素圖片
            hero_images_dir = Path.home() / "nami-backpack" / "projects" / "pixel-hero-stage"
            class_image_map = {
                "knight": "knight.png",
                "mage": "mage.png",
                "archer": "archer.png",
                "rogue": "rogue.png"
            }
            
            image_file = class_image_map.get(hero.hero_class)
            image_path = hero_images_dir / image_file if image_file else None
            
            if image_path and image_path.exists():
                await update.message.reply_photo(
                    photo=open(image_path, 'rb'),
                    caption=format_summon_result(hero),
                    parse_mode='Markdown'
                )
            else:
                # 備用：用舊的頭像生成
                from hero_avatar import generate_avatar_with_frame
                import io
                avatar_bytes = generate_avatar_with_frame(
                    block_hash=hero.source_hash,
                    rank=hero.rank,
                    hero_class=hero.hero_class,
                    size=64
                )
                await update.message.reply_photo(
                    photo=io.BytesIO(avatar_bytes),
                    caption=format_summon_result(hero),
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.warning(f"Hero image failed: {e}, fallback to text")
            await update.message.reply_text(format_summon_result(hero), parse_mode='Markdown')
        
        # 群組公告
        await announce_hero_birth(context.bot, hero, user.username or str(user.id))
        
        # v0.4.3: 新手保護 - 第一隻英雄自動設定保護
        from hero_game import get_protected_hero, set_hero_protection, load_heroes_db
        if not get_protected_hero(user.id):
            # 確認這是用戶的第一隻英雄
            db = load_heroes_db()
            user_heroes = [h for h in db.get("heroes", {}).values() 
                          if h.get("owner_id") == user.id and h.get("status") == "alive"]
            if len(user_heroes) == 1:  # 只有剛召喚的這隻
                success, _ = set_hero_protection(user.id, hero.card_id)
                if success:
                    await update.message.reply_text(
                        f"🛡️ *新手保護已啟用！*\n\n"
                        f"你的第一隻英雄已自動設定保護\n"
                        f"PvP 輸了不會死亡～\n\n"
                        f"之後更換保護需要 10 mana",
                        parse_mode='Markdown'
                    )
                    logger.info(f"🛡️ 新手保護 | @{user.username or user.id} | #{hero.card_id}")
        
    except TimeoutError as e:
        logger.warning(f"⏰ 召喚超時 | @{user.username or user.id}")
        # 如果已付款，嘗試退款
        if payment_tx_id:
            try:
                import unified_wallet
                refund_tx = await unified_wallet.refund_to_player(address, 10_00000000)
                logger.info(f"💸 退款成功 | @{user.username or user.id} | TX: {refund_tx}")
                await update.message.reply_text(
                    f"❌ 等待區塊超時\n💸 已退還 10 tKAS\n📦 TX: `{refund_tx[:16]}...`",
                    parse_mode='Markdown'
                )
            except Exception as refund_err:
                logger.error(f"退款失敗: {refund_err}")
                await update.message.reply_text(f"❌ 召喚超時，退款也失敗了 😭\n請聯繫管理員處理\nPayment TX: `{payment_tx_id}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ 等待區塊超時，請稍後再試")
    except Exception as e:
        logger.error(f"❌ 召喚失敗 | @{user.username or user.id} | {e}")
        # 如果已付款，嘗試退款
        if payment_tx_id:
            try:
                import unified_wallet
                refund_tx = await unified_wallet.refund_to_player(address, 10_00000000)
                logger.info(f"💸 退款成功 | @{user.username or user.id} | TX: {refund_tx}")
                await update.message.reply_text(
                    f"❌ 召喚失敗：{e}\n💸 已退還 10 tKAS\n📦 TX: `{refund_tx[:16]}...`",
                    parse_mode='Markdown'
                )
            except Exception as refund_err:
                logger.error(f"退款失敗: {refund_err}")
                await update.message.reply_text(f"❌ 召喚失敗，退款也失敗了 😭\n請聯繫管理員處理\nPayment TX: `{payment_tx_id}`", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ 召喚失敗：{e}")
    finally:
        # 釋放排隊
        tree_queue.release()

async def hero_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_heroes - 查看我的英雄（帶頭像）
    """
    user = update.effective_user
    heroes = get_user_heroes(user.id)
    
    # 嘗試生成英雄列表頭像
    alive_heroes = [h for h in heroes if h.status == "alive"]
    
    if alive_heroes:
        try:
            from hero_avatar import generate_avatar
            from PIL import Image
            import io
            
            # 每個頭像 16x16，最多顯示 10 個
            display_heroes = alive_heroes[:10]
            count = len(display_heroes)
            
            # 計算排列（最多 5 個一行）
            cols = min(count, 5)
            rows = (count + cols - 1) // cols
            
            # 創建拼接圖
            margin = 2
            cell_size = 16 + margin
            img_width = cols * cell_size + margin
            img_height = rows * cell_size + margin
            
            combined = Image.new('RGBA', (img_width, img_height), (30, 30, 35, 255))
            
            for i, hero in enumerate(display_heroes):
                if hero.source_hash:
                    avatar_bytes = generate_avatar(hero.source_hash, hero.rank, hero.hero_class, 16)
                    avatar = Image.open(io.BytesIO(avatar_bytes))
                    
                    col = i % cols
                    row = i // cols
                    x = margin + col * cell_size
                    y = margin + row * cell_size
                    
                    combined.paste(avatar, (x, y), avatar)
            
            # 轉換為 bytes
            buffer = io.BytesIO()
            combined.save(buffer, format='PNG')
            
            await update.message.reply_photo(
                photo=io.BytesIO(buffer.getvalue()),
                caption=format_hero_list(heroes),
                parse_mode='Markdown'
            )
            return
        except Exception as e:
            logger.warning(f"Hero list avatar failed: {e}")
    
    # Fallback: 純文字
    await update.message.reply_text(format_hero_list(heroes), parse_mode='Markdown')

SCOUT_COST = 10_00000000  # 偵查費用 10 mana

async def hero_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_hero_info <ID> [PIN] - 查看英雄詳情
    
    - 查看自己的英雄：免費
    - 查看別人的英雄：需要 10 mana + PIN（偵查費）
    
    支援回覆模式：回覆英雄訊息 + /ni
    """
    user = update.effective_user
    
    # 📲 回覆模式：從回覆訊息抓取英雄 ID
    reply_hero_id = extract_hero_id_from_reply(update)
    
    if not context.args and not reply_hero_id:
        await update.message.reply_text(
            "📜 *查看英雄詳情*\n\n"
            "查看自己的英雄（免費）：\n"
            "```\n/nami_hero_info <ID>\n```\n\n"
            "偵查敵方英雄（10 mana）：\n"
            "```\n/nami_hero_info <ID或名字> <PIN>\n```\n\n"
            "*📲 回覆模式：*\n"
            "回覆英雄訊息，只需輸入：\n"
            "```\n/ni\n```",
            parse_mode='Markdown'
        )
        return
    
    # 支援 ID 或名字查詢
    from hero_game import resolve_hero_id
    
    # 決定要查詢的英雄 ID
    if reply_hero_id and not context.args:
        # 純回覆模式：/ni（無參數）
        card_id = reply_hero_id
    elif reply_hero_id and len(context.args) == 1:
        # 回覆 + PIN 模式：/ni <PIN>（偵查敵方）
        # 先嘗試把參數當 PIN，用回覆的 ID
        card_id = reply_hero_id
    else:
        # 傳統模式
        identifier = context.args[0]
        card_id = resolve_hero_id(identifier)
    
    if card_id is None:
        identifier = context.args[0] if context.args else "（回覆訊息）"
        await update.message.reply_text(f"❌ 找不到英雄：{identifier}")
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
        # 判斷 PIN 來源（回覆模式 vs 傳統模式）
        pin = None
        if reply_hero_id and len(context.args) == 1:
            # 回覆模式：/ni <PIN>
            pin = context.args[0]
        elif len(context.args) >= 2:
            # 傳統模式：/ni <ID> <PIN>
            pin = context.args[1]
        
        if not pin:
            help_text = (
                f"🔍 *偵查敵方英雄*\n\n"
                f"英雄 `#{card_id}` 屬於其他玩家\n"
                f"偵查需要消耗 *10 mana*\n\n"
                f"確認偵查：\n"
                f"```\n/nami_hero_info {card_id} <你的PIN>\n```\n\n"
                f"*📲 回覆模式：*\n"
                f"回覆英雄訊息輸入：\n"
                f"```\n/ni <PIN>\n```"
            )
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
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
    
    # 看自己免費！直接顯示詳細列表
    is_self = (target_user_id == user.id)
    
    if is_self:
        rank_emojis = {"N": "⚪", "R": "🔵", "SR": "🟣", "SSR": "🟡"}
        class_emojis = {"knight": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}
        
        lines = [f"🔍 *我的英雄*\n"]
        
        if alive_heroes:
            lines.append("🟢 *存活：*")
            alive_heroes.sort(key=lambda x: x['atk'] + x['def'] + x['spd'], reverse=True)
            for h in alive_heroes:
                rank = h.get("rank", "N")
                rank_emoji = rank_emojis.get(rank, "⚪")
                c = class_emojis.get(h["hero_class"], "")
                total_power = h['atk'] + h['def'] + h['spd']
                protect_mark = "🛡️" if h.get("protected") else ""
                if total_power < 100:
                    power_hint = "💀"
                elif total_power < 150:
                    power_hint = ""
                elif total_power < 200:
                    power_hint = "💪"
                else:
                    power_hint = "👑"
                name_str = f'「{h["name"]}」' if h.get("name") else ""
                lines.append(f"  `#{h['card_id']}` {rank_emoji}{rank}{c} {protect_mark}⚔️{h['atk']} 🛡️{h['def']} ⚡{h['spd']} {power_hint}{name_str}")
        
        if dead_heroes:
            lines.append("\n☠️ *陣亡：*")
            for h in dead_heroes[:5]:
                rank = h.get("rank", "N")
                rank_emoji = rank_emojis.get(rank, "⚪")
                c = class_emojis.get(h["hero_class"], "")
                lines.append(f"  `#{h['card_id']}` {rank_emoji}{rank}{c}")
            if len(dead_heroes) > 5:
                lines.append(f"  _...還有 {len(dead_heroes)-5} 隻_")
        
        if not alive_heroes and not dead_heroes:
            lines.append("_還沒有任何英雄～_")
        
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
        return
    
    # 看別人：免費只顯示數量
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
    
    # v0.3: 排隊機制
    queue_size = tree_queue.queue_size()
    if queue_size > 0:
        await update.message.reply_text(f"⏳ 大地之樹忙碌中，排隊等候 {queue_size} 人...")
    
    await tree_queue.acquire(user.id)
    
    try:
        # 檢查餘額
        balance = await get_hero_balance(address)
        if balance < SCOUT_COST:
            need = (SCOUT_COST - balance) / 1e8
            await update.message.reply_text(f"❌ 餘額不足！需要 10 mana，還差 {need:.2f}")
            return
        
        # 扣款
        import unified_wallet
        tx_id = await unified_wallet.send_to_tree(user.id, pin, SCOUT_COST, f"search:{target_username}")
        
        # 格式化英雄列表
        rank_emojis = {"N": "⚪", "R": "🔵", "SR": "🟣", "SSR": "🟡"}
        class_emojis = {"knight": "⚔️", "mage": "🧙", "rogue": "🗡️", "archer": "🏹"}
        
        lines = [f"🔍 *@{target_username} 的英雄*\n"]
        lines.append(f"💰 偵查費：10 mana | TX: `{tx_id[:12]}...`\n")
        
        if alive_heroes:
            lines.append("🟢 *存活：*")
            # 按戰力排序（ATK+DEF+SPD）
            alive_heroes.sort(key=lambda x: x['atk'] + x['def'] + x['spd'], reverse=True)
            for h in alive_heroes:
                rank = h.get("rank", "N")
                rank_emoji = rank_emojis.get(rank, "⚪")
                c = class_emojis.get(h["hero_class"], "")
                total_power = h['atk'] + h['def'] + h['spd']
                
                # 保護狀態
                protect_mark = "🛡️" if h.get("protected") else ""
                
                # 戰力評估
                if total_power < 100:
                    power_hint = "💀"  # 弱雞
                elif total_power < 150:
                    power_hint = ""
                elif total_power < 200:
                    power_hint = "💪"  # 強
                else:
                    power_hint = "👑"  # 超強
                
                name_str = f'「{h["name"]}」' if h.get("name") else ""
                lines.append(f"  `#{h['card_id']}` {rank_emoji}{rank}{c} {protect_mark}⚔️{h['atk']} 🛡️{h['def']} ⚡{h['spd']} {power_hint}{name_str}")
        
        if dead_heroes:
            lines.append("\n☠️ *陣亡：*")
            for h in dead_heroes[:5]:  # 最多顯示 5 隻
                rank = h.get("rank", "N")
                rank_emoji = rank_emojis.get(rank, "⚪")
                c = class_emojis.get(h["hero_class"], "")
                lines.append(f"  `#{h['card_id']}` {rank_emoji}{rank}{c}")
            if len(dead_heroes) > 5:
                lines.append(f"  _...還有 {len(dead_heroes)-5} 隻_")
        
        # 戰術提示
        lines.append("\n📊 *圖例：* 💀弱 💪強 👑超強 🛡️保護中")
        
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
    
    except Exception as e:
        await update.message.reply_text(f"❌ 偵查失敗：{e}")
    finally:
        tree_queue.release()

async def hero_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_pvp <我的ID/名字> <對手ID/名字> <PIN> - 發起 PvP 攻擊
    
    v0.4 新增：
    - 📲 回覆模式：回覆對方英雄訊息 + /np <PIN>（用保護角色攻擊）
    - 📲 回覆模式：回覆對方英雄訊息 + /np <我的英雄> <PIN>
    - 🎛️ 確認按鈕：防止手滑
    
    鏈上 PvP 流程：
    1. 驗證雙方英雄存活
    2. 付費給大地之樹
    3. 等待命運區塊決定勝負
    4. 發送鏈上事件
    """
    user = update.effective_user
    chat = update.effective_chat
    
    # v0.4: 維護模式檢查
    if msg := check_maintenance(user.id):
        await update.message.reply_text(msg)
        return
    
    chat_info = f"[{chat.type}:{chat.id}]" if chat.type != "private" else "[私聊]"
    logger.info(f"⚔️ PvP 請求 | {chat_info} @{user.username or user.id} | args: {len(context.args or [])}")
    
    # 📲 回覆模式：從回覆訊息抓取對方英雄 ID
    reply_target_id = extract_hero_id_from_reply(update)
    
    from hero_game import load_heroes_db, Hero, PVP_COST, get_protected_hero
    db = load_heroes_db()
    
    # 解析英雄 ID（支援數字或名字）
    def resolve_hero_id_local(arg: str, owner_id: int = None) -> int | None:
        """解析英雄 ID，支援數字 ID 或名字查找"""
        # 先試數字
        try:
            return int(arg)
        except ValueError:
            pass
        # 用名字查找
        arg_lower = arg.lower()
        for hero_id, hero_data in db.get("heroes", {}).items():
            if hero_data.get("name", "").lower() == arg_lower:
                # 如果指定 owner_id，只找自己的英雄
                if owner_id is None or hero_data.get("owner_id") == owner_id:
                    return int(hero_id)
        return None
    
    # ═══════════════════════════════════════════════════════════════════════
    # v0.4: 多種輸入模式解析
    # ═══════════════════════════════════════════════════════════════════════
    my_hero_id = None
    target_hero_id = None
    pin = None
    
    if reply_target_id and len(context.args) == 1:
        # 📲 回覆模式 A：/np <PIN>（用保護角色攻擊）
        target_hero_id = reply_target_id
        pin = context.args[0]
        # 取得保護角色
        protected = get_protected_hero(user.id)
        if protected and protected.get("status") == "alive":
            my_hero_id = protected.get("card_id")
        else:
            await update.message.reply_text(
                "❌ 你沒有設定保護英雄，或保護英雄已死亡\n\n"
                "請用完整格式：`/np <你的英雄> <PIN>`\n"
                "或先設定保護英雄：`/nhp <英雄ID>`",
                parse_mode='Markdown'
            )
            return
    elif reply_target_id and len(context.args) == 2:
        # 📲 回覆模式 B：/np <我的英雄> <PIN>
        target_hero_id = reply_target_id
        my_hero_id = resolve_hero_id_local(context.args[0], owner_id=user.id)
        pin = context.args[1]
        if my_hero_id is None:
            await update.message.reply_text(f"❌ 找不到你的英雄：{context.args[0]}")
            return
    elif len(context.args) >= 3:
        # 傳統模式：/np <我的英雄> <對手英雄> <PIN>
        my_hero_id = resolve_hero_id_local(context.args[0], owner_id=user.id)
        target_hero_id = resolve_hero_id_local(context.args[1])
        pin = context.args[2]
        if my_hero_id is None:
            await update.message.reply_text(f"❌ 找不到你的英雄：{context.args[0]}")
            return
        if target_hero_id is None:
            await update.message.reply_text(f"❌ 找不到對手英雄：{context.args[1]}")
            return
    else:
        # 顯示用法
        protected = get_protected_hero(user.id)
        protect_hint = ""
        if protected and protected.get("status") == "alive":
            pname = protected.get("name") or f"#{protected.get('card_id')}"
            protect_hint = f"\n🛡️ 你的保護英雄：*{pname}*\n"
        
        await update.message.reply_text(
            "⚔️ *PvP 攻擊*\n\n"
            "*傳統用法：*\n"
            "```\n/np <我的英雄> <對手英雄> <PIN>\n```\n\n"
            "*📲 回覆模式：*\n"
            "回覆對方英雄訊息：\n"
            "```\n/np <PIN>           # 用保護角色\n"
            "/np <我的英雄> <PIN>  # 指定英雄\n```"
            f"{protect_hint}\n"
            "⚠️ 敗者永久死亡！",
            parse_mode='Markdown'
        )
        return
    
    # 不能攻擊自己的英雄
    if my_hero_id == target_hero_id:
        await update.message.reply_text("❌ 不能攻擊自己的英雄！")
        return
    
    # 取得雙方英雄資料
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
    
    # 驗證雙方都是正卡（有完整閉環驗證）
    if not my_hero_data.get("source_hash") or not my_hero_data.get("payment_tx"):
        await update.message.reply_text(f"❌ 你的英雄 #{my_hero_id} 不是正卡（缺少出生證明）")
        return
    if not target_hero_data.get("source_hash") or not target_hero_data.get("payment_tx"):
        await update.message.reply_text(f"❌ 對手英雄 #{target_hero_id} 不是正卡（缺少出生證明）")
        return
    
    # 驗證 PIN
    import unified_wallet
    if not unified_wallet.verify_pin(user.id, pin):
        await update.message.reply_text("❌ PIN 錯誤")
        return
    
    # 建立 Hero 物件
    my_hero = Hero.from_dict(my_hero_data)
    target_hero = Hero.from_dict(target_hero_data)
    
    # 中文翻譯
    class_names = {"knight": "騎士", "mage": "法師", "rogue": "盜賊", "priest": "牧師"}
    
    my_class = class_names.get(my_hero.hero_class, my_hero.hero_class)
    target_class = class_names.get(target_hero.hero_class, target_hero.hero_class)
    my_name = my_hero.name if my_hero.name else f"#{my_hero.card_id}"
    target_name = target_hero.name if target_hero.name else f"#{target_hero.card_id}"
    
    # 保護狀態
    my_protected = "🛡️" if getattr(my_hero, 'protected', False) else ""
    target_protected = "🛡️" if getattr(target_hero, 'protected', False) else ""
    
    # v0.4: 建立待確認操作
    action_id = create_pending_action(user.id, "pvp", my_hero_id, pin)
    # 額外存對手資訊
    PENDING_ACTIONS[action_id]["target_hero_id"] = target_hero_id
    
    confirm_text = (
        f"⚔️ *確認發起 PvP？*\n\n"
        f"🔵 *你的英雄*：{my_name} {my_protected}\n"
        f"   {my_hero.rarity} {my_class}\n"
        f"   ⚔️{my_hero.atk} 🛡️{my_hero.def_} ⚡{my_hero.spd}\n\n"
        f"🔴 *對手英雄*：{target_name} {target_protected}\n"
        f"   {target_hero.rarity} {target_class}\n"
        f"   ⚔️{target_hero.atk} 🛡️{target_hero.def_} ⚡{target_hero.spd}\n\n"
        f"💰 消耗：*{PVP_COST} mana*\n"
        f"⚠️ 敗者永久死亡！\n\n"
        f"⏱️ 60 秒內有效"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ 確認出戰", callback_data=f"pvp_yes:{action_id}"),
            InlineKeyboardButton("❌ 取消", callback_data=f"pvp_no:{action_id}")
        ]
    ])
    
    await update.message.reply_text(confirm_text, parse_mode='Markdown', reply_markup=keyboard)


async def execute_pvp(user, my_hero_id: int, target_hero_id: int, pin: str, 
                      edit_message=None, context=None):
    """
    執行 PvP 的核心邏輯（供 callback handler 調用）
    """
    from hero_game import load_heroes_db, Hero, PVP_COST, process_pvp_onchain
    
    db = load_heroes_db()
    my_hero_data = db.get("heroes", {}).get(str(my_hero_id))
    target_hero_data = db.get("heroes", {}).get(str(target_hero_id))
    
    if not my_hero_data or not target_hero_data:
        if edit_message:
            await edit_message("❌ 找不到英雄資料")
        return
    
    my_hero = Hero.from_dict(my_hero_data)
    target_hero = Hero.from_dict(target_hero_data)
    
    # 中文翻譯
    class_names = {"knight": "騎士", "mage": "法師", "rogue": "盜賊", "priest": "牧師"}
    rarity_names = {"common": "普通", "uncommon": "優秀", "rare": "稀有",
                    "epic": "史詩", "legendary": "傳說", "mythic": "神話",
                    "N": "普通", "R": "稀有", "SR": "史詩", "SSR": "傳說"}
    
    my_class = class_names.get(my_hero.hero_class, my_hero.hero_class)
    my_rarity = rarity_names.get(my_hero.rarity, my_hero.rarity)
    target_class = class_names.get(target_hero.hero_class, target_hero.hero_class)
    target_rarity = rarity_names.get(target_hero.rarity, target_hero.rarity)
    
    # 排隊系統
    await tree_queue.acquire(user.id)
    
    try:
        # 取得下一個 DAA 決定勝負
        from hero_commands import get_next_daa_block
        event_daa, block_hash = await get_next_daa_block()
        
        if edit_message:
            await edit_message(
                f"🎲 命運區塊：`{block_hash[:16]}...`\n"
                f"📍 DAA: {event_daa}\n\n"
                f"⏳ 計算結果並發送鏈上事件..."
            )
        
        # 處理鏈上 PvP
        from hero_game import process_pvp_onchain
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
        
        # 判斷敗者是否有保護
        loser_protected = result.get("defender_protected") if result["attacker_wins"] else result.get("attacker_protected")
        loser_fate = "🛡️ 受保護（免死）" if loser_protected else "永久死亡"
        loser_emoji = "🛡️" if loser_protected else "☠️"
        
        # 格式化戰鬥詳情
        detail = result.get("battle_detail", {})
        
        # 稀有度加成說明
        rarity_mult = {
            "common": "x1.0", "uncommon": "x1.2", "rare": "x1.5",
            "epic": "x1.5", "legendary": "x2.0", "mythic": "x3.0",
            "N": "x1.0", "R": "x1.2", "SR": "x1.5", "SSR": "x2.0"
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
        
        # 更新訊息為結果
        short_msg = f"{result_emoji} PvP {result_text}\n#{my_hero.card_id} vs #{target_hero.card_id}\n比分: {score}"
        if edit_message:
            await edit_message(short_msg)
        
        # 群組公告（完整戰報）
        if context:
            await announce_pvp_result(
                context.bot,
                result,
                my_hero,
                target_hero,
                attacker_name=user.username or str(user.id),
                defender_name=target_username
            )
        
        logger.info(f"⚔️ PvP 完成 | @{user.username} #{my_hero.card_id} vs #{target_hero.card_id} | {result_text}")
        
    except Exception as e:
        logger.error(f"PvP error: {e}")
        import traceback
        traceback.print_exc()
        if edit_message:
            await edit_message(f"❌ PvP 失敗：{e}")
    finally:
        tree_queue.release()


async def handle_pvp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    處理 PvP 確認按鈕的 callback
    """
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    data = query.data
    
    parts = data.split(":")
    if len(parts) != 2:
        await query.edit_message_text("❌ 無效的操作")
        return
    
    action_type, action_id = parts
    
    if action_type == "pvp_no":
        # 取消操作
        consume_pending_action(action_id)
        await query.edit_message_text("❌ 已取消 PvP")
        return
    
    if action_type == "pvp_yes":
        # 確認 PvP
        action = get_pending_action(action_id, user.id)
        
        if not action:
            await query.edit_message_text("❌ 操作已過期或無效\n請重新執行 /np 指令")
            return
        
        # 取出並刪除操作
        action = consume_pending_action(action_id)
        if not action:
            await query.edit_message_text("❌ 操作已處理")
            return
        
        my_hero_id = action["hero_id"]
        target_hero_id = action["target_hero_id"]
        pin = action["pin"]
        
        # 更新訊息為處理中
        await query.edit_message_text(
            f"⚔️ 正在發起 PvP...\n"
            f"#{my_hero_id} vs #{target_hero_id}\n\n"
            f"⏳ 付費中..."
        )
        
        # 執行 PvP
        async def edit_msg(text):
            await query.edit_message_text(text)
        
        await execute_pvp(
            user=user,
            my_hero_id=my_hero_id,
            target_hero_id=target_hero_id,
            pin=pin,
            edit_message=edit_msg,
            context=context
        )

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

async def hero_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /help - 快速指令列表
    """
    help_text = """🌊 *娜米的英雄奇幻冒險*

*📜 指令（完整 / 縮寫）*

🎴 *召喚 & 管理*
`/nami_hero` `/nh` - 召喚英雄
`/nami_heroes` `/nhs` - 我的英雄
`/nami_hero_info` `/ni` - 英雄詳情
`/nami_name` `/nn` - 命名英雄
`/nami_burn` `/nb` - 銷毀英雄

⚔️ *戰鬥*
`/nami_pvp` `/np` - PvP 攻擊

🔍 *查詢 & 偵查*
`/nami_search` `/nse` - 偵查敵人（10 mana）
`/nami_verify` `/nv` - 驗證出生證明
`/nami_next_reward` `/nr` - 下次獎勵
`/nami_game_status` `/ns` - 遊戲狀態

📖 *完整規則*
`/nami_rules` - 詳細遊戲說明

━━━━━━━━━━━━━━━━
💡 支援 ID 或名字：
`/np sky 380344861 1234`"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def hero_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_rules - 查看遊戲規則
    """
    rules = """🌲 *娜米的英雄奇幻冒險*
_在區塊鏈的盡頭，大地之樹守護著英雄們的命運_

━━━━━━━━━━━

*💰 費用*
🌟 召喚英雄：10 mana
⚔️ PvP 攻擊：10 mana
🔥 銷毀英雄：10 mana

*🏆 Rank 系統*
⚪ N (普通) 70%
🔵 R (稀有) 20%
🟣 SR (超稀有) 8%
🟡 SSR (傳說) 2%

*⚔️ 職業與大招*
⚔️ 騎士 — 衝擊之暈（減敵方雙條）
🧙 法師 — 流星雨（ATK ×2.5 傷害）
🗡️ 盜賊 — 幻影（閃避 + 背刺反擊）
🏹 弓手 — 穿透射擊（傷害 + 暈眩）

*🎮 ATB 戰鬥*
• 移動條滿 → 普通攻擊
• 技能條滿 → 發動大招
• ⚡ Combo 連擊加成
• ⚠️ 爆發模式（HP < 30%）
• 敗者永久死亡 ☠️

*🔗 鏈上驗證*
• 每個英雄都有出生證明
• payment\_tx → DAA → 命運區塊 → 屬性
• 任何人可用 `/nv` 驗證，無法作弊

*🌲 大地祝福（積分獎勵）*
• DAA 結尾 66666 發放獎勵
• 積分 = 存活天數 + 稀有度 + 擊殺×2
• 只有活著的英雄才能獲得祝福！

*📋 常用指令*
`/nh` 召喚 | `/nhs` 列表 | `/np` PvP
`/nb` 銷毀 | `/nv` 驗證 | `/nn` 改名

━━━━━━━━━━━
_Alive to Earn 🌊_"""
    
    await update.message.reply_text(rules, parse_mode='Markdown')

async def hero_burn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_burn <ID> <PIN> - 銷毀英雄（不可逆！）
    
    v0.4: 顯示確認按鈕，防止手滑
    支援回覆模式：回覆英雄訊息 + /nb <PIN>
    """
    user = update.effective_user
    
    # v0.4: 維護模式檢查
    if msg := check_maintenance(user.id):
        await update.message.reply_text(msg)
        return
    
    # 📲 回覆模式：從回覆訊息抓取英雄 ID
    reply_hero_id = extract_hero_id_from_reply(update)
    
    if reply_hero_id and len(context.args) == 1:
        # 回覆模式：/nb <PIN>
        hero_id = reply_hero_id
        pin = context.args[0]
    elif len(context.args) >= 2:
        # 傳統模式：/nb <ID> <PIN>
        try:
            hero_id = int(context.args[0])
            pin = context.args[1]
        except ValueError:
            await update.message.reply_text("❌ 無效的英雄 ID")
            return
    else:
        # 顯示用法
        help_text = (
            "🔥 *銷毀英雄*\n\n"
            "⚠️ 注意：銷毀不可逆！\n\n"
            "*用法：*\n"
            "```\n/nami_burn <英雄ID> <PIN>\n```\n\n"
            "*📲 回覆模式：*\n"
            "回覆英雄訊息，只需輸入：\n"
            "```\n/nb <PIN>\n```"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
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
    
    # v0.4: 驗證 PIN（提前驗證，避免按確認後才報錯）
    if not verify_hero_pin(user.id, pin):
        await update.message.reply_text("❌ PIN 錯誤")
        return
    
    # v0.4: 建立待確認操作
    action_id = create_pending_action(user.id, "burn", hero_id, pin)
    
    # 顯示英雄資訊
    rarity_emoji = {"N": "⭐", "R": "⭐⭐", "SR": "⭐⭐⭐", "SSR": "🌟🌟🌟🌟"}.get(hero.rarity, "⭐")
    class_name = {"knight": "騎士", "mage": "法師", "rogue": "盜賊", "priest": "牧師"}.get(hero.hero_class, hero.hero_class)
    hero_name = hero.name if hero.name else f"#{hero_id}"
    
    confirm_text = (
        f"⚠️ *確認銷毀英雄？*\n\n"
        f"🎴 *{hero_name}*\n"
        f"{rarity_emoji} {hero.rarity} {class_name}\n"
        f"⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}\n\n"
        f"🔥 銷毀後無法復原！\n"
        f"💰 需支付 *10 mana* 刻上死亡銘文\n\n"
        f"⏱️ 60 秒內有效"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 確認銷毀", callback_data=f"burn_yes:{action_id}"),
            InlineKeyboardButton("❌ 取消", callback_data=f"burn_no:{action_id}")
        ]
    ])
    
    await update.message.reply_text(confirm_text, parse_mode='Markdown', reply_markup=keyboard)


async def handle_burn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    處理銷毀確認按鈕的 callback
    """
    query = update.callback_query
    await query.answer()  # 先回應 callback，避免按鈕轉圈
    
    user = query.from_user
    data = query.data  # burn_yes:action_id 或 burn_no:action_id
    
    parts = data.split(":")
    if len(parts) != 2:
        await query.edit_message_text("❌ 無效的操作")
        return
    
    action_type, action_id = parts
    
    if action_type == "burn_no":
        # 取消操作
        consume_pending_action(action_id)
        await query.edit_message_text("❌ 已取消銷毀")
        return
    
    if action_type == "burn_yes":
        # 確認銷毀
        action = get_pending_action(action_id, user.id)
        
        if not action:
            await query.edit_message_text("❌ 操作已過期或無效\n請重新執行 /nb 指令")
            return
        
        # 取出並刪除操作（防止重複點擊）
        action = consume_pending_action(action_id)
        if not action:
            await query.edit_message_text("❌ 操作已處理")
            return
        
        hero_id = action["hero_id"]
        pin = action["pin"]
        
        # 更新訊息為處理中
        await query.edit_message_text(
            f"🔥 正在銷毀英雄 #{hero_id}...\n"
            f"📝 建立死亡銘文中..."
        )
        
        # 排隊系統
        await tree_queue.acquire(user.id)
        
        try:
            from hero_game import burn_hero
            result = await burn_hero(user.id, hero_id, pin)
            
            if result["success"]:
                tx_id = result["tx_id"]
                await query.edit_message_text(
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
                hero = get_hero_by_id(hero_id)
                if hero:
                    await announce_hero_death(context.bot, hero, "burn", death_tx=tx_id)
            else:
                await query.edit_message_text(f"❌ 銷毀失敗：{result['error']}")
                
        except Exception as e:
            logger.error(f"Burn callback error: {e}")
            await query.edit_message_text(f"❌ 銷毀失敗：{e}")
        finally:
            tree_queue.release()


async def hero_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_verify <ID|TX> - 驗證英雄
    
    支援：
    - 英雄 ID (數字) → 本地驗證
    - TX ID (64 hex) → 鏈上完整驗證
    
    支援回覆模式：回覆英雄訊息 + /nv
    """
    # 📲 回覆模式：從回覆訊息抓取英雄 ID
    reply_hero_id = extract_hero_id_from_reply(update)
    
    if not context.args and not reply_hero_id:
        await update.message.reply_text(
            "用法：\n"
            "```\n"
            "/nami_verify <英雄ID>  # 本地驗證\n"
            "/nami_verify <TX_ID>   # 鏈上完整驗證\n"
            "```\n\n"
            "*📲 回覆模式：*\n"
            "回覆英雄訊息，只需輸入：\n"
            "```\n/nv\n```",
            parse_mode='Markdown'
        )
        return
    
    # 決定要驗證的目標
    if reply_hero_id and not context.args:
        # 回覆模式：用回覆訊息的英雄 ID
        arg = str(reply_hero_id)
    else:
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
        # 本地驗證（用英雄 ID 或別名）
        try:
            card_id = int(arg)
        except ValueError:
            # 嘗試用別名查找
            from hero_game import load_heroes_db
            db = load_heroes_db()
            found = None
            search_name = arg.lower()
            for hid, hero in db.get("heroes", {}).items():
                hero_name = hero.get("name", "").lower()
                if hero_name and search_name in hero_name:
                    found = int(hid)
                    break
            
            if found:
                card_id = found
            else:
                await update.message.reply_text("❌ 無效的 ID（數字 = 英雄 ID，64 hex = TX ID，或英雄名字）")
                return
        
        await update.message.reply_text(f"🔍 正在驗證英雄 #{card_id}...")
        
        try:
            # 優先使用本地銘文記錄驗證（快速、可靠）
            from inscription_store import verify_chain_integrity, format_chain_summary, get_hero_chain
            
            chain = get_hero_chain(card_id)
            if chain:
                # 有本地記錄，使用本地驗證
                result = verify_chain_integrity(card_id)
                summary = format_chain_summary(card_id)
                
                # 格式化輸出
                if result["verified"]:
                    status = "✅ 驗證通過\n🎉 *正卡*"
                else:
                    status = "❌ 驗證失敗"
                
                msg = f"🔍 *驗證英雄 #{card_id}*\n\n"
                msg += f"```\n{summary}\n```\n\n"
                msg += f"*狀態*: {status}\n"
                msg += f"*鏈條長度*: {result['chain_length']} 個銘文"
                
                if result["errors"]:
                    msg += "\n\n*錯誤*:\n"
                    for err in result["errors"]:
                        msg += f"• {err}\n"
                
                # 嘗試顯示英雄頭像
                hero = get_hero_by_id(card_id)
                if hero and hero.source_hash:
                    try:
                        from hero_avatar import generate_avatar_with_frame
                        import io
                        avatar_bytes = generate_avatar_with_frame(
                            hero.source_hash, hero.rank, hero.hero_class, 64
                        )
                        await update.message.reply_photo(
                            photo=io.BytesIO(avatar_bytes),
                            caption=msg,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.warning(f"Avatar in verify failed: {e}")
                        await update.message.reply_text(msg, parse_mode='Markdown')
                else:
                    await update.message.reply_text(msg, parse_mode='Markdown')
            else:
                # 沒有本地記錄，嘗試鏈上驗證（可能超時）
                await update.message.reply_text("⏳ 本地無記錄，嘗試鏈上查詢...")
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
            rank=hero_data.get("rank", hero_data.get("rarity", "N")),
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
        class_names = {"knight": "騎士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}
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
        accumulated_mana = db.get("total_mana_pool", 0)
        BASE_REWARD = 500  # 大地之母每回合提供
        total_mana = accumulated_mana + BASE_REWARD
        
        # 取得存活英雄數
        alive_count = sum(1 for h in db.get("heroes", {}).values() if h.get("status") == "alive")
        
        # 上次發放
        last_reward_daa = db.get("last_reward_daa", 0)
        
        if remaining_hours > 0:
            time_str = f"{remaining_hours}h {remaining_minutes % 60}m"
        else:
            time_str = f"{remaining_minutes}m"
        
        # 預估每位英雄獎勵（用總額計算）
        per_hero = total_mana / alive_count if alive_count > 0 else 0
        
        # 取得前 5 名英雄（按擊殺數排序，0 殺則按稀有度）
        # v0.3: 支援新舊格式
        rank_order = {
            "LR": 6, "mythic": 6,
            "UR": 5, "legendary": 5, 
            "SSR": 4, "epic": 4,
            "SR": 3, "rare": 3,
            "R": 2, "uncommon": 2,
            "N": 1, "common": 1
        }
        alive_heroes = [(hid, h) for hid, h in db.get("heroes", {}).items() if h.get("status") == "alive"]
        
        # 排序：先按擊殺數降序，再按稀有度降序
        alive_heroes.sort(key=lambda x: (
            -(x[1].get("kills", 0)),
            -rank_order.get(x[1].get("rank") or x[1].get("rarity", "N"), 1)
        ))
        
        # 前 5 名
        top5_lines = []
        rank_emoji = {
            "N": "⭐", "common": "⭐",
            "R": "⭐⭐", "uncommon": "⭐⭐",
            "SR": "⭐⭐⭐", "rare": "⭐⭐⭐",
            "SSR": "💎", "epic": "💎",
            "UR": "✨", "legendary": "✨",
            "LR": "🔱", "mythic": "🔱"
        }
        class_emoji = {"knight": "⚔️", "mage": "🔮", "archer": "🏹", "rogue": "🗡️"}
        
        for i, (hid, h) in enumerate(alive_heroes[:5], 1):
            name = h.get("name")
            display = f"「{name}」" if name else f"#{hid}"
            kills = h.get("kills", 0)
            rank = h.get("rank") or h.get("rarity", "N")
            re = rank_emoji.get(rank, "⭐")
            ce = class_emoji.get(h.get("hero_class"), "")
            protected = "🛡️" if h.get("protected") else ""
            top5_lines.append(f"{i}. {re}{ce} {display} {protected}({kills}殺)")
        
        top5_str = "\n".join(top5_lines) if top5_lines else "無存活英雄"
        
        msg = f"""🌲 *下次獎勵發放*

📍 目前 DAA: `{current_daa}`
🎯 下次觸發: `{next_trigger}`
⏳ 剩餘: ~{time_str} ({remaining_daa:,} DAA)

💰 *🌲 大地的祝福*
累積: {accumulated_mana} mana
大地之母: +{BASE_REWARD} mana
總計: *{total_mana} mana*
預估每位: ~{per_hero:.1f} mana

👥 存活英雄: {alive_count} 位
📊 上次發放: #{last_reward_daa or '尚未發放'}

🏆 *當前排行榜 TOP 5*
{top5_str}

*獎勵按積分分配！*
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
    
    import json
    import os
    
    # v0.3: 優先讀取已上鏈的 birth inscription
    inscription_path = f"data/inscriptions/{card_id}/birth.json"
    
    if os.path.exists(inscription_path):
        # ✅ 已上鏈：顯示實際 payload
        with open(inscription_path) as f:
            birth = json.load(f)
        
        tx_id = birth.get("tx_id", "")
        payload = birth.get("payload", {})
        payload_json = json.dumps(payload, separators=(',', ':'))
        verified = "✅ 已驗證" if birth.get("verified") else "⏳ 待驗證"
        
        msg = f"""📦 英雄 #{card_id} 出生銘文

<b>狀態：{verified}</b>

<code>{payload_json}</code>

📍 命運: DAA {hero.card_id}
🔗 TX: <code>{tx_id}</code>
🔗 <a href="https://explorer-tn10.kaspa.org/txs/{tx_id}">區塊瀏覽器</a>

Size: {len(payload_json)} bytes"""
    else:
        # ⏳ 待上鏈：生成預計格式
        payload = {
            "g": "nami_hero",
            "type": "birth",
            "daa": hero.card_id,
            "pre_tx": None,
            "pay_tx": "(pending)",
            "src": "(pending)",
            "rank": hero.rarity[0].upper() if hero.rarity else "N"
        }
        payload_json = json.dumps(payload, separators=(',', ':'))
        
        msg = f"""📦 英雄 #{card_id} Payload

<b>狀態：⏳ 待上鏈</b>

<code>{payload_json}</code>

📍 命運: DAA {hero.card_id}

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
# v0.3 管理員指令
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_admin_maintenance [on|off] - 開關維護模式（管理員專用）
    """
    global MAINTENANCE_MODE
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ 此指令僅限管理員使用")
        return
    
    if not context.args:
        status = "🔴 開啟中" if MAINTENANCE_MODE else "🟢 關閉"
        await update.message.reply_text(
            f"🛠️ *維護模式狀態*\n\n"
            f"目前: {status}\n\n"
            f"用法：\n"
            f"`/nami_admin_maintenance on` - 開啟\n"
            f"`/nami_admin_maintenance off` - 關閉",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    if action == "on":
        MAINTENANCE_MODE = True
        await update.message.reply_text("🔴 維護模式已開啟\n其他用戶無法執行操作")
        logger.warning("🛠️ 維護模式已開啟")
    elif action == "off":
        MAINTENANCE_MODE = False
        await update.message.reply_text("🟢 維護模式已關閉\n系統恢復正常")
        logger.info("🛠️ 維護模式已關閉")
    else:
        await update.message.reply_text("❌ 參數錯誤，請用 on 或 off")

async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_admin_status - 查看系統狀態（管理員專用）
    """
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ 此指令僅限管理員使用")
        return
    
    from hero_game import load_heroes_db
    db = load_heroes_db()
    
    total_heroes = len(db.get("heroes", {}))
    alive_heroes = sum(1 for h in db.get("heroes", {}).values() if h.get("status") == "alive")
    mana_pool = db.get("total_mana_pool", 0)
    
    maintenance_status = "🔴 開啟" if MAINTENANCE_MODE else "🟢 關閉"
    lock_status = "🔒 鎖定中" if WALLET_LOCK.locked() else "🔓 空閒"
    queue_size = tree_queue.queue_size()
    
    await update.message.reply_text(
        f"📊 *系統狀態*\n\n"
        f"🛠️ 維護模式: {maintenance_status}\n"
        f"🔐 錢包鎖: {lock_status}\n"
        f"⏳ 排隊人數: {queue_size}\n\n"
        f"🦸 總英雄: {total_heroes}\n"
        f"🟢 存活: {alive_heroes}\n"
        f"🏦 獎池: {mana_pool} mana",
        parse_mode='Markdown'
    )


async def admin_safe_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_admin_safe_restart - 安全重開檢查（管理員專用）
    
    v0.4.3: CI/CD 安全重開機制
    1. 檢查排隊是否為空
    2. 檢查錢包鎖是否空閒
    3. 設定維護模式
    4. 等待當前操作完成
    """
    global MAINTENANCE_MODE
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ 此指令僅限管理員使用")
        return
    
    # 檢查系統狀態
    queue_size = tree_queue.queue_size()
    wallet_locked = WALLET_LOCK.locked()
    current_user = tree_queue._current_user
    
    if queue_size == 0 and not wallet_locked and current_user is None:
        # 可以安全重開
        await update.message.reply_text(
            "✅ *可以安全重開！*\n\n"
            "📊 系統狀態：\n"
            "• 排隊: 0 人\n"
            "• 錢包鎖: 🔓 空閒\n"
            "• 當前服務: 無\n\n"
            "🟢 現在可以執行 CI/CD 重開",
            parse_mode='Markdown'
        )
    else:
        # 需要等待
        status_lines = []
        if queue_size > 0:
            status_lines.append(f"• 排隊: {queue_size} 人 ⏳")
        if wallet_locked:
            status_lines.append("• 錢包鎖: 🔒 使用中")
        if current_user:
            status_lines.append(f"• 當前服務: 用戶 {current_user}")
        
        # 詢問是否要開啟維護模式
        if len(context.args) > 0 and context.args[0] == "force":
            # 強制開啟維護模式
            MAINTENANCE_MODE = True
            await update.message.reply_text(
                "⚠️ *維護模式已開啟*\n\n"
                "新請求將被阻擋，等待當前操作完成後可重開\n\n"
                "📊 當前狀態：\n" + "\n".join(status_lines) + "\n\n"
                "再次執行 `/nami_admin_safe_restart` 檢查是否可重開",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "⚠️ *暫時無法安全重開*\n\n"
                "📊 當前狀態：\n" + "\n".join(status_lines) + "\n\n"
                "建議：\n"
                "1. 等待當前操作完成\n"
                "2. 或執行 `/nami_admin_safe_restart force` 開啟維護模式",
                parse_mode='Markdown'
            )


# ═══════════════════════════════════════════════════════════════════════════════
# v0.3 保護機制
# ═══════════════════════════════════════════════════════════════════════════════

async def hero_protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_hero_protect <英雄ID> [PIN] - 設定英雄為受保護狀態
    /nhp <英雄ID> [PIN] - 縮寫
    
    v0.4.2 更新：
    - 第一次設定保護：免費
    - 更換保護角色：需要 10 mana
    - 每人可選 1 隻英雄設定保護
    - 被保護的英雄 PvP 輸了不會死亡
    """
    user = update.effective_user
    
    from hero_game import get_protected_hero, load_heroes_db, set_hero_protection
    
    PROTECT_COST = 10 * 100_000_000  # 10 mana in sompi
    
    if not context.args:
        # 顯示目前保護狀態
        protected = get_protected_hero(user.id)
        if protected:
            hero_name = protected.get("name") or f"#{str(protected['card_id'])[:6]}"
            rank = protected.get("rank") or protected.get("rarity", "N")
            await update.message.reply_text(
                f"🛡️ *你的保護英雄*\n\n"
                f"{hero_name} ({rank})\n"
                f"被保護的英雄 PvP 輸了不會死亡\n\n"
                f"更換保護對象需要 *10 mana*：\n"
                f"`/nhp <英雄ID> <PIN>`",
                parse_mode='Markdown'
            )
        else:
            # 列出可保護的英雄
            db = load_heroes_db()
            user_heroes = [h for h in db.get("heroes", {}).values() 
                          if h.get("owner_id") == user.id and h.get("status") == "alive"]
            if user_heroes:
                hero_list = "\n".join([
                    f"• `{h['card_id']}` - {h.get('name') or '無名'} ({h.get('rank') or h.get('rarity', '?')})"
                    for h in user_heroes
                ])
                await update.message.reply_text(
                    f"🛡️ *設定保護英雄*\n\n"
                    f"你還沒有設定保護英雄！\n"
                    f"被保護的英雄 PvP 輸了不會死亡\n\n"
                    f"🆓 *首次設定免費！*\n\n"
                    f"你的英雄：\n{hero_list}\n\n"
                    f"用法：`/nhp <英雄ID>`",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ 你還沒有英雄！先用 /nh 召喚一隻吧")
        return
    
    try:
        card_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 請輸入正確的英雄 ID（數字）")
        return
    
    # 檢查是否已有保護角色
    current_protected = get_protected_hero(user.id)
    
    if current_protected:
        # 已有保護角色 → 需要付 10 mana
        if len(context.args) < 2:
            current_name = current_protected.get("name") or f"#{current_protected['card_id']}"
            await update.message.reply_text(
                f"🛡️ *更換保護角色*\n\n"
                f"目前保護：{current_name}\n\n"
                f"更換需要 *10 mana*\n"
                f"用法：`/nhp {card_id} <PIN>`",
                parse_mode='Markdown'
            )
            return
        
        pin = context.args[1]
        
        # 驗證 PIN
        if not verify_hero_pin(user.id, pin):
            await update.message.reply_text("❌ PIN 錯誤")
            return
        
        # 檢查餘額並付款
        try:
            import unified_wallet
            _, address = unified_wallet.get_wallet(user.id, pin)
            balance = await unified_wallet.get_balance(address)
            
            if balance < PROTECT_COST:
                need = (PROTECT_COST - balance) / 1e8
                await update.message.reply_text(f"❌ 餘額不足！需要 10 mana，還差 {need:.2f}")
                return
            
            # 付款給世界之樹
            await update.message.reply_text("💰 付款中...")
            tx_id = await unified_wallet.send_to_tree(user.id, pin, PROTECT_COST, f"protect:{card_id}")
            
        except Exception as e:
            await update.message.reply_text(f"❌ 付款失敗：{e}")
            return
        
        # 設定保護
        success, message = set_hero_protection(user.id, card_id)
        if success:
            await update.message.reply_text(
                f"🛡️ *保護已更換！*\n\n"
                f"{message}\n\n"
                f"💰 已付 10 mana\n"
                f"TX: `{tx_id[:32]}...`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ {message}")
    else:
        # 首次設定 → 免費
        success, message = set_hero_protection(user.id, card_id)
        if success:
            await update.message.reply_text(
                f"🛡️ *保護已設定！*\n\n"
                f"{message}\n\n"
                f"🆓 首次設定免費",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ {message}")

# ═══════════════════════════════════════════════════════════════════════════════
# 註冊指令
# ═══════════════════════════════════════════════════════════════════════════════

def register_hero_commands(app):
    """註冊英雄遊戲指令到 Bot"""
    from telegram.ext import CommandHandler, CallbackQueryHandler
    
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
    app.add_handler(CommandHandler("help", hero_help))
    app.add_handler(CommandHandler("nami_game_status", hero_stats))
    app.add_handler(CommandHandler("nami_next_reward", next_reward))
    app.add_handler(CommandHandler("nami_payload", hero_payload))
    app.add_handler(CommandHandler("nami_decode", hero_decode))
    app.add_handler(CommandHandler("nami_decode_hex", hero_decode_hex))
    app.add_handler(CommandHandler("nami_hero_pin", hero_pin_setup))
    app.add_handler(CommandHandler("nami_hero_balance", hero_wallet_balance))
    app.add_handler(CommandHandler("nami_name", hero_name))
    
    # v0.3 新指令
    app.add_handler(CommandHandler("nami_hero_protect", hero_protect))
    
    # v0.3 管理員指令
    app.add_handler(CommandHandler("nami_admin_maintenance", admin_maintenance))
    app.add_handler(CommandHandler("nami_admin_status", admin_status))
    app.add_handler(CommandHandler("nami_admin_safe_restart", admin_safe_restart))
    
    # ═══════════════════════════════════════════════════════════════════════
    # 縮寫指令
    # ═══════════════════════════════════════════════════════════════════════
    app.add_handler(CommandHandler("nh", hero_summon))       # nami_hero
    app.add_handler(CommandHandler("nhs", hero_list))        # nami_heroes
    app.add_handler(CommandHandler("np", hero_attack))       # nami_pvp
    app.add_handler(CommandHandler("nb", hero_burn))         # nami_burn
    app.add_handler(CommandHandler("ni", hero_info))         # nami_hero_info
    app.add_handler(CommandHandler("nv", hero_verify))       # nami_verify
    app.add_handler(CommandHandler("nn", hero_name))         # nami_name
    app.add_handler(CommandHandler("nr", next_reward))       # nami_next_reward
    app.add_handler(CommandHandler("ns", hero_stats))        # nami_game_status
    app.add_handler(CommandHandler("nse", hero_search))      # nami_search (偵查)
    app.add_handler(CommandHandler("nhp", hero_protect))     # v0.3: nami_hero_protect
    
    # ═══════════════════════════════════════════════════════════════════════
    # v0.4: Callback Query Handlers（按鈕回調）
    # ═══════════════════════════════════════════════════════════════════════
    app.add_handler(CallbackQueryHandler(handle_burn_callback, pattern=r"^burn_(yes|no):"))
    app.add_handler(CallbackQueryHandler(handle_pvp_callback, pattern=r"^pvp_(yes|no):"))
    
    logger.info("🌲 英雄遊戲指令已註冊 (v0.4)")


# ═══════════════════════════════════════════════════════════════════════════════
# 英雄命名
# ═══════════════════════════════════════════════════════════════════════════════

async def hero_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nami_name <英雄ID> <名字> - 為英雄命名
    
    名字規則：
    - 2-12 字元
    - 支援中文、英文、數字、底線
    - 不能與其他英雄重複
    """
    user = update.effective_user
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "🏷️ *英雄命名*\n\n"
            "用法：\n"
            "```\n/nami_name <英雄ID> <名字>\n```\n\n"
            "例如：\n"
            "`/nami_name 380312869 Excalibur`\n\n"
            "規則：\n"
            "• 2-12 字元\n"
            "• 中文、英文、數字、底線\n"
            "• 名字不能重複",
            parse_mode='Markdown'
        )
        return
    
    try:
        hero_id = int(context.args[0])
        name = context.args[1]
    except (ValueError, IndexError):
        await update.message.reply_text("❌ 用法：`/nami_name <英雄ID> <名字>`", parse_mode='Markdown')
        return
    
    # 驗證名字格式（支援中文）
    import re
    # 支援中文、英文、數字、底線，2-12 字元
    if not re.match(r'^[\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9_]{2,12}$', name):
        await update.message.reply_text(
            "❌ 名字格式錯誤！\n\n"
            "規則：\n"
            "• 2-12 字元\n"
            "• 中文、英文、數字、底線"
        )
        return
    
    # 檢查英雄存在
    from hero_game import load_heroes_db, is_name_taken, set_hero_name
    
    db = load_heroes_db()
    hero = db.get("heroes", {}).get(str(hero_id))
    
    if not hero:
        await update.message.reply_text(f"❌ 找不到英雄 #{hero_id}")
        return
    
    # 驗證擁有權
    hero_owner = hero.get("owner_id")
    if hero_owner != user.id:
        logger.warning(f"⚠️ 命名權限拒絕 | user={user.id} 嘗試命名 #{hero_id} (owner={hero_owner})")
        await update.message.reply_text(f"❌ #{hero_id} 不是你的英雄！")
        return
    
    # 設定名字（包含驗證：長度 2-12、字元、不重複，改名會釋放舊名字）
    old_name = hero.get("name")
    success, error = set_hero_name(hero_id, name)
    
    if success:
        if old_name:
            await update.message.reply_text(
                f"✅ 英雄 #{hero_id} 改名成功！\n\n"
                f"舊名：{old_name}\n"
                f"新名：**{name}**",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"✅ 英雄 #{hero_id} 命名成功！\n\n"
                f"名字：**{name}**\n\n"
                f"現在可以用名字代替 ID：\n"
                f"`/ni {name}` 或 `/np {name} ...`",
                parse_mode='Markdown'
            )
        
        logger.info(f"🏷️ 命名 | @{user.username} | #{hero_id} → {name}")
    else:
        await update.message.reply_text(f"❌ {error}")
