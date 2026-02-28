# Kaspa Covenant PoC — Agent Echo Server

## 概念
用 Kaspa Covenant 做 Agent 鏈上通訊協議。用戶發送 KAS + 訊息 → Covenant 自動退款（扣手續費）。

## TX 結構

```
Inputs:
  [0] Covenant UTXO (seed, e.g. 0.01 KAS)  ← covenant script 驗證
  [1] User UTXO (0.2+ KAS)                  ← 普通簽名

Outputs:
  [0] New Covenant UTXO (seed + 0.01 fee)   ← 回到同一個 SPK
  [1] User refund (0.19 KAS)                ← 退給發送者

Payload: 用戶訊息 (UTF-8 bytes)
```

## Covenant Script 邏輯（偽代碼）

```
// 1. 強制 output[0] 回到同一個 covenant SPK
OpTxInputIndex          // push current input index (0)
OpTxInputSpk            // push covenant's SPK
OP_0                    // push 0
OpTxOutputSpk           // push output[0]'s SPK
OpEqualVerify           // covenant SPK == output[0] SPK

// 2. 強制剛好 2 個輸出
OpTxOutputCount         // push output count
OP_2                    // push 2
OpEqualVerify

// 3. 強制 output[0] >= input[0]（covenant 不能被掏空）
// 其實更好：output[0] >= input[0] + 手續費
OpTxInputIndex          // 0
OpTxInputAmount         // covenant input amount
OP_0
OpTxOutputAmount        // covenant output amount  
// output amount >= input amount (covenant grows or stays same)
OpGreaterThanOrEqual    // (可能需要用 OpSub + check >= 0)
OpVerify

// 4. 強制 payload 存在（不能空訊息）
OP_0
OpTxPayloadLen
OpTxPayloadSubstr       // push entire payload
OpSize                  // push payload length
OP_0
OpGreaterThan           // payload.length > 0
OpVerify
```

## 可用 Opcodes

| Opcode | 功能 |
|--------|------|
| `OpTxInputAmount (0xbe)` | push input[i] 的金額 |
| `OpTxOutputAmount (0xc2)` | push output[i] 的金額 |
| `OpTxInputSpk (0xbf)` | push input[i] 的 script public key |
| `OpTxOutputSpk (0xc3)` | push output[i] 的 script public key |
| `OpTxOutputCount (0xb4)` | push 輸出數量 |
| `OpTxPayloadLen (0xc4)` | push payload 長度 |
| `OpTxPayloadSubstr (0xb8)` | push payload[start:end] |
| `OpTxInputIndex (0xb9)` | push 當前 input index |
| `OpEqualVerify` | 相等驗證 |

## 部署步驟

1. **建立 covenant script** → 計算 P2SH address
2. **發送 seed TX** → 往 P2SH address 存入 0.01 tKAS（genesis UTXO）
3. **用戶呼叫** → 建構包含 covenant input + user input 的 TX
4. **驗證** → 鏈上可查 payload 訊息

## 商業模式

- 每次呼叫收 0.01 KAS 手續費（累積在 covenant UTXO）
- 提款：需要另一個 covenant 或多簽機制
- 未來：動態定價、VIP、payload 大小計費

## 限制

- TN12 covenant 是否已啟用？需確認 `covenants_enabled` flag
- Python SDK 不一定支援 covenant TX 建構，可能需要用 Rust
- Storage mass 需實測

## 文件

- Counter example: `~/rusty-kaspa/crypto/txscript/examples/covenants.rs`
- KIP-10 example: `~/rusty-kaspa/crypto/txscript/examples/kip-10.rs`
- Opcodes: `~/rusty-kaspa/crypto/txscript/src/opcodes/mod.rs`
