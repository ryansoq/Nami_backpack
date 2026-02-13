"""
🎮 v0.4.1 ATB 戰鬥系統 (Active Time Battle)
娜米的英雄奇幻冒險 - 核心戰鬥引擎

═══════════════════════════════════════════════════════════════════════════════
📋 模組說明
═══════════════════════════════════════════════════════════════════════════════

這是遊戲的核心戰鬥系統，採用類似 Final Fantasy 的 ATB 機制。
每個角色有兩個計量條：
  - 移動條 (Move Gauge): 累積到 1000 可以發動普通攻擊
  - 技能條 (Skill Gauge): 累積到 1000 可以發動職業大招

═══════════════════════════════════════════════════════════════════════════════
🔄 戰鬥流程圖
═══════════════════════════════════════════════════════════════════════════════

  hero_commands.py                    hero_game.py                     atb_battle.py
  ┌─────────────┐                   ┌─────────────┐                  ┌─────────────┐
  │ /nami_pvp   │ ──── 呼叫 ────→   │ process_pvp │ ──── 呼叫 ────→  │ atb_battle  │
  │ 指令處理    │                   │ 戰鬥流程    │                  │ 戰鬥引擎    │
  └─────────────┘                   └─────────────┘                  └─────────────┘
        │                                 │                                │
        │                                 │                                ▼
        │                                 │                     ┌─────────────────────┐
        │                                 │                     │ ATBFighter 建立     │
        │                                 │                     │ (從 Hero 物件)      │
        │                                 │                     └─────────────────────┘
        │                                 │                                │
        │                                 │                                ▼
        │                                 │                     ┌─────────────────────┐
        │                                 │                     │ 主戰鬥迴圈          │
        │                                 │                     │ (最多 80 loop)      │
        │                                 │                     │                     │
        │                                 │                     │ 每 loop:            │
        │                                 │                     │ 1. 累積移動條 +200  │
        │                                 │                     │ 2. 累積技能條       │
        │                                 │                     │ 3. 檢查大招觸發     │
        │                                 │                     │ 4. 檢查普攻觸發     │
        │                                 │                     └─────────────────────┘
        │                                 │                                │
        │                                 │                                ▼
        │                                 │                     ┌─────────────────────┐
        │                                 │                     │ 回傳結果            │
        │                                 │                     │ - winner/loser      │
        │                                 │                     │ - battle_log        │
        │                                 │                     │ - stats             │
        │                                 │                     └─────────────────────┘
        │                                 │                                │
        │                                 ◀────────────────────────────────┘
        │                                 │
        │                                 ▼
        │                     ┌─────────────────────────┐
        │                     │ 處理鏈上記錄            │
        │                     │ - 付費 TX               │
        │                     │ - 勝利/死亡 inscription │
        │                     └─────────────────────────┘
        │                                 │
        ◀─────────────────────────────────┘
        │
        ▼
  ┌─────────────────────────┐
  │ 發送戰報到群組          │
  │ announce_pvp_result()   │
  └─────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
🎯 職業特色
═══════════════════════════════════════════════════════════════════════════════

  職業      │ 技能條累積 │ 大招效果           │ 特色
  ─────────┼───────────┼──────────────────┼────────────────
  ⚔️ 騎士   │ DEF       │ 衝擊之暈：減對手條 │ 打斷節奏
  🧙 法師   │ ATK       │ 流星雨：2.5x 傷害  │ 高爆發
  🗡️ 盜賊   │ SPD       │ 幻影：閃避+背刺    │ 連擊 Combo
  🏹 弓手   │ SPD       │ 穿透射擊：傷害+暈  │ 平衡型

═══════════════════════════════════════════════════════════════════════════════
📝 更新日誌
═══════════════════════════════════════════════════════════════════════════════

v0.4.1 (2026-02-08)
  - 新增 Combo 連擊計數系統
  - 簡化戰報格式：HP 顯示在攻擊行後面
  - 移除樹枝結構，改為全部貼左
  - 新增最高連擊統計

v0.4.0 (2026-02-06)
  - 實現 ATB 雙條系統
  - 新增職業大招
  - 新增爆發模式 (HP < 30%)
  - 盜賊背刺機制

═══════════════════════════════════════════════════════════════════════════════
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
    # v0.3+ Rank 系統 - 6階 (Thanks Bob for catching this! 🔍)
    "N": 500,
    "R": 600,
    "SR": 750,
    "SSR": 1000,
    "UR": 1300,      # 傳說級 - 新增
    "LR": 1800,      # 神話級 - 新增
}

# 職業大招設定
ULTIMATE_SKILLS = {
    "mage": {"name": "流星雨", "emoji": "🧙", "type": "damage", "multiplier": 2.5},  # 5→2.5
    "knight": {"name": "衝擊之暈", "emoji": "⚔️", "type": "stun", "move_reduce": 500},
    "rogue": {"name": "幻影", "emoji": "🗡️", "type": "evade"},
    "archer": {"name": "穿透射擊", "emoji": "🏹", "type": "damage_stun", "multiplier": 3, "move_reduce": 200},
}

# 職業中文名
CLASS_NAMES = {
    "mage": "法師",
    "knight": "騎士", 
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
        elif self.hero_class == "knight":
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
    """戰鬥日誌記錄器（v0.4.1 樹枝視覺化 + v0.5 Canvas 事件）"""
    
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
        # v0.4.1: combo 追蹤
        self.last_actor: Optional[str] = None  # "p1" or "p2"
        self.combo_count: int = 0
        self.max_combo: int = 0
        self.pending_actions: List[str] = []  # 暫存同一人的連續動作
        
        # v0.5: Canvas 結構化事件
        self.events: List[Dict] = []
        self.current_tick: int = 0
    
    def set_tick(self, tick: int):
        """設定當前 tick（由戰鬥主迴圈呼叫）"""
        self.current_tick = tick
    
    def add_event(self, event_type: str, who: str = None, **kwargs):
        """
        添加 Canvas 結構化事件
        
        event_type: battle_start, attack, skill, evade, death, battle_end
        who: "attacker" or "defender" (p1=attacker, p2=defender)
        kwargs: damage, skill_name, msg, etc.
        """
        event = {
            "tick": self.current_tick,
            "type": event_type,
        }
        if who:
            event["who"] = who
        event.update(kwargs)
        self.events.append(event)
    
    def add(self, text: str):
        """原始添加（用於開場、結束等非戰鬥行）"""
        self._flush_pending()
        self.entries.append(text)
    
    def add_action(self, actor: str, is_p1: bool, text: str, 
                   target_hp: int = None, target_max_hp: int = None,
                   is_critical: bool = False):
        """
        添加戰鬥行動（智能樹枝結構）
        
        actor: 行動者名稱
        is_p1: 是否為 P1
        text: 行動描述
        target_hp: 對手當前 HP（用於顯示 HP 條）
        target_max_hp: 對手最大 HP
        is_critical: 是否為關鍵時刻（瀕死/KO）
        """
        actor_key = "p1" if is_p1 else "p2"
        actor_emoji = "🔵" if is_p1 else "🔴"
        target_emoji = "🔴" if is_p1 else "🔵"
        
        # 檢查是否換人
        if self.last_actor != actor_key:
            # 換人了，先輸出之前的動作
            self._flush_pending()
            self.combo_count = 1
            self.last_actor = actor_key
        else:
            # 同一人連擊
            self.combo_count += 1
            self.max_combo = max(self.max_combo, self.combo_count)
        
        # 組合行動文字
        combo_text = f" ⚡{self.combo_count} Combo!" if self.combo_count >= 2 else ""
        
        # v0.4.1: HP 直接顯示在攻擊行後面（簡潔版）
        hp_text = ""
        hp_warning = ""
        if target_hp is not None and target_max_hp is not None:
            target_hp_int = int(max(0, target_hp))
            hp_text = f" (敵HP:{target_hp_int})"
            if target_hp <= 0:
                hp_warning = " 💀"
            elif target_hp / target_max_hp < 0.3:
                hp_warning = " ⚠️"
        
        action_line = f"{actor_emoji}⚡ [{actor}] {text}{combo_text}{hp_text}{hp_warning}"
        self.pending_actions.append(action_line)
    
    def _make_hp_bar(self, current: int, max_hp: int, length: int = 10) -> str:
        """生成 HP 條"""
        if max_hp <= 0:
            return "[░░░░░░░░░░] 0/0"
        current = int(max(0, current))
        ratio = current / max_hp
        filled = int(ratio * length)
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}] {current}/{max_hp}"
    
    def _flush_pending(self):
        """輸出暫存的動作（v0.4.1: 無樹枝，全部貼左）"""
        if not self.pending_actions:
            return
        
        for action in self.pending_actions:
            self.entries.append(action)
        
        self.pending_actions = []
    
    def get_full_log(self) -> str:
        self._flush_pending()
        return "\n".join(self.entries)
    
    def get_max_combo(self) -> int:
        return self.max_combo


# ═══════════════════════════════════════════════════════════════════════════════
# ATB 戰鬥引擎
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_damage(attacker: ATBFighter, defender: ATBFighter) -> Tuple[int, bool, bool]:
    """計算普通攻擊傷害，回傳 (傷害, 是否狂暴, 是否背刺)"""
    variance = random.randint(-5, 5)
    
    is_berserk = False
    is_backstab = False
    
    # 盜賊背刺：ATK × 3 - DEF（先乘後減）
    if attacker.backstab_ready:
        damage = max(1, attacker.atk * 3 - defender.def_ + variance)
        is_backstab = True
        attacker.backstab_ready = False
    # 騎士狂暴：ATK × 3 - DEF（先乘後減）
    elif attacker.hero_class == "knight" and attacker.is_rage_mode:
        damage = max(1, attacker.atk * 3 - defender.def_ + variance)
        is_berserk = True
    # 普通攻擊
    else:
        damage = max(1, attacker.atk - defender.def_ + variance)
    
    return damage, is_berserk, is_backstab


def cast_ultimate(caster: ATBFighter, target: ATBFighter, log: BattleLog, is_p1: bool) -> int:
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
        log.add_action(caster.name, is_p1, 
                      f"{emoji}【{skill_name}】！{damage} 傷害",
                      target.current_hp, target.max_hp)
        log.stats["p1_damage_dealt" if is_p1 else "p2_damage_dealt"] += damage
        
    elif skill_type == "stun":
        # 騎士：衝擊之暈（移動條+技能條都減）
        move_reduce = skill.get("move_reduce", 500)
        target.move_gauge = max(0, target.move_gauge - move_reduce)
        target.skill_gauge = max(0, target.skill_gauge - move_reduce)
        log.add_action(caster.name, is_p1, f"{emoji}【{skill_name}】！暈眩 -{move_reduce}")
        
    elif skill_type == "evade":
        # 盜賊：幻影（閃避 1 次攻擊，含大招）
        caster.evade_count += 1
        log.add_action(caster.name, is_p1, f"{emoji}【{skill_name}】！準備閃避")
        
    elif skill_type == "damage_stun":
        # 弓箭手：穿透射擊
        multiplier = skill.get("multiplier", 3)
        move_reduce = skill.get("move_reduce", 200)
        damage = caster.atk * multiplier
        target.current_hp -= damage
        target.move_gauge = max(0, target.move_gauge - move_reduce)
        log.add_action(caster.name, is_p1,
                      f"{emoji}【{skill_name}】！{damage} 傷害 + 暈眩",
                      target.current_hp, target.max_hp)
        log.stats["p1_damage_dealt" if is_p1 else "p2_damage_dealt"] += damage
    
    return damage


def process_fighter_turn(attacker: ATBFighter, defender: ATBFighter, 
                         log: BattleLog, is_p1: bool) -> bool:
    """處理單一戰鬥者的回合，回傳對手是否死亡"""
    
    prefix = "p1" if is_p1 else "p2"
    who = "attacker" if is_p1 else "defender"  # v0.5 Canvas
    target = "defender" if is_p1 else "attacker"
    
    # 先處理大招（優先級高）
    if attacker.skill_gauge >= SKILL_GAUGE_MAX:
        attacker.skill_gauge -= SKILL_GAUGE_MAX
        log.stats[f"{prefix}_skills"] += 1
        
        # 如果是閃避類技能，不用檢查對手閃避
        skill = ULTIMATE_SKILLS.get(attacker.hero_class, {})
        skill_name = skill.get("name", "技能")
        
        if skill.get("type") == "evade":
            cast_ultimate(attacker, defender, log, is_p1)
            # v0.5 Canvas 事件（閃避技能）
            log.add_event("skill", who=who, skill_name=skill_name, 
                         damage=0, msg=f"{attacker.name} 發動【{skill_name}】！準備閃避")
        elif defender.is_evading and skill.get("type") in ["damage", "damage_stun"]:
            # 傷害型大招被閃避
            emoji = skill.get("emoji", "✨")
            log.add_action(attacker.name, is_p1, f"{emoji}【{skill_name}】！💨 被閃避！")
            defender.consume_evade()
            log.stats[f"{'p2' if is_p1 else 'p1'}_evades"] += 1
            # v0.5 Canvas 事件（被閃避）
            log.add_event("evade", who=target, 
                         msg=f"{defender.name} 閃避了 {attacker.name} 的【{skill_name}】！")
        else:
            old_hp = defender.current_hp
            cast_ultimate(attacker, defender, log, is_p1)
            damage_dealt = old_hp - defender.current_hp
            # v0.5 Canvas 事件
            log.add_event("skill", who=who, target=target, skill_name=skill_name,
                         damage=max(0, damage_dealt), 
                         msg=f"{attacker.name} 發動【{skill_name}】！造成 {max(0, damage_dealt)} 傷害")
        
        if not defender.is_alive:
            return True
    
    # 再處理普通攻擊
    if attacker.move_gauge >= MOVE_GAUGE_MAX:
        attacker.move_gauge -= MOVE_GAUGE_MAX
        log.stats[f"{prefix}_attacks"] += 1
        
        if defender.is_evading:
            # 被閃避
            log.add_action(attacker.name, is_p1, f"攻擊！💨 被閃避！(剩餘:{defender.evade_count-1})")
            defender.consume_evade()
            log.stats[f"{'p2' if is_p1 else 'p1'}_evades"] += 1
            # v0.5 Canvas 事件
            log.add_event("evade", who=target, 
                         msg=f"{defender.name} 閃避了 {attacker.name} 的攻擊！")
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
            
            # 使用 add_action（會自動處理 HP 條和 combo）
            log.add_action(attacker.name, is_p1, 
                          f"{action}攻擊！{damage} 傷害",
                          defender.current_hp, defender.max_hp)
            
            # v0.5 Canvas 事件
            attack_type = "backstab" if is_backstab else "berserk" if is_berserk else "attack"
            log.add_event(attack_type, who=who, target=target, damage=damage,
                         msg=f"{attacker.name} {action}攻擊！造成 {damage} 傷害")
        
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
    log.add_event("battle_start", msg="⚔️ ATB 戰鬥開始！")
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
        log.set_tick(loop * 10)  # v0.5: 每 loop = 10 tick
        
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
        # v0.5 Canvas 事件
        log.add_event("death", who="attacker", msg=f"💀 {p1.name} 倒下了...")
        log.add_event("battle_end", winner="defender", msg=f"🏆 {p2.name} 獲得勝利！")
    elif not p2.is_alive:
        result["winner"] = p1
        result["loser"] = p2
        result["draw"] = False
        log.add(f"🏆 勝者：{p1.name} (剩餘 HP: {p1.current_hp})")
        # v0.5 Canvas 事件
        log.add_event("death", who="defender", msg=f"💀 {p2.name} 倒下了...")
        log.add_event("battle_end", winner="attacker", msg=f"🏆 {p1.name} 獲得勝利！")
    else:
        # 平手
        result["winner"] = None
        result["loser"] = None
        result["draw"] = True
        log.add(f"⏰ 時間到！平手！")
        log.add(f"🌲 大地之樹沒收 10 mana")
        log.add_event("battle_end", winner=None, msg="⏰ 時間到！平手！")
    
    # 統計
    combo_text = f" | 🔥最高連擊:{log.get_max_combo()}" if log.get_max_combo() >= 2 else ""
    log.add(f"📊 Loop:{log.stats['loops']} | "
            f"閃避:{log.stats['p1_evades']+log.stats['p2_evades']} | "
            f"大招:{log.stats['p1_skills']+log.stats['p2_skills']}{combo_text}")
    
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
