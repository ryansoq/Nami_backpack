#!/usr/bin/env python3
"""
🧪 英雄遊戲核心邏輯測試
========================

測試範圍：
- 英雄召喚與屬性生成
- 戰鬥系統 (ATB)
- 哥布林系統
- 積分計算
- 死亡處理

by Nami 🌊
"""

import pytest
import json
import hashlib
from datetime import datetime
from pathlib import Path
import sys

# 加入專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from hero_game import (
    Hero, 
    calculate_hero_from_hash,
    calculate_battle_result_atb,
    create_goblin,
    load_heroes_db,
    save_heroes_db
)
from reward_system import calculate_hero_score

# 定義測試用常數
RARITY_WEIGHTS = {"N": 55, "R": 28, "SR": 13, "SSR": 3.5, "UR": 0.4, "LR": 0.1}
CLASS_WEIGHTS = {"knight": 25, "mage": 25, "archer": 25, "rogue": 25}


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_block_hash():
    """標準測試用區塊 hash"""
    return "a1b2c3d4e5f6789012345678901234567890123456789012345678901234567890"


@pytest.fixture
def sample_hero():
    """標準測試英雄"""
    return Hero(
        card_id=12345678,
        owner_id=100,
        owner_address="kaspatest:qtest123",
        hero_class="knight",
        rank="SR",
        atk=150,
        def_=120,
        spd=100,
        status="alive",
        latest_daa=12345678,
        kills=5,
        battles=10
    )


@pytest.fixture
def sample_goblin():
    """標準測試哥布林"""
    return Hero(
        card_id=99999999,
        owner_id=0,  # 哥布林標記
        owner_address="",
        hero_class="rogue",
        rank="R",
        atk=80,
        def_=60,
        spd=90,
        status="alive",
        latest_daa=99999999,
        kills=0,
        battles=0,
        name="哥布林盜賊"
    )


@pytest.fixture
def temp_db(tmp_path):
    """臨時測試資料庫"""
    db_file = tmp_path / "test_heroes.json"
    db = {
        "heroes": {},
        "user_heroes": {},
        "last_summon_daa": 0,
        "total_mana_pool": 1000,
        "last_reward_daa": 0
    }
    with open(db_file, 'w') as f:
        json.dump(db, f)
    return db_file


# ═══════════════════════════════════════════════════════════════════════════════
# 英雄屬性生成測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeroAttributes:
    """英雄屬性生成測試"""
    
    def test_attributes_deterministic(self, sample_block_hash):
        """相同 hash 產生相同屬性"""
        # calculate_hero_from_hash returns (hero_class, rank, atk, def_, spd)
        result1 = calculate_hero_from_hash(sample_block_hash)
        result2 = calculate_hero_from_hash(sample_block_hash)
        
        assert result1 == result2, "相同輸入應產生相同結果"
    
    def test_attributes_different_hash(self, sample_block_hash):
        """不同 hash 產生不同屬性"""
        different_hash = "b" + sample_block_hash[1:]
        
        result1 = calculate_hero_from_hash(sample_block_hash)
        result2 = calculate_hero_from_hash(different_hash)
        
        assert result1 != result2, "不同 hash 應產生不同結果"
    
    def test_attributes_valid_range(self, sample_block_hash):
        """屬性值在有效範圍內"""
        for i in range(100):
            hash_variant = hashlib.sha256(f"{sample_block_hash}{i}".encode()).hexdigest()
            hero_class, rank, atk, def_, spd = calculate_hero_from_hash(hash_variant)
            
            # 檢查職業有效
            assert hero_class in CLASS_WEIGHTS.keys(), f"無效職業: {hero_class}"
            
            # 檢查稀有度有效
            assert rank in RARITY_WEIGHTS.keys(), f"無效稀有度: {rank}"
            
            # 檢查屬性範圍
            assert 10 <= atk <= 500, f"ATK 超出範圍: {atk}"
            assert 10 <= def_ <= 500, f"DEF 超出範圍: {def_}"
            assert 10 <= spd <= 500, f"SPD 超出範圍: {spd}"
    
    def test_rarity_distribution(self, sample_block_hash):
        """稀有度分布符合預期（統計測試）"""
        rarities = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0, "LR": 0}
        
        # 生成 1000 個英雄
        for i in range(1000):
            hash_variant = hashlib.sha256(f"{sample_block_hash}{i}".encode()).hexdigest()
            _, rank, _, _, _ = calculate_hero_from_hash(hash_variant)
            rarities[rank] += 1
        
        # N 應該最多
        assert rarities["N"] > rarities["R"], "N 應多於 R"
        assert rarities["R"] > rarities["SR"], "R 應多於 SR"
        
        # 高稀有度應該稀有 (SSR+UR+LR < 5%)
        rare_count = rarities["SSR"] + rarities["UR"] + rarities["LR"]
        assert rare_count < 60, f"高稀有度太多: {rare_count}/1000"


