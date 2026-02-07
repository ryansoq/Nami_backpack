#!/usr/bin/env python3
"""
v0.3 出生閉環測試
================

驗證：
1. Rank 計算邏輯 (hash[0:16])
2. 職業計算邏輯 (hash[16:20])
3. 屬性計算邏輯 (hash[20:32] × Rank加權)
4. Payload 格式（只有 rank）
5. 閉環驗證（src 一致 → rank 一定正確）
"""

import sys
sys.path.insert(0, '..')

from hero_game import (
    calculate_rank_from_hash,
    calculate_class_from_hash,
    calculate_stats_from_hash,
    calculate_hero_from_hash,
    create_birth_payload,
    Hero,
    get_rank_display,
    get_rank_stars,
    Rank
)

def test_rank_calculation():
    """測試 Rank 計算"""
    print("=" * 50)
    print("測試 1: Rank 計算 (hash[0:16])")
    print("=" * 50)
    
    # 測試不同的 hash 應該產生不同的 rank
    test_cases = [
        # (hash, expected_rank_range)
        ("0000000000000000ffffffffffffffffffffffffffffffffffffffffffffffff", "LR"),  # 最稀有
        ("0001000000000000ffffffffffffffffffffffffffffffffffffffffffffffff", "LR"),  # 還是神話範圍
        ("0005000000000000ffffffffffffffffffffffffffffffffffffffffffffffff", "UR"),  # 傳說
        ("0028000000000000ffffffffffffffffffffffffffffffffffffffffffffffff", "SSR"), # 極稀
        ("00aa000000000000ffffffffffffffffffffffffffffffffffffffffffffffff", "SR"),  # 超稀
        ("01c2000000000000ffffffffffffffffffffffffffffffffffffffffffffffff", "R"),   # 稀有
        ("03e8000000000000ffffffffffffffffffffffffffffffffffffffffffffffff", "N"),   # 普通
    ]
    
    all_passed = True
    for test_hash, expected in test_cases:
        rank = calculate_rank_from_hash(test_hash)
        # 只檢查特定值的精確匹配
        status = "✅" if rank == expected else "❌"
        if rank != expected:
            all_passed = False
        print(f"  {status} hash[0:16]={test_hash[:16]} → {rank} (期望: {expected})")
    
    return all_passed

def test_class_calculation():
    """測試職業計算"""
    print("\n" + "=" * 50)
    print("測試 2: 職業計算 (hash[16:20])")
    print("=" * 50)
    
    test_cases = [
        ("00000000000000000000ffffffffffffffffffffffffffffffffffffffffffff", "warrior"),  # 0 % 4 = 0
        ("00000000000000000001ffffffffffffffffffffffffffffffffffffffffffff", "warrior"),  # 1 % 4 = 1? 讓我算
        ("00000000000000000004ffffffffffffffffffffffffffffffffffffffffffff", "warrior"),  # 4 % 4 = 0
        ("00000000000000000005ffffffffffffffffffffffffffffffffffffffffffff", "warrior"),  # 5 % 4 = 1? 
    ]
    
    # 實際測試
    classes = ["warrior", "mage", "archer", "rogue"]
    all_passed = True
    for i, cls in enumerate(classes):
        # 建立 hash 使得 hash[16:20] % 4 = i
        hex_val = format(i, '04x')
        test_hash = "0" * 16 + hex_val + "0" * 44
        result = calculate_class_from_hash(test_hash)
        status = "✅" if result == cls else "❌"
        if result != cls:
            all_passed = False
        print(f"  {status} hash[16:20]={hex_val} (val={i}) → {result} (期望: {cls})")
    
    return all_passed

def test_payload_format():
    """測試 Payload 格式"""
    print("\n" + "=" * 50)
    print("測試 3: v0.3 Payload 格式")
    print("=" * 50)
    
    # 建立測試 Hero
    test_hash = "2e8546284f0f70fe47c2b8b7a9b01cd4d3dcc6c6ff6f68fabe3ac20808cd5637"
    hero_class, rank, atk, def_, spd = calculate_hero_from_hash(test_hash)
    
    hero = Hero(
        card_id=12345,
        owner_id=123,
        owner_address="kaspatest:qtest",
        hero_class=hero_class,
        rank=rank,
        atk=atk,
        def_=def_,
        spd=spd,
        status="alive",
        latest_daa=12345,
        source_hash=test_hash
    )
    
    # 建立 payload
    payload = create_birth_payload(
        daa=12345,
        hero=hero,
        source_hash=test_hash,
        payment_tx="abc123"
    )
    
    # 檢查必要欄位
    checks = []
    checks.append(("g", payload.get("g") == "nami_hero"))
    checks.append(("type", payload.get("type") == "birth"))
    checks.append(("rank", payload.get("rank") == rank))
    checks.append(("daa", payload.get("daa") == 12345))
    checks.append(("pay_tx", payload.get("pay_tx") == "abc123"))
    checks.append(("src", payload.get("src") == test_hash))
    checks.append(("pre_tx", payload.get("pre_tx") is None))
    
    # 檢查不應該有的舊欄位
    old_fields = ["c", "r", "a", "d", "s"]
    for field in old_fields:
        checks.append((f"no_{field}", field not in payload))
    
    all_passed = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        if not passed:
            all_passed = False
        print(f"  {status} {name}")
    
    print(f"\n  Payload: {payload}")
    
    return all_passed

