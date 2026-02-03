# ShioKaze Debug 筆記

## 2026-02-03 - Block Invalid 問題排查

### 症狀
- PoW 計算本地驗證通過 (`hash < target = True`)
- 提交到節點後被 reject：`block is invalid`
- 嘗試了 30+ 次，全部失敗

### 排查過程

#### 1. 檢查區塊結構
- 用 `debug_block_structure.py` 檢查區塊完整性
- 確認 transactions、parents、coinbase 都正確
- ✅ 區塊結構沒問題

#### 2. 檢查 PoW 計算
- 用 `verify_heavy_hash.py` 驗證 HeavyHash 實現
- 對比 Rust 版本的計算結果
- ✅ HeavyHash 實現正確

#### 3. 檢查時間戳/過期
- 嘗試快速提交（< 5秒找到 nonce 立即提交）
- 仍然失敗
- ❓ 排除 template 過期問題

#### 4. 檢查 pre_pow_hash 計算 ⭐ 關鍵！
- 比對官方 `rusty-kaspa/crypto/hashes/src/hashers.rs`
- 發現官方用的是 **帶 key 的 blake2b**！

```rust
// 官方實現 (hashers.rs)
blake2b_simd::Params::new()
    .hash_length(32)
    .key(b"BlockHash")  // <-- 這個 key！
    .to_state()
```

```python
# 我的錯誤實現
hashlib.blake2b(digest_size=32)  # ❌ 沒有 key

# 正確實現
hashlib.blake2b(digest_size=32, key=b"BlockHash")  # ✅
```

### 根本原因

Kaspa 的 BlockHash（用於計算 pre_pow_hash）使用 **keyed blake2b**，
key 是 `b"BlockHash"`。

我的實現用的是普通 blake2b（沒有 key），導致：
1. 計算出的 pre_pow_hash 完全不同
2. 從錯誤的 pre_pow_hash 生成的矩陣也不對
3. 計算出的 PoW hash 在本地看起來 < target（因為用錯誤的 target 比較）
4. 節點收到區塊後重新計算，發現 hash 不匹配，reject

### 修復

```python
def calculate_pre_pow_hash(header) -> bytes:
    # 🔑 重要：必須使用帶 key 的 blake2b！
    hasher = hashlib.blake2b(digest_size=32, key=b"BlockHash")
    # ... 其他 header 欄位
```

### 學到的教訓

1. **仔細閱讀官方代碼**
   - 不要假設標準庫的用法
   - Kaspa 很多地方用了 domain separation (keyed hash)

2. **"block is invalid" 不一定是 PoW 錯誤**
   - 可能是 header hash 計算錯誤
   - 可能是其他驗證失敗

3. **本地驗證通過不代表節點會接受**
   - 如果基礎計算錯了，本地驗證也會用錯的值

4. **Kaspa 的 hash 函數列表**
   所有都使用 keyed blake2b：
   - `BlockHash` → key = b"BlockHash"
   - `TransactionHash` → key = b"TransactionHash"
   - `TransactionID` → key = b"TransactionID"
   - `MerkleBranchHash` → key = b"MerkleBranchHash"
   
   PoW 相關用 cSHAKE256：
   - `ProofOfWorkHash` → domain = "ProofOfWorkHash"
   - `HeavyHash` → domain = "HeavyHash"

### 驗證修復

```
📬 Submit Block Response:
  rejectReason: 0
  rejectReason name: NONE
✅ 🎉 BLOCK ACCEPTED!
```

---
*Nami 🌊 - 2026-02-03*
