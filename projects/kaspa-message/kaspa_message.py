#!/usr/bin/env python3
"""
🌊 Kaspa Testnet 訊息嵌入器 (完整版)
使用 kaspa Python SDK

by Nami 🌊
"""

import asyncio
import json
import os
from kaspa import (
    ScriptBuilder, Opcodes, RpcClient, Resolver,
    Mnemonic, XPrv, DerivationPath, 
    PrivateKey, Address, ScriptPublicKey,
    Generator, GeneratorSummary, PaymentOutput,
    kaspa_to_sompi, sompi_to_kaspa,
    UtxoEntries, UtxoEntry
)

WALLET_FILE = os.path.expanduser("~/clawd/.secrets/testnet-wallet.json")

def load_wallet():
    """載入測試網錢包"""
    with open(WALLET_FILE) as f:
        return json.load(f)

def create_op_return_script(message: str) -> bytes:
    """
    創建 OP_RETURN script
    """
    message_bytes = message.encode('utf-8')
    if len(message_bytes) > 75:
        raise ValueError("訊息太長 (最大 75 bytes)")
    
    # 手動構建 OP_RETURN script
    # 格式: [OP_RETURN (0x6a)] [length] [data]
    script = bytes([0x6a, len(message_bytes)]) + message_bytes
    return script

def parse_op_return_script(script: bytes) -> str:
    """
    解析 OP_RETURN script
    """
    if len(script) < 2 or script[0] != 0x6a:
        return None
    
    length = script[1]
    if len(script) < 2 + length:
        return None
    
    return script[2:2+length].decode('utf-8')

async def embed_message(message: str):
    """
    在 Kaspa Testnet 嵌入訊息
    """
    print("🌊 Kaspa Testnet 訊息嵌入器")
    print("=" * 50)
    print(f"📝 訊息: {message}")
    print()
    
    # 載入錢包
    wallet = load_wallet()
    address = wallet['address']
    private_key_hex = wallet.get('private_key', '')
    
    print(f"💰 錢包: {address}")
    
    # 連接到節點
    print("🔗 連接到 testnet...")
    resolver = Resolver()
    client = RpcClient(resolver=resolver, network_id="testnet-10")
    
    try:
        await client.connect()
        print("✅ 已連接！")
    except Exception as e:
        print(f"❌ 連接失敗: {e}")
        print()
        print("💡 確保本地 kaspad testnet 節點正在運行")
        return None
    
    # 獲取餘額
    try:
        balance_result = await client.get_balance_by_address(str(address))
        balance = int(balance_result.get('balance', 0))
        print(f"   餘額: {sompi_to_kaspa(balance):.8f} tKAS")
    except Exception as e:
        print(f"⚠️ 無法獲取餘額: {e}")
        balance = 0
    
    # 創建 OP_RETURN script
    op_return_script = create_op_return_script(message)
    print(f"\n📜 OP_RETURN Script:")
    print(f"   Hex: {op_return_script.hex()}")
    print(f"   長度: {len(op_return_script)} bytes")
    
    # 驗證解析
    parsed = parse_op_return_script(op_return_script)
    print(f"   驗證: {parsed}")
    
    print()
    print("=" * 50)
    print("📋 要發送帶訊息的交易，需要：")
    print("   1. 獲取 UTXOs")
    print("   2. 構建交易 (包含 OP_RETURN output)")
    print("   3. 簽名交易")
    print("   4. 提交到網路")
    print()
    print("💡 可以使用 kaspa-wallet CLI:")
    print(f"   kaspa-wallet --testnet send \\")
    print(f"     --op-return '{message}' \\")
    print(f"     -a <your-address> -v 0")
    
    await client.disconnect()
    return op_return_script

async def read_tx_data(tx_id: str):
    """
    從交易中讀取嵌入的資料
    """
    print(f"🔍 讀取交易: {tx_id[:20]}...")
    
    resolver = Resolver()
    client = RpcClient(resolver=resolver, network_id="testnet-10")
    
    try:
        await client.connect()
        
        # 查詢交易
        # 注意：需要節點支持相應的 RPC
        # 或者使用區塊瀏覽器 API
        
        print("⚠️ 交易查詢需要 explorer API 或特定 RPC")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
    finally:
        await client.disconnect()

def demo():
    """
    演示 OP_RETURN 創建和解析
    """
    print("🌊 OP_RETURN 演示")
    print("=" * 50)
    
    messages = [
        "Hello Kaspa!",
        "Nami was here 🌊",
        "BlockDAG is the future",
    ]
    
    for msg in messages:
        print(f"\n📝 訊息: {msg}")
        script = create_op_return_script(msg)
        print(f"   Script: {script.hex()}")
        parsed = parse_op_return_script(script)
        print(f"   解析: {parsed}")
        assert parsed == msg
        print("   ✅ OK")
    
    print("\n" + "=" * 50)
    print("📋 Script 格式: [0x6a] [length] [data]")
    print("   0x6a = OP_RETURN")
    print("   這個 output 不可花費，只用於存資料")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--demo':
            demo()
        elif sys.argv[1] == '--read':
            tx_id = sys.argv[2] if len(sys.argv) > 2 else ""
            asyncio.run(read_tx_data(tx_id))
        else:
            message = ' '.join(sys.argv[1:])
            asyncio.run(embed_message(message))
    else:
        demo()
