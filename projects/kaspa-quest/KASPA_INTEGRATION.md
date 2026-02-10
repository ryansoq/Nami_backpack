# KaspaQuest - BrowserQuest + Kaspa 整合計劃

## 專案目標
把經典的 BrowserQuest 改造成 Kaspa 區塊鏈遊戲！

## 計劃功能

### Phase 1: 基礎整合
- [ ] Kaspa 錢包登入（用錢包地址當玩家 ID）
- [ ] 打怪獲得 tKAS 獎勵
- [ ] 顯示玩家餘額

### Phase 2: 進階功能
- [ ] 裝備 NFT（稀有掉落上鏈）
- [ ] 玩家交易（P2P 換裝）
- [ ] PvP 賭注（贏家拿走賭注）

### Phase 3: 經濟系統
- [ ] 商店系統（用 tKAS 買裝備）
- [ ] 任務獎勵
- [ ] 公會金庫

## 技術架構

```
┌─────────────────┐
│  BrowserQuest   │
│  Client (HTML5) │
└────────┬────────┘
         │ WebSocket
         ▼
┌─────────────────┐      ┌─────────────┐
│  BrowserQuest   │ ───► │   Kaspa     │
│  Server (Node)  │      │   Node RPC  │
└─────────────────┘      └─────────────┘
```

## 修改清單

### Client 修改
1. `client/js/game.js` - 加入錢包連接
2. `client/js/player.js` - 顯示餘額
3. `client/index.html` - 錢包 UI

### Server 修改
1. `server/js/player.js` - 驗證錢包簽名
2. `server/js/mob.js` - 死亡時發送獎勵
3. 新增 `server/js/kaspa.js` - Kaspa RPC 連接

## 參考資源
- BrowserQuest 原版: https://github.com/mozilla/BrowserQuest
- Kaspa JS SDK: `npm install kaspa`
- Kaspa RPC: ws://localhost:17210

## 授權
- 原版: MPL 2.0 (Code) + CC-BY-SA 3.0 (Content)
- 修改版: 同上
