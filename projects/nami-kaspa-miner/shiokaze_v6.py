#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  🌊 ShioKaze v6.0 (潮風) - Nami's Kaspa Miner
═══════════════════════════════════════════════════════════════════════════════

  🦀 Rust Turbo Edition - Rust 核心加速版！
  
  Built by Nami (波浪) - 2026

【v6 新功能】
  ✨ Rust HeavyHash 核心（~10x 加速！）
  ✨ 多進程並行挖礦
  ✨ 隨機 nonce 策略
  ✨ 自動重連機制
  ✨ 精確 hashrate 統計

【用法】
  python3 shiokaze_v6.py --testnet --wallet kaspatest:qq... --workers 4 -r

═══════════════════════════════════════════════════════════════════════════════
  📍 執行流程 (Execution Flow)
═══════════════════════════════════════════════════════════════════════════════

  main()
    │
    ├─► 解析命令列參數 (parse args)
    │
    ├─► run_self_test()           # PoW 計算自檢
    │     └─► heavy_hash()        # 驗證已知測試向量
    │
    ├─► 連接 gRPC (kaspad node)
    │
    └─► mine_loop() [主循環]
          │
          ├─► get_block_template()          # 從節點取得區塊模板
          │     └─► 節點回傳: header, target, parents, transactions...
          │
          ├─► 啟動 worker 進程 (多進程並行)
          │     │
          │     └─► mine_worker() [每個 worker]
          │           │
          │           ├─► calculate_pre_pow_hash()     # ⚠️ 使用 keyed blake2b!
          │           │     └─► blake2b(header_bytes, key=b"BlockHash")
          │           │
          │           └─► [挖礦迴圈] 嘗試不同 nonce
          │                 │
          │                 ├─► heavy_hash(pre_pow_hash, nonce)
          │                 │     ├─► cSHAKE256("ProofOfWorkHash")  # 生成矩陣
          │                 │     ├─► 64x64 矩陣乘法                 # 記憶體密集
          │                 │     └─► cSHAKE256("HeavyHash")        # 最終 hash
          │                 │
          │                 └─► if hash < target: 找到區塊!
          │
          └─► submit_block()              # 提交區塊到節點
                └─► 節點驗證 → Accepted ✓ / Rejected ✗

