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

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 常數設定
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent / "data"
HEROES_DB_FILE = DATA_DIR / "heroes.json"
HERO_CHAIN_FILE = DATA_DIR / "hero_chain.json"

# 費用設定
SUMMON_COST = 10  # 召喚英雄消耗 10 mana
PVP_COST = {
    "common": 2,
    "uncommon": 3,
    "rare": 4,
    "epic": 6,
    "legendary": 8
}

# 抽卡冷卻
SUMMON_COOLDOWN = 5  # 秒

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

class Rarity(Enum):
    # WoW 風格稀有度系統（千分比機率）
    COMMON = ("common", "⚪ 普通", 1.0, 550)        # 55% 機率
    UNCOMMON = ("uncommon", "🟢 優秀", 1.1, 280)   # 28% 機率
    RARE = ("rare", "🔵 稀有", 1.2, 130)           # 13% 機率
    EPIC = ("epic", "🟣👑 史詩", 1.5, 35)          # 3.5% 機率
    LEGENDARY = ("legendary", "🟠✨ 傳說", 2.0, 5) # 0.5% 機率（超稀有！）
    
    def __init__(self, code: str, display: str, multiplier: float, chance: int):
        self.code = code
        self.display = display
        self.multiplier = multiplier
        self.chance = chance  # 千分比

