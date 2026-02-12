# 🏗️ Bot 架構改進計劃

*基於 Kaspa WASM SDK (M.S.) 的 dApp 架構思考*

## 📊 現況分析

### 目前架構
```
┌─────────────────────────────────────────────────────┐
│                  Telegram Bot                        │
│                 (Python + aiogram)                   │
├─────────────────────────────────────────────────────┤
│              hero_commands.py                        │
│           unified_wallet.py                          │
│            rpc_manager.py                            │
├─────────────────────────────────────────────────────┤
│              Python kaspa SDK                        │
│            (gRPC / wRPC 連線)                        │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │   kaspad 節點   │
              │  (port 17210)   │
              └─────────────────┘
```

### 目前痛點

| 問題 | 影響 | 嚴重度 |
|------|------|--------|
| gRPC 靜默斷線 | 需要重連機制、任務失敗 | ⚠️ 中 |
| 每次操作建新連線 | 延遲、資源浪費 | ⚠️ 中 |
| JSON-RPC 編碼 | 較慢、較大 | 🔵 低 |
| 單執行緒 Queue | 高併發時塞車 | ⚠️ 中 |
| 輪詢 DAA | 浪費資源 | 🔵 低 |

---

## 💡 改進方案

### 方案 A：漸進式優化（短期）

保持 Python 架構，優化連線管理：

```python
# 1. 改用 WebSocket 長連線
RPC_URL = "ws://127.0.0.1:17210"  # ✅ 已經是 wRPC

# 2. 啟用 Borsh 編碼（如果 Python SDK 支援）
# 二進位編碼比 JSON 快 3-5 倍

# 3. 訂閱模式取代輪詢
async def subscribe_new_blocks():
    """訂閱新區塊，不用輪詢 DAA"""
    async with get_rpc_client() as client:
        async for block in client.subscribe_blocks():
            await process_block(block)
```

**優點**：改動小、風險低
**缺點**：受限於 Python SDK 功能

---

### 方案 B：混合架構（中期）⭐ 推薦

**核心思路**：Kaspa 操作移到 Node.js 服務，Telegram bot 只管 UI

```
┌─────────────────┐         ┌──────────────────────┐
│  Telegram Bot   │◄───────►│   Kaspa Service      │
│    (Python)     │  HTTP/  │     (Node.js)        │
│                 │  IPC    │  WASM SDK + Borsh    │
└─────────────────┘         └──────────────────────┘
                                     │
                                     │ WebSocket
                                     │ (長連線)
                                     ▼
                            ┌─────────────────┐
                            │   kaspad 節點   │
                            └─────────────────┘
```

**Node.js Kaspa Service 職責**：
- 維持 WebSocket 長連線
- 處理所有 RPC 呼叫
- 訂閱區塊/交易事件
- 交易簽名與廣播
- 錢包操作

**Python Bot 職責**：
- Telegram 訊息處理
- 遊戲邏輯
- 呼叫 Kaspa Service API

**優點**：
- 利用 WASM SDK 的高效能
- 連線穩定（官方維護的 SDK）
- 職責分離、好維護
- 未來可獨立擴展

**缺點**：
- 需要多學 Node.js
- 兩個服務的運維

---

### 方案 C：全面重構（長期）

整個 bot 用 Node.js/TypeScript 重寫：

```typescript
// 用 grammy 或 telegraf 處理 Telegram
import { Bot } from "grammy";
import { RpcClient, Encoding } from "kaspa-wasm";

const bot = new Bot("BOT_TOKEN");
const rpc = new RpcClient({
    url: "127.0.0.1:17210",
    encoding: Encoding.Borsh,
    network: "testnet-10"
});

// 訂閱新區塊
rpc.subscribeVirtualDaaScoreChanged(async (score) => {
    // 自動觸發獎勵發放等邏輯
});
```

**優點**：
- 最佳效能
- 統一技術棧
- 完整利用 SDK 功能

**缺點**：
- 重寫成本高
- 學習曲線

---

## 🎯 建議路線

```
現在 ─────► 方案 A ─────► 方案 B ─────► 方案 C (可選)
            (1-2 週)      (2-4 週)       (未來)
```

### 短期（方案 A）

1. **確認 Python SDK 是否支援訂閱**
   ```python
   # 測試 subscribe 功能
   client.subscribe_virtual_daa_score_changed()
   ```

2. **優化重連機制**
   - 指數退避重試
   - 健康檢查更頻繁

3. **加入連線狀態監控**
   ```python
   # 記錄連線統計
   stats = {
       "total_requests": 0,
       "failed_requests": 0,
       "reconnects": 0,
       "avg_latency_ms": 0
   }
   ```

### 中期（方案 B）

1. **建立 Node.js Kaspa Service**
   ```
   kaspa-service/
   ├── src/
   │   ├── rpc.ts          # RPC 連線管理
   │   ├── wallet.ts       # 錢包操作
   │   ├── subscription.ts # 事件訂閱
   │   └── api.ts          # HTTP API for Python bot
   ├── package.json
   └── tsconfig.json
   ```

2. **定義 API 介面**
   ```
   POST /api/balance/:address
   POST /api/send
   POST /api/inscription
   GET  /api/daa
   WS   /events  (推送新區塊等)
   ```

3. **Python bot 改為呼叫 API**

---

## 📝 補充想法

### 事件驅動優化

目前獎勵發放靠輪詢 DAA，可以改成：

```typescript
// Node.js 服務訂閱 DAA 變化
rpc.subscribeVirtualDaaScoreChanged(async (newDaa) => {
    if (shouldTriggerReward(newDaa)) {
        // 直接觸發，不用輪詢
        await triggerReward();
    }
});
```

### 交易池監控

```typescript
// 監控待確認交易
rpc.subscribeUtxosChanged(async (event) => {
    // 玩家付款即時偵測
    // 不用等區塊確認
});
```

### 連線池

高併發時，可以用多個 RPC 連線：

```typescript
const pool = new RpcPool({
    size: 3,           // 3 個連線
    loadBalance: true  // 負載均衡
});
```

---

## 🔬 待研究

1. [ ] Python kaspa SDK 是否支援訂閱？
2. [ ] WASM SDK 的 Node.js 範例實測
3. [ ] Python ↔ Node.js IPC 效能比較 (HTTP vs Unix Socket)
4. [ ] 遊戲邏輯移到 Node.js 的可行性

---

*by Nami 🌊 | 2026-02-12*
