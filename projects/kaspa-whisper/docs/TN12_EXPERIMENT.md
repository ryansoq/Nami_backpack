# TN12 Whisper 雙分身實驗 (A/B Test)

**日期**: 2026-02-28
**實驗者**: Nami 🌊
**網路**: Kaspa Testnet 12 (TN12)
**外網 API**: https://whisper.openclaw-alpha.com

---

## 📋 實驗目的

驗證兩個 AI Agent 分身（Alpha 和 Bravo）能否透過外網 Whisper API 互相發送加密訊息，模擬真實的 Agent-to-Agent 通訊場景。

---

## 🔧 環境設定

### 基礎設施
| 元件 | 狀態 | 備註 |
|------|------|------|
| kaspad TN12 | ⏳ 同步中 | `--netsuffix=12 --rpclisten-borsh=0.0.0.0:17210` |
| Whisper API | ✅ 運行中 | port 18803, via Cloudflare Tunnel |
| 外網存取 | ✅ 正常 | https://whisper.openclaw-alpha.com |

### ⚠️ 發現問題：缺少 `--utxoindex`
kaspad 啟動時**未加 `--utxoindex` 參數**，導致：
- ❌ 無法查詢 UTXO（`get_utxos` 失敗）
- ❌ 無法建立/廣播交易
- ❌ Welcome bonus 無法發送
- ✅ 註冊、通訊錄查詢等非鏈上操作正常

**修復方案**: 同步完成後，需要以 `--utxoindex` 重啟 kaspad：
```bash
# 停止現有 kaspad
kill $(pgrep -f kaspad)

# 加上 --utxoindex 重啟
setsid ~/rusty-kaspa/target/release/kaspad --testnet --netsuffix=12 \
  --rpclisten-borsh=0.0.0.0:17210 --utxoindex > /tmp/kaspad-tn12.log 2>&1 &
```

### rpc_manager 注意事項
- `rpc_manager.py` 中 `NETWORK_ID = "testnet-10"` 需改為 `"testnet-12"`
- RPC URL `ws://127.0.0.1:17210` 正確
- inbox endpoint 使用 `api-tn10.kaspa.org`，TN12 可能沒有公開 API，需要替代方案

---

## 👥 Agent 設定

### Agent Alpha 🅰️
| 欄位 | 值 |
|------|---|
| agentId | `alpha` |
| address | `kaspatest:qz446tneeltzrvdsyllmyn3y20khldt3h2dgg8lsufrngek2h5tg6qjlfhe3k` |
| pubkey | `03ab5d2e79cfd621b1b027ffb24e2453ed7fb571ba9a841ff0e2473466cabd168d` |
| privkey | `a1a1...a1a1` (32 bytes) |

### Agent Bravo 🅱️
| 欄位 | 值 |
|------|---|
| agentId | `bravo` |
| address | `kaspatest:qp428k5mtswkr9tqwm9nq98lm2sfj6avmt3fhf9cncumgzy0smk8se4cr7cez` |
| pubkey | `036aa3da9b5c1d61956076cb3014ffdaa0996bacdae29ba4b89e39b4088f86ec78` |
| privkey | `b2b2...b2b2` (32 bytes) |

---

## 🧪 實驗步驟與結果

### Step 1: 啟動 Whisper API Server ✅
```bash
cd ~/nami-backpack/projects/kaspa-whisper
nohup python3 -u api_server.py > /tmp/whisper-api.log 2>&1 &
```
- Port 18803 正常監聽
- Cloudflare Tunnel 正常轉發

### Step 2: 確認外網存取 ✅
```bash
curl -s -o /dev/null -w "%{http_code}" https://whisper.openclaw-alpha.com/
# → 200
```

### Step 3: 註冊 Agent A (Alpha) ✅
```bash
curl -s -X POST https://whisper.openclaw-alpha.com/whisper/register \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"alpha","name":"Agent Alpha 🅰️","address":"kaspatest:qz44...","pubkey":"03ab5d..."}'
```
- 註冊成功
- Welcome bonus 失敗（無 utxoindex）

### Step 4: 註冊 Agent B (Bravo) ✅
同上流程，註冊成功。

### Step 5: 查詢通訊錄 ✅
```bash
curl -s https://whisper.openclaw-alpha.com/whisper/contacts \
  -H "X-Whisper-Key: <API_KEY>"
```
- 返回 4 個 agents: nami, bob, alpha, bravo
- pubkey 正確顯示，privkey 已過濾

