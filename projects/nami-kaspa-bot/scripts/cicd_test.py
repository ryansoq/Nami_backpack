#!/usr/bin/env python3
"""
🧪 CI/CD 測試腳本
=================

完整流程測試：
1. 開維護模式
2. 創建測試英雄 ×2（真的上鏈）
3. PvP 戰鬥（真的死亡銘文）
4. 清理測試數據
5. 驗證數據完整性
6. 關維護模式

用法：
    cd ~/nami-backpack/projects/nami-kaspa-bot
    python3 scripts/cicd_test.py

by Nami 🌊 2026-02-07
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 加入 parent 目錄到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def tree_inscription(payload: dict) -> str:
    """大地之樹發 inscription"""
    from kaspa import PrivateKey, Address, PaymentOutput, RpcClient
    from kaspa import create_transaction, sign_transaction
    
    TREE_ADDRESS = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"
    TX_FEE = 50000
    
    secrets_path = Path.home() / "clawd" / ".secrets" / "testnet-wallet.json"
    with open(secrets_path) as f:
        tree_wallet = json.load(f)
    tree_pk = PrivateKey(tree_wallet["private_key"])
    tree_addr = Address(TREE_ADDRESS)
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    
    client = RpcClient(url="ws://127.0.0.1:17210", network_id="testnet-10")
    await client.connect()
    
    try:
        utxo_response = await client.get_utxos_by_addresses({"addresses": [TREE_ADDRESS]})
        entries = utxo_response.get("entries", [])
        
        if not entries:
            raise ValueError("沒有 UTXO")
        
        # 找一個小 UTXO
        entries.sort(key=lambda e: int(e.get("utxoEntry", {}).get("amount", 0)))
        
        selected = None
        for e in entries:
            amt = int(e["utxoEntry"]["amount"])
            if amt > TX_FEE * 2:
                selected = e
                break
        
        if not selected:
            raise ValueError("沒有足夠大的 UTXO")
        
        input_amount = int(selected["utxoEntry"]["amount"])
        output_amount = input_amount - TX_FEE
        
        outputs = [PaymentOutput(tree_addr, output_amount)]
        
        tx = create_transaction(
            utxo_entry_source=[selected],
            outputs=outputs,
            priority_fee=TX_FEE,
            payload=payload_bytes
        )
        
        signed_tx = sign_transaction(tx, [tree_pk], False)
        
        result = await client.submit_transaction({
            "transaction": signed_tx,
            "allow_orphan": False
        })
        
        return result.get("transactionId", str(result))
        
    finally:
        await client.disconnect()


async def run_cicd_test():
    """執行 CI/CD 測試"""
    print("=" * 60)
    print("🧪 CI/CD 測試 - 娜米的英雄奇幻冒險")
    print("=" * 60)
    
    import hero_commands
    hero_commands.MAINTENANCE_MODE = True
    print("\n🔒 維護模式: ON")
    
    from hero_game import (
        load_heroes_db, save_heroes_db, TREE_ADDRESS,
        calculate_hero_from_hash, calculate_battle_result,
        calculate_pvp_reward, Hero, create_birth_payload, create_death_payload
    )
    from hero_commands import get_first_block_after_daa, get_tx_confirmed_daa
    import unified_wallet
    
    db = load_heroes_db()
    original = set(db.get('heroes', {}).keys())
    original_mana = db.get('total_mana_pool', 0)
    print(f"📊 測試前: {len(original)} 英雄, {original_mana} mana")
    
    test_ids = []
    test_dirs = []
    results = {"success": False, "txs": {}}
    
    try:
        # ═══════════════════════════════════════════════════════════
        # 英雄 1
        # ═══════════════════════════════════════════════════════════
        print("\n" + "-" * 60)
        print("📦 Step 1: 召喚英雄 1")
        
        p1 = await unified_wallet.send_from_tree(TREE_ADDRESS, int(10*1e8), "cicd_test_1")
        print(f"   Payment TX: {p1[:24]}...")
        await asyncio.sleep(3)
        
        d1 = await get_tx_confirmed_daa(p1)
        f1, h1 = await get_first_block_after_daa(d1)
        c1, r1, a1, df1, s1 = calculate_hero_from_hash(h1)
        
        hero1 = Hero(
            card_id=f1, owner_id=0, owner_address=TREE_ADDRESS,
            hero_class=c1, rank=r1, atk=a1, def_=df1, spd=s1,
            status="alive", latest_daa=f1,
            created_at=datetime.now().isoformat(),
            source_hash=h1, payment_tx=p1
        )
        print(f"   🦸 #{f1} | {r1} {c1} | ATK:{a1} DEF:{df1} SPD:{s1}")
        
        bp1 = create_birth_payload(f1, hero1, h1, p1)
        b1 = await tree_inscription(bp1)
        print(f"   Birth TX: {b1[:24]}...")
        
        hero1.tx_id = b1
        hero1.latest_tx = b1
        test_ids.append(str(f1))
        results["txs"]["birth1"] = b1
        
        db = load_heroes_db()
        db["heroes"][str(f1)] = {**hero1.__dict__, "birth_tx": b1, "is_test": True}
        save_heroes_db(db)
        
        dir1 = f"data/inscriptions/{f1}"
        os.makedirs(dir1, exist_ok=True)
        test_dirs.append(dir1)
        print("   ✅ 完成")
        
        await asyncio.sleep(3)
        
        # ═══════════════════════════════════════════════════════════
        # 英雄 2
        # ═══════════════════════════════════════════════════════════
        print("\n" + "-" * 60)
        print("📦 Step 2: 召喚英雄 2")
        
        p2 = await unified_wallet.send_from_tree(TREE_ADDRESS, int(10*1e8), "cicd_test_2")
        print(f"   Payment TX: {p2[:24]}...")
        await asyncio.sleep(3)
        
        d2 = await get_tx_confirmed_daa(p2)
        f2, h2 = await get_first_block_after_daa(d2)
        c2, r2, a2, df2, s2 = calculate_hero_from_hash(h2)
        
        hero2 = Hero(
            card_id=f2, owner_id=0, owner_address=TREE_ADDRESS,
            hero_class=c2, rank=r2, atk=a2, def_=df2, spd=s2,
            status="alive", latest_daa=f2,
            created_at=datetime.now().isoformat(),
            source_hash=h2, payment_tx=p2
        )
        print(f"   🦸 #{f2} | {r2} {c2} | ATK:{a2} DEF:{df2} SPD:{s2}")
        
        bp2 = create_birth_payload(f2, hero2, h2, p2)
        b2 = await tree_inscription(bp2)
        print(f"   Birth TX: {b2[:24]}...")
        
        hero2.tx_id = b2
        hero2.latest_tx = b2
        test_ids.append(str(f2))
        results["txs"]["birth2"] = b2
        
        db = load_heroes_db()
        db["heroes"][str(f2)] = {**hero2.__dict__, "birth_tx": b2, "is_test": True}
        save_heroes_db(db)
        
        dir2 = f"data/inscriptions/{f2}"
        os.makedirs(dir2, exist_ok=True)
        test_dirs.append(dir2)
        print("   ✅ 完成")
        
        await asyncio.sleep(3)
        
        # ═══════════════════════════════════════════════════════════
        # PvP
        # ═══════════════════════════════════════════════════════════
        print("\n" + "-" * 60)
        print(f"⚔️ Step 3: PvP #{f1} vs #{f2}")
        
        pp = await unified_wallet.send_from_tree(TREE_ADDRESS, int(10*1e8), "cicd_pvp")
        await asyncio.sleep(3)
        
        pd = await get_tx_confirmed_daa(pp)
        bd, bh = await get_first_block_after_daa(pd)
        
        wins, det = calculate_battle_result(hero1, hero2, bh)
        w = hero1 if wins else hero2
        l = hero2 if wins else hero1
        rwd = calculate_pvp_reward(bh)
        
        print(f"   🏆 勝者: #{w.card_id}")
        print(f"   ☠️ 敗者: #{l.card_id}")
        print(f"   💰 獎勵: {rwd} mana")
        
        dp = create_death_payload(l.card_id, l.latest_tx, "pvp", w.card_id, bd)
        dt = await tree_inscription(dp)
        print(f"   Death TX: {dt[:24]}...")
        
        results["txs"]["death"] = dt
        results["winner"] = w.card_id
        results["loser"] = l.card_id
        
        db = load_heroes_db()
        db["heroes"][str(w.card_id)]["kills"] = 1
        db["heroes"][str(l.card_id)]["status"] = "dead"
        db["heroes"][str(l.card_id)]["death_tx"] = dt
        save_heroes_db(db)
        print("   ✅ 完成")
        
        # ═══════════════════════════════════════════════════════════
        # 清理
        # ═══════════════════════════════════════════════════════════
        print("\n" + "-" * 60)
        print("🧹 Step 4: 清理測試數據")
        
        db = load_heroes_db()
        for hid in test_ids:
            if hid in db["heroes"]:
                del db["heroes"][hid]
                print(f"   ❌ 移除英雄 #{hid}")
        save_heroes_db(db)
        
        import shutil
        for d in test_dirs:
            if os.path.exists(d):
                shutil.rmtree(d)
                print(f"   ❌ 移除目錄 {d}")
        
        # ═══════════════════════════════════════════════════════════
        # 驗證
        # ═══════════════════════════════════════════════════════════
        print("\n" + "-" * 60)
        print("✅ Step 5: 驗證數據完整性")
        
        db = load_heroes_db()
        final = set(db.get('heroes', {}).keys())
        final_mana = db.get('total_mana_pool', 0)
        
        if final == original:
            print(f"   英雄數: {len(final)} (unchanged)")
            print(f"   獎池: {original_mana} → {final_mana} mana")
            print("   ✅ 數據完整性驗證通過！")
            results["success"] = True
        else:
            added = final - original
            removed = original - final
            print(f"   ⚠️ 數據變化: +{added}, -{removed}")
            results["success"] = False
        
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        
        # 緊急清理
        print("\n🧹 緊急清理...")
        db = load_heroes_db()
        for hid in test_ids:
            if hid in db.get("heroes", {}):
                del db["heroes"][hid]
        save_heroes_db(db)
        
        results["success"] = False
        results["error"] = str(e)
    
    finally:
        hero_commands.MAINTENANCE_MODE = False
        print("\n🔓 維護模式: OFF")
    
    # ═══════════════════════════════════════════════════════════
    # 結果報告
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    if results["success"]:
        print("✅ CI/CD 測試通過！")
        print("\n📋 鏈上交易（可在區塊瀏覽器驗證）：")
        for name, tx in results.get("txs", {}).items():
            print(f"   {name}: {tx}")
    else:
        print("❌ CI/CD 測試失敗！")
        if "error" in results:
            print(f"   錯誤: {results['error']}")
    print("=" * 60)
    
    return results


if __name__ == "__main__":
    results = asyncio.run(run_cicd_test())
    sys.exit(0 if results.get("success") else 1)
