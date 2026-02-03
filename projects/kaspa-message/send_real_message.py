#!/usr/bin/env python3
"""
🌊 在 Kaspa Testnet 嵌入訊息
by Nami 🌊
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))

import grpc
import kaspa_pb2
import kaspa_pb2_grpc
import struct

# 載入測試網錢包
WALLET_FILE = os.path.expanduser("~/clawd/.secrets/testnet-wallet.json")

def load_wallet():
    with open(WALLET_FILE) as f:
        return json.load(f)

def create_op_return_output(message: str):
    """創建 OP_RETURN output"""
    message_bytes = message.encode('utf-8')
    if len(message_bytes) > 75:  # OP_DATA_MAX
        raise ValueError("訊息太長")
    
    # OP_RETURN + push data
    script = bytes([0x6a, len(message_bytes)]) + message_bytes
    
    return kaspa_pb2.RpcTransactionOutput(
        amount=0,
        scriptPublicKey=kaspa_pb2.RpcScriptPublicKey(
            version=0,
            scriptPublicKey=script.hex()
        )
    )

async def send_message(message: str):
    """發送帶訊息的交易"""
    
    wallet = load_wallet()
    address = wallet['address']
    
    print(f"🌊 Kaspa Testnet 訊息嵌入")
    print(f"=" * 50)
    print(f"📝 訊息: {message}")
    print(f"💰 錢包: {address[:20]}...{address[-10:]}")
    print()
    
    # 連接到節點
    channel = grpc.insecure_channel("127.0.0.1:16210")
    stub = kaspa_pb2_grpc.RPCStub(channel)
    
    # 獲取 UTXOs
    print("🔍 獲取 UTXOs...")
    req = kaspa_pb2.KaspadMessage(
        getUtxosByAddressesRequest=kaspa_pb2.GetUtxosByAddressesRequestMessage(
            addresses=[address]
        )
    )
    resp = next(stub.MessageStream(iter([req])))
    
    if not resp.HasField('getUtxosByAddressesResponse'):
        print("❌ 無法獲取 UTXOs")
        return
    
    utxos = resp.getUtxosByAddressesResponse.entries
    if not utxos:
        print("❌ 沒有可用的 UTXO")
        return
    
    print(f"   找到 {len(utxos)} 個 UTXO")
    
    # 選擇第一個 UTXO
    utxo = utxos[0]
    input_amount = utxo.utxoEntry.amount
    print(f"   使用: {input_amount / 1e8:.8f} tKAS")
    
    # 創建 OP_RETURN output
    op_return = create_op_return_output(message)
    print(f"\n📜 OP_RETURN Script: {op_return.scriptPublicKey.scriptPublicKey}")
    
    # 這裡需要完整的交易構建和簽名
    # 由於 kaspa-pminer 只有 gRPC stubs，沒有簽名功能
    # 我們需要使用 kaspa Python SDK 或其他方式
    
    print("\n⚠️ 完整交易需要簽名功能")
    print("   建議使用 kaspa-wallet CLI:")
    print()
    print(f"   kaspa-wallet send --op-return '{message}'")
    print()
    print("   或者使用 kaspa Python SDK 的 sign_transaction")
    
    channel.close()

if __name__ == '__main__':
    message = sys.argv[1] if len(sys.argv) > 1 else "Hello from Nami! 🌊"
    asyncio.run(send_message(message))
