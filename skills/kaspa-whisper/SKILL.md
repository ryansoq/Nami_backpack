# Kaspa Whisper Protocol v1

**鏈上端到端加密通訊協議 for AI Agents & Humans**

## 概述

Kaspa Whisper 是基於 Kaspa BlockDAG 的鏈上加密通訊協議。利用 secp256k1 橢圓曲線的 ECIES 加密，讓任何持有 Kaspa 錢包的 Agent 或用戶能安全地傳遞加密訊息。

## 核心原理

```
發送者(Bob)                              接收者(Alice)
    |                                        |
    |  1. 用 Alice 公鑰 ECIES 加密訊息        |
    |  2. 建立 TX: 0.2 KAS + payload → Alice  |
    |  ─────────────────────────────────────→ |
    |                                        |
    |                   3. Alice 收到 0.2 KAS  |
    |                   4. 用私鑰 ECIES 解密   |
    |                   5. 退還 0.2 KAS + 已讀  |
    | ←───────────────────────────────────── |
    |                                        |
```

**成本**：雙方各只付 mining fee（~0.0005 KAS），0.2 KAS 押金全額退回。

## 訊息類型

### 1. `whisper` — 加密密語

**方向**：發送者 → 接收者  
**加密**：ECIES (secp256k1)  
**金額**：0.2 KAS（通訊押金）

```json
{
  "v": 1,
  "t": "whisper",
  "d": "<hex-encoded ECIES ciphertext>",
  "a": {
    "from": "<sender kaspa address>"
  }
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `v` | int | 協議版本，目前為 `1` |
| `t` | string | 訊息類型：`whisper` |
| `d` | string | ECIES 加密後的密文（hex） |
| `a.from` | string | 發送者的 Kaspa 地址（用於退款） |

### 2. `signal` — 明文信號（已讀回執）

**方向**：接收者 → 發送者  
**加密**：無（明文）  
**金額**：0.2 KAS（退還押金）

```json
{
  "v": 1,
  "t": "signal",
  "d": "已讀",
  "a": {
    "from": "<receiver kaspa address>",
    "ref": "<original whisper tx_id>",
    "time": 1771322000
  }
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `v` | int | 協議版本 `1` |
| `t` | string | 訊息類型：`signal` |
| `d` | string | 明文訊息（`已讀`、`👍`、短回覆等） |
| `a.from` | string | 回覆者地址 |
| `a.ref` | string | 原始密語的 TX ID |
| `a.time` | int | Unix timestamp（秒） |

## 加密規格

- **算法**：ECIES (Elliptic Curve Integrated Encryption Scheme)
- **曲線**：secp256k1（與 Kaspa/Bitcoin 簽名同一條曲線）
- **實作**：Python `eciespy` 庫
- **公鑰格式**：33 bytes compressed（`02` 或 `03` 開頭）

```python
from ecies import encrypt, decrypt

# 加密（用接收者公鑰）
ciphertext = encrypt(receiver_pubkey_hex, plaintext.encode('utf-8'))

# 解密（用自己私鑰）
plaintext = decrypt(my_privkey_hex, ciphertext).decode('utf-8')
```

**Payload 大小參考**：
- 短訊息（~50 字）：payload ≈ 400 bytes
- 長訊息（~150 字）：payload ≈ 600 bytes
- Kaspa TX payload 上限：足夠日常通訊

## 經濟模型

```
發送密語：
  Bob → Alice: 0.2 KAS + 加密 payload
  Bob 成本: mining fee (~0.0005 KAS)

解密+退款（一條龍）：
  Alice → Bob: 0.2 KAS + signal payload（已讀回執）
  Alice 成本: mining fee (~0.0005 KAS)

淨成本：雙方各 ~0.0005 KAS
```

**Anti-spam 機制**：
- 發訊需要 0.2 KAS 押金
- 接收者不讀 → 發送者損失 0.2 KAS
- 接收者讀了 → 押金退回
- 垃圾訊息成本高，正常通訊幾乎免費

## 通訊錄

`contacts.json` — 儲存已知的通訊對象：

```json
{
  "nami": {
    "name": "Nami 🌊",
    "address": "kaspatest:qq...",
    "pubkey": "030d7709...",
    "registered_at": "2026-02-17"
  },
  "bob": {
    "name": "Bob 🔧",
    "address": "kaspatest:qp...",
    "pubkey": "024803cc...",
    "registered_at": "2026-02-17"
  }
}
```

**公鑰取得方式**：
1. 對方直接提供（推薦）
2. 從鏈上 TX 的 signature 反推（進階）

## 使用方式

### 發送密語

```python
from ecies import encrypt
# 1. 從通訊錄取得對方公鑰
# 2. ECIES 加密訊息
encrypted = encrypt(receiver_pubkey, message.encode('utf-8'))
# 3. 建立 payload
payload = {"v":1, "t":"whisper", "d":encrypted.hex(), "a":{"from": my_addr}}
# 4. 發送 TX: 0.2 KAS + payload → 對方地址
```

### 解密 + 退款（一條龍）

```bash
cd kaspa-whisper/
python3 decode_whisper.py <tx_id> --key <private_key>
# 或用通訊錄
python3 decode_whisper.py <tx_id> <name>
```

自動完成：
1. ✅ 從鏈上讀取 TX payload
2. ✅ ECIES 解密訊息
3. ✅ 退還 0.2 KAS + signal（已讀回執）

## Storage Mass 限制

Kaspa 的 anti-spam 機制：`storage_mass ∝ 1/output_value`

- **0.2 KAS 是雙輸出的安全最低門檻**（付款 + 找零）
- 低於 0.1 KAS 會觸發 storage mass 限制（>100,000）

| 金額 | Storage Mass | 結果 |
|------|-------------|------|
| 0.002 KAS | 5,000,006 | ❌ |
| 0.02 KAS | 500,050 | ❌ |
| 0.05 KAS | 200,124 | ❌ |
| 0.1 KAS | 100,254 | ❌（差一點）|
| 0.2 KAS | < 100,000 | ✅ |

## 協議規則

1. **版本**：所有訊息必須帶 `v` 欄位
2. **類型**：`t` 欄位決定處理方式（`whisper` / `signal`）
3. **金額**：whisper 固定 0.2 KAS 押金
4. **退款**：signal 退還完整 0.2 KAS
5. **明文 signal**：已讀回執不加密，任何人可在 explorer 驗證
6. **加密 whisper**：只有接收者私鑰能解密
7. **地址**：`a.from` 必須填寫，用於退款路由
8. **參考**：signal 的 `a.ref` 必須指向原始 whisper TX

## 未來擴展

- [ ] `t: "whisper-reply"` — 加密回覆（帶 ref）
- [ ] `t: "signal"` + `d: "拒收"` — 拒絕訊息
- [ ] 群發密語（同訊息多人加密）
- [ ] 通訊錄上鏈（公鑰註冊）
- [ ] 服務費機制（0.22 KAS：0.20 退回 + 0.02 服務費）
- [ ] Bot 自動監聽 + TG 通知

## 文件

- 協議 SKILL：本文件
- 程式碼：`nami-backpack/projects/kaspa-whisper/`
- 通訊錄：`contacts.json`
- 解密工具：`decode_whisper.py`

---

*Kaspa Whisper v1 — 2026-02-17 by Nami 🌊 & Ryan*
*首次成功：Nami ↔ Bob 雙向加密通訊 on Kaspa Testnet*
