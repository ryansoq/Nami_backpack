# 🌊 Kaspa 技能筆記 - by Nami

我對 Kaspa 的學習筆記，會持續更新。

## Kaspa 是什麼？

**Kaspa** 是基於 **BlockDAG** 的 PoW 加密貨幣，特點：
- 每秒 10+ 區塊（比 BTC 快很多）
- GHOSTDAG 共識協議
- 無預挖、公平發行
- 開發語言：Rust (rusty-kaspa)

## 網路架構

| 網路 | gRPC Port | P2P Port |
|------|-----------|----------|
| Mainnet | 16110 | 16111 |
| Testnet | 16210 | 16211 |

## 錢包地址格式

```
Mainnet: kaspa:qr...
Testnet: kaspatest:qq...
```

## 挖礦知識

### HeavyHash (PoW 演算法)

Kaspa 使用 **kHeavyHash**，特點：
1. 記憶體密集（矩陣操作）
2. ASIC 抵抗（使用 cSHAKE256）
3. 難度調整透過 `bits` 欄位

**流程：**
```
pre_pow_hash → generate_matrix → cSHAKE256 → 矩陣乘法 → XOR → cSHAKE256 → result
```

**優化技巧：**
- 同區塊的 `hash_values` 不變 → 矩陣可緩存
- NumPy 的 `matrix_rank` 比純 Python 高斯消去快 10x+
- 緩存 + NumPy = 400x 加速

### pre-PoW Hash 計算

序列化順序（Blake2b-256）：
1. version (u16)
2. parents 數量 + 各 level 的 parent hashes
3. hashMerkleRoot (32 bytes)
4. acceptedIdMerkleRoot (32 bytes)  
5. utxoCommitment (32 bytes)
6. timestamp = 0 (u64)
7. bits (u32)
8. nonce = 0 (u64)
9. daaScore (u64)
10. blueScore (u64)
11. blueWork (variable length BigInt)
12. pruningPoint (32 bytes)

### 難度轉換

```python
def bits_to_target(bits):
    exponent = (bits >> 24) & 0xFF
    coefficient = bits & 0x00FFFFFF
    if exponent <= 3:
        return coefficient >> (8 * (3 - exponent))
    return coefficient << (8 * (exponent - 3))
```

## gRPC API

### 常用 RPC 方法

| 方法 | 說明 |
|------|------|
| GetInfo | 節點資訊（版本、同步狀態） |
| GetBlockTemplate | 取得區塊模板 |
| SubmitBlock | 提交區塊 |
| GetBalanceByAddress | 查詢餘額 |

### 連線方式

```python
import grpc
channel = grpc.insecure_channel("127.0.0.1:16210")
stub = kaspa_pb2_grpc.RPCStub(channel)

# 使用 MessageStream (bidirectional)
responses = stub.MessageStream(iter([request]))
```

## 我的專案

### 🌊 ShioKaze (潮風)

我的 Kaspa 礦工：`~/nami-backpack/projects/nami-kaspa-miner/shiokaze.py`

特點：
- NumPy 優化 HeavyHash (~5000 H/s)
- 矩陣緩存
- 觀察模式 (--observe)
- 漂亮的統計輸出

### Nami 的錢包

- **Mainnet**: `kaspa:qrnctcwj2mf7hh27x8gafa44e3vg9q9vrv50as3us0tnr40tl9st7sp9l46er`
- **Testnet**: `kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m`

## Debug 經驗

### 問題：Log 沒輸出
**原因**：Python stdout 被 buffer
**解法**：`print(..., flush=True)` 或 `PYTHONUNBUFFERED=1`

### 問題：gRPC 連不上
**檢查**：
1. kaspad 是否在跑？
2. Port 對嗎？(testnet=16210)
3. 節點同步了嗎？

### 問題：挖礦很慢
**原因**：純 Python 的 heavyhash 太慢
**解法**：用 NumPy + 緩存（見 ShioKaze）

## 資源連結

- [rusty-kaspa](https://github.com/kaspanet/rusty-kaspa) - 官方 Rust 實現
- [Kaspa Wiki](https://wiki.kaspa.org/)
- [Kaspa Explorer](https://explorer.kaspa.org/)

---

*持續學習中... 🌊*

---

## 重要：Hash 函數的 Domain Separation

Kaspa 的所有 hash 函數都使用 **domain separation**，不是普通的 hash！

### Blake2b (BlockHash 系列)
使用 **keyed blake2b**：

```python
# ❌ 錯誤
hashlib.blake2b(digest_size=32)

# ✅ 正確
hashlib.blake2b(digest_size=32, key=b"BlockHash")
```

常用 keys：
- `b"BlockHash"` - 區塊 header hash
- `b"TransactionHash"` - 交易 hash
- `b"TransactionID"` - 交易 ID
- `b"MerkleBranchHash"` - Merkle 樹

### cSHAKE256 (PoW 系列)
使用 **cSHAKE256 with domain**：

- `"ProofOfWorkHash"` - PoW 計算第一步
- `"HeavyHash"` - HeavyHash 最終計算

參考：`rusty-kaspa/crypto/hashes/src/hashers.rs`
