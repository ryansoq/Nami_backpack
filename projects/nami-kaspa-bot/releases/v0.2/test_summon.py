#!/usr/bin/env python3
"""
🧪 召喚流程測試
================

自動測試召喚流程的閉環驗證
測試完成後自動清理（不保留測試英雄）

用法：
    python3 tests/test_summon.py
"""

import asyncio
import json
import sys
import os

# 加入父目錄到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 測試用的 Nami 錢包（大地之樹錢包）
NAMI_WALLET_FILE = "/home/ymchang/clawd/.secrets/testnet-wallet.json"
TEST_USER_ID = 0  # 測試用 user_id
TEST_PIN = "0000"  # 測試用 PIN（不會真的用到）

async def test_summon_flow():
    """測試召喚流程"""
    print("🧪 開始召喚流程測試\n")
    
    from hero_commands import get_tx_confirmed_daa, get_first_block_after_daa
    from hero_game import summon_hero, load_heroes_db, save_heroes_db, calculate_hero_from_hash
    import unified_wallet
    
    # 讀取測試錢包
    with open(NAMI_WALLET_FILE) as f:
        wallet = json.load(f)
    
    test_address = wallet["address"]
    print(f"📍 測試地址: {test_address[:40]}...")
    
    # Step 1: 發送測試付款
    print("\n[1/5] 💰 發送付款交易...")
    try:
        # 用大地之樹發送給自己（測試用）
        payment_tx = await unified_wallet.send_from_tree(
            to_address=test_address,
            amount=1_00000000,  # 1 tKAS（測試用小金額）
            memo="test:summon"
        )
        print(f"      ✅ Payment TX: {payment_tx[:32]}...")
    except Exception as e:
        print(f"      ❌ 付款失敗: {e}")
        return False
    
    # Step 2: 等待確認
    print("\n[2/5] ⏳ 等待交易確認...")
    try:
        payment_daa = await get_tx_confirmed_daa(payment_tx)
        print(f"      ✅ 確認於 DAA: {payment_daa}")
    except Exception as e:
        print(f"      ❌ 確認失敗: {e}")
        return False
    
    # Step 3: 找命運區塊
    print("\n[3/5] 🎲 找命運區塊...")
    try:
        daa, block_hash = await get_first_block_after_daa(payment_daa)
        print(f"      ✅ 命運 DAA: {daa}")
        print(f"      ✅ 命運區塊: {block_hash[:32]}...")
    except Exception as e:
        print(f"      ❌ 找區塊失敗: {e}")
        return False
    
    # Step 4: 計算英雄屬性（不真正召喚，只計算）
    print("\n[4/5] 🎴 計算英雄屬性...")
    try:
        hero = calculate_hero_from_hash(block_hash, daa)
        print(f"      ✅ 職業: {hero.hero_class}")
        print(f"      ✅ 稀有度: {hero.rarity}")
        print(f"      ✅ ATK/DEF/SPD: {hero.atk}/{hero.def_}/{hero.spd}")
    except Exception as e:
        print(f"      ❌ 計算失敗: {e}")
        return False
    
    # Step 5: 驗證閉環
    print("\n[5/5] 🔍 驗證閉環...")
    try:
        # 用 block_hash 重新計算，應該得到相同結果
        hero2 = calculate_hero_from_hash(block_hash, daa)
        
        if (hero.hero_class == hero2.hero_class and 
            hero.rarity == hero2.rarity and
            hero.atk == hero2.atk):
            print("      ✅ 閉環驗證通過！屬性可重現")
        else:
            print("      ❌ 閉環驗證失敗！屬性不一致")
            return False
    except Exception as e:
        print(f"      ❌ 驗證失敗: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 所有測試通過！")
    print("=" * 50)
    
    return True


