#!/usr/bin/env python3
"""
Debug SDK submit - 使用官方 kaspa Python SDK 提交區塊
"""
import asyncio
import sys
import os

# 嘗試導入 kaspa SDK
try:
    from kaspa import RpcClient, Resolver
    print("✅ kaspa SDK 已導入", flush=True)
except ImportError as e:
    print(f"❌ kaspa SDK 導入失敗: {e}", flush=True)
    sys.exit(1)

async def main():
    print("\n🔗 連接到 testnet node...", flush=True)
    
    # 連接到本地 testnet 節點的 wRPC (Borsh)
    try:
        # 使用 wRPC endpoint
        client = RpcClient(
            resolver=None,
            url="ws://127.0.0.1:17210",
            encoding="borsh"  # 本地節點用 borsh
        )
        await client.connect()
        print("✅ 已連接！", flush=True)
        
        # 獲取節點信息
        info = await client.get_server_info()
        print(f"   版本: {info['serverVersion']}", flush=True)
        print(f"   同步: {info['isSynced']}", flush=True)
        
        # 獲取區塊模板
        wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"
        print(f"\n📦 獲取區塊模板...", flush=True)
        print(f"   錢包: {wallet[:30]}...", flush=True)
        
        template = await client.get_block_template(wallet, "ShioKaze SDK Test")
        
        print(f"\n📋 區塊模板:", flush=True)
        print(f"   isSynced: {template.get('isSynced')}", flush=True)
        
        block = template.get('block')
        if block:
            header = block.get('header', {})
            print(f"   timestamp: {header.get('timestamp')}", flush=True)
            print(f"   bits: {header.get('bits')}", flush=True)
            print(f"   daaScore: {header.get('daaScore')}", flush=True)
            print(f"   blueScore: {header.get('blueScore')}", flush=True)
            print(f"   transactions: {len(block.get('transactions', []))}", flush=True)
        
        await client.disconnect()
        print("\n✅ 測試完成！", flush=True)
        
    except Exception as e:
        print(f"❌ 錯誤: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
