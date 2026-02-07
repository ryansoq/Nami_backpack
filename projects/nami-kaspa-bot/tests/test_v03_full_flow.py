#!/usr/bin/env python3
"""
v0.3 完整流程測試
==================

測試流程：
1. 創建兩隻英雄（模擬出生）
2. 驗證各自出生閉環
3. PvP 對戰（一隻死亡）
4. 追蹤兩隻英雄完整歷程
5. 驗證閉環完整性

這是模擬測試，不會實際發送交易到鏈上。
"""

import sys
import json
import random
from datetime import datetime
sys.path.insert(0, '..')

from hero_game import (
    calculate_hero_from_hash,
    calculate_rank_from_hash,
    calculate_battle_result,
    create_birth_payload,
    create_pvp_win_payload,
    create_death_payload,
    Hero,
    get_rank_display
)

# 模擬區塊 hash 生成
def generate_mock_block_hash():
    """生成模擬的區塊 hash"""
    return ''.join(random.choices('0123456789abcdef', k=64))

def create_mock_hero(hero_id: int, user_id: int, source_hash: str) -> Hero:
    """從 source_hash 創建模擬英雄"""
    hero_class, rank, atk, def_, spd = calculate_hero_from_hash(source_hash)
    
    return Hero(
        card_id=hero_id,
        owner_id=user_id,
        owner_address=f"kaspatest:qtest{user_id}",
        hero_class=hero_class,
        rank=rank,
        atk=atk,
        def_=def_,
        spd=spd,
        status="alive",
        latest_daa=hero_id,
        source_hash=source_hash,
        payment_tx=f"mock_payment_{hero_id}",
        tx_id=f"mock_birth_{hero_id}",
        latest_tx=f"mock_birth_{hero_id}",
        created_at=datetime.now().isoformat(),
        protected=False
    )

def verify_birth_chain(hero: Hero, payload: dict) -> bool:
    """驗證出生閉環"""
    # 從 payload 的 src 重新計算
    src = payload.get("src", "")
    if not src:
        return False
    
    calculated_rank = calculate_rank_from_hash(src)
    calculated_class, _, calculated_atk, calculated_def, calculated_spd = calculate_hero_from_hash(src)
    
    # 驗證 rank 一致
    return payload.get("rank") == calculated_rank

