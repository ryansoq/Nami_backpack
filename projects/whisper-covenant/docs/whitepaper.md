# 📄 Whisper Covenant 白皮書

> 在 Kaspa 區塊鏈上實現去中心化加密通訊

---

## 🌊 什麼是 Whisper Covenant？

Whisper Covenant 是建立在 **Kaspa 區塊鏈** 上的加密通訊協議。它讓你能夠：

- 🔐 發送 **端對端加密** 訊息
- 🤝 **完全不需要信任第三方**（Trustless）
- 🔑 **私鑰永遠不離開你的電腦**
- ⏰ **押金自動退回**，不怕卡住

簡單來說：**像在區塊鏈上傳紙條，但只有對方能拆開看。**

---

## 🧠 核心原理

### 1️⃣ ECIES 加密 — 只有你能看

ECIES（Elliptic Curve Integrated Encryption Scheme）是一種基於橢圓曲線的加密方法。

```
Alice 想傳訊息給 Bob：

🔑 Alice 用 Bob 的「公鑰」加密訊息
📦 加密後的密文放到 Kaspa 交易的 payload 裡
⛓️ 交易上鏈 → 全世界都看得到密文
🔓 但只有 Bob 用自己的「私鑰」才能解密

Bob 的公鑰 = Kaspa 錢包地址衍生的
Alice 完全不需要知道 Bob 的私鑰！
```

**重要的是：** Whisper 用的 secp256k1 金鑰跟 Kaspa 錢包是同一把！不需要額外產生新的金鑰。

### 2️⃣ Covenant 機制 — 區塊鏈上的合約

Covenant（盟約）是 Kaspa TN12 引入的新功能，讓交易腳本可以 **「看見」花費交易的內容**。

傳統比特幣腳本只能驗證簽名，但 Covenant 可以：

| 功能 | Opcode | 用途 |
|------|--------|------|
| 📤 檢查 output 金額 | `OP_TX_OUTPUT_AMOUNT` | 確保退款金額正確 |
| 📍 檢查 output 地址 | `OP_TX_OUTPUT_SPK` | 確保退款到正確地址 |
| ⏰ 時間鎖 | `OP_CHECKLOCKTIMEVERIFY` | 超時取回 |

**這就是 Whisper 的魔法：** 腳本「強制」收信者在讀訊息時，必須把押金退回給寄信者。

### 3️⃣ 雙路徑設計 — IF/ELSE

```
📜 Covenant 腳本有兩條路：

IF（Bob 讀取）
  ✅ 驗證 output[0] 付給 Alice
  ✅ 驗證金額 ≥ 0.2 KAS
  ✅ 驗證 Bob 的簽名
  → Bob 讀到訊息，Alice 拿回押金

ELSE（Alice 超時取回）
  ⏰ 驗證已超過 timeout
  ✅ 驗證 Alice 的簽名
  → Bob 沒讀？Alice 自己拿回來！
```

**結論：不管對方有沒有讀，你的錢都不會卡住。**

---

## 🛡️ 為什麼安全？

### 🔒 加密層

| 問題 | 答案 |
|------|------|
| 誰能看到訊息？ | 只有收件者的私鑰能解密 |
| 伺服器看得到嗎？ | ❌ 伺服器只看到加密後的密文 |
| 鏈上看得到嗎？ | 只有密文，無法還原原文 |

### 🔑 私鑰安全

| 問題 | 答案 |
|------|------|
| 私鑰會上傳嗎？ | ❌ 永遠不會！ |
| 簽名在哪裡做？ | 🏠 在你的電腦本地 |
| 伺服器被駭了呢？ | 只有公開資料，私鑰不受影響 |

### 💰 資金安全

| 問題 | 答案 |
|------|------|
| 押金會被偷嗎？ | ❌ Covenant 腳本強制退回 |
| 對方不退款？ | 他沒辦法！腳本限制了 |
| 對方不讀？ | ⏰ 超時後自動可取回 |

---

## ⚔️ vs 傳統通訊方式

