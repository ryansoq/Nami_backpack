# Changelog

娜米的英雄奇幻冒險 - 版本更新記錄

---

## v0.3.0 (2026-02-07)

### 🔒 安全機制

- **管理員系統**
  - `ADMIN_IDS` 設定管理員列表
  - `is_admin()` 檢查管理員權限

- **維護模式**
  - `MAINTENANCE_MODE` 全局開關
  - 開啟時只有管理員能執行操作
  - 其他用戶收到「🛠️ 系統維護中」提示

- **錢包鎖**
  - `WALLET_LOCK` asyncio.Lock 防止 UTXO 衝突
  - `with_wallet_lock()` 確保同時只有一個錢包操作

### 🛠️ 管理員指令

- `/nami_admin_maintenance [on|off]` - 開關維護模式
- `/nami_admin_status` - 查看系統狀態
  - 維護模式狀態
  - 錢包鎖狀態
  - 排隊人數
  - 英雄統計、獎池

### 🛡️ 保護機制

- `/nami_hero_protect` (`/npp`) - 英雄保護（規劃中）

### 🔧 改進

- `hero_summon`, `hero_attack`, `hero_burn` 加入維護模式檢查
- 排隊系統 (`tree_queue`) 穩定性提升

---

## v0.2.0 (2026-02-06)

### 🌳 大地之樹排隊系統

- Queue 機制：指令加鎖，一次服務一人
- 其他人排隊等待，收到 ⌛️ 提示
- 防止並發 UTXO 衝突

### ⚔️ PvP 完整戰報

- 群聊公告顯示完整戰鬥詳情
- 三回合對決、雙方屬性、勝負結果

### 🦸 英雄管理

- 每人最多 10 隻存活英雄
- 顯示英雄存活時間（⏳1d2h）
- 超限時引導玩家燒卡

### 📝 指令縮寫

| 完整指令 | 縮寫 |
|---------|------|
| /nami_hero | /nh |
| /nami_heroes | /nhs |
| /nami_pvp | /np |
| /nami_burn | /nb |
| /nami_hero_info | /ni |
| /nami_verify | /nv |
| /nami_name | /nn |
| /nami_next_reward | /nr |
| /nami_game_status | /ns |

---

## v0.1.0 (2026-02-05)

### 🎮 初始版本

- 基礎召喚系統（10 mana）
- 4 職業 × 4 稀有度
- PvP 戰鬥（2-8 mana）
- 敗者永久死亡
- 鏈上銘文驗證
