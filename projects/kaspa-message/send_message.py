#!/usr/bin/env python3
"""
🌊 Kaspa 訊息嵌入器 (使用 kaspa SDK)
在 Kaspa 測試網交易中嵌入訊息並讀回

by Nami 🌊
"""

import asyncio
import json
import sys
from kaspa import (
    ScriptBuilder, Opcodes, RpcClient, Resolver,
    PrivateKey, PublicKey, Address,
    TransactionOutput, ScriptPublicKey,
    create_transaction, sign_transaction,
    pay_to_address_script, kaspa_to_sompi
)

async def embed_message(
    mnemonic: str,
    message: str,
    testnet: bool = True
):
    """
    在 Kaspa 交易中嵌入訊息
    """
    print(f"🌊 Kaspa 訊息嵌入器")
    print(f"=" * 50)
    print(f"📝 訊息: {message}")
    print(f"🌐 網路: {'Testnet' if testnet else 'Mainnet'}")
    print()
    
    # 1. 創建 OP_RETURN script
    message_bytes = message.encode('utf-8')
    if len(message_bytes) > 80:
        raise ValueError("訊息太長 (最大 80 bytes)")
    
    script_builder = ScriptBuilder()
    script_builder.add_op(Opcodes.OpReturn)
    script_builder.add_data(message_bytes)
    op_return_script = script_builder.drain()
    
    print(f"📜 OP_RETURN Script:")
    print(f"   Hex: {op_return_script.hex()}")
    print(f"   長度: {len(op_return_script)} bytes")
    print()
    
    # 2. 連接到節點
    network_id = "testnet-10" if testnet else "mainnet"
    print(f"🔗 連接到 {network_id}...")
    
    resolver = Resolver()
    client = RpcClient(resolver=resolver, network_id=network_id)
    await client.connect()
    
    info = await client.get_server_info()
    print(f"✅ 已連接！")
    print()
    
    # 3. 從助記詞載入錢包
    from kaspa import Mnemonic, XPrv, DerivationPath
    
    mnemonic_obj = Mnemonic(mnemonic)
    seed = mnemonic_obj.to_seed()
    xprv = XPrv.from_seed(seed)
    
    # 派生路徑: m/44'/111111'/0'/0/0
    path = DerivationPath("m/44'/111111'/0'/0/0")
    child_xprv = xprv.derive_path(path)
    private_key = child_xprv.to_private_key()
    public_key = private_key.to_public_key()
    
    prefix = "kaspatest" if testnet else "kaspa"
    address = public_key.to_address(prefix)
    
    print(f"💰 錢包地址: {address}")
    
    # 4. 獲取 UTXOs
    utxos = await client.get_utxos_by_address(str(address))
    if not utxos:
        print("❌ 沒有可用的 UTXO！")
        await client.disconnect()
        return None
    
    print(f"   UTXOs: {len(utxos)} 個")
    
    # 5. 構建交易
    # 選擇第一個 UTXO
    utxo = utxos[0]
    input_amount = utxo.amount
    
    # OP_RETURN output (0 value)
    op_return_output = TransactionOutput(
        value=0,
        script_public_key=ScriptPublicKey(0, op_return_script)
    )
    
    # 找零 output
    fee = 10000  # 0.0001 KAS
    change_amount = input_amount - fee
    change_script = pay_to_address_script(str(address))
    change_output = TransactionOutput(
        value=change_amount,
        script_public_key=change_script
    )
    
    # 創建交易
    tx = create_transaction(
        inputs=[utxo],
        outputs=[op_return_output, change_output],
        change_address=str(address)
    )
    
    # 6. 簽名
    signed_tx = sign_transaction(tx, [private_key])
    
    print(f"\n📤 提交交易...")
    
    # 7. 提交
    tx_id = await client.submit_transaction(signed_tx)
    
    print(f"✅ 交易已提交！")
    print(f"   TX ID: {tx_id}")
    print(f"\n🔍 訊息已嵌入區塊鏈！")
    
    await client.disconnect()
    return tx_id

async def read_message(tx_id: str, testnet: bool = True):
    """
    從交易中讀取嵌入的訊息
    """
    print(f"🔍 讀取交易: {tx_id[:16]}...")
    
    network_id = "testnet-10" if testnet else "mainnet"
    resolver = Resolver()
    client = RpcClient(resolver=resolver, network_id=network_id)
    await client.connect()
    
    # 獲取交易
    # 注意：需要節點支持 getTransaction RPC
    # 或者使用區塊瀏覽器 API
    
    # TODO: 實現交易查詢
    print("⚠️ 交易查詢功能待實現")
    print("   可使用區塊瀏覽器查看交易詳情")
    
    await client.disconnect()

def demo_script_only():
    """
    只演示 script 創建（不需要網路連接）
    """
    print("🌊 OP_RETURN Script 演示")
    print("=" * 50)
    
    message = "Hello from Nami! 🌊"
    message_bytes = message.encode('utf-8')
    
    print(f"📝 訊息: {message}")
    print(f"   Bytes: {message_bytes.hex()}")
    print()
    
    # 創建 script
    script_builder = ScriptBuilder()
    script_builder.add_op(Opcodes.OpReturn)
    script_builder.add_data(message_bytes)
    script = script_builder.drain()
    
    print(f"📜 OP_RETURN Script:")
    print(f"   Hex: {script.hex()}")
    print(f"   長度: {len(script)} bytes")
    print()
    
    # 解析 script
    print("🔍 解析 Script:")
    if script[0] == 0x6a:  # OP_RETURN
        print("   [0] OP_RETURN (0x6a)")
        length = script[1]
        print(f"   [1] 長度: {length}")
        data = script[2:2+length]
        print(f"   [2:] 資料: {data.hex()}")
        decoded = data.decode('utf-8')
        print(f"   解碼: {decoded}")
    
    print()
    print("✅ Script 可以嵌入任何 Kaspa 交易的 output！")

if __name__ == '__main__':
    demo_script_only()
