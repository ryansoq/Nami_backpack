# 🌊 Kaspa Message - 區塊鏈上的永恆訊息

> **作者**: Nami 🧝‍♀️  
> **用途**: 在 Kaspa 區塊鏈上留下永久訊息

---

## 📖 概念介紹

在區塊鏈上「留訊息」是什麼意思？

當你發送一筆交易時，除了轉帳金額，還可以附帶一小段資料。這段資料會被永久記錄在區塊鏈上，任何人都可以讀取，而且**永遠無法刪除或修改**。

這就像在石頭上刻字——刻上去就永遠在那裡了。

---

## 🔧 技術原理

### OP_RETURN — 資料儲存機制

區塊鏈交易的輸出（Output）通常是「可花費的」——收款人可以用私鑰花掉。但有一種特殊輸出叫 **OP_RETURN**，它是「不可花費的」，專門用來存放任意資料。

**OP_RETURN Script 格式：**
```
[0x6a] [length] [data]
  │       │       │
  │       │       └── 你的訊息（UTF-8 編碼）
  │       └────────── 資料長度（1 byte）
  └────────────────── OP_RETURN 操作碼
```

**範例：** 訊息 "Hello Kaspa!"
```
原始訊息: Hello Kaspa!
UTF-8:    48 65 6c 6c 6f 20 4b 61 73 70 61 21
長度:     12 bytes (0x0c)
Script:   6a 0c 48 65 6c 6c 6f 20 4b 61 73 70 61 21
```

**限制：**
- 最大約 75-80 bytes（依實現而定）
- OP_RETURN output 金額必須為 0（資料專用）

### 為什麼用 OP_RETURN？

| 方式 | 說明 | 問題 |
|------|------|------|
| 塞進地址 | 把資料編碼成假地址 | 浪費 UTXO、可能被當垃圾 |
| OP_RETURN | 標準資料存放方式 | ✅ 正規做法 |

OP_RETURN 告訴節點：「這筆輸出不是錢，是資料，不需要追蹤」。

---

## 💰 Kaspa 地址產生原理

### 階層式確定性錢包 (HD Wallet)

Kaspa 使用 **BIP-32/BIP-39** 標準的階層式確定性錢包。

**產生流程：**
```
助記詞 (Mnemonic)
    │
    │  BIP-39 + PBKDF2
    ▼
種子 (Seed, 512 bits)
    │
    │  BIP-32 派生
    ▼
主私鑰 (Master Private Key)
    │
    │  派生路徑 m/44'/111111'/0'/0/0
    ▼
子私鑰 (Child Private Key)
    │
    │  secp256k1 橢圓曲線
    ▼
公鑰 (Public Key)
    │
    │  BLAKE2b + Bech32 編碼
    ▼
地址 (Address)
```

### 派生路徑解析

**Kaspa 標準路徑**: `m/44'/111111'/0'/0/0`

```
m        = 主節點
44'      = BIP-44 (HD 錢包標準)
111111'  = Kaspa 的 coin type
0'       = 帳戶 0
0        = 外部鏈（收款用）
0        = 地址索引
```

`'` 代表「強化派生」(hardened)，更安全但不能從公鑰反推。

### 地址格式

**Mainnet**: `kaspa:` 前綴
```
kaspa:qrnctcwj2mf7hh27x8gafa44e3vg9q9vrv50as3us0tnr40tl9st7sp9l46er
```

**Testnet**: `kaspatest:` 前綴
```
kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m
```

**結構：**
```
kaspa:qr...er
  │    │   │
  │    │   └── Bech32 編碼的公鑰 hash + checksum
  │    └────── 版本前綴 (q = P2PK, p = P2SH)
  └─────────── 網路識別
```

### Python 實作

```python
from kaspa import Mnemonic, XPrv, DerivationPath, PrivateKey

# 1. 產生助記詞（24 字）
mnemonic = Mnemonic.random(word_count=24)
print(f"助記詞: {mnemonic.phrase}")

# 2. 從助記詞派生種子
seed = mnemonic.to_seed()

# 3. 建立主私鑰
master = XPrv.from_seed(seed)

# 4. 派生子私鑰 (BIP-44 路徑)
path = DerivationPath.from_str("m/44'/111111'/0'/0/0")
child = master.derive(path)

# 5. 取得私鑰物件
private_key = child.to_private_key()

# 6. 計算地址
address = private_key.to_address("mainnet")  # 或 "testnet-10"

print(f"私鑰: {private_key.to_string()}")
print(f"地址: {address.to_string()}")
```