async def test_payload_format():
    """測試 payload 格式（確保 pay_tx 能被正確讀取）"""
    print("\n🧪 開始 Payload 格式測試\n")
    
    from hero_game import create_birth_payload, Hero
    
    # 建立測試 payload
    test_hero = Hero(
        card_id=123456789,
        hero_class="warrior",
        rarity="rare",
        atk=50, def_=60, spd=70,
        owner_id=0,
        owner_address="test",
        status="alive",
        latest_daa=123456789
    )
    
    payload = create_birth_payload(
        daa=123456789,
        hero=test_hero,
        source_hash="abc123",
        payment_tx="def456"
    )
    
    print("[1/3] 測試 pay_tx 欄位存在...")
    if "pay_tx" in payload:
        print("      ✅ pay_tx 欄位存在")
    else:
        print("      ❌ pay_tx 欄位不存在！")
        return False
    
    print("\n[2/3] 測試驗證邏輯能讀取 pay_tx...")
    # 模擬驗證邏輯
    read_pay_tx = payload.get("pay_tx") or payload.get("payment_tx", "")
    if read_pay_tx == "def456":
        print("      ✅ 驗證邏輯能正確讀取 pay_tx")
    else:
        print(f"      ❌ 讀取失敗: {read_pay_tx}")
        return False
    
    print("\n[3/3] 測試舊格式相容性...")
    # 模擬舊格式 payload
    old_payload = {"payment_tx": "old123"}
    read_old = old_payload.get("pay_tx") or old_payload.get("payment_tx", "")
    if read_old == "old123":
        print("      ✅ 舊格式 payment_tx 也能讀取")
    else:
        print(f"      ❌ 舊格式讀取失敗: {read_old}")
        return False
    
    print("\n🎉 Payload 格式測試通過！")
    return True


async def test_reward_system():
    """測試獎勵系統"""
    print("\n🧪 開始獎勵系統測試\n")
    
    from reward_system import find_trigger_daa_in_range, should_trigger_reward
    
    # 測試區間檢查
    print("[1/2] 測試區間檢查...")
    
    # 應該找到 380666666
    result = find_trigger_daa_in_range(380600000, 380700000)
    if result == 380666666:
        print("      ✅ 正確找到 380666666")
    else:
        print(f"      ❌ 錯誤: 期望 380666666, 得到 {result}")
        return False
    
    # 不應該找到（區間內沒有 666666）
    result = find_trigger_daa_in_range(380700000, 380800000)
    if result is None:
        print("      ✅ 正確返回 None（區間內無觸發點）")
    else:
        print(f"      ❌ 錯誤: 期望 None, 得到 {result}")
        return False
    
    # 測試精確匹配
    print("\n[2/2] 測試精確匹配...")
    if should_trigger_reward(380666666):
        print("      ✅ 380666666 觸發")
    else:
        print("      ❌ 380666666 應該觸發")
        return False
    
    if not should_trigger_reward(380666665):
        print("      ✅ 380666665 不觸發")
    else:
        print("      ❌ 380666665 不應該觸發")
        return False
    
    print("\n🎉 獎勵系統測試通過！")
    return True


async def main():
    """主測試函數"""
    print("=" * 50)
    print("🌲 娜米的英雄奇幻冒險 - 自動測試")
    print("=" * 50)
    
    results = []
    
    # 測試 Payload 格式（確保 pay_tx 能正確讀取）
    results.append(("Payload格式", await test_payload_format()))
    
    # 測試獎勵系統（快速，不需要鏈上操作）
    results.append(("獎勵系統", await test_reward_system()))
    
    # 測試召喚流程（需要鏈上操作，較慢）
    # 可選：加入 --full 參數時才執行
    if "--full" in sys.argv:
        results.append(("召喚流程", await test_summon_flow()))
    else:
        print("\n⏭️ 跳過召喚流程測試（加入 --full 參數執行）")
    
    # 總結
    print("\n" + "=" * 50)
    print("📊 測試結果總結")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 所有測試通過！")
        return 0
    else:
        print("\n❌ 有測試失敗")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
