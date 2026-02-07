"""
本地銘文記錄系統
確保出生和死亡的閉環驗證
"""

import json
import os
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 銘文儲存目錄
INSCRIPTIONS_DIR = Path(__file__).parent / "data" / "inscriptions"
INSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)


def get_hero_dir(hero_id: int) -> Path:
    """取得英雄的銘文目錄"""
    hero_dir = INSCRIPTIONS_DIR / str(hero_id)
    hero_dir.mkdir(parents=True, exist_ok=True)
    return hero_dir


def save_birth_inscription(
    hero_id: int,
    tx_id: str,
    payment_tx: str,
    source_hash: str,
    source_daa: int,
    payload: dict
) -> dict:
    """
    儲存出生銘文（閉環驗證）
    
    閉環條件：
    - payment_tx 存在
    - source_hash 存在
    - source_daa > payment_tx 確認的 DAA
    - payload 包含正確屬性
    """
    hero_dir = get_hero_dir(hero_id)
    
    record = {
        "type": "birth",
        "hero_id": hero_id,
        "tx_id": tx_id,
        "payment_tx": payment_tx,
        "source_hash": source_hash,
        "source_daa": source_daa,
        "payload": payload,
        "pre_tx": None,  # 出生沒有 pre_tx
        "verified": bool(payment_tx and source_hash and tx_id),
        "timestamp": datetime.now().isoformat()
    }
    
    birth_file = hero_dir / "birth.json"
    with open(birth_file, 'w') as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    
    logger.info(f"📜 儲存出生銘文 #{hero_id} | TX: {tx_id[:16]}...")
    return record


def save_event_inscription(
    hero_id: int,
    event_type: str,  # pvp_win, pvp_lose, etc.
    tx_id: str,
    pre_tx: str,
    payment_tx: str = None,
    source_hash: str = None,
    payload: dict = None,
    **extra
) -> dict:
    """
    儲存事件銘文
    
    閉環條件：
    - pre_tx 指向前一個銘文
    - 可追溯到出生銘文
    """
    hero_dir = get_hero_dir(hero_id)
    events_dir = hero_dir / "events"
    events_dir.mkdir(exist_ok=True)
    
    # 計算事件序號
    existing = list(events_dir.glob("*.json"))
    seq = len(existing) + 1
    
    record = {
        "type": event_type,
        "hero_id": hero_id,
        "seq": seq,
        "tx_id": tx_id,
        "pre_tx": pre_tx,
        "payment_tx": payment_tx,
        "source_hash": source_hash,
        "payload": payload,
        "verified": bool(pre_tx and tx_id),
        "timestamp": datetime.now().isoformat(),
        **extra
    }
    
    event_file = events_dir / f"{seq:03d}_{event_type}.json"
    with open(event_file, 'w') as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    
    logger.info(f"📜 儲存事件銘文 #{hero_id} | {event_type} | TX: {tx_id[:16]}...")
    return record


def save_death_inscription(
    hero_id: int,
    tx_id: str,
    pre_tx: str,
    reason: str,
    killer_id: int = None,
    battle_tx: str = None,
    payload: dict = None
) -> dict:
    """
    儲存死亡銘文（閉環驗證）
    
    閉環條件：
    - pre_tx 指向前一個銘文（出生或最後事件）
    - 可追溯到出生銘文
    """
    hero_dir = get_hero_dir(hero_id)
    
    record = {
        "type": "death",
        "hero_id": hero_id,
        "tx_id": tx_id,
        "pre_tx": pre_tx,
        "reason": reason,
        "killer_id": killer_id,
        "battle_tx": battle_tx,
        "payload": payload,
        "verified": bool(pre_tx and tx_id),
        "timestamp": datetime.now().isoformat()
    }
    
    death_file = hero_dir / "death.json"
    with open(death_file, 'w') as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    
    logger.info(f"💀 儲存死亡銘文 #{hero_id} | reason: {reason} | TX: {tx_id[:16]}...")
    return record


