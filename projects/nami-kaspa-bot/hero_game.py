#!/usr/bin/env python3
"""
🌲 娜米的英雄奇幻冒險
====================
Nami's Hero Fantasy Adventure

核心遊戲模組
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum

# v0.4 ATB 戰鬥系統
from atb_battle import ATBFighter, atb_battle, RANK_HP

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 常數設定
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent / "data"
HEROES_DB_FILE = DATA_DIR / "heroes.json"
HERO_CHAIN_FILE = DATA_DIR / "hero_chain.json"

# 費用設定
SUMMON_COST = 10  # 召喚英雄消耗 10 mana
PVP_COST = 10     # PvP 統一費用 10 mana

# v0.3 設定
MAX_HEROES = 5           # 每人最多 5 隻英雄（從 10 改為 5）
PVP_REWARD_MIN = 1       # PvP 勝利獎勵最小值
PVP_REWARD_MAX = 5       # PvP 勝利獎勵最大值

# 抽卡冷卻
SUMMON_COOLDOWN = 5  # 秒

# 版本
GAME_VERSION = "0.4"  # ATB 戰鬥系統

# Bot 錢包設定
BOT_WALLET_FILE = Path(__file__).parent.parent.parent.parent / "clawd/.secrets/testnet-wallet.json"

# ═══════════════════════════════════════════════════════════════════════════════
# 職業與稀有度
# ═══════════════════════════════════════════════════════════════════════════════

class HeroClass(Enum):
    WARRIOR = ("warrior", "⚔️ 戰士", "高防扛傷")
    MAGE = ("mage", "🔮 魔法師", "高攻爆發")
    ARCHER = ("archer", "🏹 弓箭手", "高速先手")
    ROGUE = ("rogue", "🗡️ 盜賊", "暴擊閃避")
    
    def __init__(self, code: str, display: str, desc: str):
        self.code = code
        self.display = display
        self.desc = desc

class Rank(Enum):
    """
    v0.3 Rank 系統 - 6階手遊風格
    
    計算方式：hash[0:16] (8 bytes) % 1000
    """
    N   = ("N",   "⭐",           "普通", 1.0, 550)       # 55% (450-999)
    R   = ("R",   "⭐⭐",         "稀有", 1.2, 280)       # 28% (170-449)
    SR  = ("SR",  "⭐⭐⭐",       "超稀", 1.5, 130)       # 13% (40-169)
    SSR = ("SSR", "💎⭐⭐⭐⭐",   "極稀", 2.0, 35)        # 3.5% (5-39)
    UR  = ("UR",  "✨⭐⭐⭐⭐⭐", "傳說", 3.0, 4)         # 0.4% (1-4)
    LR  = ("LR",  "🔱⭐⭐⭐⭐⭐⭐", "神話", 5.0, 1)       # 0.1% (0)
    
    def __init__(self, code: str, stars: str, cn_name: str, multiplier: float, chance: int):
        self.code = code
        self.stars = stars
        self.cn_name = cn_name
        self.multiplier = multiplier
        self.chance = chance  # 千分比
    
    @property
    def display(self) -> str:
        return f"{self.stars} {self.code} {self.cn_name}"

# 向後相容：保留 Rarity 別名
Rarity = Rank

# ═══════════════════════════════════════════════════════════════════════════════
# 英雄資料結構
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Hero:
    """
    v0.3 英雄資料結構
    
    改動：
    - rarity → rank (N/R/SR/SSR/UR/LR)
    - 新增 protected 欄位（大地之母保護）
    - name 欄位
    """
    card_id: int          # DAA = 唯一 ID
    owner_id: int         # TG user_id
    owner_address: str    # Kaspa 地址
    hero_class: str       # warrior/mage/archer/rogue
    rank: str             # v0.3: N/R/SR/SSR/UR/LR
    atk: int
    def_: int
    spd: int
    status: str           # alive/dead
    latest_daa: int       # 最新狀態的 DAA
    kills: int = 0
    battles: int = 0
    created_at: str = ""
    death_time: str = ""  # 死亡時間（計算生存時間用）
    source_hash: str = "" # 來源區塊 hash（命運塊）
    payment_tx: str = ""  # 付費交易 ID（出生證明）
    tx_id: str = ""       # 出生銘文交易 ID（固定）
    latest_tx: str = ""   # 最後事件交易 ID（每次事件更新）
    name: str = ""        # 英雄名字
    protected: bool = False  # v0.3: 大地之母保護（PvP 不死）
    
    # 向後相容
    @property
    def rarity(self) -> str:
        return self.rank
    
    def display_class(self) -> str:
        for hc in HeroClass:
            if hc.code == self.hero_class:
                return hc.display
        return self.hero_class
    
    def display_rank(self) -> str:
        """v0.3: 顯示 Rank（星星 + 等級 + 中文）"""
        return get_rank_display(self.rank)
    
    # 向後相容
    def display_rarity(self) -> str:
        return self.display_rank()
    
    def to_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "owner_id": self.owner_id,
            "owner_address": self.owner_address,
            "hero_class": self.hero_class,
            "rank": self.rank,           # v0.3
            "rarity": self.rank,         # 向後相容
            "atk": self.atk,
            "def": self.def_,
            "spd": self.spd,
            "status": self.status,
            "latest_daa": self.latest_daa,
            "kills": self.kills,
            "battles": self.battles,
            "created_at": self.created_at,
            "death_time": self.death_time,
            "source_hash": self.source_hash,
            "payment_tx": self.payment_tx,
            "tx_id": self.tx_id,
            "latest_tx": self.latest_tx,
            "name": self.name,
            "protected": self.protected   # v0.3
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'Hero':
        # v0.3: 支援 rank 或 rarity
        rank = d.get("rank") or d.get("rarity", "N")
        return cls(
            card_id=d["card_id"],
            owner_id=d["owner_id"],
            owner_address=d["owner_address"],
            hero_class=d["hero_class"],
            rank=rank,
            atk=d["atk"],
            def_=d["def"],
            spd=d["spd"],
            status=d["status"],
            latest_daa=d["latest_daa"],
            kills=d.get("kills", 0),
            battles=d.get("battles", 0),
            created_at=d.get("created_at", ""),
            death_time=d.get("death_time", ""),
            source_hash=d.get("source_hash", ""),
            payment_tx=d.get("payment_tx", ""),
            tx_id=d.get("tx_id", ""),
            latest_tx=d.get("latest_tx", ""),
            name=d.get("name", ""),
            protected=d.get("protected", False)
        )

# ═══════════════════════════════════════════════════════════════════════════════
# 資料管理
# ═══════════════════════════════════════════════════════════════════════════════

def load_heroes_db() -> dict:
    """載入英雄資料庫"""
    if HEROES_DB_FILE.exists():
        with open(HEROES_DB_FILE, 'r') as f:
            return json.load(f)
    return {
        "heroes": {},           # card_id -> Hero data
        "user_heroes": {},      # user_id -> [card_id, ...]
        "last_summon_daa": 0,   # 最後一次召喚使用的 DAA
        "summon_queue": [],     # 召喚排隊
        "total_mana_pool": 0    # 大地之樹 mana 池
    }

def save_heroes_db(db: dict):
    """儲存英雄資料庫"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HEROES_DB_FILE, 'w') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def load_hero_chain() -> list:
    """載入英雄事件鏈"""
    if HERO_CHAIN_FILE.exists():
        with open(HERO_CHAIN_FILE, 'r') as f:
            return json.load(f)
    return []

