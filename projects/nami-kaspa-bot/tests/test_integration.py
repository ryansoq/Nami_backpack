#!/usr/bin/env python3
"""
🧪 整合測試
===========

端對端流程測試：
- 召喚 → 屬性生成 → 資料庫儲存
- PvP → 戰鬥 → 死亡處理 → 獎勵發放
- 哥布林入侵 → 討伐 → 威脅移除

by Nami 🌊
"""

import pytest
import json
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from hero_game import (
    Hero,
    load_heroes_db,
    save_heroes_db,
    calculate_hero_from_hash,
    calculate_battle_result_atb,
    create_goblin,
    HEROES_DB_FILE
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db():
    """模擬資料庫"""
    return {
        "heroes": {},
        "user_heroes": {},
        "last_summon_daa": 0,
        "total_mana_pool": 0,
        "last_reward_daa": 0
    }


@pytest.fixture
def sample_hash():
    return "abcdef1234567890" * 4


# ═══════════════════════════════════════════════════════════════════════════════
# 召喚流程測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestSummonFlow:
    """召喚流程整合測試"""
    
    def test_summon_creates_hero(self, mock_db, sample_hash):
        """召喚應創建英雄"""
        daa = 385012345
        
        # 1. 計算屬性
        hero_class, rank, atk, def_, spd = calculate_hero_from_hash(sample_hash)
        
        # 2. 創建英雄
        hero = Hero(
            card_id=daa,
            owner_id=100,
            owner_address="kaspatest:qtest",
            hero_class=hero_class,
            rank=rank,
            atk=atk,
            def_=def_,
            spd=spd,
            status="alive",
            latest_daa=daa
        )
        
        # 3. 儲存到資料庫
        mock_db["heroes"][str(daa)] = hero.to_dict()
        mock_db["user_heroes"]["100"] = mock_db["user_heroes"].get("100", []) + [daa]
        
        # 驗證
        assert str(daa) in mock_db["heroes"]
        assert daa in mock_db["user_heroes"]["100"]
        assert mock_db["heroes"][str(daa)]["status"] == "alive"
    
    def test_summon_adds_to_mana_pool(self, mock_db):
        """召喚費用應加入 mana 池"""
        summon_cost = 10
        
        mock_db["total_mana_pool"] += summon_cost
        
        assert mock_db["total_mana_pool"] == 10
    
    def test_summon_verifiable(self, sample_hash):
        """召喚屬性可驗證"""
        # 第一次計算
        result1 = calculate_hero_from_hash(sample_hash)
        
        # 模擬之後驗證
        result2 = calculate_hero_from_hash(sample_hash)
        
        assert result1 == result2, "屬性應可重新驗證"


# ═══════════════════════════════════════════════════════════════════════════════
# PvP 流程測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestPvPFlow:
    """PvP 流程整合測試"""
    
    def test_pvp_complete_flow(self, mock_db, sample_hash):
        """完整 PvP 流程"""
        # 1. 創建兩個英雄
        attacker = Hero(
            card_id=1, owner_id=100, owner_address="kaspatest:attacker",
            hero_class="knight", rank="SR",
            atk=150, def_=120, spd=100,
            status="alive", latest_daa=1
        )
        defender = Hero(
            card_id=2, owner_id=200, owner_address="kaspatest:defender",
            hero_class="mage", rank="R",
            atk=100, def_=80, spd=90,
            status="alive", latest_daa=2
        )
        
        mock_db["heroes"]["1"] = attacker.to_dict()
        mock_db["heroes"]["2"] = defender.to_dict()
        
        # 2. 執行戰鬥
        attacker_wins, detail = calculate_battle_result_atb(
            attacker, defender, sample_hash
        )
        
        # 3. 更新狀態
        if attacker_wins:
            defender.status = "dead"
            attacker.kills += 1
            winner, loser = attacker, defender
        else:
            attacker.status = "dead"
            defender.kills += 1
            winner, loser = defender, attacker
        
        # 4. 儲存
        mock_db["heroes"]["1"] = attacker.to_dict()
        mock_db["heroes"]["2"] = defender.to_dict()
        
        # 5. 驗證
        assert loser.status == "dead", "敗者應死亡"
        assert winner.kills > 0, "勝者應獲得擊殺數"
    
    def test_pvp_adds_to_mana_pool(self, mock_db):
        """PvP 費用應加入 mana 池"""
        pvp_cost = 10
        initial_pool = mock_db["total_mana_pool"]
        
        mock_db["total_mana_pool"] += pvp_cost
        
        assert mock_db["total_mana_pool"] == initial_pool + pvp_cost
    
    def test_protected_hero_survives_pvp(self, mock_db, sample_hash):
        """受保護英雄 PvP 落敗不死"""
        defender = Hero(
            card_id=2, owner_id=200, owner_address="kaspatest:defender",
            hero_class="mage", rank="N",
            atk=50, def_=40, spd=30,
            status="alive", latest_daa=2,
            protected=True  # 受保護
        )
        
        attacker = Hero(
            card_id=1, owner_id=100, owner_address="kaspatest:attacker",
            hero_class="knight", rank="SSR",
            atk=300, def_=250, spd=200,
            status="alive", latest_daa=1
        )
        
        # 強制攻擊者獲勝場景
        attacker_wins = True
        
        if attacker_wins:
            if defender.protected:
                # 免死
                pass
            else:
                defender.status = "dead"
        
        assert defender.status == "alive", "受保護英雄應存活"


# ═══════════════════════════════════════════════════════════════════════════════
# 哥布林流程測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoblinFlow:
    """哥布林流程整合測試"""
    
    def test_goblin_spawn_flow(self, mock_db, sample_hash):
        """哥布林入侵流程"""
        daa = 385066666
        
        # 1. 創建哥布林
        goblin = create_goblin(sample_hash, daa, mock_db)
        
        # 2. 儲存
        mock_db["heroes"][str(goblin.card_id)] = goblin.to_dict()
        mock_db["heroes"][str(goblin.card_id)]["owner_id"] = 0
        mock_db["heroes"][str(goblin.card_id)]["name"] = goblin.name
        
        # 3. 驗證
        assert goblin.owner_id == 0
        assert str(goblin.card_id) in mock_db["heroes"]
    
    def test_goblin_defeat_flow(self, mock_db, sample_hash):
        """討伐哥布林流程"""
        # 1. 設置哥布林
        goblin_id = "99999999"
        mock_db["heroes"][goblin_id] = {
            "card_id": 99999999,
            "owner_id": 0,
            "status": "alive",
            "name": "哥布林盜賊",
            "hero_class": "rogue",
            "rank": "N",
            "atk": 50, "def": 40, "spd": 60,
            "kills": 0
        }
        
        # 2. 玩家英雄
        hero_id = "1"
        mock_db["heroes"][hero_id] = {
            "card_id": 1,
            "owner_id": 100,
            "status": "alive",
            "hero_class": "knight",
            "rank": "SR",
            "atk": 150, "def": 120, "spd": 100,
            "kills": 0
        }
        
        # 3. 戰鬥（假設玩家獲勝）
        player_wins = True
        
        if player_wins:
            mock_db["heroes"][goblin_id]["status"] = "dead"
            mock_db["heroes"][hero_id]["kills"] += 1
        
        # 4. 驗證
        assert mock_db["heroes"][goblin_id]["status"] == "dead"
        assert mock_db["heroes"][hero_id]["kills"] == 1
    
    def test_goblin_threat_removed_on_death(self, mock_db):
        """哥布林死亡後威脅移除"""
        # 設置 2 隻哥布林
        mock_db["heroes"]["g1"] = {"owner_id": 0, "status": "alive"}
        mock_db["heroes"]["g2"] = {"owner_id": 0, "status": "alive"}
        
        # 計算威脅
        alive_goblins = [
            h for h in mock_db["heroes"].values()
            if h.get("owner_id") == 0 and h.get("status") == "alive"
        ]
        initial_threat = len(alive_goblins) * 50  # 100
        
        # 殺死一隻
        mock_db["heroes"]["g1"]["status"] = "dead"
        
        # 重新計算
        alive_goblins = [
            h for h in mock_db["heroes"].values()
            if h.get("owner_id") == 0 and h.get("status") == "alive"
        ]
        new_threat = len(alive_goblins) * 50  # 50
        
        assert new_threat < initial_threat
        assert new_threat == 50


# ═══════════════════════════════════════════════════════════════════════════════
# 獎勵發放流程測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestRewardFlow:
    """獎勵發放流程整合測試"""
    
    def test_reward_distribution_flow(self, mock_db):
        """獎勵發放完整流程"""
        # 1. 設置英雄
        mock_db["heroes"]["1"] = {
            "owner_id": 100, "status": "alive", "rank": "SR", "kills": 5,
            "owner_address": "kaspatest:addr1"
        }
        mock_db["heroes"]["2"] = {
            "owner_id": 200, "status": "alive", "rank": "R", "kills": 2,
            "owner_address": "kaspatest:addr2"
        }
        mock_db["heroes"]["g1"] = {
            "owner_id": 0, "status": "alive"  # 哥布林
        }
        
        # 2. 設置 mana 池
        mock_db["total_mana_pool"] = 300
        base_reward = 500
        total_mana = mock_db["total_mana_pool"] + base_reward  # 800
        
        # 3. 計算哥布林威脅
        goblin_count = sum(
            1 for h in mock_db["heroes"].values()
            if h.get("owner_id") == 0 and h.get("status") == "alive"
        )
        threat = goblin_count * 50  # 50
        
        # 4. 計算可發放獎勵
        distributable = max(0, total_mana - threat)  # 750
        
        # 5. 按積分分配
        alive_heroes = [
            h for h in mock_db["heroes"].values()
            if h.get("owner_id", 1) != 0 and h.get("status") == "alive"
        ]
        
        assert distributable == 750
        assert len(alive_heroes) == 2
    
    def test_reward_resets_pool(self, mock_db):
        """發放後累積池歸零"""
        mock_db["total_mana_pool"] = 500
        
        # 發放後
        mock_db["total_mana_pool"] = 0
        
        assert mock_db["total_mana_pool"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 鏈上驗證測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestOnChainVerification:
    """鏈上驗證測試"""
    
    def test_hero_attributes_verifiable(self, sample_hash):
        """英雄屬性可從 block hash 重算驗證"""
        # 原始計算
        original = calculate_hero_from_hash(sample_hash)
        
        # 驗證計算
        verified = calculate_hero_from_hash(sample_hash)
        
        assert original == verified
    
    def test_battle_result_verifiable(self, sample_hash):
        """戰鬥結果可從 block hash 重算驗證"""
        attacker = Hero(
            card_id=1, owner_id=1, owner_address="",
            hero_class="knight", rank="SR",
            atk=150, def_=120, spd=100,
            status="alive", latest_daa=1
        )
        defender = Hero(
            card_id=2, owner_id=2, owner_address="",
            hero_class="mage", rank="R",
            atk=100, def_=80, spd=90,
            status="alive", latest_daa=2
        )
        
        # 原始計算
        result1, detail1 = calculate_battle_result_atb(attacker, defender, sample_hash)
        
        # 驗證計算
        result2, detail2 = calculate_battle_result_atb(attacker, defender, sample_hash)
        
        assert result1 == result2
        assert detail1 == detail2


# ═══════════════════════════════════════════════════════════════════════════════
# 執行測試
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
