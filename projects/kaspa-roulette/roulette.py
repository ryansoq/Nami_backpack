#!/usr/bin/env python3
"""
🎰 Kaspa Roulette - Provably Fair 輪盤
用 Kaspa 區塊 hash 決定結果

開獎規則：見 RULES.md

作者: Nami 🌊 & Ryan
日期: 2026-02-04
"""

import urllib.request
import json
import time
import sys

# === 配置 ===
ROUND_INTERVAL = 1000        # 每 1000 blocks 開一局
BLOCKS_PER_SECOND = 14       # 約 14 blocks/sec
API_URL = "https://api-tn10.kaspa.org"
EXPLORER_URL = "https://explorer-tn10.kaspa.org/blocks"

# === 輪盤數字顏色 ===
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}


def api_get(endpoint: str) -> dict:
    """呼叫 API"""
    url = f"{API_URL}{endpoint}"
    req = urllib.request.Request(url, headers={'User-Agent': 'KaspaRoulette/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_color(number: int) -> str:
    """取得數字的顏色"""
    if number == 0:
        return "🟢 綠(0)"
    elif number == 37:
        return "🟢 綠(00)"
    elif number in RED_NUMBERS:
        return f"🔴 紅({number})"
    else:
        return f"⚫ 黑({number})"


def get_color_simple(number: int) -> str:
    """簡單顏色判斷"""
    if number == 0 or number == 37:
        return "green"
    elif number in RED_NUMBERS:
        return "red"
    else:
        return "black"


def check_bet(bet_type: str, result: int) -> bool:
    """檢查下注是否獲勝"""
    bet = bet_type.lower()
    
    if bet in ["紅", "red", "r"]:
        return result in RED_NUMBERS
    elif bet in ["黑", "black", "b"]:
        return result in BLACK_NUMBERS
    elif bet in ["奇", "odd", "o"]:
        return result > 0 and result < 37 and result % 2 == 1
    elif bet in ["偶", "even", "e"]:
        return result > 0 and result < 37 and result % 2 == 0
    elif bet in ["高", "high", "h"]:
        return 19 <= result <= 36
    elif bet in ["低", "low", "l"]:
        return 1 <= result <= 18
    elif bet == "0":
        return result == 0
    elif bet == "00":
        return result == 37
    elif bet.isdigit():
        return result == int(bet)
    return False


def get_payout(bet_type: str) -> int:
    """取得賠率 (包含本金)"""
    bet = bet_type.lower()
    
    if bet in ["紅", "黑", "red", "black", "r", "b", 
               "奇", "偶", "odd", "even", "o", "e",
               "高", "低", "high", "low", "h", "l"]:
        return 2  # 1:1 + 本金
    else:
        return 36  # 35:1 + 本金


def get_blue_score() -> int:
    """取得當前 blue score"""
    data = api_get("/info/virtual-chain-blue-score")
    return data["blueScore"]


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
    官方排序規則
    來源: rusty-kaspa/consensus/src/processes/ghostdag/ordering.rs
    
    1. blueWork 大的優先（降序）
    2. 如果相同，hash 字母順序小的優先（升序）
    """
    return sorted(blocks, key=lambda b: (-int(b['blueWork'], 16), b['hash']))


def draw_at_score(target_score: int) -> dict:
    """
    確定性開獎
    返回: {'hash': str, 'result': int, 'blocks_count': int}
    """
    blocks = get_blocks_at_score(target_score)
    
    if not blocks:
        return None
    
    # 官方排序
    sorted_blocks = sort_blocks_official(blocks)
    
    # 取第一個
    winner = sorted_blocks[0]
    result = int(winner['hash'], 16) % 38
    
    return {
        'hash': winner['hash'],
        'blueWork': winner['blueWork'],
        'result': result,
        'blocks_count': len(blocks),
        'all_blocks': sorted_blocks
    }


def display_wheel():
    """顯示輪盤"""
    print("""
    ╭─────────────────────────────────╮
    │      🎰 KASPA ROULETTE 🎰      │
    │─────────────────────────────────│
    │  🟢 0        🟢 00             │
    │─────────────────────────────────│
    │  🔴 1   ⚫ 2   🔴 3            │
    │  ⚫ 4   🔴 5   ⚫ 6            │
    │  🔴 7   ⚫ 8   🔴 9            │
    │  ⚫10   ⚫11   🔴12            │
    │  ⚫13   🔴14   ⚫15            │
    │  🔴16   ⚫17   🔴18            │
    │  🔴19   ⚫20   🔴21            │
    │  ⚫22   🔴23   ⚫24            │
    │  🔴25   ⚫26   🔴27            │
    │  ⚫28   ⚫29   🔴30            │
    │  ⚫31   🔴32   ⚫33            │
    │  🔴34   ⚫35   🔴36            │
    ╰─────────────────────────────────╯
    """)


def play_round(balance: float) -> float:
    """玩一輪"""
    print("\n" + "="*60)
    
    # 取得當前高度，計算下一個開獎高度
    current = get_blue_score()
    next_draw = ((current // ROUND_INTERVAL) + 1) * ROUND_INTERVAL
    blocks_left = next_draw - current
    seconds_left = blocks_left / BLOCKS_PER_SECOND
    
    print(f"💰 餘額: {balance:.2f} tKAS")
    print(f"📍 當前高度: {current:,}")
    print(f"🎯 開獎高度: {next_draw:,}")
    print(f"⏱️  還有 ~{seconds_left:.0f} 秒")
    print("="*60)
    
    # 下注選項
    print("""
📝 下注選項:
   紅(r)/黑(b)     → 1:1    奇(o)/偶(e)    → 1:1
   高(h)/低(l)     → 1:1    數字 0-36      → 35:1
   0 / 00          → 35:1
   
   輸入 q 離開 | w 顯示輪盤 | rules 查看規則
""")
    
    bet_type = input("下注類型: ").strip()
    
    if bet_type.lower() == 'q':
        return -1  # 離開信號
    if bet_type.lower() == 'w':
        display_wheel()
        return balance
    if bet_type.lower() == 'rules':
        print("""
📜 開獎規則 (Provably Fair):
   1. 每 1000 blueScore 開一局
   2. 取得該高度的所有區塊
   3. 按官方規則排序: blueWork↓ → hash↑
   4. 取第一個區塊的 hash
   5. 結果 = hash mod 38
   
   詳見 RULES.md
        """)
        return balance
    
    try:
        bet_amount = float(input("下注金額: "))
        if bet_amount > balance:
            print("❌ 餘額不足!")
            return balance
        if bet_amount <= 0:
            print("❌ 金額必須大於 0!")
            return balance
    except ValueError:
        print("❌ 無效金額!")
        return balance
    
    # 確認下注
    payout = get_payout(bet_type)
    print(f"\n✅ 下注確認: {bet_amount} tKAS on 【{bet_type}】(賠率 {payout-1}:1)")
    
    # 等待開獎
    print(f"\n⏳ 等待區塊 {next_draw:,}...")
    
    while True:
        current = get_blue_score()
        if current >= next_draw:
            break
        
        remaining = next_draw - current
        seconds = remaining / BLOCKS_PER_SECOND
        print(f"   {current:,} → {next_draw:,} | 還差 {remaining} (~{seconds:.0f}s)   ", end='\r')
        time.sleep(2)
    
    # 開獎
    print("\n\n🎲 開獎中...")
    time.sleep(1)
    
    draw_result = draw_at_score(next_draw)
    
    if not draw_result:
        print("❌ 無法取得開獎區塊，請稍後再試")
        return balance
    
    block_hash = draw_result['hash']
    result = draw_result['result']
    blocks_count = draw_result['blocks_count']
    
    # 顯示結果
    print("\n" + "🎰"*20)
    print(f"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                       🎲 開獎結果 🎲                          ║
    ╠═══════════════════════════════════════════════════════════════╣
    ║  開獎高度: {next_draw:<50}║
    ║  區塊數量: {blocks_count} 個 (按官方規則排序取第一)               ║
    ║  blueWork: {draw_result['blueWork']:<50}║
    ║  Hash: {block_hash[:24]}...{block_hash[-12:]:<10}║
    ║  Hash mod 38 = {result:<46}║
    ║                                                               ║
    ║              >>> {get_color(result):^20} <<<               ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    print(f"    🔗 驗證: {EXPLORER_URL}/{block_hash}")
    print("🎰"*20)
    
    # 結算
    won = check_bet(bet_type, result)
    
    if won:
        winnings = bet_amount * payout
        profit = winnings - bet_amount
        balance += profit
        print(f"""
    🎉🎉🎉 恭喜中獎！🎉🎉🎉
    
    下注: {bet_amount} tKAS on 【{bet_type}】
    賠率: {payout-1}:1
    獲得: {winnings} tKAS
    淨賺: +{profit} tKAS ✨
        """)
    else:
        balance -= bet_amount
        print(f"""
    😢 沒中...
    
    下注: {bet_amount} tKAS on 【{bet_type}】
    結果: {get_color(result)}
    損失: -{bet_amount} tKAS
        """)
    
    print(f"💰 目前餘額: {balance:.2f} tKAS")
    
    return balance


def main():
    """主程式"""
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   🎰  Kaspa Roulette - Provably Fair                         ║
    ║       用 Kaspa 區塊 hash 決定結果                            ║
    ║       by Nami 🌊 & Ryan                                       ║
    ║                                                               ║
    ║   📜 開獎規則:                                                ║
    ║      1. 每 1000 blueScore 開一局                             ║
    ║      2. 取該高度所有區塊                                      ║
    ║      3. 官方排序: blueWork↓ → hash↑                          ║
    ║      4. 取第一個區塊 hash mod 38                             ║
    ║                                                               ║
    ║   🔗 規則詳見 RULES.md                                        ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # 初始餘額（測試用虛擬籌碼）
    balance = 1000.0
    print(f"💰 初始籌碼: {balance} tKAS (虛擬)\n")
    
    # 測試 API 連線
    try:
        score = get_blue_score()
        print(f"✅ 已連接 Kaspa Testnet (當前高度: {score:,})")
    except Exception as e:
        print(f"❌ 無法連接 API: {e}")
        return
    
    while balance > 0:
        result = play_round(balance)
        
        if result == -1:  # 離開
            print(f"\n👋 遊戲結束！最終餘額: {balance:.2f} tKAS")
            break
        
        balance = result
        
        if balance <= 0:
            print("\n💸 破產了！遊戲結束。")
            break
        
        input("\n按 Enter 繼續下一局...")
    
    print("\n感謝遊玩！🎰🌊")


if __name__ == "__main__":
    main()