def save_hero_chain(chain: list):
    """儲存英雄事件鏈"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HERO_CHAIN_FILE, 'w') as f:
        json.dump(chain, f, indent=2, ensure_ascii=False)

def load_bot_wallet() -> dict:
    """載入 Bot 錢包"""
    with open(BOT_WALLET_FILE, 'r') as f:
        return json.load(f)

# ═══════════════════════════════════════════════════════════════════════════════
# v0.3 保護機制
# ═══════════════════════════════════════════════════════════════════════════════

def set_hero_protection(user_id: int, card_id: int) -> Tuple[bool, str]:
    """
    設定英雄為受保護狀態（大地之母保護）
    
    規則：
    - 每人只能保護 1 隻英雄
    - 被保護的英雄 PvP 輸了不會死亡
    - 設定新保護會取消舊保護
    
    Args:
        user_id: TG 用戶 ID
        card_id: 要保護的英雄 ID
    
    Returns:
        (success, message)
    """
    db = load_heroes_db()
    
    # 檢查英雄是否存在且屬於該用戶
    hero_data = db.get("heroes", {}).get(str(card_id))
    if not hero_data:
        return False, "❌ 找不到這隻英雄"
    
    if hero_data.get("owner_id") != user_id:
        return False, "❌ 這不是你的英雄"
    
    if hero_data.get("status") != "alive":
        return False, "❌ 這隻英雄已經死亡"
    
    # 取消該用戶其他英雄的保護
    old_protected = None
    for hid, hdata in db.get("heroes", {}).items():
        if hdata.get("owner_id") == user_id and hdata.get("protected"):
            if int(hid) != card_id:
                hdata["protected"] = False
                old_protected = hdata.get("name") or f"#{hid[:6]}"
    
    # 設定新保護
    db["heroes"][str(card_id)]["protected"] = True
    save_heroes_db(db)
    
    hero_name = hero_data.get("name") or f"#{str(card_id)[:6]}"
    if old_protected:
        return True, f"🛡️ 已將保護從「{old_protected}」轉移到「{hero_name}」\n被保護的英雄 PvP 輸了不會死亡"
    else:
        return True, f"🛡️ 已設定「{hero_name}」為受保護狀態\n被保護的英雄 PvP 輸了不會死亡"

def get_protected_hero(user_id: int) -> Optional[dict]:
    """取得用戶受保護的英雄"""
    db = load_heroes_db()
    for hid, hdata in db.get("heroes", {}).items():
        if hdata.get("owner_id") == user_id and hdata.get("protected") and hdata.get("status") == "alive":
            return hdata
    return None

def calculate_pvp_reward(block_hash: str) -> int:
    """
    v0.3: 計算 PvP 獎勵（1-5 mana）
    
    由戰鬥命運塊決定
    """
    h = block_hash.lower().replace("0x", "")
    # 用 hash 的一部分決定獎勵
    reward_val = int(h[32:36], 16) % 5 + 1  # 1-5
    return reward_val

# ═══════════════════════════════════════════════════════════════════════════════
# 鏈上交易功能
# ═══════════════════════════════════════════════════════════════════════════════

async def send_hero_tx(to_address: str, payload: dict) -> str:
    """
    發送英雄交易到鏈上
    
    Args:
        to_address: 接收者地址
        payload: 交易 payload（會轉成 JSON）
    
    Returns:
        交易 ID (tx_id)
    """
    from kaspa import RpcClient, PrivateKey, Address, create_transaction, sign_transaction
    
    try:
        # 載入 Bot 錢包
        wallet = load_bot_wallet()
        private_key = PrivateKey(wallet['private_key'])
        bot_address = Address(wallet['address'])
        
        # 連接 RPC
        client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
        await client.connect()
        
        try:
            # 取得 UTXO
            utxos_resp = await client.get_utxos_by_addresses({"addresses": [wallet['address']]})
            utxos = utxos_resp.get('entries', [])
            
            if not utxos:
                raise Exception("Bot 錢包沒有 UTXO")
            
            # 準備輸入
            total_input = 0
            inputs = []
            for utxo in utxos[:5]:  # 最多用 5 個 UTXO
                entry = utxo.get('entry', utxo)
                outpoint = utxo.get('outpoint', {})
                amount = int(entry.get('amount', entry.get('utxoEntry', {}).get('amount', 0)))
                
                inputs.append({
                    'previousOutpoint': {
                        'transactionId': outpoint.get('transactionId', ''),
                        'index': outpoint.get('index', 0)
                    },
                    'signatureScript': '',
                    'sequence': 0,
                    'sigOpCount': 1
                })
                total_input += amount
                
                if total_input >= 10000:  # 足夠支付手續費
                    break
            
            # 準備 payload
            payload_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            payload_bytes = payload_json.encode('utf-8')
            
            # 輸出：發送 1 sompi 到目標地址 + 找零
            send_amount = 1  # 1 sompi
            fee = 5000  # 手續費
            change = total_input - send_amount - fee
            
            outputs = [
                {
                    'amount': send_amount,
                    'scriptPublicKey': {
                        'version': 0,
                        'scriptPublicKey': Address(to_address).to_script_public_key()
                    }
                }
            ]
            
            if change > 0:
                outputs.append({
                    'amount': change,
                    'scriptPublicKey': {
                        'version': 0,
                        'scriptPublicKey': bot_address.to_script_public_key()
                    }
                })
            
            # 建立交易
            tx = {
                'version': 0,
                'inputs': inputs,
                'outputs': outputs,
                'lockTime': 0,
                'subnetworkId': '0000000000000000000000000000000000000000',
                'gas': 0,
                'payload': payload_bytes.hex()
            }
            
            # 簽名並發送
            # 注意：這裡需要用 kaspa SDK 的正確方式簽名和發送
            # 目前先用簡化版本
            
            # 發送交易
            result = await client.submit_transaction({
                'transaction': tx,
                'allowOrphan': False
            })
            
            tx_id = result.get('transactionId', 'unknown')
            logger.info(f"Hero TX sent: {tx_id[:16]}... to {to_address[:20]}...")
            
            return tx_id
            
        finally:
            await client.disconnect()
            
    except Exception as e:
        logger.error(f"Failed to send hero tx: {e}")
        raise

async def send_hero_tx_simple(to_address: str, payload: dict) -> str:
    """
    發送英雄交易到 Kaspa 鏈上
    
    Args:
        to_address: 接收者地址（目前未使用，payload 發給自己）
        payload: 要上鏈的 payload dict
    
    Returns:
        交易 ID
    """
    from kaspa_tx import send_payload_tx
    
    try:
        logger.info(f"Sending hero payload to chain: {payload.get('type')} daa={payload.get('daa')}")
        
        # 發送到鏈上！
        tx_id = await send_payload_tx(payload)
        
        logger.info(f"Hero TX sent successfully: {tx_id}")
        return tx_id
        
    except Exception as e:
        logger.error(f"Failed to send hero tx: {e}")
        # 記錄失敗的 payload 到本地備份
        chain = load_hero_chain()
        chain.append({
            "to": to_address,
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
            "status": "failed",
            "error": str(e)
        })
        save_hero_chain(chain)
        raise

# ═══════════════════════════════════════════════════════════════════════════════
# Hash 計算屬性
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_rank_from_hash(block_hash: str) -> str:
    """
    v0.3: 從 block hash 計算 Rank
    
    規則：
    - 用 hash[0:16] (8 bytes) 計算
    - 更大的熵，更公平的機率
    
    Args:
        block_hash: 區塊 hash (64 字元)
    
    Returns:
        rank code: "N" | "R" | "SR" | "SSR" | "UR" | "LR"
    """
    h = block_hash.lower().replace("0x", "")
    
    # Rank: hash[0:16] % 1000（千分比）
    rank_val = int(h[0:16], 16) % 1000
    
    if rank_val < 1:           # 0 = 0.1%
        return "LR"
    elif rank_val < 5:         # 1-4 = 0.4%
        return "UR"
    elif rank_val < 40:        # 5-39 = 3.5%
        return "SSR"
    elif rank_val < 170:       # 40-169 = 13%
        return "SR"
    elif rank_val < 450:       # 170-449 = 28%
        return "R"
    else:                      # 450-999 = 55%
        return "N"

def calculate_class_from_hash(block_hash: str) -> str:
    """
    v0.3: 從 block hash 計算職業
    
    規則：
    - 用 hash[16:20] 計算
    - 與 Rank 計算分開，避免相關性
    
    Args:
        block_hash: 區塊 hash (64 字元)
    
    Returns:
        hero_class: "warrior" | "mage" | "archer" | "rogue"
    """
    h = block_hash.lower().replace("0x", "")
    
    # 職業: hash[16:20] % 4
    class_val = int(h[16:20], 16) % 4
    classes = ["warrior", "mage", "archer", "rogue"]
    return classes[class_val]

def calculate_stats_from_hash(block_hash: str, rank: str) -> Tuple[int, int, int]:
    """
    v0.3: 從 block hash 計算屬性（大地之母解釋）
    
    規則：
    - 基礎屬性從 hash[20:32] 計算
    - 套用 Rank 加權
    
    Args:
        block_hash: 區塊 hash (64 字元)
        rank: Rank code
    
    Returns:
        (atk, def, spd)
    """
    h = block_hash.lower().replace("0x", "")
    
    # Rank 加權
    RANK_MULTIPLIER = {
        "N": 1.0,
        "R": 1.2,
        "SR": 1.5,
        "SSR": 2.0,
        "UR": 3.0,
        "LR": 5.0
    }
    multiplier = RANK_MULTIPLIER.get(rank, 1.0)
    
    # 基礎屬性: 10-100（從 hash[20:32] 計算）
    base_atk = int(h[20:24], 16) % 91 + 10
    base_def = int(h[24:28], 16) % 91 + 10
    base_spd = int(h[28:32], 16) % 91 + 10
    
    # 套用 Rank 加權
    atk = int(base_atk * multiplier)
    def_ = int(base_def * multiplier)
    spd = int(base_spd * multiplier)
    
    return atk, def_, spd

def calculate_hero_from_hash(block_hash: str) -> Tuple[str, str, int, int, int]:
    """
    v0.3: 從 block hash 計算英雄完整屬性
    
    這是大地之母的「解釋」功能：
    - Rank: hash[0:16] (8 bytes)
    - 職業: hash[16:20]
    - 屬性: hash[20:32] × Rank 加權
    
    Args:
        block_hash: 區塊 hash (64 字元)
    
    Returns:
        (hero_class, rank, atk, def, spd)
    """
    rank = calculate_rank_from_hash(block_hash)
    hero_class = calculate_class_from_hash(block_hash)
    atk, def_, spd = calculate_stats_from_hash(block_hash, rank)
    
    return hero_class, rank, atk, def_, spd

def get_rank_display(rank: str) -> str:
    """取得 Rank 的顯示文字"""
    for r in Rank:
        if r.code == rank:
            return r.display
    return rank

def get_rank_stars(rank: str) -> str:
    """取得 Rank 的星星顯示"""
    for r in Rank:
        if r.code == rank:
            return r.stars
    return "⭐"

def calculate_battle_result_atb(attacker: Hero, defender: Hero, block_hash: str) -> Tuple[bool, dict]:
    """
    v0.4 ATB 戰鬥系統
    
    使用 Active Time Battle 系統計算戰鬥結果
    """
    import random
    random.seed(int(block_hash[:16], 16))  # 用 block_hash 作為種子確保可驗證
    
    # 建立 ATB 戰鬥單位
    atk_fighter = ATBFighter(
        card_id=attacker.card_id,
        name=getattr(attacker, 'name', '') or f"#{attacker.card_id}",
        hero_class=attacker.hero_class,
        rank=getattr(attacker, 'rank', 'N'),
        atk=attacker.atk,
        def_=attacker.def_,
        spd=attacker.spd,
    )
    
    def_fighter = ATBFighter(
        card_id=defender.card_id,
        name=getattr(defender, 'name', '') or f"#{defender.card_id}",
        hero_class=defender.hero_class,
        rank=getattr(defender, 'rank', 'N'),
        atk=defender.atk,
        def_=defender.def_,
        spd=defender.spd,
    )
    
    # 執行 ATB 戰鬥
    result = atb_battle(atk_fighter, def_fighter)
    
    # 轉換結果格式
    attacker_wins = not result["draw"] and result.get("winner") and result["winner"].card_id == attacker.card_id
    
    battle_detail = {
        "atb_version": "0.4",
        "loops": result["loops"],
        "draw": result["draw"],
        "battle_log": result["logs"].get_full_log(),
        "stats": result["stats"],
    }
    
    if not result["draw"]:
        battle_detail["winner_id"] = result["winner"].card_id
        battle_detail["loser_id"] = result["loser"].card_id
        battle_detail["winner_hp"] = result["winner"].current_hp
    
    return attacker_wins, battle_detail


def calculate_battle_result(attacker: Hero, defender: Hero, block_hash: str) -> Tuple[bool, dict]:
    """
    計算戰鬥結果
    
    對決規則：
    - 回合1: ⚔️攻擊 vs 🛡️防禦
    - 回合2: 🛡️防禦 vs ⚡速度
    - 回合3: ⚡速度 vs ⚔️攻擊
    
    稀有度加成：
    - 普通: ×1.0
    - 優秀: ×1.1
    - 稀有: ×1.2
    - 史詩: ×1.5
    - 傳說: ×2.0
    - 神話: ×3.0
    
    反殺機制（命運逆轉）：
    - 弱者攻擊強者時有機率直接獲勝
    - 機率根據稀有度差距遞減
    - 由區塊 hash 決定是否觸發
    
    勝者：3 回合中贏 2 回合者
    平手時用稀有度 + hash 決定
    
    Args:
        attacker: 攻擊方英雄
        defender: 防守方英雄
        block_hash: 決定勝負的區塊 hash
    
    Returns:
        (attacker_wins, battle_detail)
    """
    h = block_hash.lower().replace("0x", "")
    
    # v0.3 Rank 等級（數字越大越稀有）
    RANK_LEVEL = {
        "N": 0, "R": 1, "SR": 2,
        "SSR": 3, "UR": 4, "LR": 5,
        # 向後相容舊版
        "common": 0, "uncommon": 1, "rare": 2,
        "epic": 3, "legendary": 4, "mythic": 5
    }
    
    # 反殺機率（千分比）根據 Rank 差距
    # 差距越大，反殺機率越低
    REVERSAL_CHANCE = {
        0: 0,      # 同級：無反殺
        1: 100,    # 1級差：10%
        2: 50,     # 2級差：5%
        3: 20,     # 3級差：2%
        4: 5,      # 4級差：0.5%
        5: 1       # 5級差：0.1% (N→LR)
    }
    
    atk_rank = RANK_LEVEL.get(attacker.rank, 0)
    def_rank = RANK_LEVEL.get(defender.rank, 0)
    rank_diff = def_rank - atk_rank  # 正數表示防守方 Rank 更高
    
    # 檢查命運逆轉（弱者反殺強者）
    reversal_triggered = False
    if rank_diff > 0:  # 攻擊方是弱者
        reversal_roll = int(h[20:24], 16) % 1000  # 用 hash 的一部分
        reversal_threshold = REVERSAL_CHANCE.get(rank_diff, 0)
        if reversal_roll < reversal_threshold:
            reversal_triggered = True
    
    # v0.3 Rank 加成倍率
    RANK_MULT = {
        "N": 1.0, "R": 1.2, "SR": 1.5,
        "SSR": 2.0, "UR": 3.0, "LR": 5.0,
        # 向後相容舊版
        "common": 1.0, "uncommon": 1.1, "rare": 1.2,
        "epic": 1.5, "legendary": 2.0, "mythic": 3.0
    }
    
    atk_mult = RANK_MULT.get(attacker.rank, 1.0)
    def_mult = RANK_MULT.get(defender.rank, 1.0)
    
    # 三回合對決
    rounds = []
    atk_wins = 0
    def_wins = 0
    
    # 回合1: 攻擊者的⚔️ vs 防守者的🛡️
    r1_atk_base = attacker.atk
    r1_def_base = defender.def_
    r1_atk = int(r1_atk_base * atk_mult)
    r1_def = int(r1_def_base * def_mult)
    if r1_atk > r1_def:
        r1_winner = "atk"
        atk_wins += 1
    elif r1_atk < r1_def:
        r1_winner = "def"
        def_wins += 1
    else:
        r1_winner = "tie"
    rounds.append({
        "name": "⚔️ vs 🛡️",
        "atk_stat": f"⚔️{r1_atk_base}×{atk_mult}={r1_atk}",
        "def_stat": f"🛡️{r1_def_base}×{def_mult}={r1_def}",
        "atk_val": r1_atk,
        "def_val": r1_def,
        "winner": r1_winner
    })
    
    # 回合2: 攻擊者的🛡️ vs 防守者的⚡
    r2_atk_base = attacker.def_
    r2_def_base = defender.spd
    r2_atk = int(r2_atk_base * atk_mult)
    r2_def = int(r2_def_base * def_mult)
    if r2_atk > r2_def:
        r2_winner = "atk"
        atk_wins += 1
    elif r2_atk < r2_def:
        r2_winner = "def"
        def_wins += 1
    else:
        r2_winner = "tie"
    rounds.append({
        "name": "🛡️ vs ⚡",
        "atk_stat": f"🛡️{r2_atk_base}×{atk_mult}={r2_atk}",
        "def_stat": f"⚡{r2_def_base}×{def_mult}={r2_def}",
        "atk_val": r2_atk,
        "def_val": r2_def,
        "winner": r2_winner
    })
    
    # 回合3: 攻擊者的⚡ vs 防守者的⚔️
    r3_atk_base = attacker.spd
    r3_def_base = defender.atk
    r3_atk = int(r3_atk_base * atk_mult)
    r3_def = int(r3_def_base * def_mult)
    if r3_atk > r3_def:
        r3_winner = "atk"
        atk_wins += 1
    elif r3_atk < r3_def:
        r3_winner = "def"
        def_wins += 1
    else:
        r3_winner = "tie"
    rounds.append({
        "name": "⚡ vs ⚔️",
        "atk_stat": f"⚡{r3_atk_base}×{atk_mult}={r3_atk}",
        "def_stat": f"⚔️{r3_def_base}×{def_mult}={r3_def}",
        "atk_val": r3_atk,
        "def_val": r3_def,
        "winner": r3_winner
    })
    
    # 決定最終勝負
    if reversal_triggered:
        # 命運逆轉！弱者反殺強者！
        attacker_wins = True
        reversal_chance = REVERSAL_CHANCE.get(rank_diff, 0) / 10
        final_reason = f"⚡命運逆轉！ ({reversal_chance}%機率)"
    elif atk_wins > def_wins:
        attacker_wins = True
        final_reason = f"回合勝 {atk_wins}:{def_wins}"
    elif def_wins > atk_wins:
        attacker_wins = False
        final_reason = f"回合勝 {atk_wins}:{def_wins}"
    else:
        # 平手：用稀有度 + hash 決定
        rarity_order = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
        atk_rarity_idx = rarity_order.index(attacker.rarity) if attacker.rarity in rarity_order else 0
        def_rarity_idx = rarity_order.index(defender.rarity) if defender.rarity in rarity_order else 0
        
        if atk_rarity_idx > def_rarity_idx:
            attacker_wins = True
            final_reason = "平手，稀有度較高"
        elif def_rarity_idx > atk_rarity_idx:
            attacker_wins = False
            final_reason = "平手，稀有度較高"
        else:
            # 完全平手：用 hash 決定
            roll = int(h[16:20], 16) % 100
            attacker_wins = roll < 50
            final_reason = f"完全平手，命運決定 (roll={roll})"
    
    battle_detail = {
        "rounds": rounds,
        "atk_wins": atk_wins,
        "reversal": reversal_triggered,
        "def_wins": def_wins,
        "attacker_wins": attacker_wins,
        "final_reason": final_reason,
        "hash_used": h[16:20]
    }
    
    return attacker_wins, battle_detail


def format_battle_detail(detail: dict, attacker: Hero, defender: Hero) -> str:
    """格式化戰鬥詳情"""
    lines = ["🎴 *田忌賽馬對決*\n"]
    
    for i, r in enumerate(detail["rounds"], 1):
        if r["winner"] == "atk":
            result = "🔵 攻方勝"
        elif r["winner"] == "def":
            result = "🔴 守方勝"
        else:
            result = "⚪ 平手"
        
        lines.append(f"回合{i}: {r['name']}")
        lines.append(f"  🔵 {r['atk_stat']} vs 🔴 {r['def_stat']} → {result}")
    
    lines.append(f"\n📊 *比分: {detail['atk_wins']}:{detail['def_wins']}*")
    lines.append(f"📝 {detail['final_reason']}")
    
    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════════════
# 鏈上記錄格式（Payload）v0.2
# ═══════════════════════════════════════════════════════════════════════════════
#
# 統一架構：所有 payload 共用核心欄位
#
#   共用欄位：
#   ├─ g: "nami_hero"         # 遊戲標籤（固定）
#   ├─ type: "..."            # birth/pvp/pve/death/...
#   ├─ daa: 380012345         # 命運 DAA（pay_tx 確認後 +1）
#   ├─ pre_tx: "..." | null   # 前一個銘文（出生時 null）
#   ├─ pay_tx: "..."          # 付費交易 ID
#   └─ src: "..."             # 命運區塊 hash
#
#   type 專屬欄位：依 type 擴展
#
# ═══════════════════════════════════════════════════════════════════════════════


def _base_payload(type_: str, daa: int, pre_tx: str = None, 
                  pay_tx: str = None, src: str = None) -> dict:
    """建立基礎 payload（共用欄位）"""
    return {
        "g": "nami_hero",
        "type": type_,
        "daa": daa,
        "pre_tx": pre_tx,
        "pay_tx": pay_tx,
        "src": src
    }


def create_birth_payload(daa: int, hero: Hero, source_hash: str = "",
                         payment_tx: str = None) -> dict:
    """
    v0.3 建立出生 payload
    
    最小化 payload，最大化解釋：
    - 只存 rank（命運塊決定）
    - 職業、屬性由大地之母從 src 解釋
    
    驗證閉環：
    pay_tx → 確認 DAA (N) → 找 DAA > N 的最小存在 DAA 
    → 取該 DAA 官方第一塊 → 驗證 src → rank 自動正確
    """
    payload = _base_payload(
        type_="birth",
        daa=daa,
        pre_tx=None,           # 出生沒有前一個銘文
        pay_tx=payment_tx,     # 付費證明
        src=source_hash        # 命運區塊 hash
    )
    # v0.3: 只存 rank，其他由大地之母解釋
    payload["rank"] = hero.rank
    return payload


def create_event_payload(daa: int, pre_tx: str, action: str, 
                         attacker_id: int, target_id: int, result: str,
                         pay_tx: str = None, src: str = None) -> dict:
    """
    建立事件 payload（通用事件）
    
    專屬欄位：action, attacker, target, result
    """
    payload = _base_payload(
        type_="event",
        daa=daa,
        pre_tx=pre_tx,
        pay_tx=pay_tx,
        src=src
    )
    payload.update({
        "action": action,
        "attacker": attacker_id,
        "target": target_id,
        "result": result
    })
    return payload


def create_state_payload(daa: int, pre_tx: str, hero: Hero) -> dict:
    """
    建立狀態更新 payload（非鏈上，僅本地記錄用）
    
    Note: 狀態更新不上鏈，僅用於本地追蹤
    """
    return {
        "g": "nami_hero",
        "type": "state",
        "daa": daa,
        "pre_tx": pre_tx,
        "card": hero.card_id,
        "status": hero.status,
        "kills": hero.kills,
        "battles": hero.battles
    }


def create_death_payload(hero_id: int, pre_tx: str, reason: str = "burn",
                         killer_id: int = None, battle_tx: str = None,
                         pay_tx: str = None, src: str = None) -> dict:
    """
    建立死亡 payload
    
    專屬欄位：reason, killer, battle_tx
    
    Note: 死亡由大地之母簽發（系統發送）
    """
    payload = _base_payload(
        type_="death",
        daa=hero_id,
        pre_tx=pre_tx,
        pay_tx=pay_tx,
        src=src
    )
    payload.update({
        "reason": reason
    })
    if killer_id:
        payload["killer"] = killer_id
    if battle_tx:
        payload["battle_tx"] = battle_tx
    return payload


def create_pvp_win_payload(hero_id: int, pre_tx: str, target_id: int,
                           payment_tx: str, source_hash: str) -> dict:
    """
    建立 PvP 勝利 payload
    
    專屬欄位：target, kills
    
    Note:
        kills 固定為 1（每個 pvp_win 事件 = 1 次擊殺）
        總擊殺數 = 追鏈後所有 pvp_win 事件的數量
    """
    payload = _base_payload(
        type_="pvp_win",
        daa=hero_id,
        pre_tx=pre_tx,
        pay_tx=payment_tx,
        src=source_hash
    )
    payload.update({
        "target": target_id,
        "kills": 1  # 固定 1，追鏈加總
    })
    return payload

# ═══════════════════════════════════════════════════════════════════════════════
# 遊戲邏輯
# ═══════════════════════════════════════════════════════════════════════════════

# v0.3: 統一使用 MAX_HEROES
MAX_HEROES_PER_USER = MAX_HEROES  # 5 隻

async def summon_hero(user_id: int, username: str, address: str, 
                      daa: int, block_hash: str, pin: str = None,
                      payment_tx_id: str = None) -> Hero:
    """
    召喚英雄（KRC-20/721 風格 Inscription）
    
    新架構：玩家自己打給自己 + payload
    - 真正的 inscription
    - 玩家簽名 = 玩家擁有
    
    新流程（閉環驗證）：
    1. 外部先發 payment_tx
    2. 等待確認，取得 DAA
    3. 找 DAA 之後的第一個官方區塊作為命運區塊
    4. 用命運區塊計算屬性
    5. 發 inscription_tx（包含 payment_tx 證明）
    
    Args:
        user_id: TG 用戶 ID
        username: TG 用戶名
        address: Kaspa 地址
        daa: 命運區塊 DAA
        block_hash: 命運區塊 hash
        pin: 玩家 PIN（用於簽名 inscription）
        payment_tx_id: 已完成的付款 TX ID（新流程）
    
    Returns:
        新召喚的英雄
    
    Raises:
        ValueError: 超過英雄上限
    """
    # 檢查英雄上限
    db = load_heroes_db()
    user_heroes = [h for h in db.get("heroes", {}).values() 
                   if h.get("owner_id") == user_id and h.get("status") == "alive"]
    if len(user_heroes) >= MAX_HEROES_PER_USER:
        raise ValueError(f"英雄數量已達上限（{MAX_HEROES_PER_USER}隻）！請先用 /nami_burn 燒掉不需要的英雄")
    
    # v0.3: 從命運塊計算屬性
    hero_class, rank, atk, def_, spd = calculate_hero_from_hash(block_hash)
    
    # 檢查是否為第一隻英雄（預設保護）
    is_first_hero = len(user_heroes) == 0
    
    # 建立英雄
    hero = Hero(
        card_id=daa,
        owner_id=user_id,
        owner_address=address,
        hero_class=hero_class,
        rank=rank,              # v0.3: 用 rank 取代 rarity
        atk=atk,
        def_=def_,
        spd=spd,
        status="alive",
        latest_daa=daa,
        kills=0,
        battles=0,
        created_at=datetime.now().isoformat(),
        source_hash=block_hash, # 儲存來源區塊 hash（命運塊）
        protected=is_first_hero # v0.3: 第一隻英雄預設保護
    )
    
    # 儲存到資料庫
    db = load_heroes_db()
    db["heroes"][str(daa)] = hero.to_dict()
    
    user_key = str(user_id)
    if user_key not in db["user_heroes"]:
        db["user_heroes"][user_key] = []
    db["user_heroes"][user_key].append(daa)
    
    db["last_summon_daa"] = daa
    db["total_mana_pool"] = db.get("total_mana_pool", 0) + SUMMON_COST
    
    save_heroes_db(db)
    
    # 建立 birth payload（source_hash 已知，payment_tx 稍後由 mint 填入）
    birth_payload = create_birth_payload(daa, hero, source_hash=block_hash)
    
    # 發送到鏈上（方案 A：兩筆交易）
    # 注意：payment_tx_id 可能從參數傳入（新流程）
    inscription_tx_id = None
    tx_id = None  # 用於舊方式（大地之樹代發）
    
    if pin:
        try:
            import unified_wallet
            
            if payment_tx_id:  # 從參數傳入的 payment_tx_id
                # 新流程：付款已在外部完成，只需發 inscription
                logger.info(f"🎴 新流程: payment_tx 已提供 ({payment_tx_id[:16]}...)")
                
                # 加入 pay_tx 到 payload（統一用 pay_tx）
                birth_payload["pay_tx"] = payment_tx_id
                
                inscription_tx_id = await unified_wallet.mint_hero_inscription_only(
                    user_id=user_id,
                    pin=pin,
                    hero_payload=birth_payload
                )
            else:
                # 舊流程：TX1 付費 + TX2 inscription
                payment_tx_id, inscription_tx_id = await unified_wallet.mint_hero_inscription(
                    user_id=user_id,
                    pin=pin,
                    hero_payload=birth_payload,
                    skip_payment=False
                )
            
            hero.tx_id = inscription_tx_id
            hero.latest_tx = inscription_tx_id
            
            logger.info(f"🎴 Hero mint 完成!")
            logger.info(f"   📤 付費 TX: {payment_tx_id}")
            logger.info(f"   📝 Inscription TX: {inscription_tx_id}")
            
            # 更新資料庫
            db["heroes"][str(daa)]["tx_id"] = inscription_tx_id
            db["heroes"][str(daa)]["latest_tx"] = inscription_tx_id
            db["heroes"][str(daa)]["payment_tx"] = payment_tx_id
            save_heroes_db(db)
            
        except Exception as e:
            # 嚴格模式：birth_tx 失敗則刪除英雄記錄
            logger.error(f"Failed to send mint inscription: {e}")
            # 刪除剛創建的本地記錄
            if str(daa) in db["heroes"]:
                del db["heroes"][str(daa)]
            user_key = str(user_id)
            if user_key in db["user_heroes"] and daa in db["user_heroes"][user_key]:
                db["user_heroes"][user_key].remove(daa)
            save_heroes_db(db)
            raise Exception(f"鏈上 birth_tx 發送失敗，英雄未創建: {e}")
    else:
        # 沒有 PIN，嘗試舊方式（大地之樹代發，向後兼容）
        try:
            tx_id = await send_hero_tx_simple(address, birth_payload)
            hero.tx_id = tx_id
            hero.latest_tx = tx_id
            logger.info(f"Hero birth tx sent (tree signed): {tx_id}")
            
            db["heroes"][str(daa)]["tx_id"] = tx_id
            db["heroes"][str(daa)]["latest_tx"] = tx_id
            save_heroes_db(db)
        except Exception as e:
            # 嚴格模式：birth_tx 失敗則刪除英雄記錄
            logger.error(f"Failed to send birth tx: {e}")
            if str(daa) in db["heroes"]:
                del db["heroes"][str(daa)]
            user_key = str(user_id)
            if user_key in db["user_heroes"] and daa in db["user_heroes"][user_key]:
                db["user_heroes"][user_key].remove(daa)
            save_heroes_db(db)
            raise Exception(f"鏈上 birth_tx 發送失敗，英雄未創建: {e}")
    
    # 記錄到本地鏈條（舊系統）
    chain = load_hero_chain()
    final_tx_id = inscription_tx_id if pin else tx_id
    birth_payload["tx_id"] = final_tx_id or ""
    birth_payload["signer"] = "player" if pin else "tree"  # 標記簽名者
    chain.append(birth_payload)
    save_hero_chain(chain)
    
    # 記錄到新的銘文系統（閉環驗證）
    try:
        from inscription_store import save_birth_inscription
        save_birth_inscription(
            hero_id=daa,
            tx_id=final_tx_id or "",
            payment_tx=payment_tx_id or "",
            source_hash=block_hash,
            source_daa=daa,
            payload=birth_payload
        )
    except Exception as e:
        logger.warning(f"銘文記錄失敗（非致命）: {e}")
    
    logger.info(f"Hero summoned: #{daa} {hero.display_class()} {hero.display_rarity()} for user {user_id}")
    
    return hero


async def burn_hero(user_id: int, hero_id: int, pin: str) -> dict:
    """
    銷毀英雄（Burn）
    
    流程：
    1. 驗證擁有權
    2. 創造 death payload
    3. 發送 inscription TX（付 10 mana）
    4. 更新索引
    
    Args:
        user_id: 用戶 ID
        hero_id: 英雄 ID
        pin: PIN 碼
    
    Returns:
        結果 dict
    """
    result = {
        "success": False,
        "hero_id": hero_id,
        "tx_id": None,
        "error": None
    }
    
    # 1. 取得英雄
    hero = get_hero_by_id(hero_id)
    if not hero:
        result["error"] = "找不到此英雄"
        return result
    
    # 2. 驗證擁有權
    if hero.owner_id != user_id:
        result["error"] = "這不是你的英雄"
        return result
    
    # 3. 檢查是否已死亡
    if hero.status == "dead":
        result["error"] = "英雄已經死亡"
        return result
    
    # 4. 取得 pre_tx（當前 latest_tx）
    pre_tx = hero.latest_tx or hero.tx_id or ""
    if not pre_tx:
        result["error"] = "找不到英雄的鏈上記錄"
        return result
    
    # 5. 創造 death payload
    death_payload = create_death_payload(hero_id, pre_tx, reason="burn")
    
    # 6. 發送 inscription TX
    try:
        import unified_wallet
        payment_tx_id, inscription_tx_id = await unified_wallet.mint_hero_inscription(
            user_id=user_id,
            pin=pin,
            hero_payload=death_payload,
            skip_payment=False
        )
        
        result["tx_id"] = inscription_tx_id
        result["payment_tx"] = payment_tx_id
        
    except Exception as e:
        result["error"] = f"交易失敗：{e}"
        return result
    
    # 7. 更新本地資料庫
    db = load_heroes_db()
    db["heroes"][str(hero_id)]["status"] = "dead"
    db["heroes"][str(hero_id)]["latest_tx"] = inscription_tx_id
    db["heroes"][str(hero_id)]["death_reason"] = "burn"
    db["heroes"][str(hero_id)]["death_tx"] = inscription_tx_id
    save_heroes_db(db)
    
    # 8. 記錄到本地鏈條
    chain = load_hero_chain()
    death_payload["tx_id"] = inscription_tx_id
    death_payload["payment_tx"] = payment_tx_id
    chain.append(death_payload)
    save_hero_chain(chain)
    
    logger.info(f"🔥 Hero burned: #{hero_id} by user {user_id}, tx: {inscription_tx_id}")
    
    result["success"] = True
    return result


def get_user_heroes(user_id: int, alive_only: bool = False) -> list[Hero]:
    """取得用戶的英雄列表"""
    db = load_heroes_db()
    user_key = str(user_id)
    
    if user_key not in db["user_heroes"]:
        return []
    
    heroes = []
    for card_id in db["user_heroes"][user_key]:
        hero_data = db["heroes"].get(str(card_id))
        if hero_data:
            hero = Hero.from_dict(hero_data)
            if not alive_only or hero.status == "alive":
                heroes.append(hero)
    
    return heroes

def get_hero_by_id(card_id: int) -> Optional[Hero]:
    """根據 ID 取得英雄"""
    db = load_heroes_db()
    hero_data = db["heroes"].get(str(card_id))
    if hero_data:
        return Hero.from_dict(hero_data)
    return None

async def process_battle(attacker: Hero, defender: Hero, 
                         event_daa: int, result_daa: int, 
                         block_hash: str) -> Tuple[Hero, Hero, bool]:
    """
    處理戰鬥
    
    Args:
        attacker: 攻擊方
        defender: 防守方
        event_daa: 事件 DAA
        result_daa: 結果 DAA
        block_hash: 決定勝負的 hash
    
    Returns:
        (更新後的攻擊方, 更新後的防守方, 攻擊方是否獲勝)
    """
    # 計算勝負
    attacker_wins, battle_detail = calculate_battle_result(attacker, defender, block_hash)
    
    # 更新狀態
    attacker.battles += 1
    defender.battles += 1
    
    from datetime import datetime
    if attacker_wins:
        attacker.kills += 1
        # v0.3: 保護機制 - 受保護的英雄不會死
        if getattr(defender, 'protected', False):
            logger.info(f"🛡️ 防守者 #{defender.card_id} 受保護，免於死亡")
            # 不改變 status
        else:
            defender.status = "dead"
            defender.death_time = datetime.now().isoformat()
        result = "win"
    else:
        defender.kills += 1
        # v0.3: 保護機制 - 受保護的英雄不會死
        if getattr(attacker, 'protected', False):
            logger.info(f"🛡️ 攻擊者 #{attacker.card_id} 受保護，免於死亡")
            # 不改變 status
        else:
            attacker.status = "dead"
            attacker.death_time = datetime.now().isoformat()
        result = "lose"
    
    attacker.latest_daa = result_daa
    defender.latest_daa = result_daa
    
    # 儲存到資料庫（用 merge 保留額外欄位如 name, payment_tx）
    db = load_heroes_db()
    
    # Merge attacker
    attacker_key = str(attacker.card_id)
    if attacker_key in db["heroes"]:
        db["heroes"][attacker_key].update(attacker.to_dict())
    else:
        db["heroes"][attacker_key] = attacker.to_dict()
    
    # Merge defender
    defender_key = str(defender.card_id)
    if defender_key in db["heroes"]:
        db["heroes"][defender_key].update(defender.to_dict())
    else:
        db["heroes"][defender_key] = defender.to_dict()
    
    # PvP 費用加入 mana 池
    pvp_cost = PVP_COST
    db["total_mana_pool"] = db.get("total_mana_pool", 0) + pvp_cost
    
    # v0.3: 計算並派發 PvP 獎勵（從 mana 池扣除）
    pvp_reward = calculate_pvp_reward(block_hash)
    current_pool = db.get("total_mana_pool", 0)
    if current_pool >= pvp_reward:
        db["total_mana_pool"] = current_pool - pvp_reward
        logger.info(f"🎁 PvP 獎勵: {pvp_reward} mana (池剩餘: {db['total_mana_pool']})")
    else:
        pvp_reward = 0  # 池不夠就不派發
        logger.warning(f"⚠️ Mana 池不足，無法派發獎勵")
    
    save_heroes_db(db)
    
    # 記錄事件到鏈條
    chain = load_hero_chain()
    
    # 事件記錄
    chain.append(create_event_payload(
        event_daa, attacker.latest_daa, "pvp",
        attacker.card_id, defender.card_id, result
    ))
    
    # 攻擊方狀態
    chain.append(create_state_payload(result_daa, event_daa, attacker))
    
    # 防守方狀態
    chain.append(create_state_payload(result_daa + 1, event_daa, defender))
    
    save_hero_chain(chain)
    
    logger.info(f"Battle: #{attacker.card_id} vs #{defender.card_id} -> {'attacker wins' if attacker_wins else 'defender wins'}")
    
    return attacker, defender, attacker_wins


async def process_pvp_onchain(
    attacker: Hero,
    defender: Hero,
    attacker_user_id: int,
    attacker_pin: str,
    block_hash: str
) -> dict:
    """
    處理鏈上 PvP 戰鬥
    
    流程：
    1. 攻擊者付費給大地之樹
    2. 計算戰鬥結果
    3. 發送鏈上事件
       - 攻擊者贏：攻擊者發 pvp_win，大地之樹發 death 給防守者
       - 攻擊者輸：大地之樹發 death 給攻擊者
    4. 更新本地資料庫
    
    Returns:
        {
            "attacker_wins": bool,
            "winner": Hero,
            "loser": Hero,
            "payment_tx": str,
            "win_tx": str (if attacker wins),
            "death_tx": str
        }
    """
    import unified_wallet
    from datetime import datetime
    
    result = {
        "attacker_wins": False,
        "payment_tx": None,
        "win_tx": None,
        "death_tx": None
    }
    
    # 1. 計算戰鬥結果（v0.4 ATB 系統）
    attacker_wins, battle_detail = calculate_battle_result_atb(attacker, defender, block_hash)
    result["attacker_wins"] = attacker_wins
    result["battle_detail"] = battle_detail
    
    # 2. 取得 PvP 費用
    pvp_cost = PVP_COST
    pvp_cost_sompi = int(pvp_cost * 1e8)
    
    # 3. 攻擊者付費給大地之樹
    logger.info(f"⚔️ PvP: #{attacker.card_id} vs #{defender.card_id}")
    logger.info(f"   付費 {pvp_cost} mana 給大地之樹...")
    
    payment_tx = await unified_wallet.send_to_tree(
        user_id=attacker_user_id,
        pin=attacker_pin,
        amount=pvp_cost_sompi
    )
    result["payment_tx"] = payment_tx
    logger.info(f"   付費 TX: {payment_tx}")
    
    # 等待 UTXO 更新（避免 mempool 衝突）
    import asyncio
    logger.info(f"   ⏳ 等待 UTXO 確認...")
    await asyncio.sleep(10)  # 增加等待時間確保 UTXO 更新
    
    # 4. 更新狀態
    attacker.battles += 1
    defender.battles += 1
    
    # v0.3: 計算 PvP 獎勵
    pvp_reward = calculate_pvp_reward(block_hash)
    result["pvp_reward"] = pvp_reward
    
    if attacker_wins:
        attacker.kills += 1
        
        # v0.3: 保護機制檢查
        defender_protected = getattr(defender, 'protected', False)
        if defender_protected:
            logger.info(f"🛡️ 防守者 #{defender.card_id} 受保護，免於死亡")
            result["defender_protected"] = True
        else:
            defender.status = "dead"
            defender.death_time = datetime.now().isoformat()
            result["defender_protected"] = False
            
        result["winner"] = attacker
        result["loser"] = defender
        
        # 5a. 攻擊者贏 - 發送 pvp_win 事件
        logger.info(f"   ✅ 攻擊者勝利！發送 pvp_win 事件...")
        
        # 保存舊的 latest_tx（用於銘文記錄的 pre_tx）
        attacker_old_ltx = attacker.latest_tx or attacker.tx_id or ""
        defender_old_ltx = defender.latest_tx or defender.tx_id or ""
        
        win_payload = create_pvp_win_payload(
            hero_id=attacker.card_id,
            pre_tx=attacker_old_ltx,
            target_id=defender.card_id,
            payment_tx=payment_tx,
            source_hash=block_hash
        )
        
        # 攻擊者簽名發送 win 事件
        _, win_tx = await unified_wallet.mint_hero_inscription(
            user_id=attacker_user_id,
            pin=attacker_pin,
            hero_payload=win_payload,
            skip_payment=True
        )
        result["win_tx"] = win_tx
        attacker.latest_tx = win_tx
        logger.info(f"   Win TX: {win_tx}")
        
        # 等待 UTXO 確認（大地之樹需要發死亡交易）
        logger.info(f"   ⏳ 等待 UTXO 確認...")
        await asyncio.sleep(5)
        
        # 6a. 大地之樹發送死亡事件給防守者（如果沒受保護）
        if not defender_protected:
            logger.info(f"   🌲 大地之樹發送死亡事件給 #{defender.card_id}...")
            
            death_payload = create_death_payload(
                hero_id=defender.card_id,
                pre_tx=defender.latest_tx or "",
                reason="pvp",
                killer_id=attacker.card_id,
                battle_tx=win_tx
            )
            
            from kaspa_tx import send_payload_tx
            death_tx = await send_payload_tx(death_payload)
            result["death_tx"] = death_tx
            defender.latest_tx = death_tx
            defender.death_tx = death_tx
            defender.death_reason = "pvp"
            defender.ltx = death_tx
            logger.info(f"   Death TX: {death_tx}")
            
            # 記錄到 hero_chain
            chain = load_hero_chain()
            death_payload["tx_id"] = death_tx
            death_payload["signer"] = "tree"
            chain.append(death_payload)
            save_hero_chain(chain)
            logger.info(f"   ✅ 死亡事件已記錄到 hero_chain")
        else:
            logger.info(f"   🛡️ 防守者受保護，跳過死亡事件")
        
        # 記錄銘文（攻擊者勝利 + 防守者死亡，如果沒受保護）
        try:
            from inscription_store import save_event_inscription, save_death_inscription
            # 攻擊者的勝利事件（使用保存的舊 ltx）
            save_event_inscription(
                hero_id=attacker.card_id,
                event_type="pvp_win",
                tx_id=win_tx,
                pre_tx=attacker_old_ltx,
                payment_tx=payment_tx,
                source_hash=block_hash,
                target_id=defender.card_id
            )
            # 防守者的死亡（只有沒受保護時，使用保存的舊 ltx）
            if not defender_protected:
                save_death_inscription(
                    hero_id=defender.card_id,
                    tx_id=death_tx,
                    pre_tx=defender_old_ltx,
                    reason="pvp",
                    killer_id=attacker.card_id,
                    battle_tx=win_tx
                )
        except Exception as e:
            logger.warning(f"銘文記錄失敗（非致命）: {e}")
        
    else:
        defender.kills += 1
        
        # v0.3: 保護機制檢查
        attacker_protected = getattr(attacker, 'protected', False)
        if attacker_protected:
            logger.info(f"🛡️ 攻擊者 #{attacker.card_id} 受保護，免於死亡")
            result["attacker_protected"] = True
        else:
            attacker.status = "dead"
            attacker.death_time = datetime.now().isoformat()
            result["attacker_protected"] = False
            
        result["winner"] = defender
        result["loser"] = attacker
        
        # 5b. 攻擊者輸 - 大地之樹發送死亡事件給攻擊者（如果沒受保護）
        # 保存舊的 latest_tx（用於銘文記錄的 pre_tx）
        attacker_old_ltx = attacker.latest_tx or attacker.tx_id or ""
        defender_old_ltx = defender.latest_tx or defender.tx_id or ""
        
        if not attacker_protected:
            logger.info(f"   ❌ 攻擊者落敗！🌲 大地之樹發送死亡事件...")
            
            death_payload = create_death_payload(
                hero_id=attacker.card_id,
                pre_tx=attacker_old_ltx,
                reason="pvp",
                killer_id=defender.card_id,
                battle_tx=payment_tx  # 用付款 TX 作為戰鬥證明
            )
            death_payload["src"] = block_hash  # 加入命運區塊
            
            from kaspa_tx import send_payload_tx
            death_tx = await send_payload_tx(death_payload)
            result["death_tx"] = death_tx
            attacker.latest_tx = death_tx
            attacker.death_tx = death_tx
            attacker.death_reason = "pvp"
            attacker.ltx = death_tx
            logger.info(f"   Death TX: {death_tx}")
            
            # 記錄到 hero_chain
            chain = load_hero_chain()
            death_payload["tx_id"] = death_tx
            death_payload["signer"] = "tree"
            chain.append(death_payload)
            save_hero_chain(chain)
            logger.info(f"   ✅ 死亡事件已記錄到 hero_chain")
            
            # 記錄銘文（防守者勝利 + 攻擊者死亡，使用保存的舊 ltx）
            try:
                from inscription_store import save_event_inscription, save_death_inscription
                # 防守者的勝利事件
                save_event_inscription(
                    hero_id=defender.card_id,
                    event_type="pvp_win",
                    tx_id=payment_tx,  # 用付款 TX 作為證明
                    pre_tx=defender_old_ltx,
                    source_hash=block_hash,
                    target_id=attacker.card_id
                )
                # 攻擊者的死亡
                save_death_inscription(
                    hero_id=attacker.card_id,
                    tx_id=death_tx,
                    pre_tx=attacker_old_ltx,
                    reason="pvp",
                    killer_id=defender.card_id,
                    battle_tx=payment_tx
                )
            except Exception as e:
                logger.warning(f"銘文記錄失敗（非致命）: {e}")
        else:
            logger.info(f"   🛡️ 攻擊者受保護，跳過死亡事件")
    
    # 7. 更新本地資料庫（用 merge 保留額外欄位如 name, payment_tx, source_hash）
    db = load_heroes_db()
    
    # Merge attacker
    attacker_key = str(attacker.card_id)
    if attacker_key in db["heroes"]:
        db["heroes"][attacker_key].update(attacker.to_dict())
    else:
        db["heroes"][attacker_key] = attacker.to_dict()
    
    # Merge defender
    defender_key = str(defender.card_id)
    if defender_key in db["heroes"]:
        db["heroes"][defender_key].update(defender.to_dict())
    else:
        db["heroes"][defender_key] = defender.to_dict()
    
    # v0.3: PvP 費用加入 mana 池
    db["total_mana_pool"] = db.get("total_mana_pool", 0) + pvp_cost
    
    # v0.3: 從 mana 池扣除獎勵（勝者領取）
    current_pool = db.get("total_mana_pool", 0)
    if current_pool >= pvp_reward:
        db["total_mana_pool"] = current_pool - pvp_reward
        result["reward_paid"] = True
        logger.info(f"🎁 PvP 獎勵: {pvp_reward} mana 從池中扣除 (剩餘: {db['total_mana_pool']})")
    else:
        result["reward_paid"] = False
        result["pvp_reward"] = 0
        logger.warning(f"⚠️ Mana 池不足 ({current_pool})，無法派發獎勵")
    
    save_heroes_db(db)
    
    # v0.3: 發獎勵給勝者
    if result.get("reward_paid") and pvp_reward > 0:
        winner = result.get("winner")
        if winner and winner.owner_address:
            try:
                reward_amount = pvp_reward * 100_000_000  # 轉換為 sompi
                reward_tx = await unified_wallet.send_from_tree(
                    to_address=winner.owner_address,
                    amount=reward_amount,
                    memo=f"pvp_reward:{winner.card_id}"
                )
                result["reward_tx"] = reward_tx
                logger.info(f"🎁 獎勵已發送: {pvp_reward} mana -> {winner.owner_address[:20]}... TX: {reward_tx[:20]}...")
            except Exception as e:
                logger.error(f"❌ 發獎失敗: {e}")
                result["reward_tx"] = None
                result["reward_error"] = str(e)
    
    logger.info(f"⚔️ PvP 完成: #{attacker.card_id} vs #{defender.card_id} -> {'攻擊者勝' if attacker_wins else '防守者勝'}")
    
    return result


def get_game_stats() -> dict:
    """取得遊戲統計"""
    db = load_heroes_db()
    
    total_heroes = len(db.get("heroes", {}))
    alive_heroes = sum(1 for h in db.get("heroes", {}).values() if h.get("status") == "alive")
    dead_heroes = total_heroes - alive_heroes
    
    total_players = len(db.get("user_heroes", {}))
    mana_pool = db.get("total_mana_pool", 0)
    
    # 稀有度統計
    rarity_counts = {"common": 0, "uncommon": 0, "rare": 0, "epic": 0, "legendary": 0}
    for hero in db.get("heroes", {}).values():
        r = hero.get("rarity", "common")
        rarity_counts[r] = rarity_counts.get(r, 0) + 1
    
    return {
        "total_heroes": total_heroes,
        "alive_heroes": alive_heroes,
        "dead_heroes": dead_heroes,
        "total_players": total_players,
        "mana_pool": mana_pool,
        "rarity_counts": rarity_counts
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 格式化輸出
# ═══════════════════════════════════════════════════════════════════════════════

def format_hero_card(hero: Hero) -> str:
    """
    v0.3: 格式化英雄卡片顯示（HTML 格式）
    
    顯示格式：
    💎⭐⭐⭐⭐ SSR 極稀 - 戰士 ⚔️
    """
    from datetime import datetime
    
    status_icon = "🟢" if hero.status == "alive" else "☠️"
    protected_icon = "🛡️" if getattr(hero, 'protected', False) else ""
    
    # v0.3: Rank 顯示（星星 + 等級 + 中文）
    rank_display = get_rank_display(hero.rank)
    class_name = get_class_name(hero.hero_class)
    class_emoji = get_class_emoji(hero.hero_class)
    title_line = f"{rank_display} - {class_name} {class_emoji}"
    
    # 計算生存時間
    age_str = ""
    if hero.created_at:
        try:
            created = datetime.fromisoformat(hero.created_at)
            if hero.status == "alive":
                age = datetime.now() - created
            else:
                # 死亡的英雄用 death_time 或現在
                death_time = getattr(hero, 'death_time', None)
                if death_time:
                    age = datetime.fromisoformat(death_time) - created
                else:
                    age = datetime.now() - created
            
            days = age.days
            hours = age.seconds // 3600
            if days > 0:
                age_str = f"⏳ {days}天{hours}時"
            else:
                minutes = (age.seconds % 3600) // 60
                age_str = f"⏳ {hours}時{minutes}分"
        except:
            age_str = ""
    
    # Explorer link (HTML 格式)
    explorer_link = ""
    if hero.source_hash:
        explorer_link = f'\n🔗 <a href="https://explorer-tn10.kaspa.org/blocks/{hero.source_hash}">區塊瀏覽器</a>'
    
    # 取得名字（如果有）
    db = load_heroes_db()
    hero_data = db.get("heroes", {}).get(str(hero.card_id), {})
    hero_name = hero_data.get("name")
    name_display = f"「{hero_name}」" if hero_name else ""
    
    return f"""🎴 英雄 #{hero.card_id} {name_display}

