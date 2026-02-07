"""
🎮 v0.4 ATB 戰鬥系統
Active Time Battle - 雙條系統 + 職業大招
"""

import random
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# 常數設定
# ═══════════════════════════════════════════════════════════════════════════════

MAX_LOOPS = 80           # 最大 loop 數（超過判平手）
MOVE_GAUGE_MAX = 1000     # 移動條門檻
SKILL_GAUGE_MAX = 1000    # 技能條門檻
MOVE_GAIN = 200           # 移動條每 loop 固定累積
RAGE_THRESHOLD = 0.3      # 爆發模式觸發（HP < 30%）
RAGE_MULTIPLIER = 2       # 爆發模式技能累積倍率

# Rank -> HP 對照表
RANK_HP = {
    "N": 500,
    "R": 600,
    "SR": 750,
    "SSR": 1000,
}

# 職業大招設定
ULTIMATE_SKILLS = {
    "mage": {"name": "流星雨", "emoji": "🧙", "type": "damage", "multiplier": 3},  # 5→3
    "warrior": {"name": "衝擊之暈", "emoji": "⚔️", "type": "stun", "move_reduce": 500},
    "rogue": {"name": "幻影", "emoji": "🗡️", "type": "evade"},
    "archer": {"name": "穿透射擊", "emoji": "🏹", "type": "damage_stun", "multiplier": 3, "move_reduce": 200},
}

