#!/usr/bin/env python3
"""
🎰 Kaspa Roulette - 確定性開獎查詢
使用官方排序規則：blueWork > hash

用法：python3 draw.py <blueScore>

作者: Nami 🌊 & Ryan
"""

import urllib.request
import json
import sys

API_URL = "https://api-tn10.kaspa.org"
EXPLORER_URL = "https://explorer-tn10.kaspa.org/blocks"


def api_get(endpoint: str) -> dict:
    """呼叫 API"""
    url = f"{API_URL}{endpoint}"
    req = urllib.request.Request(url, headers={'User-Agent': 'KaspaRoulette/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_blocks_at_score(target_score: int) -> list:
    """取得指定 blueScore 的所有區塊"""
    data = api_get(f"/blocks-from-bluescore?blueScore={target_score}&limit=20")
    
    blocks = []
    for block in data:
        score = int(block.get('verboseData', {}).get('blueScore', 0))
        if score == target_score:
            blocks.append({
                'hash': block['verboseData']['hash'],
                'blueScore': score,
                'blueWork': block['header']['blueWork'],
                'isChainBlock': block['verboseData'].get('isChainBlock', False)
            })
    
    return blocks


def sort_blocks_official(blocks: list) -> list:
    """
    官方排序規則（來自 rusty-kaspa/consensus/src/processes/ghostdag/ordering.rs）
    
    1. 先按 blueWork 降序（數值大的優先）
    2. 如果相同，按 hash 升序（字母順序）
    """
    return sorted(blocks, key=lambda b: (-int(b['blueWork'], 16), b['hash']))


def hash_to_result(block_hash: str) -> int:
    """將區塊 hash 轉換為輪盤結果 (0-37)"""
    hash_int = int(block_hash, 16)
    return hash_int % 38


def get_color(number: int) -> str:
    """取得數字的顏色"""
    RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    if number == 0:
        return "🟢 綠(0)"
    elif number == 37:
        return "🟢 綠(00)"
    elif number in RED:
        return f"🔴 紅({number})"
    else:
        return f"⚫ 黑({number})"


def draw(target_score: int):
    """開獎！"""
    print(f"\n🎰 Kaspa Roulette 開獎查詢")
    print(f"=" * 60)
    print(f"📍 目標高度: {target_score:,}")
    print()
    
    # 取得該高度的所有區塊
    print("🔍 查詢區塊中...")
    blocks = get_blocks_at_score(target_score)
    
    if not blocks:
        print(f"❌ 找不到 blueScore={target_score} 的區塊")
        print(f"   可能還沒到達這個高度，或需要調整查詢範圍")
        return
    
    print(f"   找到 {len(blocks)} 個區塊\n")
    
    # 官方排序
    sorted_blocks = sort_blocks_official(blocks)
    
    # 顯示所有區塊
    print("📊 區塊列表（按官方規則排序）:")
    print("-" * 60)
    for i, block in enumerate(sorted_blocks):
        chain_mark = "⭐" if block['isChainBlock'] else "  "
        print(f"  {i+1}. {chain_mark} {block['hash'][:16]}...{block['hash'][-8:]}")
        print(f"       blueWork: {block['blueWork']}")
        print(f"       isChainBlock: {block['isChainBlock']}")
        print()
    
    # 取第一個（最高 blueWork）
    winner = sorted_blocks[0]
    result = hash_to_result(winner['hash'])
    
    print("=" * 60)
    print(f"🏆 開獎區塊（排序第一名）:")
    print(f"   Hash: {winner['hash']}")
    print(f"   blueWork: {winner['blueWork']} (0x → {int(winner['blueWork'], 16):,})")
    print(f"   isChainBlock: {winner['isChainBlock']}")
    print()
    print(f"🎲 開獎結果:")
    print(f"   {winner['hash']} mod 38 = {result}")
    print(f"   >>> {get_color(result)} <<<")
    print()
    print(f"🔗 驗證連結:")
    print(f"   {EXPLORER_URL}/{winner['hash']}")
    print("=" * 60)


def main():
    if len(sys.argv) < 2:
        # 沒給參數，查詢當前高度
        print("🔍 查詢當前 blueScore...")
        data = api_get("/info/virtual-chain-blue-score")
        current = data['blueScore']
        print(f"📍 當前高度: {current:,}")
        
        # 建議的開獎高度
        round_interval = 1000
        last_draw = (current // round_interval) * round_interval
        next_draw = last_draw + round_interval
        
        print(f"\n💡 建議:")
        print(f"   上一期開獎: python3 draw.py {last_draw}")
        print(f"   下一期開獎: {next_draw:,} (還差 {next_draw - current} blocks)")
        return
    
    try:
        target = int(sys.argv[1])
        draw(target)
    except ValueError:
        print(f"❌ 無效的 blueScore: {sys.argv[1]}")
        print("用法: python3 draw.py <blueScore>")


if __name__ == "__main__":
    main()