{title_line}

⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}

{status_icon} {hero.status} | ⚔️ {hero.battles}戰 {hero.kills}殺 {age_str}

📍 命運: DAA <code>{hero.card_id}</code>{explorer_link}

快速指令：
<pre>/nami_verify {hero.card_id}</pre>
<pre>/nami_payload {hero.card_id}</pre>"""

def format_hero_list(heroes: list[Hero]) -> str:
    """
    v0.3: 格式化英雄列表（Markdown 格式）
    
    顯示格式：
    🟢🛡️ #123456 💎⭐⭐⭐⭐ SSR 戰士⚔️ 3殺 ⏳2d
    """
    from datetime import datetime
    
    if not heroes:
        return "📜 你還沒有英雄\n\n使用 `/nh` 召喚你的第一位英雄！"
    
    alive = [h for h in heroes if h.status == "alive"]
    dead = [h for h in heroes if h.status == "dead"]
    
    def get_age_str(h):
        """計算生存時間字串"""
        if not h.created_at:
            return ""
        try:
            created = datetime.fromisoformat(h.created_at)
            if h.status == "alive":
                age = datetime.now() - created
            else:
                if h.death_time:
                    age = datetime.fromisoformat(h.death_time) - created
                else:
                    age = datetime.now() - created
            days = age.days
            hours = age.seconds // 3600
            if days > 0:
                return f"⏳{days}d"
            else:
                return f"⏳{hours}h"
        except:
            return ""
    
    # v0.3: 上限改為 5
    lines = [f"📜 你的英雄 ({len(alive)}/{MAX_HEROES} 存活 | {len(dead)} 陣亡)\n"]
    
    for h in alive:
        # v0.3: 使用 Rank 顯示
        rank_stars = get_rank_stars(h.rank)
        class_name = get_class_name(h.hero_class)
        class_emoji = get_class_emoji(h.hero_class)
        age = get_age_str(h)
        # v0.3: 顯示保護狀態
        protected = "🛡️" if getattr(h, 'protected', False) else ""
        name_part = f"「{h.name}」" if h.name else ""
        lines.append(f"🟢{protected} `#{h.card_id}` {rank_stars} {h.rank} {class_name}{class_emoji} {name_part} {h.kills}殺 {age}")
    
    for h in dead:
        rank_stars = get_rank_stars(h.rank)
        class_name = get_class_name(h.hero_class)
        class_emoji = get_class_emoji(h.hero_class)
        age = get_age_str(h)
        name_part = f"「{h.name}」" if h.name else ""
        lines.append(f"☠️ `#{h.card_id}` {rank_stars} {h.rank} {class_name}{class_emoji} {name_part} {age}")
    
    lines.append("\n━━━━━━━━━━━━")
    lines.append("🛡️ = 受保護（PvP輸了不死）")
    lines.append("━━━━━━━━━━━━")
    lines.append("\n查看詳情：`/ni <ID>`")
    lines.append("設定保護：`/nhp <ID>`")
    
    return "\n".join(lines)

def get_class_emoji(hero_class: str) -> str:
    """獲取職業 emoji"""
    emoji_map = {"warrior": "⚔️", "mage": "🔮", "archer": "🏹", "rogue": "🗡️"}
    return emoji_map.get(hero_class, "🎴")

def get_class_name(hero_class: str) -> str:
    """獲取職業中文名"""
    name_map = {"warrior": "戰士", "mage": "魔法師", "archer": "弓箭手", "rogue": "盜賊"}
    return name_map.get(hero_class, hero_class)

def get_rarity_display(rarity: str) -> str:
    """
    獲取稀有度/Rank 顯示
    
    v0.3: 支援新舊兩種格式
    """
    display_map = {
        # v0.3 Rank
        "N": "⭐ N 普通",
        "R": "⭐⭐ R 稀有",
        "SR": "⭐⭐⭐ SR 超稀",
        "SSR": "💎⭐⭐⭐⭐ SSR 極稀",
        "UR": "✨⭐⭐⭐⭐⭐ UR 傳說",
        "LR": "🔱⭐⭐⭐⭐⭐⭐ LR 神話",
        # 舊版向後相容
        "common": "⚪普通",
        "uncommon": "🟢優秀",
        "rare": "🔵稀有", 
        "epic": "🟣👑史詩",
        "legendary": "🟡✨傳說",
        "mythic": "🔴🔱神話"
    }
    return display_map.get(rarity, rarity)

def format_summon_result(hero: Hero) -> str:
    """
    v0.3: 格式化召喚結果（星星顯示）
    """
    # v0.3 特效標題（手遊風格）
    rank = hero.rank
    if rank == "LR":
        header = "🔱🔱🔱 ⚡ 神話降世！！！ ⚡ 🔱🔱🔱\n\n🌊 大地之樹震動！傳說現世！\n\n"
    elif rank == "UR":
        header = "✨✨✨ 傳說降臨！✨✨✨\n\n"
    elif rank == "SSR":
        header = "💎💎 極稀出現！💎💎\n\n"
    elif rank == "SR":
        header = "⭐⭐⭐ 超稀！\n\n"
    elif rank == "R":
        header = "⭐⭐ 稀有！\n\n"
    else:
        header = ""
    
    # v0.3: Rank + 職業 顯示
    rank_display = get_rank_display(rank)
    class_name = get_class_name(hero.hero_class)
    class_emoji = get_class_emoji(hero.hero_class)
    title_line = f"{rank_display} - {class_name} {class_emoji}"
    
    # 保護狀態
    protected_note = ""
    if getattr(hero, 'protected', False):
        protected_note = "🛡️ *已受大地之母保護*\n\n"
    
    # 區塊瀏覽器連結 (純 URL，Telegram 會自動偵測)
    explorer_link = ""
    if hero.source_hash:
        explorer_link = f'🔗 命運區塊:\nhttps://explorer-tn10.kaspa.org/blocks/{hero.source_hash}'
    
    # v0.3: 簡化版 payload 顯示（只有 rank）
    payload_preview = f'{{"g":"nami_hero","type":"birth","rank":"{rank}","daa":{hero.card_id}}}'
    
    # 鏈上交易連結
    tx_links = ""
    inscription_note = ""
    
    if hasattr(hero, 'tx_id') and hero.tx_id and not hero.tx_id.startswith('daa_'):
        tx_links = f'📝 銘文:\nhttps://explorer-tn10.kaspa.org/txs/{hero.tx_id}'
        inscription_note = ""
    else:
        tx_links = "⚠️ *鏈上銘文發送失敗*"
        inscription_note = f"💡 使用 `/nami_remint {hero.card_id} <PIN>` 補發"
    
    return f"""🎴 召喚成功！