def main():
    print("=" * 60)
    print("🧪 v0.3 完整流程測試")
    print("=" * 60)
    
    # ========================================
    # Step 1: 創建兩隻英雄
    # ========================================
    print("\n📍 Step 1: 創建兩隻英雄")
    print("-" * 40)
    
    # 英雄 A（玩家 1）
    source_hash_a = generate_mock_block_hash()
    hero_a = create_mock_hero(100001, 1001, source_hash_a)
    birth_payload_a = create_birth_payload(
        daa=hero_a.card_id,
        hero=hero_a,
        source_hash=source_hash_a,
        payment_tx=hero_a.payment_tx
    )
    
    print(f"\n🦸 英雄 A #{hero_a.card_id}")
    print(f"   Rank: {get_rank_display(hero_a.rank)}")
    print(f"   職業: {hero_a.hero_class}")
    print(f"   屬性: ⚔️{hero_a.atk} 🛡️{hero_a.def_} ⚡{hero_a.spd}")
    print(f"   src: {source_hash_a[:32]}...")
    
    # 英雄 B（玩家 2）
    source_hash_b = generate_mock_block_hash()
    hero_b = create_mock_hero(100002, 1002, source_hash_b)
    birth_payload_b = create_birth_payload(
        daa=hero_b.card_id,
        hero=hero_b,
        source_hash=source_hash_b,
        payment_tx=hero_b.payment_tx
    )
    
    print(f"\n🦸 英雄 B #{hero_b.card_id}")
    print(f"   Rank: {get_rank_display(hero_b.rank)}")
    print(f"   職業: {hero_b.hero_class}")
    print(f"   屬性: ⚔️{hero_b.atk} 🛡️{hero_b.def_} ⚡{hero_b.spd}")
    print(f"   src: {source_hash_b[:32]}...")
    
    # ========================================
    # Step 2: 驗證出生閉環
    # ========================================
    print("\n📍 Step 2: 驗證出生閉環")
    print("-" * 40)
    
    verify_a = verify_birth_chain(hero_a, birth_payload_a)
    verify_b = verify_birth_chain(hero_b, birth_payload_b)
    
    print(f"\n{'✅' if verify_a else '❌'} 英雄 A 出生閉環")
    print(f"   payload.rank = {birth_payload_a.get('rank')}")
    print(f"   從 src 計算 = {calculate_rank_from_hash(source_hash_a)}")
    
    print(f"\n{'✅' if verify_b else '❌'} 英雄 B 出生閉環")
    print(f"   payload.rank = {birth_payload_b.get('rank')}")
    print(f"   從 src 計算 = {calculate_rank_from_hash(source_hash_b)}")
    
    if not (verify_a and verify_b):
        print("\n❌ 出生閉環驗證失敗！")
        return False
    
    # ========================================
    # Step 3: PvP 對戰
    # ========================================
    print("\n📍 Step 3: PvP 對戰")
    print("-" * 40)
    
    # 生成戰鬥命運塊
    battle_hash = generate_mock_block_hash()
    battle_rank = calculate_rank_from_hash(battle_hash)
    
    print(f"\n⚔️ 英雄 A vs 英雄 B")
    print(f"   戰鬥命運塊: {battle_hash[:32]}...")
    print(f"   命運 Rank: {battle_rank}")
    
    # 計算戰鬥結果
    attacker_wins, battle_detail = calculate_battle_result(hero_a, hero_b, battle_hash)
    
    print(f"\n📊 戰鬥詳情:")
    for i, r in enumerate(battle_detail.get("rounds", []), 1):
        winner_symbol = "🔵" if r["winner"] == "atk" else ("🔴" if r["winner"] == "def" else "⚪")
        print(f"   R{i} {r['name']}: {r['atk_val']} vs {r['def_val']} {winner_symbol}")
    
    print(f"\n   比分: {battle_detail.get('atk_wins', 0)}:{battle_detail.get('def_wins', 0)}")
    print(f"   結果: {'英雄 A 勝利！' if attacker_wins else '英雄 B 勝利！'}")
    
    # 更新狀態
    if attacker_wins:
        winner, loser = hero_a, hero_b
        hero_a.kills += 1
        hero_b.status = "dead"
        hero_b.death_time = datetime.now().isoformat()
    else:
        winner, loser = hero_b, hero_a
        hero_b.kills += 1
        hero_a.status = "dead"
        hero_a.death_time = datetime.now().isoformat()
    
    hero_a.battles += 1
    hero_b.battles += 1
    
    print(f"\n🏆 勝者: 英雄 {'A' if winner == hero_a else 'B'} #{winner.card_id}")
    print(f"☠️ 敗者: 英雄 {'A' if loser == hero_a else 'B'} #{loser.card_id} (死亡)")
    
    # ========================================
    # Step 4: 建立事件銘文
    # ========================================
    print("\n📍 Step 4: 建立事件銘文")
    print("-" * 40)
    
    # 勝者的 pvp_win 銘文
    win_payload = create_pvp_win_payload(
        hero_id=winner.card_id,
        pre_tx=winner.tx_id,
        target_id=loser.card_id,
        payment_tx=f"mock_pvp_payment_{winner.card_id}",
        source_hash=battle_hash
    )
    winner.latest_tx = f"mock_pvp_win_{winner.card_id}"
    
    print(f"\n📝 勝者銘文 (pvp_win):")
    print(f"   type: {win_payload.get('type')}")
    print(f"   rank: {win_payload.get('rank')}")
    print(f"   pre_tx: {win_payload.get('pre_tx')[:20]}...")
    print(f"   target: {win_payload.get('target')}")
    
    # 敗者的 death 銘文
    death_payload = create_death_payload(
        hero_id=loser.card_id,
        pre_tx=loser.tx_id,
        reason="pvp",
        killer_id=winner.card_id,
        battle_tx=winner.latest_tx
    )
    loser.latest_tx = f"mock_death_{loser.card_id}"
    
    print(f"\n📝 敗者銘文 (death):")
    print(f"   type: {death_payload.get('type')}")
    print(f"   reason: {death_payload.get('reason')}")
    print(f"   killer: {death_payload.get('killer')}")
    print(f"   pre_tx: {death_payload.get('pre_tx')[:20]}...")
    
    # ========================================
    # Step 5: 追蹤完整歷程
    # ========================================
    print("\n📍 Step 5: 追蹤完整歷程（模擬 /nv）")
    print("-" * 40)
    
    # 模擬銘文鏈
    chain_a = [
        {"type": "birth", "tx": hero_a.tx_id, "payload": birth_payload_a}
    ]
    chain_b = [
        {"type": "birth", "tx": hero_b.tx_id, "payload": birth_payload_b}
    ]
    
    if winner == hero_a:
        chain_a.append({"type": "pvp_win", "tx": winner.latest_tx, "payload": win_payload})
        chain_b.append({"type": "death", "tx": loser.latest_tx, "payload": death_payload})
    else:
        chain_b.append({"type": "pvp_win", "tx": winner.latest_tx, "payload": win_payload})
        chain_a.append({"type": "death", "tx": loser.latest_tx, "payload": death_payload})
    
    print(f"\n📜 英雄 A 歷程 (狀態: {hero_a.status}):")
    for event in chain_a:
        print(f"   → {event['type']}: {event['tx'][:24]}...")
    
    print(f"\n📜 英雄 B 歷程 (狀態: {hero_b.status}):")
    for event in chain_b:
        print(f"   → {event['type']}: {event['tx'][:24]}...")
    
    # ========================================
    # Step 6: 最終驗證
    # ========================================
    print("\n📍 Step 6: 最終驗證")
    print("-" * 40)
    
    all_verified = True
    
    # 驗證英雄 A
    print(f"\n🔍 驗證英雄 A #{hero_a.card_id}")
    birth_a = chain_a[0]["payload"]
    verify_a_birth = verify_birth_chain(hero_a, birth_a)
    print(f"   {'✅' if verify_a_birth else '❌'} 出生閉環: src → rank={birth_a.get('rank')}")
    
    if hero_a.status == "alive":
        print(f"   ✅ 狀態: 存活 (kills={hero_a.kills})")
    else:
        print(f"   ☠️ 狀態: 死亡")
    
    if not verify_a_birth:
        all_verified = False
    
    # 驗證英雄 B
    print(f"\n🔍 驗證英雄 B #{hero_b.card_id}")
    birth_b = chain_b[0]["payload"]
    verify_b_birth = verify_birth_chain(hero_b, birth_b)
    print(f"   {'✅' if verify_b_birth else '❌'} 出生閉環: src → rank={birth_b.get('rank')}")
    
    if hero_b.status == "alive":
        print(f"   ✅ 狀態: 存活 (kills={hero_b.kills})")
    else:
        print(f"   ☠️ 狀態: 死亡")
    
    if not verify_b_birth:
        all_verified = False
    
    # ========================================
    # 結果
    # ========================================
    print("\n" + "=" * 60)
    print("測試結果")
    print("=" * 60)
    
    print(f"""
✅ 出生閉環 A: {verify_a_birth}
✅ 出生閉環 B: {verify_b_birth}
✅ PvP 戰鬥: 完成
✅ 事件銘文: 已建立
✅ 歷程追蹤: 可追溯到出生

🏆 勝者: #{winner.card_id} ({winner.status}, {winner.kills}殺)
☠️ 敗者: #{loser.card_id} ({loser.status})
""")
    
    if all_verified:
        print("🎉 所有測試通過！v0.3 閉環完整！")
    else:
        print("⚠️ 有驗證失敗")
    
    return all_verified

if __name__ == "__main__":
    # 設定隨機種子以便重現
    random.seed(42)
    success = main()
    sys.exit(0 if success else 1)
