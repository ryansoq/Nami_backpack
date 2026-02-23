# Kaspa Architecture Research Notes
Date: 2026-02-01

## rusty-kaspa 架構概覽

### 目錄結構
- `consensus/` - 共識層（包含 PoW）
- `mining/` - 挖礦管理
- `rpc/` - RPC 服務（gRPC + wRPC）
- `crypto/` - 加密相關（hashes, secp256k1）
- `wallet/` - 錢包功能
- `wasm/` - WebAssembly 綁定

### gRPC Mining Flow

1. **GetBlockTemplate** - 取得區塊模板
   - Request: `payAddress`, `extraData`
   - Response: `block` (RpcBlock), `isSynced` (bool)

2. **Solve PoW** - 解工作量證明
   - 計算 pre_pow_hash
   - 跑 HeavyHash 找合適的 nonce

3. **SubmitBlock** - 提交區塊
   - Request: `block` (完整的 RpcBlock，含 nonce)
   - Response: `rejectReason` (NONE/BLOCK_INVALID/IS_IN_IBD)

### HeavyHash 算法（consensus/pow/）

關鍵檔案：
- `lib.rs` - State struct，快取 matrix 和 hasher
- `matrix.rs` - 64x64 矩陣生成與乘法
- `xoshiro.rs` - Xoshiro256++ PRNG

優化點：
- State 快取避免重複計算 matrix
- 矩陣乘法同時計算兩行
- 使用 MaybeUninit 避免初始化開銷

### pre_pow_hash 計算

header 序列化順序（80 bytes）：
```
[0:32]  = hash_values (4 x uint64, little-endian)
[32:40] = timestamp (uint64, little-endian)
[40:72] = padding (32 bytes of zeros)
[72:80] = nonce (uint64, little-endian)
```

然後用 CShake256(header, b'ProofOfWorkHash', 32) 哈希

### Proto 定義

位置：`rpc/grpc/core/proto/`
- `messages.proto` - Request/Response 包裝
- `rpc.proto` - 各 API 的詳細結構

### Testnet 資訊

- Network ID: testnet-10
- 預設 gRPC port: 16210 (但我們用 17110 for JSON-RPC)
- 地址前綴: `kaspatest:`

## Ryan's Python Miner 分析

### 正確的部分
- HeavyHash 核心算法
- Xoshiro256++ PRNG
- 矩陣秩計算
- CShake256 使用

### 可優化的部分
- 每次重算 matrix（可快取）
- 矩陣乘法逐行計算（可並行/合併）

### gRPC 客戶端
`kaspa_grpc_client.py` 看起來結構正確，需要測試確認。