{header}{title_line}

⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}

{protected_note}📍 命運: DAA {hero.card_id}
{explorer_link}

{tx_links}
{inscription_note}

英雄 ID: `#{hero.card_id}`

快速指令：
```
/nami_verify {hero.tx_id if hasattr(hero, 'tx_id') and hero.tx_id and not hero.tx_id.startswith('daa_') else hero.card_id}
```"""

def format_battle_result(attacker: Hero, defender: Hero, 
                         attacker_wins: bool, attacker_name: str, 
                         defender_name: str) -> str:
    """格式化戰鬥結果"""
    # 格式化雙方顯示
    def hero_line(h: Hero) -> str:
        rarity = get_rarity_display(h.rarity)
        class_name = get_class_name(h.hero_class)
        class_emoji = get_class_emoji(h.hero_class)
        return f"#{h.card_id} {rarity} - {class_name} {class_emoji}"
    
    if attacker_wins:
        return f"""⚔️ 戰鬥結果！

🏆 勝者：@{attacker_name}
{hero_line(attacker)}

☠️ 敗者：@{defender_name}
{hero_line(defender)}
→ 英雄陣亡！"""
    else:
        return f"""⚔️ 戰鬥結果！

🛡️ 逆轉！

☠️ 敗者：@{attacker_name}
{hero_line(attacker)}
→ 英雄陣亡！