# 職業中文名
CLASS_NAMES = {
    "mage": "法師",
    "warrior": "戰士", 
    "rogue": "盜賊",
    "archer": "弓箭手",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 戰鬥單位
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ATBFighter:
    """ATB 戰鬥單位"""
    card_id: int
    name: str
    hero_class: str
    rank: str
    
    # 屬性（命運區塊決定）
    atk: int
    def_: int
    spd: int
    
    # HP（Rank 決定）
    max_hp: int = 0
    current_hp: int = 0
    
    # 戰鬥狀態
    move_gauge: int = 0
    skill_gauge: int = 0
    evade_count: int = 0  # 閃避次數
    backstab_ready: bool = False  # 背刺準備（閃避成功後）
    
    def __post_init__(self):
        # HP 由 Rank 決定
        self.max_hp = RANK_HP.get(self.rank, 500)
        self.current_hp = self.max_hp
        
        # 盜賊先手優勢：開場自帶 300 技能條（降低）
        if self.hero_class == "rogue":
            self.skill_gauge = 300
    
    @property
    def hp_percent(self) -> float:
        return self.current_hp / self.max_hp if self.max_hp > 0 else 0
    
    @property
    def is_rage_mode(self) -> bool:
        """是否進入爆發模式"""
        return self.hp_percent < RAGE_THRESHOLD
    
    @property
    def is_evading(self) -> bool:
        """是否在閃避狀態"""
        return self.evade_count > 0
    
    def consume_evade(self):
        """消耗一次閃避，觸發背刺"""
        if self.evade_count > 0:
            self.evade_count -= 1
            if self.hero_class == "rogue":
                self.backstab_ready = True  # 盜賊閃避後準備背刺
    
    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0
    
    def get_skill_gain(self) -> int:
        """取得技能條累積值（根據職業）"""
        if self.hero_class == "mage":
            return self.atk
        elif self.hero_class == "warrior":
            return self.def_
        elif self.hero_class == "rogue":
            return self.spd  # SPD（盜賊要快才能閃）
        elif self.hero_class == "archer":
            return self.spd
        return 50  # 預設
    
    def get_class_emoji(self) -> str:
        return ULTIMATE_SKILLS.get(self.hero_class, {}).get("emoji", "❓")
    
    def get_class_name(self) -> str:
        return CLASS_NAMES.get(self.hero_class, self.hero_class)
    
    @classmethod
    def from_hero(cls, hero) -> "ATBFighter":
        """從現有 Hero 物件建立 ATBFighter"""
        return cls(
            card_id=hero.card_id,
            name=getattr(hero, 'name', '') or f"#{hero.card_id}",
            hero_class=hero.hero_class,
            rank=getattr(hero, 'rank', 'N'),
            atk=hero.atk,
            def_=hero.def_,
            spd=hero.spd,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 戰鬥日誌
# ═══════════════════════════════════════════════════════════════════════════════

class BattleLog:
    """戰鬥日誌記錄器"""
    
    def __init__(self):
        self.entries: List[str] = []
        self.stats = {
            "loops": 0,
            "p1_attacks": 0,
            "p2_attacks": 0,
            "p1_skills": 0,
            "p2_skills": 0,
            "p1_evades": 0,
            "p2_evades": 0,
            "p1_damage_dealt": 0,
            "p2_damage_dealt": 0,
        }
    
    def add(self, text: str):
        self.entries.append(text)
    
    def get_full_log(self) -> str:
        return "\n".join(self.entries)


# ═══════════════════════════════════════════════════════════════════════════════
# ATB 戰鬥引擎
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_damage(attacker: ATBFighter, defender: ATBFighter) -> Tuple[int, bool, bool]:
    """計算普通攻擊傷害，回傳 (傷害, 是否狂暴, 是否背刺)"""
    base_damage = attacker.atk - defender.def_
    variance = random.randint(-5, 5)
    damage = max(1, base_damage + variance)
    
    is_berserk = False
    is_backstab = False
    
    # 戰士狂暴姿態：HP < 30% 時傷害 300%
    if attacker.hero_class == "warrior" and attacker.is_rage_mode:
        damage *= 3
        is_berserk = True
    
    # 盜賊背刺：閃避成功後攻擊傷害 300%
    if attacker.backstab_ready:
        damage *= 3
        is_backstab = True
        attacker.backstab_ready = False
    
    return damage, is_berserk, is_backstab


def cast_ultimate(caster: ATBFighter, target: ATBFighter, log: BattleLog) -> int:
    """發動職業大招，回傳造成的傷害"""
    skill = ULTIMATE_SKILLS.get(caster.hero_class, {})
    skill_name = skill.get("name", "技能")
    skill_type = skill.get("type", "damage")
    emoji = skill.get("emoji", "✨")
    
    damage = 0
    
    if skill_type == "damage":
        # 法師：流星雨
        multiplier = skill.get("multiplier", 5)
        damage = caster.atk * multiplier
        target.current_hp -= damage
        log.add(f"{emoji} [{caster.name}]【{skill_name}】！造成 {damage} 傷害 (敵HP:{max(0, target.current_hp)})")
        log.stats["p1_damage_dealt" if caster == log._p1 else "p2_damage_dealt"] += damage
        
    elif skill_type == "stun":
        # 戰士：衝擊之暈（移動條+技能條都減）
        move_reduce = skill.get("move_reduce", 500)
        target.move_gauge = max(0, target.move_gauge - move_reduce)
        target.skill_gauge = max(0, target.skill_gauge - move_reduce)
        log.add(f"{emoji} [{caster.name}]【{skill_name}】！對手移動條&技能條 -{move_reduce}")
        
    elif skill_type == "evade":
        # 盜賊：幻影（閃避 1 次攻擊，含大招）
        caster.evade_count += 1
        log.add(f"{emoji} [{caster.name}]【{skill_name}】！準備閃避")
        
    elif skill_type == "damage_stun":
        # 弓箭手：穿透射擊
        multiplier = skill.get("multiplier", 3)
        move_reduce = skill.get("move_reduce", 200)
        damage = caster.atk * multiplier
        target.current_hp -= damage
        target.move_gauge = max(0, target.move_gauge - move_reduce)
        log.add(f"{emoji} [{caster.name}]【{skill_name}】！造成 {damage} 傷害 + 擊退 -{move_reduce} (敵HP:{max(0, target.current_hp)})")
        log.stats["p1_damage_dealt" if caster == log._p1 else "p2_damage_dealt"] += damage
    
    return damage


def process_fighter_turn(attacker: ATBFighter, defender: ATBFighter, 
                         log: BattleLog, is_p1: bool) -> bool:
    """處理單一戰鬥者的回合，回傳對手是否死亡"""
    
    prefix = "p1" if is_p1 else "p2"
    
    # 先處理大招（優先級高）
    if attacker.skill_gauge >= SKILL_GAUGE_MAX:
        attacker.skill_gauge -= SKILL_GAUGE_MAX
        log.stats[f"{prefix}_skills"] += 1
        
        # 如果是閃避類技能，不用檢查對手閃避
        skill = ULTIMATE_SKILLS.get(attacker.hero_class, {})
        if skill.get("type") == "evade":
            cast_ultimate(attacker, defender, log)
        elif defender.is_evading and skill.get("type") in ["damage", "damage_stun"]:
            # 傷害型大招被閃避
            skill_name = skill.get("name", "技能")
            emoji = skill.get("emoji", "✨")
            log.add(f"{emoji} [{attacker.name}]【{skill_name}】！💨 被閃避！！")
            defender.consume_evade()
            log.stats[f"{'p2' if is_p1 else 'p1'}_evades"] += 1
        else:
            cast_ultimate(attacker, defender, log)
        
        if not defender.is_alive:
            return True
    
    # 再處理普通攻擊
    if attacker.move_gauge >= MOVE_GAUGE_MAX:
        attacker.move_gauge -= MOVE_GAUGE_MAX
        log.stats[f"{prefix}_attacks"] += 1
        
        if defender.is_evading:
            # 被閃避
            log.add(f"⚡ [{attacker.name}] 攻擊！💨 被閃避！(剩餘閃避:{defender.evade_count-1})")
            defender.consume_evade()
            log.stats[f"{'p2' if is_p1 else 'p1'}_evades"] += 1
        else:
            # 正常傷害
            damage, is_berserk, is_backstab = calculate_damage(attacker, defender)
            defender.current_hp -= damage
            log.stats[f"{prefix}_damage_dealt"] += damage
            
            # 特效文字
            if is_backstab:
                action = "🗡️背刺！"
            elif is_berserk:
                action = "🔥狂暴！"
            else:
                action = ""
            hp_warning = " ⚠️爆發模式！" if defender.is_rage_mode and defender.is_alive else ""
            log.add(f"⚡ [{attacker.name}] {action}攻擊！{damage} 傷害 (敵HP:{max(0, defender.current_hp)}){hp_warning}")
        
        if not defender.is_alive:
            return True
    
    return False


def atb_battle(p1: ATBFighter, p2: ATBFighter) -> Dict:
    """
    執行 ATB 戰鬥
    
    Returns:
        {
            "winner": ATBFighter or None (平手),
            "loser": ATBFighter or None,
            "draw": bool,
            "logs": BattleLog,
            "loops": int,
        }
    """
    log = BattleLog()
    log._p1 = p1  # 用於統計
    log._p2 = p2
    
    # 開場
    log.add(f"⚔️ ATB 決鬥開始！")
    log.add("═" * 35)
    log.add(f"")
    log.add(f"🔵 {p1.name} ({p1.get_class_emoji()}{p1.get_class_name()} {p1.rank})")
    log.add(f"   HP:{p1.max_hp} | ATK:{p1.atk} DEF:{p1.def_} SPD:{p1.spd}")
    log.add(f"")
    log.add(f"🔴 {p2.name} ({p2.get_class_emoji()}{p2.get_class_name()} {p2.rank})")
    log.add(f"   HP:{p2.max_hp} | ATK:{p2.atk} DEF:{p2.def_} SPD:{p2.spd}")
    log.add(f"")
    log.add("═" * 35)
    log.add("")
    
    # 主戰鬥迴圈
    for loop in range(MAX_LOOPS):
        log.stats["loops"] = loop + 1
        
        # ─── 累積移動條（固定 200）───
        p1.move_gauge += MOVE_GAIN
        p2.move_gauge += MOVE_GAIN
        
        # ─── 累積技能條（職業專屬，爆發模式 x2）───
        p1_skill_gain = p1.get_skill_gain()
        p2_skill_gain = p2.get_skill_gain()
        
        if p1.is_rage_mode:
            p1_skill_gain *= RAGE_MULTIPLIER
        if p2.is_rage_mode:
            p2_skill_gain *= RAGE_MULTIPLIER
            
        p1.skill_gauge += p1_skill_gain
        p2.skill_gauge += p2_skill_gain
        
        # ─── P1 行動 ───
        if process_fighter_turn(p1, p2, log, is_p1=True):
            # P2 死亡，P1 獲勝
            break
        
        # ─── P2 行動 ───
        if process_fighter_turn(p2, p1, log, is_p1=False):
            # P1 死亡，P2 獲勝
            break
    
    # 結算
    log.add("")
    log.add("═" * 35)
    
    result = {
        "logs": log,
        "loops": log.stats["loops"],
        "stats": log.stats,
    }
    
    if not p1.is_alive:
        result["winner"] = p2
        result["loser"] = p1
        result["draw"] = False
        log.add(f"🏆 勝者：{p2.name} (剩餘 HP: {p2.current_hp})")
    elif not p2.is_alive:
        result["winner"] = p1
        result["loser"] = p2
        result["draw"] = False
        log.add(f"🏆 勝者：{p1.name} (剩餘 HP: {p1.current_hp})")
    else:
        # 平手
        result["winner"] = None
        result["loser"] = None
        result["draw"] = True
        log.add(f"⏰ 時間到！平手！")
        log.add(f"🌲 大地之樹沒收 10 mana")
    
    # 統計
    log.add(f"📊 Loop:{log.stats['loops']} | "
            f"閃避:{log.stats['p1_evades']+log.stats['p2_evades']} | "
            f"大招:{log.stats['p1_skills']+log.stats['p2_skills']}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 測試
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 測試戰鬥
    
    # R 盜賊（高敏捷）
    rogue = ATBFighter(
        card_id=1,
        name="偷偷殺你",
        hero_class="rogue",
        rank="R",
        atk=45,
        def_=35,
        spd=130,  # 高敏捷！
    )
    
    # SSR 法師（高攻擊）
    mage = ATBFighter(
        card_id=2,
        name="大魔王",
        hero_class="mage",
        rank="SSR",
        atk=95,  # 高攻擊
        def_=40,
        spd=70,
    )
    
    print("=" * 50)
    print("測試：R 高敏捷盜賊 vs SSR 高攻擊法師")
    print("=" * 50)
    
    result = atb_battle(rogue, mage)
    print(result["logs"].get_full_log())
    print()
    
    if result["draw"]:
        print("結果：平手！")
    else:
        print(f"結果：{result['winner'].name} 獲勝！")
