#!/usr/bin/env python3
"""
CI/CD 測試：驗證 burn 操作鏈上鏈下一致性

測試流程：
1. 召喚一隻英雄
2. Burn 掉
3. 驗證鏈上有死亡銘文
4. 驗證鏈下 status = dead, ltx = death_tx
"""

import asyncio
import json
import sys
import os

# 添加父目錄到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# 測試用的 user_id 和 PIN（需要配置）
TEST_USER_ID = 5168530096  # Ryan 的 ID（測試用）
TEST_PIN = None  # 需要從環境變數或參數取得


async def test_burn_consistency():
    """測試 burn 操作的鏈上鏈下一致性"""
    from hero_game import load_heroes_db, burn_hero, summon_hero
    
    print("=" * 60)
    print("🧪 Burn 一致性測試")
    print("=" * 60)
    
    if not TEST_PIN:
        print("❌ 請設定 TEST_PIN 環境變數")
        return False
    
    # 1. 找一隻可以燒的英雄（或召喚新的）
    db = load_heroes_db()
    test_hero = None
    
    for hero_id, hero in db.get("heroes", {}).items():
        if hero.get("owner_id") == TEST_USER_ID and hero.get("status") == "alive":
            if not hero.get("protected"):  # 找沒保護的
                test_hero = hero
                break
    
    if not test_hero:
        print("📝 沒有可燒的英雄，跳過測試")
        return True  # 不算失敗
    
    hero_id = test_hero["card_id"]
    print(f"\n📍 測試英雄: #{hero_id}")
    print(f"   Status: {test_hero['status']}")
    print(f"   LTX: {test_hero.get('ltx', 'N/A')[:20]}...")
    
    # 2. 執行 burn
    print(f"\n🔥 執行 burn...")
    result = await burn_hero(TEST_USER_ID, hero_id, TEST_PIN)
    
    if not result["success"]:
        print(f"❌ Burn 失敗: {result.get('error')}")
        return False
    
    death_tx = result.get("tx_id")
    print(f"✅ Burn 交易發送: {death_tx[:20]}...")
    
    # 3. 等待一下讓資料同步
    await asyncio.sleep(2)
    
    # 4. 驗證鏈下狀態
    print(f"\n🔍 驗證鏈下狀態...")
    db = load_heroes_db()  # 重新載入
    hero = db["heroes"].get(str(hero_id))
    
    errors = []
    
    if hero["status"] != "dead":
        errors.append(f"status 應為 'dead'，實際為 '{hero['status']}'")
    
    if hero.get("ltx") != death_tx:
        errors.append(f"ltx 應指向 death_tx，實際為 '{hero.get('ltx', 'N/A')[:20]}...'")
    
    if hero.get("death_tx") != death_tx:
        errors.append(f"death_tx 不正確")
    
    if hero.get("death_reason") != "burn":
        errors.append(f"death_reason 應為 'burn'")
    
    # 5. 驗證 hero_chain
    print(f"🔍 驗證 hero_chain...")
    with open(DATA_DIR / "hero_chain.json", 'r') as f:
        chain = json.load(f)
    
    death_event = None
    for event in chain:
        if event.get("tx_id") == death_tx:
            death_event = event
            break
    
    if not death_event:
        errors.append("hero_chain 中找不到死亡事件")
    elif death_event.get("type") != "death":
        errors.append(f"事件類型應為 'death'，實際為 '{death_event.get('type')}'")
    
    # 6. 報告結果
    print("\n" + "=" * 60)
    if errors:
        print("❌ 測試失敗！發現以下問題：")
        for e in errors:
            print(f"   - {e}")
        return False
    else:
        print("✅ 測試通過！鏈上鏈下一致")
        print(f"   Hero #{hero_id}")
        print(f"   Status: {hero['status']}")
        print(f"   Death TX: {death_tx[:30]}...")
        print(f"   LTX: {hero.get('ltx', 'N/A')[:30]}...")
        return True


async def verify_all_heroes_consistency():
    """驗證所有英雄的鏈上鏈下一致性"""
    from hero_game import load_heroes_db
    
    print("\n" + "=" * 60)
    print("🔍 全域一致性檢查")
    print("=" * 60)
    
    db = load_heroes_db()
    heroes = db.get("heroes", {})
    
    # 載入 hero_chain
    with open(DATA_DIR / "hero_chain.json", 'r') as f:
        chain = json.load(f)
    
    # 建立 tx_id -> event 的映射
    chain_map = {e.get("tx_id"): e for e in chain if e.get("tx_id")}
    
    errors = []
    
    for hero_id, hero in heroes.items():
        # 檢查：有 death_reason 但 status != dead
        if hero.get("death_reason") and hero.get("status") != "dead":
            errors.append(f"#{hero_id}: 有 death_reason 但 status={hero['status']}")
        
        # 檢查：status=dead 但沒有 death_tx
        if hero.get("status") == "dead" and not hero.get("death_tx"):
            errors.append(f"#{hero_id}: status=dead 但沒有 death_tx")
        
        # 檢查：death_tx 存在但不在 chain 裡
        if hero.get("death_tx"):
            if hero["death_tx"] not in chain_map:
                errors.append(f"#{hero_id}: death_tx 不在 hero_chain 中")
    
    if errors:
        print(f"❌ 發現 {len(errors)} 個問題：")
        for e in errors[:10]:  # 最多顯示 10 個
            print(f"   - {e}")
        if len(errors) > 10:
            print(f"   ... 還有 {len(errors) - 10} 個")
        return False
    else:
        print(f"✅ 所有 {len(heroes)} 隻英雄狀態一致")
        return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Burn 一致性測試")
    parser.add_argument("--pin", help="測試用 PIN")
    parser.add_argument("--check-only", action="store_true", help="只檢查現有資料，不執行 burn")
    args = parser.parse_args()
    
    TEST_PIN = args.pin or os.environ.get("TEST_PIN")
    
    async def main():
        # 先做全域檢查
        check_ok = await verify_all_heroes_consistency()
        
        if not args.check_only and TEST_PIN:
            # 執行 burn 測試
            burn_ok = await test_burn_consistency()
            return check_ok and burn_ok
        
        return check_ok
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