🏆 勝者：@{defender_name}
{hero_line(defender)}"""

# ═══════════════════════════════════════════════════════════════════════════════
# 驗證功能
# ═══════════════════════════════════════════════════════════════════════════════

async def verify_hero(card_id: int) -> dict:
    """
    驗證英雄資料（使用儲存的來源 hash）
    
    Args:
        card_id: 英雄 ID (DAA)
    
    Returns:
        驗證結果 dict
    """
    result = {
        "card_id": card_id,
        "verified": False,
        "local_data": None,
        "chain_data": None,
        "errors": []
    }
    
    # 1. 取得本地資料
    hero = get_hero_by_id(card_id)
    if not hero:
        result["errors"].append("本地找不到此英雄")
        return result
    
    result["local_data"] = hero.to_dict()
    
    # 2. 檢查是否有儲存來源 hash
    source_hash = hero.source_hash
    if not source_hash:
        result["errors"].append("此英雄沒有儲存來源區塊 hash（舊版資料）")
        return result
    
    # 3. 用儲存的 hash 重新計算屬性
    try:
        hero_class, rarity, atk, def_, spd = calculate_hero_from_hash(source_hash)
        
        result["chain_data"] = {
            "source_daa": card_id,
            "block_hash": source_hash,
            "explorer_url": f"https://explorer-tn10.kaspa.org/blocks/{source_hash}",
            "calculated": {
                "hero_class": hero_class,
                "rarity": rarity,
                "atk": atk,
                "def": def_,
                "spd": spd
            }
        }
        
        # 4. 比對
        local = result["local_data"]
        calc = result["chain_data"]["calculated"]
        
        if (local["hero_class"] == calc["hero_class"] and
            local["rarity"] == calc["rarity"] and
            local["atk"] == calc["atk"] and
            local["def"] == calc["def"] and
            local["spd"] == calc["spd"]):
            result["verified"] = True
        else:
            result["errors"].append("屬性不匹配！可能資料被竄改")
            
    except Exception as e:
        result["errors"].append(f"驗證失敗: {e}")
    
    return result

def format_verify_result(result: dict) -> str:
    """格式化驗證結果"""
    card_id = result["card_id"]
    
    if result["verified"]:
        local = result["local_data"]
        chain = result["chain_data"]
        explorer_url = chain.get("explorer_url", "")
        
        return f"""🔍 驗證英雄 #{card_id}