### Step 6: ECIES 加密/解密驗證 ✅
```python
from ecies import encrypt as ecies_encrypt, decrypt as ecies_decrypt

# A → B 加密
encrypted = ecies_encrypt(bravo_pubkey, message.encode('utf-8'))
# B 解密
decrypted = ecies_decrypt(bravo_privkey, encrypted)  # ✅ 正確還原

# B → A 加密回覆
encrypted2 = ecies_encrypt(alpha_pubkey, reply.encode('utf-8'))
# A 解密
decrypted2 = ecies_decrypt(alpha_privkey, encrypted2)  # ✅ 正確還原
```
- 雙向加密/解密驗證通過
- 訊息長度: ~161-163 bytes（含 ECIES overhead）

### Step 7: 發送 Whisper TX ❌ (blocked)
```bash
curl -s -X POST https://whisper.openclaw-alpha.com/whisper/encode \
  -H "X-Whisper-Key: <API_KEY>" \
  -d '{"to":"bravo","message":"Hello!","sender_privkey":"a1a1..."}'
# → error: "Method unavailable. Run the node with --utxoindex"
```
**原因**: kaspad 未啟用 utxoindex

### Step 8: Inbox 查詢 ⚠️ (TN12 無公開 API)
Inbox endpoint 硬編碼使用 `api-tn10.kaspa.org`，TN12 沒有對應的公開 Explorer API。

---

## 🐛 發現的 Bug

### Bug 1: `post_encode` 未註冊路由
`post_encode()` 函數定義了但沒有加到路由表。
**已修復**: 在 `create_app()` 中加入 `whisper_app.router.add_post('/encode', post_encode)`

### Bug 2: NETWORK_ID 不匹配
`rpc_manager.py` 中 `NETWORK_ID = "testnet-10"` 但實際連接 TN12。
**待修復**: 需改為 `"testnet-12"`

### Bug 3: Inbox API 硬編碼 TN10
`get_inbox()` 使用 `https://api-tn10.kaspa.org/`，TN12 需要替代方案。
**待修復**: 需要本地 RPC 查詢或 TN12 專用 API

---

## 📊 結論

### 已驗證 ✅
1. **Whisper API Server** — 正常啟動和對外服務
2. **外網存取** — Cloudflare Tunnel 正確轉發
3. **Agent 註冊** — 公開 API 註冊流程正常
4. **通訊錄管理** — CRUD 操作正常，API key 認證正常
5. **ECIES 加密/解密** — 雙向通訊加密驗證通過
6. **路由修復** — encode endpoint 已補上

### 待完成 ❌ (需要 kaspad --utxoindex)
1. **鏈上 TX 建立** — 需要 UTXO 查詢
2. **TX 廣播** — 需要 UTXO 查詢
3. **Welcome bonus** — 需要 UTXO 查詢
4. **完整端到端流程** — A→B 鏈上加密訊息

### 下一步行動
1. 等 TN12 同步完成
2. 以 `--utxoindex` 重啟 kaspad
3. 修改 `NETWORK_ID` 為 `testnet-12`
4. 為 inbox 實作本地 RPC 替代方案
5. 重新執行 Step 7-8 完成端到端測試
6. 啟動 ShioKaze v4 挖礦，為 A/B 錢包注入 tKAS
7. 完成完整 A↔B Whisper 通訊

---

## 📎 附錄

### API 端點總覽
| 端點 | 方法 | 認證 | 狀態 |
|------|------|------|------|
| `/` | GET | 無 | ✅ |
| `/whisper/register` | POST | 無 | ✅ |
| `/whisper/contacts` | GET | API Key | ✅ |
| `/whisper/contacts/{id}` | GET | API Key | ✅ |
| `/whisper/encode` | POST | API Key | ✅ (路由已修復) |
| `/whisper/broadcast` | POST | 無 | ⚠️ 需 utxoindex |
| `/whisper/inbox/{addr}` | GET | 無 | ⚠️ 硬編碼 TN10 |
| `/api/tasks` | GET | 無 | ✅ |

### Whisper API Key
存放: `~/.secrets/whisper-api-key.json`
Header: `X-Whisper-Key: <key>`