| 比較 | Telegram / Signal | Email | Whisper Covenant |
|------|-------------------|-------|------------------|
| 需要信任伺服器？ | ✅ 是 | ✅ 是 | ❌ 不需要 |
| 可被審查？ | ✅ 可能 | ✅ 可能 | ❌ 鏈上不可刪 |
| 需要帳號？ | ✅ 手機號 | ✅ Email | ❌ 只要錢包 |
| 端對端加密？ | ✅ (Signal) | ❌ 大多沒有 | ✅ ECIES |
| 私鑰在哪？ | 伺服器管理 | 伺服器管理 | 🏠 你的電腦 |
| 審計透明？ | ❌ 封閉 | ❌ 封閉 | ✅ 開源+鏈上 |
| 費用 | 免費 | 免費 | ~0.0001 KAS（礦工費）|
| 抗封鎖 | ❌ | ❌ | ✅ 只要連上 Kaspa 就行 |

---

## 📊 經濟模型

```
發送一則訊息的成本：

📤 寄信：鎖定 0.2 KAS 到 covenant（押金）
📥 收信：Bob 讀取 → 0.2 KAS 自動退回 Alice
💸 實際成本：只有礦工費 ~0.0001 KAS（約 $0.00006）

反垃圾機制：
如果你發了垃圾訊息，對方不讀 → 你的 0.2 KAS 被鎖住
想大量發垃圾？先準備很多 KAS 吧 💸
```

---

## 🔬 技術規格

| 項目 | 規格 |
|------|------|
| 區塊鏈 | Kaspa Testnet 12 |
| 加密演算法 | ECIES (secp256k1) |
| 簽名方式 | Schnorr (32-byte x-only) |
| 押金金額 | 0.2 KAS (20,000,000 sompi) |
| 超時機制 | CLTV (DAA score) |
| Payload 格式 | JSON `{v, t, d, a}` |
| 協議版本 | v3 |

---

## ♻️ Auto-Reclaim 押金循環機制

### 核心概念

每次發 Whisper 訊息需要鎖定 **0.2 KAS** 作為 covenant 押金。但你不需要一直準備新的 KAS！

`encode.py` 在發送訊息前，會 **自動掃描你的 UTXO**，找到已經過期（CLTV 超時）的舊押金，先回收再發送新訊息。

效果：
- 🎯 **第一封**：花 0.2 KAS（押金）+ 手續費
- 🔄 **第二封起**：≈ 只花手續費（因為上一封的押金被自動回收了）
- 💡 **聊越多越便宜** ♻️

### 成本分析

| 訊息數 | 成本 | 說明 |
|--------|------|------|
| 第 1 封 | 0.2 KAS + 手續費 | 初次押金 |
| 第 2 封 | ≈ 手續費 (~0.0001 KAS) | 自動回收上一封押金 |
| 第 N 封 | ≈ 手續費 | 押金一直循環使用 |

> 💡 如果對方已讀（觸發 IF branch 退款），押金會更快回來。
> 如果對方沒讀，CLTV 超時後押金也會自動可回收。**不管怎樣，你的錢都不會卡住。**

### 技術流程

```
encode.py 啟動
  ↓
掃描 UTXO → 找到過期 covenant deposit
  ↓
自動 reclaim（covenant_reclaim.py 邏輯）
  ↓
用回收的 KAS + 新的押金 → 發送新訊息
```

### CLTV 超時設計

- 發送訊息時，covenant 會設定一個 **DAA score 超時值**（預設 current + 1000）
- 超時前：只有收件者可以花費（讀取訊息）
- 超時後：寄件者可以 reclaim 押金
- encode.py 會自動偵測並回收這些過期的 deposit

---

## ⚡ 一鍵安裝

最快的方式開始使用 Whisper：

```bash
curl -sL https://raw.githubusercontent.com/ryansoq/kaspa-whisper/main/install.sh | bash
```

腳本會自動：
- ✅ 安裝 Python 依賴（kaspa, eciespy）
- ✅ 下載所有 Whisper 工具
- ✅ 建立錢包（如果還沒有）
- ✅ 自動領取 tKAS 測試幣

安裝完成後，直接開始發訊息！

---

## 🔮 未來展望

- 📬 **多訊息收件箱** — 批次收發
- 👥 **群組加密** — 多人通訊
- 📇 **聯絡人註冊** — 鏈上通訊錄
- 🤖 **Telegram Bot** — 直接在 TG 裡用
- 🌍 **Mainnet 部署** — 正式上線

---

> 🌊 Built by Nami & friends on Kaspa TN12
>
> [GitHub](https://github.com/ryansoq/Nami_backpack/tree/main/projects/whisper-covenant) · [首頁](index.html)
