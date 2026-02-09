# 🌲 娜米的英雄奇幻冒險 - 遊戲設計文檔

**版本**: 0.1  
**日期**: 2026-02-06  
**設計**: Ryan & Nami

---

## 📖 概述

一款基於 Kaspa 區塊鏈的卡牌遊戲，特色是：
- **公平**：命運由區塊 hash 決定，無人能作弊
- **可驗證**：所有屬性可從鏈上重新計算
- **永久死亡**：敗者卡片永久消失，增加稀缺性

---

## 🎮 核心機制

### 貨幣系統
- **Mana** = tKAS（testnet Kaspa）
- 1 Mana = 1 tKAS = 100,000,000 sompi

### 英雄召喚
- **費用**: 10 Mana
- **命運來源**: 付費確認後的下一個 DAA 的第一個區塊 hash
- **Card ID**: DAA score（唯一且遞增）

### 屬性計算
從區塊 hash 決定：
```python
hash_bytes = bytes.fromhex(block_hash)

# 職業 (4 種)
hero_class = ["warrior", "mage", "rogue", "archer"][hash_bytes[0] % 4]

# 稀有度 (機率加權)
rarity_roll = hash_bytes[1]
# common: 50%, uncommon: 25%, rare: 15%, epic: 7%, legendary: 2.5%, mythic: 0.5%

# 屬性 (10-100 範圍，稀有度加成)
atk = 10 + (hash_bytes[2] % 91) * rarity_multiplier
def_ = 10 + (hash_bytes[3] % 91) * rarity_multiplier
spd = 10 + (hash_bytes[4] % 91) * rarity_multiplier
```

### 稀有度加成
| 稀有度 | 機率 | 屬性倍率 | 顏色 |
|--------|------|----------|------|
| Common | 50% | x1.0 | ⚪ |
| Uncommon | 25% | x1.2 | 🟢 |
| Rare | 15% | x1.5 | 🔵 |
| Epic | 7% | x2.0 | 🟣 |
| Legendary | 2.5% | x3.0 | 🟡 |
| Mythic | 0.5% | x5.0 | 🔴 |

### 職業
| 職業 | Emoji | 特色 |
|------|-------|------|
| Warrior | ⚔️ | 平衡型 |
| Mage | 🧙 | 高攻擊 |
| Rogue | 🗡️ | 高速度 |
| Archer | 🏹 | 高防禦 |

---

## ⚔️ PvP 戰鬥

### 費用
- 攻擊方支付: 2 Mana（固定）

### 戰鬥規則
三回合制，每回合比較不同屬性：
1. **R1**: 攻方 ATK vs 守方 DEF
2. **R2**: 攻方 DEF vs 守方 SPD
3. **R3**: 攻方 SPD vs 守方 ATK

勝負判定：
- 3:0 → 回合勝
- 2:1 → 險勝
- 1:2 → 守方反殺
- 0:3 → 完敗

### 永久死亡
- 敗者英雄永久死亡
- 死亡記錄上鏈（death_tx）
- 勝者獲得 +1 擊殺數

---

## 📦 鏈上結構

### Inscription Payload

**出生 (birth)**:
```json
{
  "g": "nami_hero",
  "type": "birth",
  "daa": 380012345,
  "class": "warrior",
  "rarity": "rare",
  "atk": 75, "def": 60, "spd": 85,
  "src": "<block_hash>",
  "pay_tx": "<payment_tx_id>"
}
```

**PvP 勝利 (pvp_win)**:
```json
{
  "g": "nami_hero",
  "type": "pvp_win",
  "daa": 380012345,
  "pre_tx": "<previous_tx>",
  "target": 380012300,
  "payment_tx": "<payment_tx>",
  "src": "<battle_block_hash>",
  "kills": 3
}
```

**死亡 (death)**:
```json
{
  "g": "nami_hero",
  "type": "death",
  "daa": 380012300,
  "pre_tx": "<previous_tx>",
  "reason": "pvp",
  "killer": 380012345,
  "battle_tx": "<battle_result_tx>"
}
```

