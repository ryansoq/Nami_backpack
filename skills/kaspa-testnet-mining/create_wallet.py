#!/usr/bin/env python3
"""
🌊 Kaspa Testnet 錢包創建腳本
by Nami (波浪)

用法:
  python3 create_wallet.py
  python3 create_wallet.py --mainnet  # 主網錢包
"""

import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='創建 Kaspa 錢包')
    parser.add_argument('--mainnet', action='store_true', help='創建主網錢包')
    parser.add_argument('--output', '-o', type=str, help='輸出檔案路徑')
    args = parser.parse_args()
    
    try:
        from kaspa import Wallet, NetworkType
    except ImportError:
        print("❌ 請先安裝 kaspa SDK:")
        print("   pip install kaspa")
        return
    
    # 選擇網路
    network = NetworkType.MAINNET if args.mainnet else NetworkType.TESTNET
    network_name = "mainnet" if args.mainnet else "testnet"
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  🌊 Kaspa 錢包創建工具                                        ║
║  Network: {network_name.upper():<10}                                    ║
╚═══════════════════════════════════════════════════════════════╝
""")
    
    # 創建錢包
    print("🔐 正在創建錢包...")
    wallet = Wallet.create(network)
    
    # 取得資訊
    mnemonic = wallet.mnemonic()
    address = str(wallet.receive_address())
    
    print(f"""
✅ 錢包創建成功！

📍 地址:
   {address}

🔑 助記詞 (24 字) - 請務必安全備份！
   {mnemonic}

⚠️  警告: 助記詞是恢復錢包的唯一方式，請勿洩露給任何人！
""")
    
    # 保存到檔案
    output_path = args.output or f"kaspa-{network_name}-wallet.json"
    wallet_data = {
        'network': network_name,
        'address': address,
        'mnemonic': mnemonic,
        'created': __import__('datetime').datetime.now().isoformat(),
    }
    
    with open(output_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    print(f"💾 已保存到: {output_path}")
    print(f"\n🎉 完成！現在可以開始挖礦了～")

if __name__ == '__main__':
    main()
