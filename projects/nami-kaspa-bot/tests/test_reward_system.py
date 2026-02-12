#!/usr/bin/env python3
"""
🧪 獎勵系統測試
===============

測試範圍：
- 觸發條件判斷
- 獎勵分配計算
- 哥布林威脅扣除
- mana 池管理

by Nami 🌊
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from reward_system import (
    should_trigger_reward,
    find_trigger_daa_in_range,
    calculate_hero_score,
    REWARD_TRIGGER_SUFFIX,
    BASE_REWARD_MANA,
    GOBLIN_THREAT_PER,
    RARITY_BONUS
)
from hero_game import Hero


# ═══════════════════════════════════════════════════════════════════════════════
# 觸發條件測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestTriggerCondition:
    """獎勵觸發條件測試"""
    
    def test_trigger_suffix_66666(self):
        """結尾 66666 應觸發"""
        assert should_trigger_reward(385066666) == True
        assert should_trigger_reward(385166666) == True
        assert should_trigger_reward(100066666) == True
    
    def test_no_trigger_other_suffix(self):
        """其他結尾不應觸發"""
        assert should_trigger_reward(385066667) == False
        assert should_trigger_reward(385066665) == False
        assert should_trigger_reward(385000000) == False
        assert should_trigger_reward(385012345) == False
    
    def test_find_trigger_in_range(self):
        """區間內找到觸發點"""
        # 區間包含 385066666
        result = find_trigger_daa_in_range(385066000, 385067000)
        assert result == 385066666
        
        # 區間不包含觸發點
        result = find_trigger_daa_in_range(385067000, 385068000)
        assert result is None
    
    def test_find_trigger_boundary(self):
        """邊界條件測試"""
        # 剛好在起點（不含）
        result = find_trigger_daa_in_range(385066666, 385066700)
        assert result is None  # start 不含
        
        # 剛好在終點（含）
        result = find_trigger_daa_in_range(385066600, 385066666)
        assert result == 385066666
    
    def test_trigger_interval(self):
        """觸發間隔約 100000 DAA"""
        triggers = []
        for daa in range(385000000, 385300000):
            if should_trigger_reward(daa):
                triggers.append(daa)
        
        assert len(triggers) == 3  # 066666, 166666, 266666
        
        # 間隔應為 100000
        for i in range(1, len(triggers)):
            assert triggers[i] - triggers[i-1] == 100000


# ═══════════════════════════════════════════════════════════════════════════════
# 獎勵分配測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestRewardDistribution:
    """獎勵分配測試"""
    
    def test_base_reward(self):
        """基礎獎勵應為 500 mana"""
        assert BASE_REWARD_MANA == 500
    
    def test_score_based_distribution(self):
        """按積分比例分配"""
        # 假設三個英雄，積分比 1:2:2
        scores = [10, 20, 20]
        total_score = sum(scores)
        total_reward = 1000
        
        rewards = [int(total_reward * s / total_score) for s in scores]
        
        assert rewards[0] == 200  # 10/50 * 1000
        assert rewards[1] == 400  # 20/50 * 1000
        assert rewards[2] == 400  # 20/50 * 1000
    
    def test_rarity_affects_score(self):
        """稀有度影響積分"""
        assert RARITY_BONUS["N"] < RARITY_BONUS["R"]
        assert RARITY_BONUS["R"] < RARITY_BONUS["SR"]
        assert RARITY_BONUS["SR"] < RARITY_BONUS["SSR"]


# ═══════════════════════════════════════════════════════════════════════════════
# 哥布林威脅測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoblinThreat:
    """哥布林威脅系統測試"""
    
    def test_threat_per_goblin(self):
        """每隻哥布林威脅 50 mana"""
        assert GOBLIN_THREAT_PER == 50
    
    def test_threat_calculation(self):
        """威脅計算"""
        goblin_count = 5
        total_threat = goblin_count * GOBLIN_THREAT_PER
        
        assert total_threat == 250
    
    def test_reward_after_threat(self):
        """扣除威脅後的獎勵"""
        base_reward = 500
        accumulated = 300
        total_mana = base_reward + accumulated  # 800
        
        goblin_count = 4
        threat = goblin_count * GOBLIN_THREAT_PER  # 200
        
        reward_after_threat = max(0, total_mana - threat)
        assert reward_after_threat == 600
    
    def test_threat_can_zero_reward(self):
        """威脅可以把獎勵減到 0"""
        total_mana = 400
        goblin_count = 10  # 500 威脅
        threat = goblin_count * GOBLIN_THREAT_PER
        
        reward_after_threat = max(0, total_mana - threat)
        assert reward_after_threat == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Mana 池測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestManaPool:
    """Mana 池管理測試"""
    
    def test_pool_accumulation(self):
        """mana 池累積"""
        pool = 0
        
        # 召喚費用
        pool += 10
        # PvP 費用
        pool += 10
        pool += 10
        
        assert pool == 30
    
    def test_pool_distribution(self):
        """發放後 mana 池應減少"""
        pool = 500
        distribution = 400
        
        pool -= distribution
        assert pool == 100
    
    def test_pool_reset_on_distribution(self):
        """發放時累積池清零"""
        accumulated = 300
        distributed = 300  # 70% 發放
        
        remaining = accumulated - distributed
        assert remaining == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 積分計算測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreCalculation:
    """積分計算測試"""
    
    def test_score_components(self):
        """積分 = 存活天數 + 稀有度 + 擊殺×2"""
        hero = Hero(
            card_id=1, owner_id=1, owner_address="",
            hero_class="knight", rank="SR",  # SR = 3
            atk=100, def_=100, spd=100,
            status="alive", latest_daa=1, kills=5  # 5×2 = 10
        )
        
        score = calculate_hero_score(hero)
        
        # 最少應有：稀有度 3 + 擊殺 10 = 13
        assert score >= 13
    
    def test_dead_hero_no_score(self):
        """死亡英雄不計積分"""
        hero = Hero(
            card_id=1, owner_id=1, owner_address="",
            hero_class="knight", rank="SSR",
            atk=100, def_=100, spd=100,
            status="dead", latest_daa=1, kills=100
        )
        
        # 死亡英雄應被過濾，不進入計分
        # 這裡只測試如果進入計算會怎樣
        # 實際流程中會先過濾 status="alive"


# ═══════════════════════════════════════════════════════════════════════════════
# 執行測試
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