═══════════════════════════════════════════════════════════════════════════════
"""

__version__ = "6.0.0"
__author__ = "Nami 🌊"

import sys
import os
import time
import struct
import argparse
import signal
import random
import multiprocessing as mp
from multiprocessing import Process, Value, Array, Manager
from typing import Optional, Tuple, List
from datetime import datetime
from collections import deque

import numpy as np
import grpc

# gRPC proto
sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc

# ═══════════════════════════════════════════════════════════════════════════════
# Rust / Cython 加速模組（自動 fallback）
# ═══════════════════════════════════════════════════════════════════════════════

USE_RUST = False
USE_CYTHON = False
BACKEND = "python"

try:
    import kaspa_pow_py
    USE_RUST = True
    BACKEND = "rust"
    print("🦀 Rust HeavyHash 已載入（10x 加速）！", flush=True)
except ImportError:
    try:
        import kaspa_pow_v2
        USE_CYTHON = True
        BACKEND = "cython"
        print("🚀 Cython HeavyHash 已載入！", flush=True)
    except ImportError:
        from Crypto.Hash import cSHAKE256
        print("⚠️ 加速模組未找到，使用純 Python（較慢）", flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 啟動自檢（驗證 PoW 計算正確性）
# ═══════════════════════════════════════════════════════════════════════════════

def run_self_test() -> bool:
    """
    使用已知測試向量驗證 PoW 計算
    參考 rusty-kaspa/consensus/pow/src/matrix.rs 的測試
    """
    print("[Test] 🔍 執行 PoW 自檢...", flush=True)
    
    # 測試向量：固定的 pre_pow_hash
    test_hash = bytes([
        0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef,
        0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef,
        0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef,
        0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef,
    ])
    test_timestamp = 1234567890
    test_nonce = 99999
    
    # 生成矩陣
    if USE_RUST:
        matrix = kaspa_pow_py.gen_matrix(test_hash)
    elif USE_CYTHON:
        matrix = kaspa_pow_v2.generate_matrix(test_hash)
    else:
        print("[Test] ⚠️ 無加速模組，跳過自檢", flush=True)
        return True
    
    # 計算 PoW
    if USE_RUST:
        pow_hash = kaspa_pow_py.compute_pow(test_hash, test_timestamp, test_nonce, matrix)
    else:
        pow_hash = kaspa_pow_v2.compute_pow(test_hash, test_timestamp, test_nonce, matrix)
    
    # 預期結果（使用 Cython v2 作為參考，已驗證正確）
    expected_hex = "d2154c1435c99a4ea58ca81dc35829ebd1513b67b0bdec12ba15fb27fefadc82"
    expected = bytes.fromhex(expected_hex)
    
    if pow_hash == expected:
        print(f"[Test] ✅ PoW 計算正確！", flush=True)
        print(f"[Test]    Hash: {pow_hash.hex()[:32]}...", flush=True)
        return True
    else:
        print(f"[Test] ❌ PoW 計算錯誤！", flush=True)
        print(f"[Test]    預期: {expected_hex[:32]}...", flush=True)
        print(f"[Test]    實際: {pow_hash.hex()[:32]}...", flush=True)
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   🌊  ShioKaze v6.0 (潮風) - 🦀 Rust Turbo Edition                            ║
║       Nami's Kaspa Miner                                                      ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════════════════════════════════════════
# HeavyHash（純 Python fallback）
# ═══════════════════════════════════════════════════════════════════════════════

if not USE_CYTHON:
    def xoshiro256_next(state: np.ndarray) -> int:
        result = np.uint64((np.uint64(state[0]) + np.uint64(state[3])))
        result = np.uint64((result << 23 | result >> 41) + state[0])
        t = np.uint64(state[1] << 17)
        state[2] ^= state[0]
        state[3] ^= state[1]
        state[1] ^= state[2]
        state[0] ^= state[3]
        state[2] ^= t
        state[3] = np.uint64(state[3] << 45 | state[3] >> 19)
        return int(result)

    def compute_matrix_rank(matrix: np.ndarray) -> int:
        EPS = 1e-9
        mat = matrix.astype(np.float64).copy()
        rank = 0
        row_selected = [False] * 64
        for i in range(64):
            j = 0
            while j < 64:
                if not row_selected[j] and abs(mat[j, i]) > EPS:
                    break
                j += 1
            if j != 64:
                rank += 1
                row_selected[j] = True
                for p in range(i + 1, 64):
                    mat[j, p] /= mat[j, i]
                for k in range(64):
                    if k != j and abs(mat[k, i]) > EPS:
                        for p in range(i + 1, 64):
                            mat[k, p] -= mat[j, p] * mat[k, i]
        return rank

    def generate_matrix(hash_bytes: bytes) -> np.ndarray:
        state = np.zeros(4, dtype=np.uint64)
        for i in range(4):
            state[i] = int.from_bytes(hash_bytes[i*8:(i+1)*8], 'little')
        while True:
            matrix = np.zeros((64, 64), dtype=np.uint16)
            for i in range(64):
                for j in range(0, 64, 16):
                    value = xoshiro256_next(state)
                    for k in range(16):
                        matrix[i, j + k] = (value >> (4 * k)) & 0x0F
            if compute_matrix_rank(matrix) == 64:
                return matrix

    def heavy_hash(matrix: np.ndarray, hash_bytes: bytes) -> bytes:
        header_arr = np.frombuffer(hash_bytes, dtype=np.uint8)
        v = np.zeros(64, dtype=np.uint16)
        v[0::2] = (header_arr >> 4) & 0x0F
        v[1::2] = header_arr & 0x0F
        p = np.dot(matrix.astype(np.uint64), v.astype(np.uint64))
        p = (p >> 10) & 0x0F
        digest = bytearray(32)
        for i in range(32):
            high4 = int(p[i * 2]) & 0x0F
            low4 = int(p[i * 2 + 1]) & 0x0F
            digest[i] = hash_bytes[i] ^ ((high4 << 4) | low4)
        h = cSHAKE256.new(data=bytes(digest), custom=b"HeavyHash")
        return h.read(32)

    def compute_pow_python(pre_pow_hash: bytes, timestamp: int, nonce: int, matrix: np.ndarray) -> bytes:
        data = pre_pow_hash + struct.pack('<Q', timestamp) + (b'\x00' * 32) + struct.pack('<Q', nonce)
        h = cSHAKE256.new(data=data, custom=b"ProofOfWorkHash")
        pow_hash = h.read(32)
        return heavy_hash(matrix, pow_hash)

# ═══════════════════════════════════════════════════════════════════════════════
# PoW 計算（Cython 或 Python）
# ═══════════════════════════════════════════════════════════════════════════════

def bytes_to_hash_values(pre_pow_hash: bytes) -> List[int]:
    """將 32 bytes 轉為 4 個 uint64"""
    return [
        int.from_bytes(pre_pow_hash[0:8], 'little'),
        int.from_bytes(pre_pow_hash[8:16], 'little'),
        int.from_bytes(pre_pow_hash[16:24], 'little'),
        int.from_bytes(pre_pow_hash[24:32], 'little'),
    ]

def compute_pow(pre_pow_hash: bytes, timestamp: int, nonce: int, matrix=None) -> bytes:
    """計算 PoW（自動選擇 Rust / Cython / Python）"""
    if USE_RUST:
        # Rust: 最快！matrix 是 bytes
        return kaspa_pow_py.compute_pow(pre_pow_hash, timestamp, nonce, matrix)
    elif USE_CYTHON:
        # Cython: matrix 是 numpy array
        return kaspa_pow_v2.compute_pow(pre_pow_hash, timestamp, nonce, matrix)
    else:
        return compute_pow_python(pre_pow_hash, timestamp, nonce, matrix)

def generate_matrix(pre_pow_hash: bytes):
    """生成矩陣（自動選擇後端）"""
    if USE_RUST:
        return kaspa_pow_py.gen_matrix(pre_pow_hash)
    elif USE_CYTHON:
        return kaspa_pow_v2.generate_matrix(pre_pow_hash)
    return None

def hash_to_int(hash_bytes: bytes) -> int:
    return int.from_bytes(hash_bytes, 'little')

def bits_to_target(bits: int) -> int:
    exponent = (bits >> 24) & 0xFF
    mantissa = bits & 0x00FFFFFF
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target

def target_to_bytes(target: int) -> bytes:
    """將 target 整數轉為 32 bytes (little-endian)"""
    result = bytearray(32)
    temp = target
    for i in range(32):
        result[i] = temp & 0xFF
        temp >>= 8
    return bytes(result)

# ═══════════════════════════════════════════════════════════════════════════════
# Pre-PoW Hash 計算
# ═══════════════════════════════════════════════════════════════════════════════

import hashlib

def hash_from_hex(hex_str: str) -> bytes:
    if not hex_str:
        return b'\x00' * 32
    return bytes.fromhex(hex_str)

def write_len(hasher, length: int):
    hasher.update(struct.pack('<Q', length))

def write_var_bytes(hasher, data: bytes):
    write_len(hasher, len(data))
    hasher.update(data)

def write_blue_work(hasher, blue_work: str):
    if not blue_work:
        write_var_bytes(hasher, b'')
        return
    hex_str = blue_work
    if len(hex_str) % 2 == 1:
        hex_str = '0' + hex_str
    work_bytes = bytes.fromhex(hex_str)
    start = 0
    while start < len(work_bytes) and work_bytes[start] == 0:
        start += 1
    write_var_bytes(hasher, work_bytes[start:])

def calculate_pre_pow_hash(header) -> bytes:
    # 🔑 重要：必須使用帶 key 的 blake2b！key="BlockHash"
    # 參考 rusty-kaspa/crypto/hashes/src/hashers.rs
    hasher = hashlib.blake2b(digest_size=32, key=b"BlockHash")
    hasher.update(struct.pack('<H', header.version))
    parents = list(header.parents)
    write_len(hasher, len(parents))
    for level in parents:
        parent_hashes = list(level.parentHashes)
        write_len(hasher, len(parent_hashes))
        for h in parent_hashes:
            hasher.update(hash_from_hex(h))
    hasher.update(hash_from_hex(header.hashMerkleRoot))
    hasher.update(hash_from_hex(header.acceptedIdMerkleRoot))
    hasher.update(hash_from_hex(header.utxoCommitment))
    hasher.update(struct.pack('<Q', 0))
    hasher.update(struct.pack('<I', header.bits))
    hasher.update(struct.pack('<Q', 0))
    hasher.update(struct.pack('<Q', header.daaScore))
    hasher.update(struct.pack('<Q', header.blueScore))
    write_blue_work(hasher, header.blueWork)
    hasher.update(hash_from_hex(header.pruningPoint))
    return hasher.digest()

# ═══════════════════════════════════════════════════════════════════════════════
# Worker 進程
# ═══════════════════════════════════════════════════════════════════════════════

def worker_process(
    worker_id: int,
    shared_state: dict,
    result_queue: mp.Queue,
    stats_array: mp.Array,
    running: mp.Value
):
    """Worker 進程 - Rust 優化版"""
    
    log_prefix = f"[Worker {worker_id}]"
    local_hashes = 0
    last_report = time.time()
    
    # Worker 自己的模板緩存
    cached_pre_pow_hash = None
    cached_matrix = None  # for non-Rust fallback
    
    while running.value:
        template_data = shared_state.get('template')
        if not template_data:
            time.sleep(0.1)
            continue
        
        pre_pow_hash = template_data['pre_pow_hash']
        timestamp = template_data['timestamp']
        target = template_data['target']
        template_id = template_data['id']
        target_bytes = template_data.get('target_bytes', b'\xff' * 32)
        
        num_workers = shared_state.get('num_workers', 4)
        random_nonce = shared_state.get('random_nonce', False)
        
        # 當 template 改變時，更新 Rust 狀態
        if pre_pow_hash != cached_pre_pow_hash:
            if USE_RUST:
                # 使用新 API: setup_mining 會生成矩陣並保存狀態
                kaspa_pow_py.setup_mining(pre_pow_hash, timestamp, target_bytes)
            elif USE_CYTHON:
                cached_matrix = kaspa_pow_v2.generate_matrix(pre_pow_hash)
            else:
                cached_matrix = generate_matrix_python(pre_pow_hash)
            cached_pre_pow_hash = pre_pow_hash
        
        # 計算起始 nonce
        if random_nonce:
            start_nonce = random.randint(0, 0xFFFFFFFFFFFFFFFF)
        else:
            chunk_size = 0xFFFFFFFFFFFFFFFF // num_workers
            start_nonce = worker_id * chunk_size + random.randint(0, chunk_size // 1000)
        
        # 挖礦循環
        if USE_RUST:
            batch_size = 50000  # 新 API 可以用更大 batch
        elif USE_CYTHON:
            batch_size = 5000
        else:
            batch_size = 1000
        
        nonce = start_nonce
        
        while running.value and shared_state.get('template', {}).get('id') == template_id:
            if USE_RUST:
                # 使用新 API: mine_range 在 Rust 內部迴圈
                found_nonce, pow_hash, hashes_done = kaspa_pow_py.mine_range(
                    nonce, batch_size, random_nonce
                )
                local_hashes += hashes_done
                
                if found_nonce is not None:
                    result_queue.put({
                        'type': 'found',
                        'worker_id': worker_id,
                        'nonce': found_nonce,
                        'hash': pow_hash.hex() if pow_hash else '',
                        'template_id': template_id
                    })
                    print(f"{log_prefix} 💎 FOUND nonce={found_nonce}", flush=True)
                
                if random_nonce:
                    nonce = random.randint(0, 0xFFFFFFFFFFFFFFFF)
                else:
                    nonce += batch_size
            else:
                # Fallback: 舊的逐個計算方式
                for _ in range(batch_size):
                    pow_hash = compute_pow(pre_pow_hash, timestamp, nonce, cached_matrix)
                    hash_val = hash_to_int(pow_hash)
                    local_hashes += 1
                    
                    if hash_val < target:
                        result_queue.put({
                            'type': 'found',
                            'worker_id': worker_id,
                            'nonce': nonce,
                            'hash': pow_hash.hex(),
                            'template_id': template_id
                        })
                        print(f"{log_prefix} 💎 FOUND nonce={nonce}", flush=True)
                    
                    if random_nonce:
                        nonce = random.randint(0, 0xFFFFFFFFFFFFFFFF)
                    else:
                        nonce += 1
            
            now = time.time()
            if now - last_report >= 1.0:
                stats_array[worker_id] = local_hashes
                local_hashes = 0
                last_report = now
    
    print(f"{log_prefix} 停止", flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 主礦工類
# ═══════════════════════════════════════════════════════════════════════════════

class ShioKazeMiner:
    """ShioKaze v5 主礦工 - Cython Turbo"""
    
    def __init__(self, address: str, wallet: str, num_workers: int = 4, random_nonce: bool = False):
        self.address = address
        self.wallet = wallet
        self.num_workers = num_workers
        self.random_nonce = random_nonce
        
        self.manager = Manager()
        self.shared_state = self.manager.dict()
        self.shared_state['num_workers'] = num_workers
        self.shared_state['random_nonce'] = random_nonce
        
        self.stats_array = Array('d', num_workers)
        self.running = Value('b', True)
        self.result_queue = mp.Queue()
        self.workers = []
        
        self.channel = None
        self.stub = None
        
        self.start_time = None
        self.total_hashes = 0
        self.blocks_found = 0
        self.blocks_accepted = 0
        self.template_count = 0
        self.hashrate_history = deque(maxlen=60)
        
        self.template_cache = {}
        self.template_ids = deque(maxlen=100)
    
    def connect(self):
        print(f"[Main] 🔗 連接到 {self.address}...", flush=True)
        self.channel = grpc.insecure_channel(
            self.address,
            options=[
                ('grpc.keepalive_time_ms', 10000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.keepalive_permit_without_calls', True),
            ]
        )
        self.stub = kaspa_pb2_grpc.RPCStub(self.channel)
        
        try:
            request = kaspa_pb2.KaspadMessage(
                getInfoRequest=kaspa_pb2.GetInfoRequestMessage()
            )
            response = self._call_rpc(request)
            
            if response and response.HasField('getInfoResponse'):
                info = response.getInfoResponse
                print(f"[Main] ✅ 已連接！版本: {info.serverVersion}", flush=True)
                print(f"[Main]    同步: {info.isSynced} | Mempool: {info.mempoolSize}", flush=True)
                return info.isSynced
            return False
        except Exception as e:
            print(f"[Main] ❌ 連接失敗: {e}", flush=True)
            return False
    
    def _call_rpc(self, request, timeout=10):
        """🔧 修復：加入 timeout 避免永久卡住"""
        try:
            responses = self.stub.MessageStream(iter([request]), timeout=timeout)
            for response in responses:
                return response
        except grpc.RpcError as e:
            print(f"[Main] gRPC error: {e.code()} - {e.details()}", flush=True)
            self._handle_disconnect()
            return None
        except Exception as e:
            print(f"[Main] RPC error: {e}", flush=True)
            return None
    
    def disconnect(self):
        if self.channel:
            try:
                self.channel.close()
            except:
                pass
            self.channel = None
            self.stub = None
    
    def _handle_disconnect(self):
        print("[Main] ⚠️ 連接中斷，嘗試重連...", flush=True)
        self.disconnect()
        time.sleep(2)
        try:
            if self.connect():
                print("[Main] ✅ 重連成功！", flush=True)
            else:
                print("[Main] ❌ 重連失敗", flush=True)
        except Exception as e:
            print(f"[Main] ❌ 重連失敗: {e}", flush=True)
    
    def start_workers(self):
        print(f"[Main] 🚀 啟動 {self.num_workers} 個 workers...", flush=True)
        for i in range(self.num_workers):
            p = Process(
                target=worker_process,
                args=(i, self.shared_state, self.result_queue, self.stats_array, self.running)
            )
            p.daemon = True
            p.start()
            self.workers.append(p)
        print(f"[Main] ✅ Workers 已啟動", flush=True)
    
    def stop_workers(self):
        print(f"[Main] 🛑 停止 workers...", flush=True)
        self.running.value = False
        for p in self.workers:
            p.join(timeout=2)
            if p.is_alive():
                p.terminate()
        self.workers = []
    
    def get_block_template(self) -> Optional[dict]:
        try:
            request = kaspa_pb2.KaspadMessage(
                getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
                    payAddress=self.wallet,
                    extraData="ShioKaze v5 Cython"
                )
            )
            response = self._call_rpc(request)
            
            if not response or not response.HasField('getBlockTemplateResponse'):
                return None
            
            resp = response.getBlockTemplateResponse
            if resp.error and resp.error.message:
                print(f"[Main] ⚠️ Template error: {resp.error.message}", flush=True)
                return None
            
            block = resp.block
            header = block.header
            
            pre_pow_hash = calculate_pre_pow_hash(header)
            timestamp = header.timestamp
            bits = header.bits
            target = bits_to_target(bits)
            
            # 生成矩陣（Cython 或 Python）
            if USE_CYTHON:
                matrix = kaspa_pow_v2.generate_matrix(pre_pow_hash)
            elif not USE_RUST:
                matrix = generate_matrix(pre_pow_hash)
            else:
                matrix = None  # Rust 自己管理矩陣
            
            return {
                'block': block,
                'pre_pow_hash': pre_pow_hash,
                'timestamp': timestamp,
                'bits': bits,
                'target': target,
                'target_bytes': target_to_bytes(target),
                'matrix': matrix,
                'id': time.time()
            }
            
        except Exception as e:
            print(f"[Main] ❌ Template error: {e}", flush=True)
            return None
    
    def submit_block(self, template: dict, nonce: int) -> bool:
        try:
            block = template['block']
            pre_pow_hash = template['pre_pow_hash']
            timestamp = template['timestamp']
            target = template['target']
            
            # 🔍 提交前自檢：重新計算 PoW 確認正確
            if USE_RUST:
                matrix = kaspa_pow_py.gen_matrix(pre_pow_hash)
                verify_hash = kaspa_pow_py.compute_pow(pre_pow_hash, timestamp, nonce, matrix)
            elif USE_CYTHON:
                matrix = kaspa_pow_v2.generate_matrix(pre_pow_hash)
                verify_hash = kaspa_pow_v2.compute_pow(pre_pow_hash, timestamp, nonce, matrix)
            else:
                matrix = generate_matrix(pre_pow_hash)
                verify_hash = compute_pow_python(pre_pow_hash, timestamp, nonce, matrix)
            
            verify_int = hash_to_int(verify_hash)
            
            print(f"[Submit] 🔍 自檢:", flush=True)
            print(f"         pre_pow_hash: {pre_pow_hash.hex()[:32]}...", flush=True)
            print(f"         timestamp: {timestamp}", flush=True)
            print(f"         nonce: {nonce}", flush=True)
            print(f"         target: {target:064x}", flush=True)
            print(f"         pow_hash: {verify_hash.hex()}", flush=True)
            print(f"         hash_int: {verify_int:064x}", flush=True)
            print(f"         hash < target: {verify_int < target}", flush=True)
            
            if verify_int >= target:
                print(f"[Submit] ❌ 自檢失敗！hash >= target，不提交", flush=True)
                return False
            
            # 🔍 Debug: 檢查 header 時間戳一致性
            header_ts = block.header.timestamp
            print(f"[Submit] 🕐 header.timestamp: {header_ts} vs template.timestamp: {timestamp}", flush=True)
            print(f"[Submit]    match: {header_ts == timestamp}", flush=True)
            
            # 確保使用 template 返回時的 timestamp
            if header_ts != timestamp:
                print(f"[Submit] ⚠️ 時間戳不一致！這可能導致 PoW 失敗", flush=True)
            
            block.header.nonce = nonce
            
            request = kaspa_pb2.KaspadMessage(
                submitBlockRequest=kaspa_pb2.SubmitBlockRequestMessage(
                    block=block,
                    allowNonDAABlocks=False
                )
            )
            response = self._call_rpc(request)
            
            if not response or not response.HasField('submitBlockResponse'):
                print(f"[Main] ⚠️ No response for submit", flush=True)
                return False
            
            resp = response.submitBlockResponse
            if resp.error and resp.error.message:
                print(f"[Main] ⚠️ Block rejected: {resp.error.message}", flush=True)
                return False
            
            if resp.rejectReason:
                print(f"[Main] ⚠️ Block rejected: {resp.rejectReason}", flush=True)
                return False
            
            print(f"[Main] ✅ 🎉 BLOCK ACCEPTED!", flush=True)
            return True
            
        except Exception as e:
            print(f"[Main] ❌ Submit error: {e}", flush=True)
            return False
    
    def print_stats(self):
        current_hashes = sum(self.stats_array)
        self.total_hashes += current_hashes
        self.hashrate_history.append(current_hashes)
        
        for i in range(self.num_workers):
            self.stats_array[i] = 0
        
        avg_hashrate = sum(self.hashrate_history) / max(len(self.hashrate_history), 1)
        
        now = datetime.now().strftime("%H:%M:%S")
        
        # 顯示單位
        if avg_hashrate >= 1000000:
            hr_str = f"{avg_hashrate/1000000:.2f} MH/s"
        elif avg_hashrate >= 1000:
            hr_str = f"{avg_hashrate/1000:.1f} kH/s"
        else:
            hr_str = f"{avg_hashrate:.0f} H/s"
        
        print(f"[{now}] 🌊 ⚡ {current_hashes:,} H/s (avg: {hr_str}) | "
              f"Templates: {self.template_count} | Found: {self.blocks_found} | "
              f"Accepted: {self.blocks_accepted}", flush=True)
    
    def run(self):
        print(BANNER, flush=True)
        print(f"[Main] 🌊 ShioKaze v{__version__}", flush=True)
        if USE_RUST:
            mode = "🦀 Rust (10x 加速)"
        elif USE_CYTHON:
            mode = "🐍 Cython"
        else:
            mode = "🐢 Pure Python"
        print(f"[Main] 🚀 Mode: {mode}", flush=True)
        print(f"[Main] 🎲 Nonce: {'Random' if self.random_nonce else 'Sequential'}", flush=True)
        print(f"[Main] 💰 Wallet: {self.wallet[:20]}...{self.wallet[-10:]}", flush=True)
        print(f"[Main] 👷 Workers: {self.num_workers}", flush=True)
        print("", flush=True)
        
        # 啟動前自檢
        if not run_self_test():
            print("[Main] ❌ 自檢失敗，停止挖礦！", flush=True)
            return
        print("", flush=True)
        
        if not self.connect():
            return
        
        self.start_workers()
        self.start_time = time.time()
        
        current_template = None
        last_template_time = 0
        last_stats_time = time.time()
        
        try:
            consecutive_failures = 0
            max_failures = 10
            
            while self.running.value:
                now = time.time()
                if now - last_template_time >= 0.5:
                    new_template = self.get_block_template()
                    
                    if new_template is None:
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            print(f"[Main] ⚠️ 連續 {max_failures} 次失敗，重連...", flush=True)
                            self._handle_disconnect()
                            consecutive_failures = 0
                        continue
                    
                    consecutive_failures = 0
                    if new_template:
                        if (not current_template or 
                            new_template['pre_pow_hash'] != current_template['pre_pow_hash']):
                            
                            current_template = new_template
                            self.template_count += 1
                            
                            tid = new_template['id']
                            self.template_cache[tid] = new_template
                            self.template_ids.append(tid)
                            while len(self.template_ids) > 100:
                                old_id = self.template_ids.popleft()
                                self.template_cache.pop(old_id, None)
                            
                            # 不傳 matrix，讓 worker 自己生成（避免序列化問題）
                            self.shared_state['template'] = {
                                'pre_pow_hash': new_template['pre_pow_hash'],
                                'timestamp': new_template['timestamp'],
                                'target': new_template['target'],
                                'target_bytes': new_template['target_bytes'],
                                'id': new_template['id']
                            }
                            
                            bits_hex = f"0x{new_template['bits']:08x}"
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌊 "
                                  f"Template #{self.template_count}: bits={bits_hex}", flush=True)
                    
                    last_template_time = now
                
                while not self.result_queue.empty():
                    try:
                        result = self.result_queue.get_nowait()
                        if result['type'] == 'found':
                            self.blocks_found += 1
                            print(f"[Main] ✨ 💎 Found nonce: {result['nonce']}", flush=True)
                            
                            submit_template = self.template_cache.get(result['template_id'])
                            if submit_template:
                                if self.submit_block(submit_template, result['nonce']):
                                    self.blocks_accepted += 1
                            else:
                                print(f"[Main] ⚠️ Template expired", flush=True)
                    except:
                        break
                
                if now - last_stats_time >= 1.0:
                    self.print_stats()
                    last_stats_time = now
                
                time.sleep(0.05)
        
        except KeyboardInterrupt:
            print("\n[Main] 🛑 收到停止信號...", flush=True)
        
        finally:
            self.stop_workers()
            runtime = time.time() - self.start_time
            avg_hr = self.total_hashes / max(runtime, 1)
            
            print(f"\n[Main] 📊 總結:", flush=True)
            print(f"       運行時間: {runtime:.1f} 秒", flush=True)
            print(f"       總 Hash: {self.total_hashes:,}", flush=True)
            print(f"       平均算力: {avg_hr:,.0f} H/s", flush=True)
            print(f"       發現: {self.blocks_found}", flush=True)
            print(f"       接受: {self.blocks_accepted}", flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ShioKaze v6 - Rust Turbo Edition 🦀")
    parser.add_argument('--testnet', action='store_true', help='Use testnet')
    parser.add_argument('--wallet', '-w', required=True, help='Kaspa wallet address')
    parser.add_argument('--workers', '-n', type=int, default=4, help='Number of workers')
    parser.add_argument('--address', '-a', help='gRPC address (auto-detect if not set)')
    parser.add_argument('--random-nonce', '-r', action='store_true', 
                        help='Use random nonce (better luck for slow miners)')
    
    args = parser.parse_args()
    
    if args.address:
        address = args.address
    elif args.testnet:
        address = "localhost:16210"
    else:
        address = "localhost:16110"
    
    miner = ShioKazeMiner(
        address=address,
        wallet=args.wallet,
        num_workers=args.workers,
        random_nonce=args.random_nonce
    )
    
    miner.run()

if __name__ == "__main__":
    main()
