#!/usr/bin/env python3
"""
🌊 Nami's Kaspa Graffiti
在 Kaspa 區塊鏈上留下訊息！

by Nami 🌊
"""

import asyncio
import json
import sys
from kaspa import (
    RpcClient,
    PrivateKey, Address, Hash,
    Generator, PaymentOutput,
    sign_transaction,
    kaspa_to_sompi, sompi_to_kaspa,
    UtxoEntries, UtxoEntry, UtxoEntryReference,
    TransactionOutpoint, ScriptPublicKey
)

WALLET_FILE = "/home/ymchang/clawd/.secrets/testnet-wallet.json"

def load_wallet():
    """載入測試網錢包"""
    with open(WALLET_FILE) as f:
        return json.load(f)

def dict_to_utxo_entry_ref(item):
    """將 dict 轉換為 UtxoEntryReference"""
    outpoint = TransactionOutpoint(
        transaction_id=Hash(item['outpoint']['transactionId']),
        index=item['outpoint']['index']
    )
    
    # scriptPublicKey 格式：前 4 hex (2 bytes) = version，後面 = script
    raw_spk = item['utxoEntry']['scriptPublicKey']
    version = int(raw_spk[:4], 16)
    script = bytes.fromhex(raw_spk[4:])
    
    entry = UtxoEntry(
        amount=item['utxoEntry']['amount'],
        script_public_key=ScriptPublicKey(version, script),
        block_daa_score=item['utxoEntry']['blockDaaScore'],
        is_coinbase=item['utxoEntry'].get('isCoinbase', False)
    )
    
    return UtxoEntryReference(
        outpoint=outpoint,
        entry=entry,
        address=Address(item['address'])
    )

async def send_graffiti(message: str, dry_run: bool = False):
    """
    在 Kaspa Testnet 上留下訊息
    
    Args:
        message: 要嵌入的訊息
        dry_run: 如果 True，只模擬不實際發送
    """
    print("🌊 Nami's Kaspa Graffiti", flush=True)
    print("=" * 50, flush=True)
    
    # 載入錢包
    wallet = load_wallet()
    address_str = wallet['address']
    private_key_hex = wallet.get('private_key', '')
    
    print(f"📝 訊息: {message}", flush=True)
    
    # 編碼訊息
    payload = message.encode('utf-8')
    if len(payload) > 80:
        print(f"❌ 訊息太長！最大 80 bytes，目前 {len(payload)} bytes", flush=True)
        return None
    
    print(f"   Hex: {payload.hex()}", flush=True)
    print(f"   長度: {len(payload)} bytes", flush=True)
    print(flush=True)
    
    print(f"💰 錢包: {address_str[:30]}...", flush=True)
    
    # 連接到本地節點 (wRPC/borsh on 17210)
    print("🔗 連接到 testnet wRPC (127.0.0.1:17210)...", flush=True)
    
    try:
        # 直接連接本地節點 (wRPC borsh 格式)
        client = RpcClient(
            url="ws://127.0.0.1:17210",
            network_id="testnet-10"
        )
        await client.connect()
        print("✅ 已連接！", flush=True)
    except Exception as e:
        print(f"❌ 連接失敗: {e}", flush=True)
        return None
    
    try:
        # 獲取伺服器資訊
        info = await client.get_server_info()
        print(f"   網路: testnet-10, synced: {info.get('isSynced', False)}", flush=True)
        
        # 獲取 UTXOs
        print("\n🔍 獲取 UTXOs...", flush=True)
        
        address = Address(address_str)
        utxo_response = await client.get_utxos_by_addresses({'addresses': [address_str]})
        
        # API 返回 {'entries': [...]}
        utxo_list = utxo_response.get('entries', [])
        
        if not utxo_list:
            print("❌ 沒有可用的 UTXO", flush=True)
            return None
        
        print(f"   找到 {len(utxo_list)} 個 UTXO", flush=True)
        
        # 計算總餘額
        total = sum(u['utxoEntry']['amount'] for u in utxo_list)
        print(f"   總餘額: {sompi_to_kaspa(total):.8f} tKAS", flush=True)
        
        # 轉換為 UtxoEntryReference 列表（只取前 10 個，足夠支付手續費）
        utxo_refs = [dict_to_utxo_entry_ref(u) for u in utxo_list[:10]]
        entries = UtxoEntries(utxo_refs)
        
        # 設定交易：發送給自己（主要是為了 payload）
        # 手續費約 0.0001 KAS = 10000 sompi
        fee = kaspa_to_sompi(0.0001)
        send_amount = kaspa_to_sompi(0.001)  # 發送少量給自己
        
        output = PaymentOutput(address, send_amount)
        
        print(f"\n📤 準備交易:", flush=True)
        print(f"   發送: {sompi_to_kaspa(send_amount):.8f} tKAS (給自己)", flush=True)
        print(f"   手續費: {sompi_to_kaspa(fee):.8f} tKAS", flush=True)
        print(f"   Payload: {message}", flush=True)
        
        # 使用 Generator 建立交易
        generator = Generator(
            network_id="testnet-10",
            entries=entries,
            change_address=address,
            outputs=[output],
            payload=payload,
            priority_fee=fee
        )
        
        # 獲取待簽名的交易
        print("\n✍️ 建立交易...", flush=True)
        
        # 從 generator 取得 pending transactions
        pending_txs = []
        for pending_tx in generator:
            pending_txs.append(pending_tx)
        
        if not pending_txs:
            print("❌ 無法建立交易", flush=True)
            return None
        
        print(f"   建立了 {len(pending_txs)} 個交易", flush=True)
        
        # 簽名
        private_key = PrivateKey(private_key_hex)
        
        for i, pending_tx in enumerate(pending_txs):
            # 簽名交易
            signed = sign_transaction(pending_tx.transaction, [private_key], False)
            
            print(f"\n📋 交易 #{i+1}:", flush=True)
            print(f"   ID: {signed.id}", flush=True)
            
            if dry_run:
                print("   [DRY RUN] 不實際發送", flush=True)
            else:
                # 提交交易
                print("   📡 提交到網路...", flush=True)
                try:
                    result = await client.submit_transaction({'transaction': signed, 'allowOrphan': False})
                    print(f"   ✅ 成功！TX ID: {result}", flush=True)
                except Exception as e:
                    print(f"   ❌ 提交失敗: {e}", flush=True)
        
        print("\n" + "=" * 50, flush=True)
        if not dry_run:
            print("🎉 訊息已永久刻在 Kaspa 區塊鏈上！", flush=True)
            print(f"🔍 可以在區塊瀏覽器查看交易", flush=True)
        
    except Exception as e:
        print(f"❌ 錯誤: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()

async def main():
    message = "Nami到此一遊 🌊"
    dry_run = "--dry-run" in sys.argv
    
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        message = sys.argv[1]
    
    await send_graffiti(message, dry_run)

if __name__ == "__main__":
    asyncio.run(main())