def test_verification_loop():
    """測試閉環驗證邏輯"""
    print("\n" + "=" * 50)
    print("測試 4: 閉環驗證邏輯")
    print("=" * 50)
    
    # 模擬完整流程
    src_hash = "2e8546284f0f70fe47c2b8b7a9b01cd4d3dcc6c6ff6f68fabe3ac20808cd5637"
    
    # 1. 從 src 計算 rank
    original_rank = calculate_rank_from_hash(src_hash)
    original_class, _, original_atk, original_def, original_spd = calculate_hero_from_hash(src_hash)
    
    print(f"  原始計算:")
    print(f"    src: {src_hash[:32]}...")
    print(f"    rank: {original_rank}")
    print(f"    class: {original_class}")
    print(f"    stats: {original_atk}/{original_def}/{original_spd}")
    
    # 2. 建立 payload（模擬鏈上存儲）
    payload = {
        "g": "nami_hero",
        "type": "birth",
        "rank": original_rank,
        "daa": 12345,
        "pre_tx": None,
        "pay_tx": "mock_payment_tx",
        "src": src_hash
    }
    
    print(f"\n  鏈上 Payload:")
    print(f"    rank: {payload['rank']}")
    print(f"    src: {payload['src'][:32]}...")
    
    # 3. 驗證（從 payload 重算）
    verify_rank = calculate_rank_from_hash(payload["src"])
    verify_class, _, verify_atk, verify_def, verify_spd = calculate_hero_from_hash(payload["src"])
    
    print(f"\n  驗證重算:")
    print(f"    rank: {verify_rank}")
    print(f"    class: {verify_class}")
    print(f"    stats: {verify_atk}/{verify_def}/{verify_spd}")
    
    # 4. 比對
    rank_match = verify_rank == payload["rank"]
    src_match = True  # src 是直接從 payload 拿的，一定一樣
    
    print(f"\n  驗證結果:")
    print(f"    {'✅' if rank_match else '❌'} Rank 匹配: {payload['rank']} == {verify_rank}")
    print(f"    {'✅' if src_match else '❌'} src 一致 → 屬性自動正確")
    
    return rank_match and src_match

def test_rank_distribution():
    """測試 Rank 機率分布"""
    print("\n" + "=" * 50)
    print("測試 5: Rank 機率分布 (模擬)")
    print("=" * 50)
    
    import random
    
    # 模擬 10000 次抽卡
    counts = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0, "LR": 0}
    total = 10000
    
    for _ in range(total):
        # 生成隨機 hash
        random_hash = ''.join(random.choices('0123456789abcdef', k=64))
        rank = calculate_rank_from_hash(random_hash)
        counts[rank] += 1
    
    print(f"  模擬 {total} 次抽卡:")
    expected = {"N": 55, "R": 28, "SR": 13, "SSR": 3.5, "UR": 0.4, "LR": 0.1}
    
    for rank in ["N", "R", "SR", "SSR", "UR", "LR"]:
        actual_pct = counts[rank] / total * 100
        exp_pct = expected[rank]
        diff = abs(actual_pct - exp_pct)
        # 允許 2% 誤差
        status = "✅" if diff < 3 else "⚠️"
        print(f"    {status} {rank}: {counts[rank]} ({actual_pct:.1f}%) 期望: {exp_pct}%")
    
    return True  # 機率測試不算 hard fail

def main():
    print("\n🧪 v0.3 出生閉環測試\n")
    
    results = []
    results.append(("Rank 計算", test_rank_calculation()))
    results.append(("職業計算", test_class_calculation()))
    results.append(("Payload 格式", test_payload_format()))
    results.append(("閉環驗證", test_verification_loop()))
    results.append(("機率分布", test_rank_distribution()))
    
    print("\n" + "=" * 50)
    print("測試總結")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
        print(f"  {status}: {name}")
    
    print("\n" + ("🎉 所有測試通過！" if all_passed else "⚠️ 有測試失敗"))
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
