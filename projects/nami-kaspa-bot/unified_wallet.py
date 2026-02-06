#!/usr/bin/env python3
"""
🌊 娜米統一錢包平台
共用錢包系統：輪盤 + 英雄遊戲

PIN 推導錢包：user_id + PIN → 確定性私鑰
同一個 user + PIN = 永遠同一個錢包

by Nami 🌊
"""

import hashlib
import json
import logging
from pathlib import Path
from kaspa import PrivateKey, Address, PaymentOutput, RpcClient
from kaspa import create_transaction, sign_transaction

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
UNIFIED_PINS_FILE = DATA_DIR / "unified_pins.json"

# 大地之樹地址（遊戲收款）
TREE_ADDRESS = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

# 費用設定（sompi）
TX_FEE = 2000  # 交易手續費

# ═══════════════════════════════════════════════════════════════════════════════
# 錢包推導
# ═══════════════════════════════════════════════════════════════════════════════

def derive_private_key(user_id: int, pin: str, salt: str = "nami_wallet_v2") -> str:
    """從 user_id + PIN 推導私鑰（確定性）"""
    data = f"{salt}:{user_id}:{pin}".encode('utf-8')
    private_key_bytes = hashlib.sha256(data).digest()
    return private_key_bytes.hex()

def get_wallet(user_id: int, pin: str) -> tuple[str, str]:
    """
    從 user_id + PIN 獲取錢包
    
    Returns:
        (private_key_hex, address_string)
    """
    pk_hex = derive_private_key(user_id, pin)
    pk = PrivateKey(pk_hex)
    address = pk.to_address("testnet")
    return pk_hex, address.to_string()

# ═══════════════════════════════════════════════════════════════════════════════
# PIN 管理
# ═══════════════════════════════════════════════════════════════════════════════

def load_pins() -> dict:
    """載入統一 PIN 設定"""
    if UNIFIED_PINS_FILE.exists():
        with open(UNIFIED_PINS_FILE) as f:
            return json.load(f)
    return {}

