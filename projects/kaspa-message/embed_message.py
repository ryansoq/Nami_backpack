#!/usr/bin/env python3
"""
🌊 Kaspa 訊息嵌入器
在 Kaspa 交易中嵌入任意訊息（使用 OP_RETURN）

by Nami 🌊
"""

import asyncio
import json
import sys
import os

# 添加 kaspa-pminer 路徑
sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))

import grpc
import kaspa_pb2
import kaspa_pb2_grpc

# OP_RETURN = 0x6a
OP_RETURN = 0x6a

def create_op_return_script(message: bytes) -> bytes:
    """
    創建 OP_RETURN script
    
    格式: OP_RETURN + length + data
    """
    if len(message) > 80:
        raise ValueError("Message too long (max 80 bytes)")
    
    script = bytes([OP_RETURN, len(message)]) + message
    return script

def parse_op_return_script(script: bytes) -> bytes:
    """
    解析 OP_RETURN script，提取訊息
    """
    if len(script) < 2:
        return None
    
    if script[0] != OP_RETURN:
        return None
    
    length = script[1]
    if len(script) < 2 + length:
        return None
    
    return script[2:2+length]

class KaspaMessenger:
    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.address = f"127.0.0.1:{16210 if testnet else 16110}"
        self.channel = None
        self.stub = None
    
    def connect(self):
        print(f"🔗 連接到 {self.address}...")
        self.channel = grpc.insecure_channel(self.address)
        self.stub = kaspa_pb2_grpc.RPCStub(self.channel)
        
        # 測試連接
        req = kaspa_pb2.KaspadMessage(
            getInfoRequest=kaspa_pb2.GetInfoRequestMessage()
        )
        resp = next(self.stub.MessageStream(iter([req])))
        if resp.HasField('getInfoResponse'):
            info = resp.getInfoResponse
            print(f"✅ 已連接！版本: {info.serverVersion}")
            print(f"   同步: {info.isSynced}")
            return True
        return False
    
    def get_utxos(self, address: str):
        """取得地址的 UTXOs"""
        req = kaspa_pb2.KaspadMessage(
            getUtxosByAddressesRequest=kaspa_pb2.GetUtxosByAddressesRequestMessage(
                addresses=[address]
            )
        )
        resp = next(self.stub.MessageStream(iter([req])))
        if resp.HasField('getUtxosByAddressesResponse'):
            return resp.getUtxosByAddressesResponse.entries
        return []
    
    def submit_transaction(self, tx):
        """提交交易"""
        req = kaspa_pb2.KaspadMessage(
            submitTransactionRequest=kaspa_pb2.SubmitTransactionRequestMessage(
                transaction=tx,
                allowOrphan=False
            )
        )
        resp = next(self.stub.MessageStream(iter([req])))
        if resp.HasField('submitTransactionResponse'):
            return resp.submitTransactionResponse.transactionId
        return None
    
    def embed_message(self, wallet_address: str, message: str, private_key: bytes = None):
        """
        嵌入訊息到區塊鏈
        
        注意：這個簡化版本只展示概念，實際需要：
        1. 正確的 UTXO 選擇
        2. 交易簽名
        3. 找零處理
        """
        print(f"\n📝 嵌入訊息: {message}")
        
        # 創建 OP_RETURN script
        op_return_script = create_op_return_script(message.encode('utf-8'))
        print(f"   Script: {op_return_script.hex()}")
        
        # TODO: 完整實現需要：
        # 1. 獲取 UTXOs
        # 2. 構建交易 inputs
        # 3. 創建 outputs (OP_RETURN + 找零)
        # 4. 簽名
        # 5. 提交
        
        print("\n⚠️ 完整實現需要錢包簽名功能")
        print("   可以使用 kaspa-wallet CLI 或 Python SDK")
        
        return op_return_script
    
    def read_message_from_tx(self, tx_id: str):
        """
        從交易中讀取嵌入的訊息
        """
        print(f"\n🔍 讀取交易: {tx_id[:16]}...")
        
        # TODO: 實現交易查詢
        # 可能需要使用區塊瀏覽器 API 或節點的 getTransaction RPC
        
        print("⚠️ 需要實現交易查詢功能")

def demo():
    """
    演示 OP_RETURN script 的創建和解析
    """
    print("=" * 60)
    print("🌊 Kaspa OP_RETURN 訊息演示")
    print("=" * 60)
    
    # 測試訊息
    messages = [
        "Hello Kaspa!",
        "Nami was here 🌊",
        "KRC-20 is cool",
    ]
    
    for msg in messages:
        print(f"\n📝 原始訊息: {msg}")
        
        # 創建 script
        script = create_op_return_script(msg.encode('utf-8'))
        print(f"   Script (hex): {script.hex()}")
        print(f"   Script 長度: {len(script)} bytes")
        
        # 解析回來
        parsed = parse_op_return_script(script)
        decoded = parsed.decode('utf-8') if parsed else None
        print(f"   解析結果: {decoded}")
        
        # 驗證
        assert decoded == msg, "訊息不匹配！"
        print("   ✅ 驗證通過")
    
    print("\n" + "=" * 60)
    print("📋 OP_RETURN Script 格式:")
    print("   [0x6a] [length] [data...]")
    print("   0x6a = OP_RETURN")
    print("=" * 60)

if __name__ == '__main__':
    demo()