✅ *驗證通過！*

📦 *本地資料：*
職業：{local['hero_class']}
稀有度：{local['rarity']}
攻/防/速：{local['atk']}/{local['def']}/{local['spd']}

⛓️ *鏈上來源：*
DAA: {chain['source_daa']}
Block: `{chain['block_hash'][:16]}...`

🔢 *重新計算：*
職業：{chain['calculated']['hero_class']} ✓
稀有度：{chain['calculated']['rarity']} ✓
攻/防/速：{chain['calculated']['atk']}/{chain['calculated']['def']}/{chain['calculated']['spd']} ✓

🔗 [區塊瀏覽器]({explorer_url})

*公平性驗證通過！數據來自區塊鏈！*"""
    
    else:
        errors = "\n".join(f"• {e}" for e in result.get("errors", ["未知錯誤"]))
        return f"""🔍 驗證英雄 #{card_id}

❌ *驗證失敗*

{errors}"""


# ═══════════════════════════════════════════════════════════════════════════════
# 鏈上完整驗證
# ═══════════════════════════════════════════════════════════════════════════════

TREE_ADDRESS = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

async def verify_from_tx(tx_id: str) -> dict:
    """
    從鏈上 TX 完整驗證英雄
    
    流程：
    1. 從 TX 取得 payload
    2. 解析 payload 取得 src（來源區塊 hash）
    3. 用 src 重算屬性
    4. 比對 payload 中的 c/r/a/d/s
    5. 如果有 payment_tx，驗證付款給大地之樹
    
    Args:
        tx_id: 銘文交易 ID
    
    Returns:
        驗證結果 dict
    """
    import aiohttp
    import json as json_lib
    
    result = {
        "tx_id": tx_id,
        "verified": False,
        "payload": None,
        "calculated": None,
        "payment_verified": None,
        "errors": [],
        "checks": []
    }
    
    # 1. 從 API 取得 TX
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api-tn10.kaspa.org/transactions/{tx_id}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    result["errors"].append(f"找不到交易：{tx_id[:16]}...")
                    return result
                tx_data = await resp.json()
    except Exception as e:
        result["errors"].append(f"查詢交易失敗：{e}")
        return result
    
    # 2. 解碼 payload
    payload_hex = tx_data.get("payload", "")
    if not payload_hex:
        result["errors"].append("交易沒有 payload")
        return result
    
    try:
        payload_bytes = bytes.fromhex(payload_hex)
        payload = json_lib.loads(payload_bytes.decode('utf-8'))
        result["payload"] = payload
    except Exception as e:
        result["errors"].append(f"Payload 解碼失敗：{e}")
        return result
    
    # 3. 檢查是否為 nami_hero
    if payload.get("g") != "nami_hero":
        result["errors"].append("不是 Nami Hero 銘文")
        return result
    
    result["checks"].append("✓ Nami Hero 銘文")
    
    # 4. 取得來源 hash 並驗證屬性
    source_hash = payload.get("src", "")
    if source_hash:
        try:
            hero_class, rank, atk, def_, spd = calculate_hero_from_hash(source_hash)
            result["calculated"] = {
                "hero_class": hero_class,
                "rank": rank,
                "atk": atk,
                "def": def_,
                "spd": spd
            }
            
            # v0.3: 檢查 rank 欄位
            p_rank = payload.get("rank")
            if p_rank:
                # v0.3 格式：只驗證 rank（其他由大地之母解釋）
                if p_rank == rank:
                    result["checks"].append(f"✓ Rank 驗證通過 ({rank})")
                    result["checks"].append(f"✓ 大地之母解釋：{hero_class}/{atk}/{def_}/{spd}")
                else:
                    result["errors"].append(f"Rank 不匹配！payload: {p_rank}, 計算: {rank}")
                    return result
            else:
                # v0.2 格式：檢查 c/r/a/d/s
                p_class = payload.get("c")
                p_rarity = payload.get("r")
                
                # 轉換為一致格式比對
                if (str(p_class) == str(hero_class) and 
                    str(p_rarity) == str(rank) and
                    payload.get("a") == atk and
                    payload.get("d") == def_ and
                    payload.get("s") == spd):
                    result["checks"].append("✓ 屬性驗證通過 (v0.2)")
                else:
                    result["errors"].append(f"屬性不匹配！payload: {p_class}/{p_rarity}/{payload.get('a')}/{payload.get('d')}/{payload.get('s')}, 計算: {hero_class}/{rank}/{atk}/{def_}/{spd}")
                    return result
        except Exception as e:
            result["errors"].append(f"屬性驗證失敗：{e}")
            return result
    else:
        result["checks"].append("⚠ 舊版格式，無來源 hash（無法重算驗證）")
    
    # 5. 驗證付款（支援新舊格式：pay_tx / payment_tx）
    payment_tx = payload.get("pay_tx") or payload.get("payment_tx", "")
    if payment_tx:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api-tn10.kaspa.org/transactions/{payment_tx}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        pay_data = await resp.json()
                        
                        # 檢查是否有付給大地之樹
                        outputs = pay_data.get("outputs", [])
                        paid_to_tree = False
                        paid_amount = 0
                        
                        for out in outputs:
                            addr = out.get("script_public_key_address", "")
                            if addr == TREE_ADDRESS:
                                paid_to_tree = True
                                paid_amount = out.get("amount", 0)
                                break
                        
                        if paid_to_tree:
                            result["payment_verified"] = True
                            result["payment_amount"] = paid_amount / 1e8
                            result["checks"].append(f"✓ 付款驗證通過（{paid_amount / 1e8:.2f} tKAS → 大地之樹）")
                        else:
                            result["payment_verified"] = False
                            result["checks"].append("✗ 付款交易未付給大地之樹")
                    else:
                        result["checks"].append("⚠ 付款交易查詢失敗")
        except Exception as e:
            result["checks"].append(f"⚠ 付款驗證失敗：{e}")
    else:
        result["checks"].append("⚠ 無付款記錄")
    
    # 判斷最終結果
    if not result["errors"]:
        if source_hash and result.get("payment_verified"):
            result["verified"] = True
            result["verdict"] = "🎉 正卡"
        elif source_hash:
            result["verdict"] = "⚠️ 屬性正確，但付款未驗證"
        elif result.get("payment_verified"):
            result["verdict"] = "⚠️ 已付款，但舊版格式無法驗證屬性"
        else:
            result["verdict"] = "⚠️ 舊版格式，無法完整驗證"
    
    return result


def format_tx_verify_result(result: dict) -> str:
    """格式化 TX 驗證結果"""
    tx_id = result["tx_id"]
    
    if result.get("errors"):
        errors = "\n".join(f"• {e}" for e in result["errors"])
        return f"""🔍 驗證銘文

