#!/usr/bin/env python3
"""
Debug SDK submit v2 - 使用官方 kaspa Python SDK
"""
import asyncio
import sys

from kaspa import RpcClient

async def main():
    print("🔗 連接到 testnet node...", flush=True)
    
    client = RpcClient(
        resolver=None,
        url="ws://127.0.0.1:17210",
        encoding="borsh"
    )
    await client.connect()
    print("✅ 已連接！", flush=True)
    
    # 嘗試不同的 request 格式
    wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"
    
    print("\n📦 嘗試獲取區塊模板...", flush=True)
    
    # 嘗試用字典
    try:
        template = await client.get_block_template({
            "pay_address": wallet,
            "extra_data": "test"
        })
        print(f"✅ 字典格式成功！", flush=True)
        print(f"   template: {template}", flush=True)
    except Exception as e:
        print(f"❌ 字典格式失敗: {e}", flush=True)
    
    # 嘗試只傳錢包地址字符串
    try:
        template = await client.get_block_template(wallet)
        print(f"✅ 字符串格式成功！", flush=True)
        print(f"   template: {template}", flush=True)
    except Exception as e:
        print(f"❌ 字符串格式失敗: {e}", flush=True)
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