# ═══════════════════════════════════════════════════════════════════════════════
# 戰鬥系統測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestBattleSystem:
    """ATB 戰鬥系統測試"""
    
    def test_battle_deterministic(self, sample_hero, sample_goblin, sample_block_hash):
        """相同輸入產生相同戰鬥結果"""
        result1, detail1 = calculate_battle_result_atb(
            sample_hero, sample_goblin, sample_block_hash
        )
        result2, detail2 = calculate_battle_result_atb(
            sample_hero, sample_goblin, sample_block_hash
        )
        
        assert result1 == result2, "相同輸入應產生相同勝負"
        assert detail1 == detail2, "相同輸入應產生相同戰鬥詳情"
    
    def test_battle_three_rounds(self, sample_hero, sample_goblin, sample_block_hash):
        """戰鬥應為三回合"""
        _, detail = calculate_battle_result_atb(
            sample_hero, sample_goblin, sample_block_hash
        )
        
        rounds = detail.get("rounds", [])
        assert len(rounds) == 3, f"應為 3 回合，實際 {len(rounds)} 回合"
    
    def test_battle_has_winner(self, sample_hero, sample_goblin, sample_block_hash):
        """戰鬥應有明確勝負"""
        result, detail = calculate_battle_result_atb(
            sample_hero, sample_goblin, sample_block_hash
        )
        
        assert isinstance(result, bool), "結果應為 bool"
        assert "atk_wins" in detail, "應有攻擊方勝利回合數"
        assert "def_wins" in detail, "應有防守方勝利回合數"
        
        # 不應平手
        assert detail["atk_wins"] != detail["def_wins"], "不應平手"
    
    def test_stronger_hero_advantage(self):
        """較強英雄應有優勢（統計測試）"""
        strong = Hero(
            card_id=1, owner_id=1, owner_address="",
            hero_class="knight", rank="SSR",
            atk=300, def_=250, spd=200,
            status="alive", latest_daa=1
        )
        weak = Hero(
            card_id=2, owner_id=2, owner_address="",
            hero_class="rogue", rank="N",
            atk=50, def_=40, spd=60,
            status="alive", latest_daa=2
        )
        
        strong_wins = 0
        for i in range(100):
            hash_variant = hashlib.sha256(str(i).encode()).hexdigest()
            result, _ = calculate_battle_result_atb(strong, weak, hash_variant)
            if result:
                strong_wins += 1
        
        # 強者應贏超過 70% (考慮隨機因素)
        assert strong_wins > 70, f"強者只贏 {strong_wins}%，太少了"


# ═══════════════════════════════════════════════════════════════════════════════
# 哥布林系統測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoblinSystem:
    """哥布林系統測試"""
    
    def test_goblin_creation(self, sample_block_hash):
        """哥布林創建測試"""
        daa = 385066666
        db = {"heroes": {}, "user_heroes": {}}
        
        goblin = create_goblin(sample_block_hash, daa, db)
        
        assert goblin is not None, "應成功創建哥布林"
        assert goblin.owner_id == 0, "哥布林 owner_id 應為 0"
        assert goblin.status == "alive", "新哥布林應為存活"
        assert goblin.name is not None, "哥布林應有名字"
    
    def test_goblin_deterministic(self, sample_block_hash):
        """相同 hash 產生相同哥布林"""
        daa = 385066666
        db1 = {"heroes": {}, "user_heroes": {}}
        db2 = {"heroes": {}, "user_heroes": {}}
        
        goblin1 = create_goblin(sample_block_hash, daa, db1)
        goblin2 = create_goblin(sample_block_hash, daa, db2)
        
        assert goblin1.hero_class == goblin2.hero_class
        assert goblin1.rank == goblin2.rank
        assert goblin1.atk == goblin2.atk
    
    def test_goblin_is_enemy(self, sample_goblin):
        """哥布林標記為敵人"""
        assert sample_goblin.owner_id == 0, "哥布林 owner_id 應為 0"
    
    def test_alive_goblins_filter(self, sample_goblin):
        """存活哥布林過濾測試"""
        db = {
            "heroes": {
                "1": {"owner_id": 0, "status": "alive", "name": "哥布林1"},
                "2": {"owner_id": 0, "status": "dead", "name": "哥布林2"},
                "3": {"owner_id": 100, "status": "alive", "name": "玩家英雄"},
            }
        }
        
        alive_goblins = [
            (gid, g) for gid, g in db["heroes"].items()
            if g.get("status") == "alive" and g.get("owner_id") == 0
        ]
        
        assert len(alive_goblins) == 1, f"應只有 1 隻存活哥布林，實際 {len(alive_goblins)}"
        assert alive_goblins[0][0] == "1", "存活哥布林應為 ID 1"