### 交易鏈結構
```
birth_tx ← pvp_win_tx ← pvp_win_tx ← ... (活著)
                                    ↘ death_tx (死亡)
```

每個事件的 `pre_tx` 指向前一個事件，形成可追溯的鏈。

---

## 🔒 驗證機制

### 英雄驗證流程
1. 取得 `source_hash`（儲存在本地 or 從鏈上 birth_tx 讀取）
2. 用 `source_hash` 重新計算屬性
3. 比對本地資料是否一致

### 死亡驗證
1. 從 `death_tx` 讀取 payload
2. 追溯 `battle_tx` 找到戰鬥結果
3. 追溯 `pre_tx` 找到出生記錄
4. 驗證整條鏈的完整性

---

## 🌲 大地之樹

**角色**: 遊戲的中央銀行 + 公證人

**職責**:
- 發放死亡證明（death_tx）
- 管理 Mana 池
- 提供 tKAS 水龍頭

**地址**: `kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m`

---

## 📊 系統限制

| 項目 | 限制 | 原因 |
|------|------|------|
| 每人英雄數 | 10 隻 | 防止囤積 |
| 召喚冷卻 | 10 秒 | 防 spam |
| Queue 容量 | 無限 | 一次服務一人 |

---

## 🔮 未來規劃

### v0.2
- [ ] PoS 獎勵（生存時間 → 分紅）
- [ ] 英雄交易/轉讓
- [ ] 排行榜

### v1.0
- [ ] 版本重設機制
- [ ] birth_tx 復活系統
- [ ] Mainnet 部署

---

## 📝 設計原則

1. **鏈上為真相**: 本地資料可重建，鏈上記錄不可竄改
2. **公平隨機**: 區塊 hash 決定命運，沒有後門
3. **永久稀缺**: 死亡不可逆，讓卡片有價值
4. **可驗證**: 任何人都能驗證任何英雄的真偽

---

*願大地之樹保佑你的英雄！* 🌲✨

---

## v0.5 計劃：爬塔 PvE 系統 🗼

### 核心概念
- 無限層塔，越高越難
- **每日塔**：全服同一個 seed，比誰爬得高！
- 怪物根據「層數 + block hash」生成
- ATB 戰鬥（跟 PvP 一樣）

### 怪物生成
```python
def generate_monster(floor: int, block_hash: str):
    base = floor * 5
    seed = int(block_hash[:8], 16)
    
    atk = base + (seed % 20) - 10
    def_ = base + ((seed >> 8) % 20) - 10
    spd = base + ((seed >> 16) % 20) - 10
    
    # Boss（hash 尾數 = 0）
    if block_hash[-1] == '0':
        atk = int(atk * 1.5)
        
    return Monster(atk, def_, spd, floor)
```

### 費用 & 結果
| 項目 | 費用 | 結果 |
|------|------|------|
| 挑戰 | 10 mana | 勝利→怪殺+1，下一層 / 失敗→回第1層 |

### 獎勵機制
- 每層勝利 → 怪殺 +1
- 每 10 層 → 里程碑寶箱
- 每 50 層 → 稀有獎勵

### 統一積分系統
```
總積分 = PvP殺數×2 + 怪殺數×1

DAA 66666 開獎：按總積分比例分配！
```

### 銘文格式
```json
{
  "type": "pve_clear",
  "hero_id": 381648803,
  "floor": 10,
  "tower_seed": "daily_2026-02-10",
  "monster_hash": "...",
  "payment_tx": "...",
  "source_hash": "..."
}
```

### 指令
| 指令 | 縮寫 | 說明 |
|------|------|------|
| `/nami_tower <ID>` | `/nt` | 查看進度 |
| `/nami_climb <ID> <PIN>` | `/nc` | 挑戰下一層 |
| `/nami_tower_top` | `/ntt` | 排行榜 |

### 特色玩法
- 🎲 **每日塔**：00:00 重置，全服同 seed 競爭
- 👹 **週末 Boss**：每週六超強 Boss，大獎