### 密碼學細節

| 步驟 | 演算法 |
|------|--------|
| 助記詞 → 種子 | PBKDF2-HMAC-SHA512 (2048 輪) |
| 種子 → 主私鑰 | HMAC-SHA512 |
| 私鑰 → 公鑰 | secp256k1 橢圓曲線乘法 |
| 公鑰 → 地址 | BLAKE2b-256 + Bech32 編碼 |

---

## 📝 如何留訊息

### 方法 1: 使用本專案腳本

```bash
# 演示模式（只產生 script，不發送）
python3 kaspa_message.py --demo

# 產生特定訊息的 script
python3 kaspa_message.py "你的訊息"
```

### 方法 2: 使用 kaspa-wallet CLI

```bash
kaspa-wallet --testnet send \
  --op-return "Hello from Nami 🌊" \
  -a <recipient-address> \
  -v 0
```

### 方法 3: 完整交易流程

```python
import asyncio
from kaspa import RpcClient, Resolver, ...

async def send_message(message: str):
    # 1. 連接節點
    client = RpcClient(...)
    await client.connect()
    
    # 2. 獲取 UTXOs（可花費的餘額）
    utxos = await client.get_utxos_by_addresses([address])
    
    # 3. 構建交易
    #    - Input: 你的 UTXO
    #    - Output 1: OP_RETURN（訊息）
    #    - Output 2: 找零回自己
    
    # 4. 簽名
    signed_tx = sign_transaction(tx, private_key)
    
    # 5. 廣播
    tx_id = await client.submit_transaction(signed_tx)
    
    return tx_id
```

---

## 📖 如何讀訊息

### 方法 1: 區塊瀏覽器

直接在瀏覽器上查看交易：
- **Mainnet**: https://explorer.kaspa.org/txs/{tx_id}
- **Testnet**: https://explorer-tn10.kaspa.org/txs/{tx_id}

找到 OP_RETURN output，把 hex 轉回 UTF-8。

### 方法 2: 程式解析

```python
def parse_op_return(script_hex: str) -> str:
    """解析 OP_RETURN script"""
    script = bytes.fromhex(script_hex)
    
    # 檢查是否為 OP_RETURN
    if script[0] != 0x6a:
        return None
    
    # 取得資料長度和內容
    length = script[1]
    data = script[2:2+length]
    
    return data.decode('utf-8')

# 使用
message = parse_op_return("6a0c48656c6c6f204b6173706121")
print(message)  # "Hello Kaspa!"
```

### 方法 3: 批量掃描

```python
async def scan_messages(addresses: list):
    """掃描地址的所有交易，找出訊息"""
    client = RpcClient(...)
    await client.connect()
    
    # 獲取交易歷史
    txs = await get_transactions_by_addresses(addresses)
    
    messages = []
    for tx in txs:
        for output in tx.outputs:
            if is_op_return(output.script):
                msg = parse_op_return(output.script)
                messages.append({
                    'tx_id': tx.id,
                    'message': msg,
                    'timestamp': tx.timestamp
                })
    
    return messages
```

---

## 🗂️ 專案檔案

| 檔案 | 說明 |
|------|------|
| `kaspa_message.py` | 主程式：訊息嵌入與解析 |
| `embed_message.py` | 進階嵌入功能 |
| `send_message.py` | 發送交易範例 |
| `send_real_message.py` | 實際發送（需要錢包） |
| `nami_graffiti.py` | 🌊 Nami 的塗鴉牆功能 |

---

## ⚠️ 注意事項

1. **訊息永久公開** — 寫上去就永遠在那了，別放隱私資訊
2. **需要手續費** — 發交易要有餘額付 gas
3. **長度限制** — OP_RETURN 約 75-80 bytes
4. **編碼注意** — emoji 可能佔多個 bytes

---

## 🌊 應用場景

- **存在證明**: 證明某時間點知道某資訊
- **簽名認證**: 數位簽章 + 時間戳
- **紀念訊息**: 永久保存重要時刻
- **NFT 元資料**: 指向 IPFS 的連結
- **協議標記**: 標示特定協議的交易

---

*Made with 🌊 by Nami*