# ═══════════════════════════════════════════════════════════════════════════════
# 英雄資料結構
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Hero:
    card_id: int          # DAA = 唯一 ID
    owner_id: int         # TG user_id
    owner_address: str    # Kaspa 地址
    hero_class: str       # warrior/mage/archer/rogue
    rarity: str           # common/rare/epic/legendary
    atk: int
    def_: int
    spd: int
    status: str           # alive/dead
    latest_daa: int       # 最新狀態的 DAA
    kills: int = 0
    battles: int = 0
    created_at: str = ""
    source_hash: str = "" # 來源區塊 hash（用於驗證）
    tx_id: str = ""       # 出生公告交易 ID（固定）
    latest_tx: str = ""   # 最後事件交易 ID（每次事件更新）
    
    def display_class(self) -> str:
        for hc in HeroClass:
            if hc.code == self.hero_class:
                return hc.display
        return self.hero_class
    
    def display_rarity(self) -> str:
        for r in Rarity:
            if r.code == self.rarity:
                return r.display
        return self.rarity
    
    def to_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "owner_id": self.owner_id,
            "owner_address": self.owner_address,
            "hero_class": self.hero_class,
            "rarity": self.rarity,
            "atk": self.atk,
            "def": self.def_,
            "spd": self.spd,
            "status": self.status,
            "latest_daa": self.latest_daa,
            "kills": self.kills,
            "battles": self.battles,
            "created_at": self.created_at,
            "source_hash": self.source_hash,
            "tx_id": self.tx_id,
            "latest_tx": self.latest_tx
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'Hero':
        return cls(
            card_id=d["card_id"],
            owner_id=d["owner_id"],
            owner_address=d["owner_address"],
            hero_class=d["hero_class"],
            rarity=d["rarity"],
            atk=d["atk"],
            def_=d["def"],
            spd=d["spd"],
            status=d["status"],
            latest_daa=d["latest_daa"],
            kills=d.get("kills", 0),
            battles=d.get("battles", 0),
            created_at=d.get("created_at", ""),
            source_hash=d.get("source_hash", ""),
            tx_id=d.get("tx_id", ""),
            latest_tx=d.get("latest_tx", "")
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

def calculate_hero_from_hash(block_hash: str) -> Tuple[str, str, int, int, int]:
    """
    從 block hash 計算英雄屬性
    
    Args:
        block_hash: 區塊 hash (64 字元)
    
    Returns:
        (hero_class, rarity, atk, def, spd)
    """
    # 移除 0x 前綴（如果有）
    h = block_hash.lower().replace("0x", "")
    
    # 職業: hash[0:2] % 4
    class_val = int(h[0:2], 16) % 4
    classes = ["warrior", "mage", "archer", "rogue"]
    hero_class = classes[class_val]
    
    # 稀有度: hash[2:6] % 1000（千分比）
    # 🟠✨ 傳說 0.5% | 🟣👑 史詩 3.5% | 🔵 稀有 13% | 🟢 優秀 28% | ⚪ 普通 55%
    rarity_val = int(h[2:6], 16) % 1000
    if rarity_val < 5:           # 0-4 = 0.5%
        rarity = "legendary"
        multiplier = 2.0
    elif rarity_val < 40:        # 5-39 = 3.5%
        rarity = "epic"
        multiplier = 1.5
    elif rarity_val < 170:       # 40-169 = 13%
        rarity = "rare"
        multiplier = 1.2
    elif rarity_val < 450:       # 170-449 = 28%
        rarity = "uncommon"
        multiplier = 1.1
    else:                        # 450-999 = 55%
        rarity = "common"
        multiplier = 1.0
    
    # 基礎屬性: 10-100
    base_atk = int(h[4:8], 16) % 91 + 10
    base_def = int(h[8:12], 16) % 91 + 10
    base_spd = int(h[12:16], 16) % 91 + 10
    
    # 套用稀有度加成
    atk = int(base_atk * multiplier)
    def_ = int(base_def * multiplier)
    spd = int(base_spd * multiplier)
    
    return hero_class, rarity, atk, def_, spd

def calculate_battle_result(attacker: Hero, defender: Hero, block_hash: str) -> Tuple[bool, str]:
    """
    計算戰鬥結果
    
    Args:
        attacker: 攻擊方英雄
        defender: 防守方英雄
        block_hash: 決定勝負的區塊 hash
    
    Returns:
        (attacker_wins, description)
    """
    h = block_hash.lower().replace("0x", "")
    
    # 基礎勝率：根據稀有度
    rarity_order = ["common", "uncommon", "rare", "epic", "legendary"]
    atk_rarity_idx = rarity_order.index(attacker.rarity) if attacker.rarity in rarity_order else 0
    def_rarity_idx = rarity_order.index(defender.rarity) if defender.rarity in rarity_order else 0
    
    # 翻盤率
    upset_chances = {
        (-3, ): 3,   # common vs legendary: 3%
        (-2, ): 5,   # rare vs legendary: 5%
        (-1, ): 10,  # epic vs legendary: 10%
        (0, ): 50,   # 同級: 50%
        (1, ): 90,   # 高一級: 90%
        (2, ): 95,   # 高兩級: 95%
        (3, ): 97,   # 高三級: 97%
    }
    
    rarity_diff = atk_rarity_idx - def_rarity_idx
    
    # 決定勝率
    if rarity_diff <= -3:
        win_chance = 3
    elif rarity_diff == -2:
        win_chance = 5
    elif rarity_diff == -1:
        win_chance = 10
    elif rarity_diff == 0:
        # 同級比屬性
        atk_power = attacker.atk + attacker.spd
        def_power = defender.def_ + defender.spd
        if atk_power > def_power:
            win_chance = 60
        elif atk_power < def_power:
            win_chance = 40
        else:
            win_chance = 50
    elif rarity_diff == 1:
        win_chance = 90
    elif rarity_diff == 2:
        win_chance = 95
    else:
        win_chance = 97
    
    # 用 hash 決定
    roll = int(h[16:20], 16) % 100
    attacker_wins = roll < win_chance
    
    if attacker_wins:
        desc = f"🎯 攻擊命中！{attacker.display_rarity()} vs {defender.display_rarity()}"
    else:
        desc = f"🛡️ 防守成功！{defender.display_rarity()} 逆轉 {attacker.display_rarity()}！"
    
    return attacker_wins, desc

# ═══════════════════════════════════════════════════════════════════════════════
# 鏈上記錄格式（Payload）
# ═══════════════════════════════════════════════════════════════════════════════

def create_birth_payload(daa: int, hero: Hero) -> dict:
    """
    建立出生 payload
    
    格式：
    - daa: 英雄身份證（命運 DAA）
    - pre_tx: 前一個 payload 的 TX ID（出生為空字串）
    - 英雄資訊
    """
    return {
        "g": "nami_hero",
        "type": "hero",
        "daa": daa,           # 英雄身份證
        "pre_tx": "",         # 出生沒有前置 TX
        "card": hero.card_id,
        "c": hero.hero_class,
        "r": hero.rarity,
        "a": hero.atk,
        "d": hero.def_,
        "s": hero.spd,
        "status": "alive"
    }

def create_event_payload(daa: int, pre_tx: str, action: str, 
                         attacker_id: int, target_id: int, result: str) -> dict:
    """建立事件 payload"""
    return {
        "g": "nami_hero",
        "type": "event",
        "daa": daa,           # 事件結果 DAA
        "pre_tx": pre_tx,     # 前一個 payload 的 TX ID
        "action": action,
        "attacker": attacker_id,
        "target": target_id,
        "result": result
    }

def create_state_payload(daa: int, pre_tx: str, hero: Hero) -> dict:
    """建立狀態更新 payload"""
    return {
        "g": "nami_hero",
        "type": "hero",
        "daa": daa,           # 英雄身份證 DAA（不變）
        "pre_tx": pre_tx,     # 前一個 payload 的 TX ID
        "card": hero.card_id,
        "status": hero.status,
        "kills": hero.kills,
        "battles": hero.battles
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 遊戲邏輯
# ═══════════════════════════════════════════════════════════════════════════════

async def summon_hero(user_id: int, username: str, address: str, 
                      daa: int, block_hash: str) -> Hero:
    """
    召喚英雄
    
    Args:
        user_id: TG 用戶 ID
        username: TG 用戶名
        address: Kaspa 地址
        daa: 來源 DAA
        block_hash: 來源區塊 hash
    
    Returns:
        新召喚的英雄
    """
    # 計算屬性
    hero_class, rarity, atk, def_, spd = calculate_hero_from_hash(block_hash)
    
    # 建立英雄
    hero = Hero(
        card_id=daa,
        owner_id=user_id,
        owner_address=address,
        hero_class=hero_class,
        rarity=rarity,
        atk=atk,
        def_=def_,
        spd=spd,
        status="alive",
        latest_daa=daa,
        kills=0,
        battles=0,
        created_at=datetime.now().isoformat(),
        source_hash=block_hash  # 儲存來源區塊 hash
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
    
    # 建立 birth payload
    birth_payload = create_birth_payload(daa, hero)
    
    # 發送到鏈上
    try:
        tx_id = await send_hero_tx_simple(address, birth_payload)
        hero.tx_id = tx_id
        hero.latest_tx = tx_id  # 出生時，最後交易 = 出生交易
        logger.info(f"Hero birth tx sent: {tx_id}")
        
        # 更新資料庫中的 tx_id
        db["heroes"][str(daa)]["tx_id"] = tx_id
        db["heroes"][str(daa)]["latest_tx"] = tx_id
        save_heroes_db(db)
    except Exception as e:
        logger.warning(f"Failed to send birth tx (continuing anyway): {e}")
    
    # 記錄到本地鏈條
    chain = load_hero_chain()
    birth_payload["tx_id"] = getattr(hero, 'tx_id', None)
    chain.append(birth_payload)
    save_hero_chain(chain)
    
    logger.info(f"Hero summoned: #{daa} {hero.display_class()} {hero.display_rarity()} for user {user_id}")
    
    return hero

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
    attacker_wins, desc = calculate_battle_result(attacker, defender, block_hash)
    
    # 更新狀態
    attacker.battles += 1
    defender.battles += 1
    
    if attacker_wins:
        attacker.kills += 1
        defender.status = "dead"
        result = "win"
    else:
        defender.kills += 1
        attacker.status = "dead"
        result = "lose"
    
    attacker.latest_daa = result_daa
    defender.latest_daa = result_daa
    
    # 儲存到資料庫
    db = load_heroes_db()
    db["heroes"][str(attacker.card_id)] = attacker.to_dict()
    db["heroes"][str(defender.card_id)] = defender.to_dict()
    
    # PvP 費用加入 mana 池
    pvp_cost = PVP_COST.get(attacker.rarity, 2)
    db["total_mana_pool"] = db.get("total_mana_pool", 0) + pvp_cost
    
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
    """格式化英雄卡片顯示（HTML 格式）"""
    status_icon = "🟢" if hero.status == "alive" else "☠️"
    
    # 稀有度 - 職業 顯示
    rarity_display = get_rarity_display(hero.rarity)
    class_name = get_class_name(hero.hero_class)
    class_emoji = get_class_emoji(hero.hero_class)
    title_line = f"{rarity_display} - {class_name} {class_emoji}"
    
    # Explorer link (HTML 格式)
    explorer_link = ""
    if hero.source_hash:
        explorer_link = f'\n🔗 <a href="https://explorer-tn10.kaspa.org/blocks/{hero.source_hash}">區塊瀏覽器</a>'
    
    return f"""🎴 英雄 #{hero.card_id}

{title_line}

⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}

{status_icon} {hero.status} | 戰績 {hero.battles}戰 {hero.kills}殺

📍 命運: DAA {hero.card_id}{explorer_link}

/nami_payload {hero.card_id} 查看鏈上資料"""

def format_hero_list(heroes: list[Hero]) -> str:
    """格式化英雄列表"""
    if not heroes:
        return "📜 你還沒有英雄\n\n使用 /nami_hero 召喚你的第一位英雄！"
    
    alive = [h for h in heroes if h.status == "alive"]
    dead = [h for h in heroes if h.status == "dead"]
    
    lines = [f"📜 你的英雄 ({len(alive)} 存活 / {len(dead)} 陣亡)\n"]
    
    for h in alive:
        rarity = get_rarity_display(h.rarity)
        class_name = get_class_name(h.hero_class)
        class_emoji = get_class_emoji(h.hero_class)
        lines.append(f"🟢 #{h.card_id} {rarity} {class_name}{class_emoji} - {h.kills}殺")
    
    for h in dead:
        rarity = get_rarity_display(h.rarity)
        class_name = get_class_name(h.hero_class)
        class_emoji = get_class_emoji(h.hero_class)
        lines.append(f"☠️ #{h.card_id} {rarity} {class_name}{class_emoji}")
    
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
    """獲取稀有度顯示（WoW 風格）"""
    display_map = {
        "common": "⚪ 普通",
        "uncommon": "🟢 優秀",
        "rare": "🔵 稀有", 
        "epic": "🟣👑 史詩",
        "legendary": "🟠✨ 傳說"
    }
    return display_map.get(rarity, rarity)

def format_summon_result(hero: Hero) -> str:
    """格式化召喚結果"""
    # 特效標題（WoW 風格）
    if hero.rarity == "legendary":
        header = "🟠🟠🟠 ✨ 傳說降臨！✨ 🟠🟠🟠\n\n"
    elif hero.rarity == "epic":
        header = "🟣🟣 👑 史詩級！👑 🟣🟣\n\n"
    elif hero.rarity == "rare":
        header = "🔵 稀有！\n\n"
    elif hero.rarity == "uncommon":
        header = "🟢 優秀！\n\n"
    else:
        header = ""
    
    # 稀有度 - 職業 顯示
    rarity_display = get_rarity_display(hero.rarity)
    class_name = get_class_name(hero.hero_class)
    class_emoji = get_class_emoji(hero.hero_class)
    title_line = f"{rarity_display} - {class_name} {class_emoji}"
    
    # 區塊瀏覽器連結 (純 URL，Telegram 會自動偵測)
    explorer_link = ""
    if hero.source_hash:
        explorer_link = f'🔗 命運區塊:\nhttps://explorer-tn10.kaspa.org/blocks/{hero.source_hash}'
    
    # 構建簡化版 payload 顯示
    payload_preview = f'{{"g":"nami_hero","daa":{hero.card_id},"c":"{hero.hero_class[:3]}","r":"{hero.rarity[:3]}","a":{hero.atk},"d":{hero.def_},"s":{hero.spd}}}'
    
    # 公告 TX 連結（如果有）
    tx_link = ""
    if hasattr(hero, 'tx_id') and hero.tx_id and not hero.tx_id.startswith('daa_'):
        tx_link = f'🔗 鏈上公告:\nhttps://explorer-tn10.kaspa.org/txs/{hero.tx_id}'
    else:
        tx_link = "🔗 (本地記錄)"
    
    return f"""🎴 召喚成功！

{header}{title_line}

⚔️ {hero.atk} | 🛡️ {hero.def_} | ⚡ {hero.spd}

📍 命運: DAA {hero.card_id}
{explorer_link}

📦 公告 TX:
{tx_link}

英雄 ID: #{hero.card_id}
/nami_verify {hero.card_id} 驗證"""

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