def save_pins(data: dict):
    """儲存統一 PIN 設定"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(UNIFIED_PINS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def set_pin(user_id: int, pin: str) -> str:
    """
    設定用戶的 PIN
    
    Returns:
        對應的錢包地址
    """
    # 驗證 PIN 格式
    if not pin.isdigit() or not (4 <= len(pin) <= 6):
        raise ValueError("PIN 需為 4-6 位數字")
    
    _, address = get_wallet(user_id, pin)
    
    # 儲存（只存地址和 PIN hash，不存私鑰！）
    pins = load_pins()
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()[:16]
    
    pins[str(user_id)] = {
        "address": address,
        "pin_hash": pin_hash,
        "created_at": __import__('time').time()
    }
    save_pins(pins)
    
    logger.info(f"PIN set for user {user_id}: {address}")
    return address

def verify_pin(user_id: int, pin: str) -> bool:
    """驗證 PIN 是否正確"""
    pins = load_pins()
    user_data = pins.get(str(user_id))
    if not user_data:
        return False
    
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()[:16]
    return user_data.get("pin_hash") == pin_hash

def has_wallet(user_id: int) -> bool:
    """檢查用戶是否有錢包"""
    pins = load_pins()
    return str(user_id) in pins

def get_user_address(user_id: int) -> str | None:
    """取得用戶的錢包地址（不需要 PIN）"""
    pins = load_pins()
    user_data = pins.get(str(user_id))
    if user_data:
        return user_data.get("address")
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# 餘額查詢
# ═══════════════════════════════════════════════════════════════════════════════

async def get_balance(address: str) -> int:
    """取得錢包餘額（sompi）"""
    client = RpcClient(url="ws://127.0.0.1:17210", network_id="testnet-10")
    await client.connect()
    try:
        result = await client.get_balance_by_address({"address": address})
        return result.get("balance", 0)
    finally:
        await client.disconnect()

async def get_balance_tkas(address: str) -> float:
    """取得錢包餘額（tKAS）"""
    sompi = await get_balance(address)
    return sompi / 1e8

# ═══════════════════════════════════════════════════════════════════════════════
# 交易發送
# ═══════════════════════════════════════════════════════════════════════════════

async def send_payment(
    user_id: int, 
    pin: str, 
    to_address: str,
    amount: int,
    payload: bytes = None
) -> str:
    """
    從用戶錢包發送交易
    
    Args:
        user_id: 用戶 ID
        pin: PIN 碼
        to_address: 收款地址
        amount: 金額（sompi）
        payload: 可選 payload
    
    Returns:
        交易 ID
    
    Raises:
        ValueError: PIN 錯誤或餘額不足
    """
    # 驗證 PIN
    if not verify_pin(user_id, pin):
        raise ValueError("PIN 碼錯誤")
    
    pk_hex, from_address = get_wallet(user_id, pin)
    pk = PrivateKey(pk_hex)
    
    client = RpcClient(url="ws://127.0.0.1:17210", network_id="testnet-10")
    await client.connect()
    
    try:
        # 取得 UTXO
        utxo_response = await client.get_utxos_by_addresses({"addresses": [from_address]})
        entries = utxo_response.get("entries", [])
        
        if not entries:
            raise ValueError("錢包沒有餘額")
        
        # 計算總餘額
        total = sum(e["utxoEntry"]["amount"] for e in entries)
        if total < amount + TX_FEE:
            raise ValueError(f"餘額不足：需要 {(amount + TX_FEE) / 1e8:.4f} tKAS，只有 {total / 1e8:.4f} tKAS")
        
        # 建立輸出
        to_addr = Address(to_address)
        outputs = [PaymentOutput(to_addr, amount)]
        
        # 建立交易
        tx = create_transaction(
            utxo_entry_source=entries,
            outputs=outputs,
            priority_fee=TX_FEE,
            payload=payload
        )
        
        # 簽名
        signed_tx = sign_transaction(tx, [pk], False)
        
        # 發送
        result = await client.submit_transaction({
            "transaction": signed_tx,
            "allow_orphan": False
        })
        
        tx_id = result.get("transactionId", str(result))
        logger.info(f"Payment sent: {tx_id} ({amount / 1e8:.4f} tKAS from user {user_id})")
        
        return tx_id
        
    finally:
        await client.disconnect()

async def send_to_tree(user_id: int, pin: str, amount: int, memo: str = "") -> str:
    """
    發送到大地之樹（遊戲收款）
    
    用於：輪盤下注、英雄召喚、PvP 等
    """
    payload = memo.encode('utf-8') if memo else None
    return await send_payment(user_id, pin, TREE_ADDRESS, amount, payload)

# ═══════════════════════════════════════════════════════════════════════════════
# 遷移工具
# ═══════════════════════════════════════════════════════════════════════════════

def migrate_from_roulette_pins():
    """
    從舊的 roulette_pins.json 遷移
    （只能遷移有設過 PIN 的用戶）
    
    注意：因為舊系統用私鑰綁定，而新系統用推導
    無法直接遷移錢包地址，只能提醒用戶重新設定
    """
    old_file = DATA_DIR / "roulette_pins.json"
    if not old_file.exists():
        return []
    
    with open(old_file) as f:
        old_pins = json.load(f)
    
    migrated_users = list(old_pins.keys())
    logger.info(f"Found {len(migrated_users)} users to migrate (they need to re-setup with /nami_wallet)")
    
    return migrated_users

def migrate_from_hero_pins():
    """
    從舊的 hero_pins.json 遷移
    因為推導邏輯相同，可以直接遷移
    """
    old_file = DATA_DIR / "hero_pins.json"
    if not old_file.exists():
        return 0
    
    with open(old_file) as f:
        old_pins = json.load(f)
    
    # 載入現有統一 PIN
    pins = load_pins()
    count = 0
    
    for user_id, data in old_pins.items():
        if user_id not in pins:
            pins[user_id] = {
                "address": data.get("address"),
                "pin_hash": data.get("pin_hash"),
                "created_at": __import__('time').time(),
                "migrated_from": "hero_pins"
            }
            count += 1
    
    if count > 0:
        save_pins(pins)
        logger.info(f"Migrated {count} users from hero_pins.json")
    
    return count

# ═══════════════════════════════════════════════════════════════════════════════
# 測試
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    
    async def test():
        user_id = 5168530096
        pin = "1234"
        
        # 設定 PIN
        address = set_pin(user_id, pin)
        print(f"✅ PIN: {pin}")
        print(f"📍 Address: {address}")
        
        # 查餘額
        balance = await get_balance_tkas(address)
        print(f"💰 Balance: {balance:.4f} tKAS")
        
        # 驗證 PIN
        print(f"✓ Verify correct: {verify_pin(user_id, pin)}")
        print(f"✗ Verify wrong: {verify_pin(user_id, '9999')}")
        
        # 測試相同 PIN 推導相同地址
        _, address2 = get_wallet(user_id, pin)
        print(f"🔄 Same address: {address == address2}")
    
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test())
