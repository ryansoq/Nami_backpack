#!/usr/bin/env python3
"""
🌲 英雄遊戲錢包模組
PIN 碼推導私鑰，用於付費召喚/戰鬥

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
HERO_PINS_FILE = DATA_DIR / "hero_pins.json"

# 大地之樹地址（收款）
TREE_ADDRESS = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

# 費用設定（sompi）
SUMMON_COST = 1000000000  # 10 tKAS
PVP_COST_BASE = 200000000  # 2 tKAS (基礎)
TX_FEE = 5000  # 交易手續費（inscription 需要更多）

def derive_private_key(user_id: int, pin: str, salt: str = "nami_hero_v1") -> str:
    """從 user_id + PIN 推導私鑰（確定性）"""
    data = f"{salt}:{user_id}:{pin}".encode('utf-8')
    private_key_bytes = hashlib.sha256(data).digest()
    return private_key_bytes.hex()

def get_hero_wallet(user_id: int, pin: str) -> tuple[str, str]:
    """
    從 user_id + PIN 獲取英雄錢包
    
    Returns:
        (private_key_hex, address_string)
    """
    pk_hex = derive_private_key(user_id, pin)
    pk = PrivateKey(pk_hex)
    address = pk.to_address("testnet")
    return pk_hex, address.to_string()

def load_hero_pins() -> dict:
    """載入 PIN 設定（只存地址，不存私鑰！）"""
    if HERO_PINS_FILE.exists():
        with open(HERO_PINS_FILE) as f:
            return json.load(f)
    return {}

def save_hero_pins(data: dict):
    """儲存 PIN 設定"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HERO_PINS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def set_hero_pin(user_id: int, pin: str) -> str:
    """
    設定用戶的英雄遊戲 PIN
    
    Returns:
        對應的錢包地址
    """
    _, address = get_hero_wallet(user_id, pin)
    
    # 儲存（只存地址和 PIN hash，不存私鑰！）
    pins = load_hero_pins()
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()[:16]
    
    pins[str(user_id)] = {
        "address": address,
        "pin_hash": pin_hash  # 用於驗證 PIN 正確性
    }
    save_hero_pins(pins)
    
    return address

def verify_hero_pin(user_id: int, pin: str) -> bool:
    """驗證 PIN 是否正確"""
    pins = load_hero_pins()
    user_data = pins.get(str(user_id))
    if not user_data:
        return False
    
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()[:16]
    return user_data.get("pin_hash") == pin_hash

def get_user_hero_address(user_id: int) -> str | None:
    """取得用戶的英雄錢包地址（不需要 PIN）"""
    pins = load_hero_pins()
    user_data = pins.get(str(user_id))
    if user_data:
        return user_data.get("address")
    return None

async def get_hero_balance(address: str) -> int:
    """取得英雄錢包餘額（sompi）"""
    client = RpcClient(url="ws://127.0.0.1:17210", network_id="testnet-10")
    await client.connect()
    try:
        result = await client.get_balance_by_address({"address": address})
        return result.get("balance", 0)
    finally:
        await client.disconnect()

async def send_hero_payment(user_id: int, pin: str, amount: int, memo: str = "") -> str:
    """
    從英雄錢包發送付費交易
    
    Args:
        user_id: 用戶 ID
        pin: PIN 碼
        amount: 金額（sompi）
        memo: 備註（可選，會放入 payload）
    
    Returns:
        交易 ID
    """
    pk_hex, address = get_hero_wallet(user_id, pin)
    pk = PrivateKey(pk_hex)
    
    client = RpcClient(url="ws://127.0.0.1:17210", network_id="testnet-10")
    await client.connect()
    
    try:
        # 取得 UTXO
        utxo_response = await client.get_utxos_by_addresses({"addresses": [address]})
        entries = utxo_response.get("entries", [])
        
        if not entries:
            raise Exception("錢包沒有餘額")
        
        # 計算總餘額
        total = sum(e["utxoEntry"]["amount"] for e in entries)
        if total < amount + TX_FEE:
            raise Exception(f"餘額不足：需要 {(amount + TX_FEE) / 1e8:.4f} tKAS，只有 {total / 1e8:.4f} tKAS")
        
        # 輸出：付款到大地之樹
        tree_addr = Address(TREE_ADDRESS)
        outputs = [PaymentOutput(tree_addr, amount)]
        
        # Payload（可選）
        payload = None
        if memo:
            payload = memo.encode('utf-8')
        
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
        logger.info(f"Hero payment sent: {tx_id} ({amount / 1e8:.4f} tKAS)")
        
        return tx_id
        
    finally:
        await client.disconnect()

# 測試
if __name__ == "__main__":
    import asyncio
    
    async def test():
        user_id = 5168530096
        pin = "1234"
        
        # 設定 PIN
        address = set_hero_pin(user_id, pin)
        print(f"PIN: {pin}")
        print(f"Address: {address}")
        
        # 查餘額
        balance = await get_hero_balance(address)
        print(f"Balance: {balance / 1e8:.4f} tKAS")
        
        # 驗證 PIN
        print(f"Verify correct: {verify_hero_pin(user_id, pin)}")
        print(f"Verify wrong: {verify_hero_pin(user_id, '9999')}")
    
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test())
