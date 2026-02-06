#!/usr/bin/env python3
"""
🌊 Kaspa 交易發送模組
用於在 Kaspa 區塊鏈上發送帶 payload 的交易

by Nami 🌊
"""

import asyncio
import json
import logging
from pathlib import Path
from kaspa import (
    RpcClient, PrivateKey, Address, PaymentOutput,
    create_transaction, sign_transaction
)

logger = logging.getLogger(__name__)

WALLET_FILE = Path("/home/ymchang/clawd/.secrets/testnet-wallet.json")
RPC_URL = "ws://127.0.0.1:17210"
NETWORK_ID = "testnet-10"

def load_wallet() -> dict:
    """載入錢包"""
    with open(WALLET_FILE) as f:
        return json.load(f)

async def send_payload_tx(payload: dict | bytes, min_fee: int = 5000) -> str:
    """
    發送帶 payload 的交易
    
    Args:
        payload: 要嵌入的資料 (dict 會轉成 JSON)
        min_fee: 最小手續費 (sompi)
    
    Returns:
        交易 ID
    """
    # 準備 payload
    if isinstance(payload, dict):
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    else:
        payload_bytes = payload
    
    if len(payload_bytes) > 1000:  # Kaspa payload 限制
        raise ValueError(f"Payload 太大: {len(payload_bytes)} bytes (最大 1000)")
    
    # 載入錢包
    wallet = load_wallet()
    pk = PrivateKey(wallet['private_key'])
    address = Address(wallet['address'])
    
    # 連接 RPC
    client = RpcClient(url=RPC_URL, network_id=NETWORK_ID)
    await client.connect()
    
    try:
        # 取得 UTXO
        utxo_response = await client.get_utxos_by_addresses({'addresses': [wallet['address']]})
        entries = utxo_response.get('entries', [])
        
        if not entries:
            raise Exception("錢包沒有 UTXO")
        
        # 優先使用非 coinbase 的小額 UTXO
        non_coinbase = [e for e in entries if not e['utxoEntry'].get('isCoinbase', False)]
        
        # 找一個足夠支付手續費的 UTXO
        suitable = [e for e in (non_coinbase or entries) if e['utxoEntry']['amount'] > min_fee * 2]
        
        if not suitable:
            raise Exception(f"沒有足夠大的 UTXO (需要 > {min_fee * 2} sompi)")
        
        # 用最小的合適 UTXO
        entry = min(suitable, key=lambda e: e['utxoEntry']['amount'])
        amount = entry['utxoEntry']['amount']
        
        logger.info(f"使用 UTXO: {amount / 1e8:.6f} tKAS")
        
        # 計算輸出
        send_amount = amount - min_fee
        outputs = [PaymentOutput(address, send_amount)]
        
        # 建立交易
        tx = create_transaction(
            utxo_entry_source=[entry],
            outputs=outputs,
            priority_fee=0,
            payload=payload_bytes
        )
        
        # 簽名
        signed_tx = sign_transaction(tx, [pk], False)
        
        # 發送
        result = await client.submit_transaction({
            'transaction': signed_tx,
            'allow_orphan': False
        })
        
        tx_id = result.get('transactionId', str(result))
        logger.info(f"交易發送成功: {tx_id}")
        
        return tx_id
        
    finally:
        await client.disconnect()

async def get_current_daa() -> int:
    """取得當前 DAA score"""
    client = RpcClient(url=RPC_URL, network_id=NETWORK_ID)
    await client.connect()
    try:
        info = await client.get_block_dag_info()
        return info.get('virtualDaaScore', 0)
    finally:
        await client.disconnect()

# 測試
if __name__ == "__main__":
    async def test():
        payload = {"g": "nami_hero", "type": "test", "msg": "Hello from kaspa_tx.py!"}
        tx_id = await send_payload_tx(payload)
        print(f"TX ID: {tx_id}")
        print(f"🔗 https://explorer-tn10.kaspa.org/txs/{tx_id}")
    
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test())