TX: `{tx_id[:32]}...`

❌ *驗證失敗*

{errors}"""
    
    payload = result.get("payload", {})
    calculated = result.get("calculated", {})
    checks = "\n".join(result.get("checks", []))
    verdict = result.get("verdict", "")
    
    # 英雄資訊
    daa = payload.get("daa", "?")
    
    # v0.3: 從 calculated 取得屬性（大地之母解釋）
    if calculated:
        hero_class = calculated.get("hero_class", "?")
        rank = calculated.get("rank", payload.get("rank", "?"))
        atk = calculated.get("atk", "?")
        def_ = calculated.get("def", "?")
        spd = calculated.get("spd", "?")
    else:
        # v0.2 格式
        hero_class = payload.get("c", "?")
        rank = payload.get("r", payload.get("rank", "?"))
        atk = payload.get("a", "?")
        def_ = payload.get("d", "?")
        spd = payload.get("s", "?")
    
    # 翻譯對照
    class_names = {"warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}
    rank_names = {
        # v0.3 Rank
        "N": "⭐ N 普通", "R": "⭐⭐ R 稀有", "SR": "⭐⭐⭐ SR 超稀",
        "SSR": "💎 SSR 極稀", "UR": "✨ UR 傳說", "LR": "🔱 LR 神話",
        # v0.2 向後相容
        "common": "普通", "uncommon": "優秀", "rare": "稀有",
        "epic": "史詩", "legendary": "傳說", "mythic": "神話"
    }
    class_zh = class_names.get(hero_class, hero_class)
    rank_zh = rank_names.get(rank, rank)
    
    return f"""🔍 驗證銘文

