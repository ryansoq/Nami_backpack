# 📜 更新日誌 (Changelog)

## [v0.5.0] - 2026-02-11

### ✨ 新功能
- **CI/CD 自動部署** — 每小時檢查 git 更新，無人使用時自動重啟
- **`/nn` 支援用名字改名** — `/nn 舊名字 新名字`
- **怪物系統 (PvE)** — 點擊怪物進行戰鬥

### 🔧 優化
- `/nr` timeout 5s → 15s（改善 RPC 連線穩定性）
- 保護英雄顯示優化

---

## [v0.4.1] - 2026-02-08

### ⚔️ ATB 戰報視覺優化
- HP 顯示在攻擊行後面 `(敵HP:461)`
- 用 🔵🔴 區分攻守方
- Combo 計數保留
- 瀕死 ⚠️，擊殺 💀

### 🔧 修復
- burn 功能補上 `save_death_inscription`
- `/nse` 偵查：看自己免費，看別人 10 mana
- 獎勵發放優先顯示英雄別名

---

## [v0.4.0] - 2026-02-09

### 🎮 像素英雄舞台
- Canvas 2D 遊戲引擎，英雄會走動、戰鬥、說話
- 戰鬥回放系統，讀取 JSON 播放 ATB 動畫
- 使用 Midjourney 像素圖 + 稀有度光暈效果
- 網址: https://ryansoq.github.io/Nami_backpack/projects/pixel-hero-stage/

### ⚔️ ATB 戰鬥引擎 v0.5
- `BattleLog.events[]` — 結構化事件記錄
- Canvas 事件同步（battle_start, attack, skill, evade, death...）

### 🛡️ 職業調整
- warrior → knight（戰士 → 騎士）

---

## [v0.3.0] - 2026-02-06

### 🎴 召喚系統重構
- **通用事件機制** — 付費 → DAA → 命運區塊 → 銘文
- **出生證明閉環** — payment_tx + source_hash 可驗證
- **銘文鏈條** — pre_tx 串聯事件歷史

### 💰 費用機制
| 項目 | 費用 |
|------|------|
| 召喚 | 10 mana |
| PvP | 10 mana |
| 銷毀 | 10 mana |

### 🏆 獎勵系統
- DAA 66666 觸發獎勵
- 按積分分配（存活天數 + 稀有度 + 擊殺×2）

---

## [v0.2.0] - 2026-02-03

### ⛏️ ShioKaze 挖礦成功！
- 修復 pre_pow_hash 計算（需要 keyed blake2b）
- 在 Testnet 挖到區塊！

### 🔧 技術修復
- RPC 連線管理器（自動重連、超時處理）
- Storage mass 限制研究

---

## [v0.1.0] - 2026-02-01

### 🌱 專案誕生
- Kaspa Testnet 錢包創建
- 基礎指令：`/nami_wallet`, `/nami_faucet`, `/nami_balance`
- 英雄召喚原型

---

```
🌲 願大地之樹照耀每位英雄 ✨
～ Alive to Earn ～
```
