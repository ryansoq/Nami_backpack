#!/usr/bin/env python3
"""
🌊 娜米統一錢包平台
共用錢包系統：輪盤 + 英雄遊戲

PIN 推導錢包：user_id + PIN → 確定性私鑰
同一個 user + PIN = 永遠同一個錢包

by Nami 🌊

更新 2026-02-09: 使用 rpc_manager 統一管理 RPC 連線
"""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from kaspa import PrivateKey, Address, PaymentOutput
from kaspa import create_transaction, sign_transaction

# 使用統一 RPC 管理器
from rpc_manager import get_rpc_client, rpc_call, get_balance as rpc_get_balance

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
UNIFIED_PINS_FILE = DATA_DIR / "unified_pins.json"

# 大地之樹地址（遊戲收款）
TREE_ADDRESS = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

# 費用設定（sompi）
TX_FEE = 50000  # 交易手續費（大額 UTXO 需要更多 storage mass）
MIN_INSCRIPTION_AMOUNT = 10000  # 0.0001 tKAS - inscription marker 最小金額

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
    從 user_id + PIN 獲取錢包（支援新舊系統）
    
    Returns:
        (private_key_hex, address_string)
    """
    # 1. 先檢查舊的輪盤 PIN 系統（直接存私鑰）
    roulette_pins_file = DATA_DIR / "roulette_pins.json"
    if roulette_pins_file.exists():
        with open(roulette_pins_file) as f:
            roulette_pins = json.load(f)
        user_pins = roulette_pins.get(str(user_id), {})
        if pin in user_pins:
            # 舊系統：PIN 直接對應私鑰
            pk_hex = user_pins[pin]
            pk = PrivateKey(pk_hex)
            address = pk.to_address("testnet")
            return pk_hex, address.to_string()
    
    # 2. 新系統：從 user_id + PIN 推導
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
    """驗證 PIN 是否正確（支援新舊系統）"""
    # 1. 先檢查新的統一 PIN 系統
    pins = load_pins()
    user_data = pins.get(str(user_id))
    if user_data:
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()[:16]
        if user_data.get("pin_hash") == pin_hash:
            return True
    
    # 2. Fallback: 舊的輪盤 PIN 系統
    roulette_pins_file = DATA_DIR / "roulette_pins.json"
    if roulette_pins_file.exists():
        with open(roulette_pins_file) as f:
            roulette_pins = json.load(f)
        user_pins = roulette_pins.get(str(user_id), {})
        if pin in user_pins:
            return True
    
    return False

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
# 餘額查詢（使用 rpc_manager）
# ═══════════════════════════════════════════════════════════════════════════════

async def get_balance(address: str) -> int:
    """取得錢包餘額（sompi）- 使用統一 RPC 管理器"""
    return await rpc_get_balance(address)

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
    
    # 使用統一 RPC 管理器（自動重連）
    async with get_rpc_client() as client:
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
        from_addr = Address(from_address)
        outputs = [PaymentOutput(to_addr, amount)]
        
        # 計算找零
        change = total - amount - TX_FEE
        if change > 0:
            outputs.append(PaymentOutput(from_addr, change))
            logger.info(f"  找零: {change / 1e8:.4f} tKAS")
        
        # 建立交易
        tx = create_transaction(
            utxo_entry_source=entries,
            outputs=outputs,
            priority_fee=TX_FEE,
            payload=payload
        )
        
        # 簽名
        signed_tx = sign_transaction(tx, [pk], False)
        
        # 發送（使用 rpc_manager 的 submit_transaction）
        from rpc_manager import submit_transaction
        tx_id = await submit_transaction(signed_tx, allow_orphan=False)
        
        logger.info(f"Payment sent: {tx_id} ({amount / 1e8:.4f} tKAS from user {user_id})")
        
        return tx_id

async def send_to_tree(user_id: int, pin: str, amount: int, memo: str = "") -> str:
    """
    發送到大地之樹（遊戲收款）
    
    用於：輪盤下注、英雄召喚、PvP 等
    """
    payload = memo.encode('utf-8') if memo else None
    return await send_payment(user_id, pin, TREE_ADDRESS, amount, payload)


async def send_summon_payment(user_id: int, pin: str) -> str:
    """
    發送召喚英雄的付款（10 mana）
    
    這是新流程的第一步：先付款，後取命運區塊
    返回 payment_tx_id 用於後續驗證
    """
    SUMMON_COST = 10  # 10 tKAS
    amount = int(SUMMON_COST * 1e8)  # 轉換為 sompi
    
    logger.info(f"📤 發送召喚付款: {SUMMON_COST} tKAS from user {user_id}")
    
    tx_id = await send_payment(user_id, pin, TREE_ADDRESS, amount, None)
    
    logger.info(f"✅ 召喚付款成功: {tx_id}")
    return tx_id


async def send_from_tree(to_address: str, amount: int, memo: str = "") -> str:
    """
    從大地之樹發送（獎勵發放）
    
    Args:
        to_address: 接收地址
        amount: 金額（sompi）
        memo: 備註
    
    Returns:
        交易 ID
    """
    import json as json_lib
    from pathlib import Path
    
    # 載入大地之樹私鑰（Nami testnet wallet）
    secrets_path = Path(__file__).parent.parent.parent / "clawd" / ".secrets" / "testnet-wallet.json"
    if not secrets_path.exists():
        # 嘗試另一個路徑
        secrets_path = Path.home() / "clawd" / ".secrets" / "testnet-wallet.json"
    
    if not secrets_path.exists():
        raise ValueError("找不到大地之樹私鑰")
    
    with open(secrets_path) as f:
        tree_wallet = json_lib.load(f)
    
    tree_pk_hex = tree_wallet.get("private_key", "")
    if not tree_pk_hex:
        raise ValueError("大地之樹私鑰無效")
    
    tree_pk = PrivateKey(tree_pk_hex)
    
    # 使用統一 RPC 管理器（自動重連）
    from rpc_manager import get_utxos, submit_transaction
    
    # 取得 UTXO
    entries = await get_utxos(TREE_ADDRESS)
    
    if not entries:
        raise ValueError("大地之樹沒有餘額")
    
    # 選擇 UTXO
    total_needed = amount + TX_FEE
    selected = []
    total = 0
    
    for e in sorted(entries, key=lambda x: x["utxoEntry"]["amount"], reverse=True):
        selected.append(e)
        total += e["utxoEntry"]["amount"]
        if total >= total_needed:
            break
    
    if total < total_needed:
        raise ValueError(f"大地之樹餘額不足：需要 {total_needed/1e8:.4f} tKAS")
    
    # 建立交易
    to_addr = Address(to_address)
    tree_addr = Address(TREE_ADDRESS)
    
    change = total - amount - TX_FEE
    outputs = [PaymentOutput(to_addr, amount)]
    if change > 0:
        outputs.append(PaymentOutput(tree_addr, change))
    
    tx = create_transaction(
        utxo_entry_source=selected,
        outputs=outputs,
        priority_fee=TX_FEE,
        payload=memo.encode('utf-8') if memo else None
    )
    
    signed_tx = sign_transaction(tx, [tree_pk], False)
    tx_id = await submit_transaction(signed_tx, allow_orphan=False)
    
    logger.info(f"🌲 大地之樹發送 | {amount/1e8:.4f} tKAS → {to_address[:20]}... | TX: {tx_id[:16]}...")
    
    return tx_id


async def get_tree_balance() -> int:
    """取得大地之樹餘額 - 使用統一 RPC 管理器"""
    from rpc_manager import get_utxos
    
    entries = await get_utxos(TREE_ADDRESS)
    total = sum(e["utxoEntry"]["amount"] for e in entries)
    return total


async def refund_to_player(to_address: str, amount: int) -> str:
    """
    退款給玩家（召喚失敗時使用）
    
    Args:
        to_address: 玩家錢包地址
        amount: 金額（sompi）
    
    Returns:
        交易 ID
    """
    return await send_from_tree(to_address, amount, memo="refund")


# ═══════════════════════════════════════════════════════════════════════════════
# Inscription（符合 KRC-20/721 標準）
# ═══════════════════════════════════════════════════════════════════════════════

async def self_inscription(
    user_id: int,
    pin: str,
    payload: dict | bytes,
    amount: int = 0
) -> str:
    """
    玩家自己打給自己 + Payload（真正的 Inscription！）
    
    這是 KRC-20/721 風格的 inscription：
    - 自己的地址 → 自己的地址
    - 附帶 payload
    - 由玩家自己簽名
    
    Args:
        user_id: 用戶 ID
        pin: PIN 碼
        payload: 要刻入的資料（dict 會自動轉 JSON）
        amount: 附帶金額（sompi），預設 0
    
    Returns:
        交易 ID
    """
    # 驗證 PIN
    if not verify_pin(user_id, pin):
        raise ValueError("PIN 碼錯誤")
    
    pk_hex, address = get_wallet(user_id, pin)
    pk = PrivateKey(pk_hex)
    
    # 準備 payload
    if isinstance(payload, dict):
        import json as json_lib
        payload_bytes = json_lib.dumps(payload, separators=(',', ':')).encode('utf-8')
    else:
        payload_bytes = payload
    
    if len(payload_bytes) > 1000:
        raise ValueError(f"Payload 太大: {len(payload_bytes)} bytes (最大 1000)")
    
    # 使用統一 RPC 管理器
    from rpc_manager import get_utxos, submit_transaction
    
    # 取得 UTXO
    entries = await get_utxos(address)
    
    if not entries:
        raise ValueError("錢包沒有餘額（需要手續費）")
    
    # 計算總餘額
    total = sum(e["utxoEntry"]["amount"] for e in entries)
    required = amount + TX_FEE
    if total < required:
        raise ValueError(f"餘額不足：需要 {required / 1e8:.4f} tKAS，只有 {total / 1e8:.4f} tKAS")
    
    # 建立輸出（打給自己）
    to_addr = Address(address)
    outputs = [PaymentOutput(to_addr, amount)] if amount > 0 else []
    
    # 建立交易（自己 → 自己 + payload）
    tx = create_transaction(
        utxo_entry_source=entries,
        outputs=outputs,
        priority_fee=TX_FEE,
        payload=payload_bytes
    )
    
    # 簽名（用自己的私鑰）
    signed_tx = sign_transaction(tx, [pk], False)
    
    # 發送
    tx_id = await submit_transaction(signed_tx, allow_orphan=False)
    
    logger.info(f"Self-inscription: {tx_id} (user {user_id}, payload {len(payload_bytes)} bytes)")
    
    return tx_id

async def mint_hero_inscription_only(
    user_id: int,
    pin: str,
    hero_payload: dict
) -> str:
    """
    只發送 Inscription TX（付款已在外部完成）
    
    新流程專用：
    1. 外部先發 payment_tx
    2. 確認後取得命運區塊
    3. 調用此函數只發 inscription
    
    Args:
        user_id: 用戶 ID
        pin: 用戶 PIN
        hero_payload: 英雄 payload（應已包含 payment_tx）
    
    Returns:
        inscription_tx_id
    """
    import json as json_lib
    
    # 取得用戶錢包
    result = get_wallet(user_id, pin)
    if not result:
        raise ValueError("錢包不存在或 PIN 錯誤")
    private_key_hex, address = result
    
    pk = PrivateKey(private_key_hex)
    
    logger.info(f"📝 發送 Inscription TX (payment 已完成)...")
    
    payload_bytes = json_lib.dumps(hero_payload, separators=(',', ':')).encode('utf-8')
    
    if len(payload_bytes) > 1000:
        raise ValueError(f"Payload 太大: {len(payload_bytes)} bytes (最大 1000)")
    
    # 使用統一 RPC 管理器（含自動重連）
    from rpc_manager import get_utxos, submit_transaction
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # 取得 UTXO（使用 rpc_manager，自動重連）
            all_entries = await get_utxos(address)
            
            if not all_entries:
                raise ValueError("錢包沒有餘額")
            
            # 優先使用小額 UTXO
            MAX_UTXO = 10000000  # 0.1 tKAS
            small_entries = [e for e in all_entries if e["utxoEntry"]["amount"] <= MAX_UTXO]
            
            if not small_entries:
                logger.info("  沒有小額 UTXO，使用最小的 UTXO")
                small_entries = all_entries
            
            entry = min(small_entries, key=lambda x: x["utxoEntry"]["amount"])
            amount = entry["utxoEntry"]["amount"]
            
            logger.info(f"  [嘗試 {attempt+1}/{max_retries}] 使用 UTXO: {amount / 1e8:.6f} tKAS")
            
            # 單一輸出（自己 → 自己）
            self_addr = Address(address)
            fee = 2000
            self_amount = amount - fee
            
            outputs = [PaymentOutput(self_addr, self_amount)]
            
            tx = create_transaction(
                utxo_entry_source=[entry],
                outputs=outputs,
                priority_fee=0,
                payload=payload_bytes
            )
            
            signed_tx = sign_transaction(tx, [pk], False)
            inscription_tx_id = await submit_transaction(signed_tx, allow_orphan=False)
            
            logger.info(f"✅ Inscription TX 成功: {inscription_tx_id}")
            
            return inscription_tx_id
            
        except Exception as e:
            last_error = e
            error_msg = str(e).lower()
            
            if 'already spent' in error_msg or 'mempool' in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"  ⏳ UTXO 衝突，等待 {wait_time} 秒後重試...")
                    await asyncio.sleep(wait_time)
                    continue
            
            raise
    
    raise Exception(f"Inscription TX 發送失敗（重試 {max_retries} 次）: {last_error}")


async def mint_hero_inscription(
    user_id: int,
    pin: str,
    hero_payload: dict,
    mint_cost: int = None,
    skip_payment: bool = False
) -> tuple[str, str]:
    """
    鑄造英雄 Inscription（舊流程：兩筆交易一起發）
    
    注意：新流程應使用 send_summon_payment + mint_hero_inscription_only
    
    流程：
    1. TX1: 玩家 → 大地之樹（驅動費）
    2. TX2: 玩家 → 玩家 + payload（inscription，包含 TX1 證明）
    
    注意：Kaspa storage mass 限制，TX2 只能單一輸出
    
    Args:
        user_id: 用戶 ID
        pin: PIN 碼
        hero_payload: 英雄資料（會自動加入 payment_tx）
        mint_cost: 鑄造費用（sompi），預設 10 tKAS
        skip_payment: 跳過付費（測試用）
    
    Returns:
        (payment_tx_id, inscription_tx_id)
    """
    import json as json_lib
    from hero_game import SUMMON_COST
    
    # 驗證 PIN
    if not verify_pin(user_id, pin):
        raise ValueError("PIN 碼錯誤")
    
    pk_hex, address = get_wallet(user_id, pin)
    pk = PrivateKey(pk_hex)
    
    # 計算費用
    if mint_cost is None:
        mint_cost = int(SUMMON_COST * 1e8)  # 10 tKAS
    
    payment_tx_id = None
    
    # 使用統一 RPC 管理器（自動重連）
    from rpc_manager import get_utxos, submit_transaction
    
    # ═══════════════════════════════════════════════════════════════════════
    # TX1: 付費給大地之樹（驅動費）
    # ═══════════════════════════════════════════════════════════════════════
    if not skip_payment:
        logger.info(f"📤 TX1: 付費 {mint_cost / 1e8:.2f} tKAS 給大地之樹...")
        
        # 取得 UTXO（用大額的來付費）
        entries = await get_utxos(address)
        
        if not entries:
            raise ValueError("錢包沒有餘額")
        
        # 找足夠支付的 UTXO
        total_needed = mint_cost + TX_FEE
        selected = []
        total = 0
        
        for e in sorted(entries, key=lambda x: x["utxoEntry"]["amount"], reverse=True):
            selected.append(e)
            total += e["utxoEntry"]["amount"]
            if total >= total_needed:
                break
        
        if total < total_needed:
            raise ValueError(f"餘額不足：需要 {total_needed / 1e8:.4f} tKAS")
        
        # 建立付費交易
        tree_addr = Address(TREE_ADDRESS)
        self_addr = Address(address)
        
        change = total - mint_cost - TX_FEE
        outputs = [PaymentOutput(tree_addr, mint_cost)]
        if change > 0:
            outputs.append(PaymentOutput(self_addr, change))
        
        tx = create_transaction(
            utxo_entry_source=selected,
            outputs=outputs,
            priority_fee=TX_FEE
        )
        
        signed_tx = sign_transaction(tx, [pk], False)
        payment_tx_id = await submit_transaction(signed_tx, allow_orphan=False)
        
        logger.info(f"✅ TX1 成功: {payment_tx_id}")
        
        # 等待讓 UTXO 更新（mempool 確認需要時間）
        await asyncio.sleep(5)
    
    # ═══════════════════════════════════════════════════════════════════════
    # TX2: Inscription（自己 → 自己 + payload）帶重試機制
    # ═══════════════════════════════════════════════════════════════════════
    logger.info(f"📝 TX2: 發送 inscription...")
    
    # 加入付費證明到 payload
    if payment_tx_id:
        hero_payload["payment_tx"] = payment_tx_id
    
    payload_bytes = json_lib.dumps(hero_payload, separators=(',', ':')).encode('utf-8')
    
    if len(payload_bytes) > 1000:
        raise ValueError(f"Payload 太大: {len(payload_bytes)} bytes (最大 1000)")
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # 取得 UTXO（需要小額的來發 inscription）
            all_entries = await get_utxos(address)
            
            if not all_entries:
                raise ValueError("錢包沒有餘額（需要小額 UTXO 發 inscription）")
            
            # 優先使用小額 UTXO（< 0.1 tKAS），但如果沒有就用最小的
            MAX_UTXO = 10000000  # 0.1 tKAS
            small_entries = [e for e in all_entries if e["utxoEntry"]["amount"] <= MAX_UTXO]
            
            if not small_entries:
                # 沒有小額 UTXO，使用最小的 UTXO（remint 等情況）
                logger.info("  沒有小額 UTXO，使用最小的 UTXO")
                small_entries = all_entries  # 使用全部，下面會選最小的
            
            # 選最小的 UTXO（節省大 UTXO）
            entry = min(small_entries, key=lambda x: x["utxoEntry"]["amount"])
            amount = entry["utxoEntry"]["amount"]
            
            logger.info(f"  [嘗試 {attempt+1}/{max_retries}] 使用小 UTXO: {amount / 1e8:.6f} tKAS")
            
            # 單一輸出（自己 → 自己）
            self_addr = Address(address)
            fee = 2000
            self_amount = amount - fee
            
            outputs = [PaymentOutput(self_addr, self_amount)]
            
            tx = create_transaction(
                utxo_entry_source=[entry],
                outputs=outputs,
                priority_fee=0,
                payload=payload_bytes
            )
            
            signed_tx = sign_transaction(tx, [pk], False)
            inscription_tx_id = await submit_transaction(signed_tx, allow_orphan=False)
            
            logger.info(f"✅ TX2 成功: {inscription_tx_id}")
            logger.info(f"🎴 Hero mint 完成 | user={user_id} | payment={payment_tx_id} | inscription={inscription_tx_id}")
            
            return payment_tx_id, inscription_tx_id
            
        except Exception as e:
            last_error = e
            error_msg = str(e).lower()
            
            # 如果是 UTXO 已花費的錯誤，等待後重試
            if 'already spent' in error_msg or 'mempool' in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # 5, 10, 15 秒遞增
                    logger.warning(f"  ⏳ UTXO 衝突，等待 {wait_time} 秒後重試...")
                    await asyncio.sleep(wait_time)
                    continue
            
            # 其他錯誤直接拋出
            raise
    
    # 重試都失敗
    raise Exception(f"TX2 發送失敗（重試 {max_retries} 次）: {last_error}")

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
