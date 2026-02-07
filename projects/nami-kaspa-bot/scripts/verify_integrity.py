#!/usr/bin/env python3
"""
🔍 英雄系統完整性驗證 (CI/CD)

流程：
1. 鏈上驗證 - 確認 TX 都在鏈上
2. 鏈下驗證 - 檢查本地銘文鏈條
3. 一致性檢查 - 鏈上 = 本地
4. 狀態檢查 - alive/dead 正確

用法：
    python3 scripts/verify_integrity.py
    python3 scripts/verify_integrity.py --fix  # 自動修復
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# 切換到專案目錄
PROJECT_DIR = Path(__file__).parent.parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

from inscription_store import verify_chain_integrity, get_hero_chain


def load_db():
    with open("data/heroes.json", "r") as f:
        return json.load(f)


def save_db(db):
    with open("data/heroes.json", "w") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def check_tx_on_chain(tx_id: str) -> tuple[bool, dict]:
    """檢查 TX 是否在鏈上"""
    result = subprocess.run(
        ["curl", "-s", f"https://api-tn10.kaspa.org/transactions/{tx_id}"],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
        return data.get("is_accepted", False), data
    except:
        return False, {}


def verify_hero(hero_id: int, hero_data: dict, fix: bool = False) -> dict:
    """驗證單個英雄"""
    result = {
        "hero_id": hero_id,
        "status": hero_data.get("status", "?"),
        "chain_ok": False,
        "ltx_ok": False,
        "on_chain_ok": False,
        "errors": [],
        "fixed": []
    }
    
    # 1. 本地鏈條驗證
    chain_result = verify_chain_integrity(hero_id)
    result["chain_ok"] = chain_result["verified"]
    if not chain_result["verified"]:
        result["errors"].extend(chain_result["errors"])
    
    # 2. ltx 一致性
    chain = get_hero_chain(hero_id)
    if chain:
        last_tx = chain[-1].get("tx_id", "")
        local_ltx = hero_data.get("latest_tx") or hero_data.get("ltx", "")
        
        if last_tx == local_ltx:
            result["ltx_ok"] = True
        else:
            result["errors"].append(f"ltx 不符: {local_ltx[:16]} ≠ {last_tx[:16]}")
            if fix:
                hero_data["latest_tx"] = last_tx
                hero_data["ltx"] = last_tx
                result["fixed"].append("ltx")
        
        # 3. 鏈上驗證（檢查最後一個 TX）
        on_chain, _ = check_tx_on_chain(last_tx)
        result["on_chain_ok"] = on_chain
        if not on_chain:
            result["errors"].append(f"latest_tx 不在鏈上: {last_tx[:16]}")
        
        # 4. 狀態檢查
        last_type = chain[-1].get("type", "")
        expected_status = "dead" if last_type == "death" else "alive"
        if last_type == "resurrection":
            expected_status = "alive"
        
        if hero_data.get("status") != expected_status:
            result["errors"].append(f"狀態不符: {hero_data.get('status')} ≠ {expected_status}")
            if fix:
                hero_data["status"] = expected_status
                result["fixed"].append("status")
    else:
        result["errors"].append("無本地銘文記錄")
    
    return result


def main(fix: bool = False):
    print("🔍 英雄系統完整性驗證")
    print("=" * 50)
    
    db = load_db()
    heroes = db.get("heroes", {})
    
    print(f"\n總角色數: {len(heroes)}")
    print()
    
    results = []
    errors_count = 0
    fixed_count = 0
    
    for hid, hero in heroes.items():
        result = verify_hero(int(hid), hero, fix=fix)
        results.append(result)
        
        # 顯示結果
        status_emoji = "🟢" if result["status"] == "alive" else "☠️"
        
        all_ok = result["chain_ok"] and result["ltx_ok"] and result["on_chain_ok"] and not result["errors"]
        
        if all_ok:
            print(f"{status_emoji} #{hid}: ✅")
        else:
            errors_count += 1
            print(f"{status_emoji} #{hid}: ❌")
            for err in result["errors"]:
                print(f"     ⚠️ {err}")
            if result["fixed"]:
                fixed_count += 1
                print(f"     🔧 已修復: {', '.join(result['fixed'])}")
    
    # 保存修復
    if fix and fixed_count > 0:
        save_db(db)
        print(f"\n💾 已保存修復 ({fixed_count} 個角色)")
    
    # 總結
    print("\n" + "=" * 50)
    print(f"✅ 正常: {len(results) - errors_count}")
    print(f"❌ 問題: {errors_count}")
    if fix:
        print(f"🔧 修復: {fixed_count}")
    
    # CI/CD 退出碼
    if errors_count > 0 and not fix:
        print("\n❌ 驗證失敗！使用 --fix 自動修復")
        sys.exit(1)
    else:
        print("\n✅ 驗證通過！")
        sys.exit(0)


if __name__ == "__main__":
    fix_mode = "--fix" in sys.argv
    main(fix=fix_mode)