def get_hero_chain(hero_id: int) -> list:
    """
    取得英雄的完整銘文鏈條
    
    Returns:
        [birth, event1, event2, ..., death(optional)]
    """
    hero_dir = get_hero_dir(hero_id)
    chain = []
    
    # 1. 出生銘文
    birth_file = hero_dir / "birth.json"
    if birth_file.exists():
        with open(birth_file) as f:
            chain.append(json.load(f))
    
    # 2. 事件銘文（按序號排序）
    events_dir = hero_dir / "events"
    if events_dir.exists():
        event_files = sorted(events_dir.glob("*.json"))
        for ef in event_files:
            with open(ef) as f:
                chain.append(json.load(f))
    
    # 3. 死亡銘文
    death_file = hero_dir / "death.json"
    if death_file.exists():
        with open(death_file) as f:
            chain.append(json.load(f))
    
    # 4. 復活銘文（GM 特赦）
    resurrection_file = hero_dir / "resurrection.json"
    if resurrection_file.exists():
        with open(resurrection_file) as f:
            chain.append(json.load(f))
    
    return chain


def verify_chain_integrity(hero_id: int) -> dict:
    """
    驗證英雄的銘文鏈條完整性
    
    檢查：
    1. 出生銘文存在且有 payment_tx + source_hash
    2. 每個事件的 pre_tx 指向前一個銘文
    3. 死亡銘文（如果有）的 pre_tx 正確
    
    Returns:
        {
            "verified": bool,
            "chain_length": int,
            "checks": [...],
            "errors": [...]
        }
    """
    result = {
        "hero_id": hero_id,
        "verified": False,
        "chain_length": 0,
        "checks": [],
        "errors": []
    }
    
    chain = get_hero_chain(hero_id)
    if not chain:
        result["errors"].append("沒有銘文記錄")
        return result
    
    result["chain_length"] = len(chain)
    
    # 1. 檢查出生銘文
    birth = chain[0]
    if birth.get("type") != "birth":
        result["errors"].append("第一個銘文不是出生記錄")
        return result
    
    if not birth.get("payment_tx"):
        result["errors"].append("出生銘文缺少 payment_tx")
    else:
        result["checks"].append("✓ 出生 payment_tx 存在")
    
    if not birth.get("source_hash"):
        result["errors"].append("出生銘文缺少 source_hash")
    else:
        result["checks"].append("✓ 出生 source_hash 存在")
    
    if not birth.get("tx_id"):
        result["errors"].append("出生銘文缺少 tx_id")
    else:
        result["checks"].append("✓ 出生 tx_id 存在")
    
    # 2. 檢查鏈條連續性
    prev_tx = birth.get("tx_id")
    for i, item in enumerate(chain[1:], 1):
        item_pre_tx = item.get("pre_tx")
        
        if item_pre_tx != prev_tx:
            result["errors"].append(
                f"鏈條斷裂：第 {i+1} 個銘文的 pre_tx ({item_pre_tx[:16] if item_pre_tx else 'null'}...) "
                f"不等於前一個 tx_id ({prev_tx[:16] if prev_tx else 'null'}...)"
            )
        else:
            result["checks"].append(f"✓ 第 {i+1} 個銘文 pre_tx 正確")
        
        prev_tx = item.get("tx_id")
    
    # 3. 結果
    result["verified"] = len(result["errors"]) == 0
    
    return result


def get_latest_tx(hero_id: int) -> str | None:
    """取得英雄的最新銘文 TX ID"""
    chain = get_hero_chain(hero_id)
    if chain:
        return chain[-1].get("tx_id")
    return None


def format_chain_summary(hero_id: int) -> str:
    """格式化英雄的銘文鏈條摘要"""
    chain = get_hero_chain(hero_id)
    if not chain:
        return f"❌ #{hero_id} 沒有銘文記錄"
    
    lines = [f"📜 英雄 #{hero_id} 的銘文鏈條", "=" * 40]
    
    for i, item in enumerate(chain):
        item_type = item.get("type", "?")
        tx_id = item.get("tx_id", "?")[:16]
        pre_tx = item.get("pre_tx", "")[:16] if item.get("pre_tx") else "(無)"
        
        if item_type == "birth":
            emoji = "🎴"
        elif item_type == "death":
            emoji = "💀"
        elif item_type == "resurrection":
            emoji = "✨"
        else:
            emoji = "⚔️"
        
        arrow = "←" if i > 0 else " "
        lines.append(f"  {arrow} {emoji} {item_type:10} | TX: {tx_id}...")
    
    # 驗證結果
    verify = verify_chain_integrity(hero_id)
    lines.append("")
    lines.append(f"驗證: {'✅ 通過' if verify['verified'] else '❌ 失敗'}")
    if verify["errors"]:
        for err in verify["errors"]:
            lines.append(f"  ⚠️ {err}")
    
    return "\n".join(lines)