TX: `{tx_id[:32]}...`

📦 *Payload 內容：*
• 英雄 ID: #{daa}
• Rank: {rank_zh}
• 職業: {class_zh}（大地之母解釋）
• 屬性: ⚔️{atk} 🛡️{def_} ⚡{spd}

🔬 *驗證項目：*
{checks}

{verdict}

🔗 [區塊瀏覽器](https://explorer-tn10.kaspa.org/txs/{tx_id})"""


async def verify_hero_by_id(hero_id: int) -> dict:
    """
    從英雄 ID 完整驗證（追蹤整條鏈）
    
    流程：
    1. 從本地索引拿 latest_tx
    2. 從 latest_tx 往回追 pre_tx
    3. 追到 birth（pre_tx 為空）
    4. 每層都驗證 payment_tx
    5. 驗證 birth 的屬性
    
    Returns:
        完整驗證結果
    """
    import aiohttp
    import json as json_lib
    
    result = {
        "hero_id": hero_id,
        "verified": False,
        "is_dead": False,
        "death_reason": None,
        "chain": [],  # 所有 TX 的 payload
        "birth_payload": None,
        "checks": [],
        "errors": []
    }
    
    # 1. 從本地索引拿 latest_tx
    hero = get_hero_by_id(hero_id)
    if not hero:
        result["errors"].append("找不到此英雄")
        return result
    
    latest_tx = hero.latest_tx or hero.tx_id
    if not latest_tx or latest_tx.startswith('daa_'):
        result["errors"].append("此英雄沒有鏈上記錄")
        return result
    
    result["latest_tx"] = latest_tx
    result["local_status"] = hero.status
    
    # 2. 從 latest_tx 往回追蹤
    current_tx = latest_tx
    visited = set()
    
    timeout = aiohttp.ClientTimeout(total=15)  # 15 秒超時
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while current_tx and current_tx not in visited:
            visited.add(current_tx)
            
            # 讀取 TX（帶重試）
            tx_data = None
            for retry in range(2):
                try:
                    url = f"https://api-tn10.kaspa.org/transactions/{current_tx}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            tx_data = await resp.json()
                            break
                        elif resp.status == 404:
                            result["errors"].append(f"未找到出生記錄")
                            break
                except asyncio.TimeoutError:
                    if retry == 0:
                        continue  # 重試一次
                    result["errors"].append(f"API 超時，請稍後再試")
                    break
                except Exception as e:
                    result["errors"].append(f"網路錯誤：{e}")
                    break
            
            if not tx_data:
                break
            
            # 解碼 payload
            payload_hex = tx_data.get("payload", "")
            if not payload_hex:
                result["errors"].append(f"交易 {current_tx[:16]}... 沒有 payload")
                break
            
            try:
                payload = json_lib.loads(bytes.fromhex(payload_hex).decode('utf-8'))
                payload["_tx_id"] = current_tx
                result["chain"].append(payload)
            except Exception as e:
                result["errors"].append(f"Payload 解碼失敗：{e}")
                break
            
            # 檢查類型
            tx_type = payload.get("type", "")
            
            if tx_type == "death":
                result["is_dead"] = True
                result["death_reason"] = payload.get("reason", "unknown")
                result["checks"].append(f"☠️ 死亡事件：{payload.get('reason', 'unknown')}")
            elif tx_type == "birth":
                result["birth_payload"] = payload
                result["checks"].append("🎒 找到出生記錄")
            elif tx_type == "event":
                result["checks"].append(f"⚔️ 事件：{payload.get('action', 'unknown')}")
            
            # 驗證 payment_tx（支援新舊格式）
            payment_tx = payload.get("pay_tx") or payload.get("payment_tx", "")
            if payment_tx:
                try:
                    pay_url = f"https://api-tn10.kaspa.org/transactions/{payment_tx}"
                    async with session.get(pay_url) as pay_resp:
                        if pay_resp.status == 200:
                            pay_data = await pay_resp.json()
                            outputs = pay_data.get("outputs", [])
                            paid_to_tree = any(
                                out.get("script_public_key_address") == TREE_ADDRESS
                                for out in outputs
                            )
                            if paid_to_tree:
                                result["checks"].append(f"✓ 付款驗證通過")
                            else:
                                result["checks"].append(f"✗ 付款未付給大地之樹")
                except:
                    result["checks"].append(f"⚠ 付款驗證失敗")
            
            # 往回追
            pre_tx = payload.get("pre_tx", "")
            if not pre_tx:
                # 到達源頭
                break
            current_tx = pre_tx
    
    # 3. 驗證 birth 的屬性
    if result["birth_payload"]:
        birth = result["birth_payload"]
        source_hash = birth.get("src", "")
        
        if source_hash:
            try:
                hero_class, rarity, atk, def_, spd = calculate_hero_from_hash(source_hash)
                
                # 比對
                if (str(birth.get("c")) == str(hero_class) and
                    str(birth.get("r")) == str(rarity) and
                    birth.get("a") == atk and
                    birth.get("d") == def_ and
                    birth.get("s") == spd):
                    result["checks"].append("✓ 屬性驗證通過")
                    result["verified"] = True
                else:
                    result["checks"].append("✗ 屬性不匹配")
            except Exception as e:
                result["checks"].append(f"⚠ 屬性驗證失敗：{e}")
        else:
            result["checks"].append("⚠ 舊版格式，無 src")
    else:
        # 沒有出生記錄，但如果有死亡事件也是有效的
        if result["is_dead"]:
            result["checks"].append("⚠️ 出生銘文缺失（本地記錄）")
            # 從本地資料補充資訊
            if hero:
                result["local_hero"] = {
                    "hero_class": hero.hero_class,
                    "rarity": hero.rarity,
                    "atk": hero.atk,
                    "def": hero.def_,
                    "spd": hero.spd
                }
        else:
            result["errors"].append("未找到出生記錄")
    
    return result


def format_hero_verify_result(result: dict) -> str:
    """格式化英雄 ID 驗證結果"""
    hero_id = result["hero_id"]
    
    if result.get("errors"):
        errors = "\n".join(f"• {e}" for e in result["errors"])
        return f"""🔍 驗證英雄 #{hero_id}

❌ *驗證失敗*

{errors}"""
    
    checks = "\n".join(result.get("checks", []))
    chain_len = len(result.get("chain", []))
    
    # 判斷結果
    if result["verified"]:
        if result["is_dead"]:
            verdict = f"🎉 正卡（☠️ 已死亡 - {result.get('death_reason', 'unknown')}）"
        else:
            verdict = "🎉 正卡"
    elif result["is_dead"]:
        # 死亡但沒有出生銘文
        verdict = f"☠️ 已死亡 - {result.get('death_reason', 'unknown')}（出生銘文缺失）"
    else:
        verdict = "⚠️ 驗證未完成"
    
    # 英雄資訊（優先用 birth_payload，沒有就用 local_hero）
    birth = result.get("birth_payload") or {}
    local_hero = result.get("local_hero") or {}
    
    hero_class = birth.get("c") or local_hero.get("hero_class", "?")
    rarity = birth.get("r") or local_hero.get("rarity", "?")
    atk = birth.get("a") or local_hero.get("atk", "?")
    def_ = birth.get("d") or local_hero.get("def", "?")
    spd = birth.get("s") or local_hero.get("spd", "?")
    
    # 翻譯對照
    class_names = {"warrior": "戰士", "mage": "法師", "rogue": "盜賊", "archer": "弓箭手"}
    rarity_names = {"common": "普通", "uncommon": "優秀", "rare": "稀有",
                    "epic": "史詩", "legendary": "傳說", "mythic": "神話"}
    class_zh = class_names.get(hero_class, hero_class)
    rarity_zh = rarity_names.get(rarity, rarity)
    
    latest_tx = result.get("latest_tx", "")[:32]
    
    return f"""🔍 驗證英雄 #{hero_id}

📦 *英雄資訊：*
• 職業: {class_zh}
• 稀有度: {rarity_zh}
• 屬性: ⚔️{atk} 🛡️{def_} ⚡{spd}

🔗 *鏈上追蹤（{chain_len} 筆）：*
{checks}

{verdict}

📝 Latest TX: `{latest_tx}...`"""


# ═══════════════════════════════════════════════════════════════════════════════
# 英雄命名系統
# ═══════════════════════════════════════════════════════════════════════════════

def get_hero_names_index() -> dict:
    """取得名字索引 {name: hero_id}"""
    db = load_heroes_db()
    names = {}
    for hid, hero in db.get("heroes", {}).items():
        name = hero.get("name")
        if name:
            names[name.lower()] = int(hid)
    return names

def is_name_taken(name: str) -> bool:
    """檢查名字是否已被使用"""
    names = get_hero_names_index()
    return name.lower() in names

def get_hero_by_name(name: str) -> dict | None:
    """用名字查詢英雄"""
    names = get_hero_names_index()
    hero_id = names.get(name.lower())
    if hero_id:
        db = load_heroes_db()
        return db.get("heroes", {}).get(str(hero_id))
    return None

def set_hero_name(hero_id: int, name: str) -> tuple[bool, str]:
    """
    設定英雄名字（本地別名，不上鏈）
    
    規則：
    - 2-12 字元
    - 支援中文、英文、數字、底線
    - 不可重複
    - 大小寫不敏感
    
    Returns:
        (success, error_message)
    """
    import re
    
    # 驗證長度
    if len(name) < 2:
        return False, "名字太短（至少 2 字元）"
    if len(name) > 12:
        return False, "名字太長（最多 12 字元）"
    
    # 驗證字元（允許中文、英文、數字、底線）
    if not re.match(r'^[\u4e00-\u9fff\w]+$', name):
        return False, "名字只能包含中英文、數字、底線"
    
    db = load_heroes_db()
    hero = db.get("heroes", {}).get(str(hero_id))
    if not hero:
        return False, "找不到英雄"
    
    # 取得舊名字
    old_name = hero.get("name")
    
    # 檢查名字是否被使用（排除自己）
    if is_name_taken(name):
        # 如果是自己改成自己的名字（大小寫變化），允許
        if not (old_name and old_name.lower() == name.lower()):
            return False, "名字已被使用"
    
    # 設定新名字
    hero["name"] = name
    db["heroes"][str(hero_id)] = hero
    save_heroes_db(db)
    
    logger.info(f"Hero #{hero_id} named: {name}")
    return True, ""

def resolve_hero_id(identifier: str) -> int | None:
    """
    解析英雄標識符（ID 或名字）
    
    Args:
        identifier: 數字 ID 或英雄名字
    
    Returns:
        hero_id 或 None
    """
    # 嘗試作為數字 ID
    try:
        return int(identifier)
    except ValueError:
        pass
    
    # 嘗試作為名字
    names = get_hero_names_index()
    return names.get(identifier.lower())