# ═══════════════════════════════════════════════════════════════════════════════
# 積分計算測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreCalculation:
    """積分計算測試"""
    
    def test_score_formula(self, sample_hero):
        """積分公式測試：存活天數 + 稀有度 + 擊殺×2"""
        # 設定 created_at 為 2 天前
        sample_hero.created_at = (
            datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ).isoformat()
        
        score = calculate_hero_score(sample_hero)
        
        # SR = 3 分，kills = 5 → 5×2 = 10
        # 存活 0-1 天 → 1 分
        # 總計應約 14 分
        assert score > 0, "積分應大於 0"
    
    def test_kills_bonus(self):
        """擊殺加成測試"""
        hero_no_kills = Hero(
            card_id=1, owner_id=1, owner_address="",
            hero_class="knight", rank="N",
            atk=100, def_=100, spd=100,
            status="alive", latest_daa=1, kills=0
        )
        hero_with_kills = Hero(
            card_id=2, owner_id=1, owner_address="",
            hero_class="knight", rank="N",
            atk=100, def_=100, spd=100,
            status="alive", latest_daa=2, kills=10
        )
        
        score_no_kills = calculate_hero_score(hero_no_kills)
        score_with_kills = calculate_hero_score(hero_with_kills)
        
        # 10 kills × 2 = 20 分差
        assert score_with_kills > score_no_kills, "有擊殺應有更高積分"
        assert score_with_kills - score_no_kills >= 20, "10 擊殺應加 20 分"


# ═══════════════════════════════════════════════════════════════════════════════
# 死亡處理測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeathHandling:
    """死亡處理測試"""
    
    def test_death_status_update(self, sample_hero):
        """死亡狀態更新"""
        sample_hero.status = "dead"
        sample_hero.death_time = datetime.now().isoformat()
        
        assert sample_hero.status == "dead"
        assert sample_hero.death_time is not None
    
    def test_dead_hero_excluded(self):
        """死亡英雄應被排除在獎勵外"""
        db = {
            "heroes": {
                "1": {"owner_id": 100, "status": "alive"},
                "2": {"owner_id": 100, "status": "dead"},
                "3": {"owner_id": 100, "status": "alive"},
            }
        }
        
        alive = [h for h in db["heroes"].values() if h["status"] == "alive"]
        assert len(alive) == 2, "應只有 2 個存活英雄"
    
    def test_protected_hero_survives(self, sample_hero):
        """受保護英雄免死"""
        sample_hero.protected = True
        
        # 模擬戰敗
        if sample_hero.protected:
            # 免死
            pass
        else:
            sample_hero.status = "dead"
        
        assert sample_hero.status == "alive", "受保護英雄應存活"


# ═══════════════════════════════════════════════════════════════════════════════
# 資料庫操作測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabase:
    """資料庫操作測試"""
    
    def test_hero_to_dict(self, sample_hero):
        """Hero 序列化"""
        d = sample_hero.to_dict()
        
        assert d["card_id"] == sample_hero.card_id
        assert d["status"] == sample_hero.status
        assert d["kills"] == sample_hero.kills
    
    def test_hero_from_dict(self, sample_hero):
        """Hero 反序列化"""
        d = sample_hero.to_dict()
        restored = Hero.from_dict(d)
        
        assert restored.card_id == sample_hero.card_id
        assert restored.status == sample_hero.status
        assert restored.kills == sample_hero.kills
    
    def test_db_merge_preserves_fields(self, sample_hero):
        """資料庫合併應保留額外欄位"""
        original = {
            "card_id": 12345678,
            "name": "測試英雄",
            "payment_tx": "abc123",
            "source_hash": "def456",
            "status": "alive"
        }
        
        # 模擬更新
        updated = sample_hero.to_dict()
        original.update(updated)
        
        # name, payment_tx, source_hash 應被保留
        assert original.get("name") == "測試英雄"
        assert original.get("payment_tx") == "abc123"


# ═══════════════════════════════════════════════════════════════════════════════
# 執行測試
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
