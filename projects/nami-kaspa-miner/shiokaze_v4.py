#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  🌊 ShioKaze v4.0 (潮風) - Nami's Kaspa Miner
═══════════════════════════════════════════════════════════════════════════════

  The complete edition - 完整優化版！
  
  Built by Nami (波浪) - 2026

【v4 新功能】
  ✨ 多進程並行挖礦
  ✨ 智能 nonce 分配（跳躍式搜索）
  ✨ 共享狀態監控
  ✨ 自動重連機制
  ✨ 更精確的 hashrate 統計
  ✨ 乾淨的日誌輸出

【用法】
  python3 shiokaze_v4.py --testnet --wallet kaspatest:qq... --workers 4

═══════════════════════════════════════════════════════════════════════════════
"""

__version__ = "4.0.0"
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
from typing import Optional, Tuple
from datetime import datetime
from collections import deque

import numpy as np
from Crypto.Hash import cSHAKE256
import grpc

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc

# ═══════════════════════════════════════════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   🌊  ShioKaze v4.0 (潮風)                                                    ║
║       Nami's Kaspa Miner                                                      ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════════════════════════════════════════
# HeavyHash 核心
# ═══════════════════════════════════════════════════════════════════════════════

def xoshiro256_next(state: np.ndarray) -> int:
    """xoshiro256++ PRNG - 用於矩陣生成"""
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

def generate_matrix(hash_bytes: bytes) -> np.ndarray:
    """生成 64x64 HeavyHash 矩陣"""
    state = np.zeros(4, dtype=np.uint64)
    for i in range(4):
        state[i] = int.from_bytes(hash_bytes[i*8:(i+1)*8], 'little')
    
    matrix = np.zeros((64, 64), dtype=np.uint16)
    for i in range(64):
        for j in range(0, 64, 16):
            value = xoshiro256_next(state)
            for k in range(16):
                matrix[i, j + k] = (value >> (4 * k)) & 0x0F
    return matrix

def heavy_hash(matrix: np.ndarray, hash_bytes: bytes) -> bytes:
    """HeavyHash 核心計算"""
    # 展開成 64 個 4-bit 值
    header_arr = np.frombuffer(hash_bytes, dtype=np.uint8)
    v = np.zeros(64, dtype=np.uint16)
    v[0::2] = (header_arr >> 4) & 0x0F
    v[1::2] = header_arr & 0x0F
    
    # 矩陣乘法（NumPy 加速）
    p = np.dot(matrix.astype(np.uint64), v.astype(np.uint64))
    p = (p >> 10) & 0xFFFF
    
    # XOR 回原 hash
    digest = bytearray(32)
    for i in range(32):
        digest[i] = hash_bytes[i] ^ ((int(p[i * 2]) << 4) | int(p[i * 2 + 1]))
    
    # 最終 cSHAKE256
    h = cSHAKE256.new(data=bytes(digest), custom=b"HeavyHash")
    return h.read(32)

def compute_pow(pre_pow_hash: bytes, timestamp: int, nonce: int, matrix: np.ndarray) -> bytes:
    """計算完整 PoW hash"""
    data = pre_pow_hash + struct.pack('<Q', timestamp) + (b'\x00' * 32) + struct.pack('<Q', nonce)
    h = cSHAKE256.new(data=data, custom=b"ProofOfWorkHash")
    pow_hash = h.read(32)
    return heavy_hash(matrix, pow_hash)

def hash_to_int(hash_bytes: bytes) -> int:
    """Hash 轉為大整數（用於比較 target）"""
    return int.from_bytes(hash_bytes, 'little')

def bits_to_target(bits: int) -> int:
    """將 bits 轉換為 target"""
    exponent = (bits >> 24) & 0xFF
    mantissa = bits & 0x00FFFFFF
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target

# ═══════════════════════════════════════════════════════════════════════════════
# Pre-PoW Hash 計算
# ═══════════════════════════════════════════════════════════════════════════════

import hashlib

def hash_from_hex(hex_str: str) -> bytes:
    """將十六進制字串轉為 32 bytes"""
    if not hex_str:
        return b'\x00' * 32
    return bytes.fromhex(hex_str)

def write_len(hasher, length: int):
    """寫入變長整數 (u64 little-endian)"""
    hasher.update(struct.pack('<Q', length))

def write_var_bytes(hasher, data: bytes):
    """寫入變長 bytes"""
    write_len(hasher, len(data))
    hasher.update(data)

def write_blue_work(hasher, blue_work: str):
    """序列化 blue_work (BigInt)"""
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
    """計算 pre-PoW hash（與 rusty-kaspa 一致）"""
    hasher = hashlib.blake2b(digest_size=32)
    
    # 1. Version
    hasher.update(struct.pack('<H', header.version))
    
    # 2-3. Parents
    parents = list(header.parents)
    write_len(hasher, len(parents))
    for level in parents:
        parent_hashes = list(level.parentHashes)
        write_len(hasher, len(parent_hashes))
        for h in parent_hashes:
            hasher.update(hash_from_hex(h))
    
    # 4-6. Merkle roots
    hasher.update(hash_from_hex(header.hashMerkleRoot))
    hasher.update(hash_from_hex(header.acceptedIdMerkleRoot))
    hasher.update(hash_from_hex(header.utxoCommitment))
    
    # 7-9. timestamp=0, bits, nonce=0 (for pre-pow)
    hasher.update(struct.pack('<Q', 0))  # timestamp = 0
    hasher.update(struct.pack('<I', header.bits))
    hasher.update(struct.pack('<Q', 0))  # nonce = 0
    
    # 10-12. DAA score, blue score, blue work
    hasher.update(struct.pack('<Q', header.daaScore))
    hasher.update(struct.pack('<Q', header.blueScore))
    write_blue_work(hasher, header.blueWork)
    
    # 13. Pruning point
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
    """Worker 進程 - 負責實際挖礦"""
    
    log_prefix = f"[Worker {worker_id}]"
    local_hashes = 0
    last_report = time.time()
    
    while running.value:
        # 取得當前 template
        template_data = shared_state.get('template')
        if not template_data:
            time.sleep(0.1)
            continue
        
        pre_pow_hash = template_data['pre_pow_hash']
        timestamp = template_data['timestamp']
        target = template_data['target']
        template_id = template_data['id']
        matrix = template_data['matrix']
        
        # 計算 nonce 範圍（每個 worker 負責不同區段）
        num_workers = shared_state.get('num_workers', 4)
        chunk_size = 0xFFFFFFFFFFFFFFFF // num_workers
        nonce_start = worker_id * chunk_size
        nonce = nonce_start + random.randint(0, chunk_size // 1000)  # 隨機起點
        
        # 挖礦循環
        batch_size = 1000
        while running.value and shared_state.get('template', {}).get('id') == template_id:
            for _ in range(batch_size):
                # 計算 PoW
                pow_hash = compute_pow(pre_pow_hash, timestamp, nonce, matrix)
                hash_val = hash_to_int(pow_hash)
                local_hashes += 1
                
                # 檢查是否符合難度
                if hash_val < target:
                    result_queue.put({
                        'type': 'found',
                        'worker_id': worker_id,
                        'nonce': nonce,
                        'hash': pow_hash.hex(),
                        'template_id': template_id
                    })
                    print(f"{log_prefix} 💎 FOUND nonce={nonce}", flush=True)
                
                nonce += 1
            
            # 更新統計（每秒）
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
    """ShioKaze v4 主礦工"""
    
    def __init__(self, address: str, wallet: str, num_workers: int = 4):
        self.address = address
        self.wallet = wallet
        self.num_workers = num_workers
        
        # 共享狀態
        self.manager = Manager()
        self.shared_state = self.manager.dict()
        self.shared_state['num_workers'] = num_workers
        
        # 統計
        self.stats_array = Array('d', num_workers)  # 每個 worker 的 hash 數
        self.running = Value('b', True)
        self.result_queue = mp.Queue()
        
        # 進程
        self.workers = []
        
        # gRPC
        self.channel = None
        self.stub = None
        
        # 統計追蹤
        self.start_time = None
        self.total_hashes = 0
        self.blocks_found = 0
        self.blocks_accepted = 0
        self.template_count = 0
        self.hashrate_history = deque(maxlen=60)  # 最近 60 秒
    
    def connect(self):
        """連接到 Kaspa 節點"""
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
        
        # 測試連接
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
    
    def _call_rpc(self, request):
        """發送 RPC 請求（使用 MessageStream）"""
        try:
            responses = self.stub.MessageStream(iter([request]))
            for response in responses:
                return response
        except Exception as e:
            print(f"[Main] RPC error: {e}", flush=True)
            return None
    
    def start_workers(self):
        """啟動 worker 進程"""
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
        """停止所有 workers"""
        print(f"[Main] 🛑 停止 workers...", flush=True)
        self.running.value = False
        
        for p in self.workers:
            p.join(timeout=2)
            if p.is_alive():
                p.terminate()
        
        self.workers = []
    
    def get_block_template(self) -> Optional[dict]:
        """取得新的區塊模板"""
        try:
            request = kaspa_pb2.KaspadMessage(
                getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
                    payAddress=self.wallet,
                    extraData="ShioKaze v4"
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
            
            # 計算 pre_pow_hash（需要序列化 header）
            pre_pow_hash = calculate_pre_pow_hash(header)
            timestamp = header.timestamp
            bits = header.bits
            target = bits_to_target(bits)
            
            # 生成矩陣（緩存）
            matrix = generate_matrix(pre_pow_hash)
            
            return {
                'block': block,
                'pre_pow_hash': pre_pow_hash,
                'timestamp': timestamp,
                'bits': bits,
                'target': target,
                'matrix': matrix,
                'id': time.time()  # 用於識別 template
            }
            
        except Exception as e:
            print(f"[Main] ❌ Template error: {e}", flush=True)
            return None
    
    def submit_block(self, template: dict, nonce: int) -> bool:
        """提交區塊"""
        try:
            block = template['block']
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
        """輸出統計"""
        # 計算 hashrate
        current_hashes = sum(self.stats_array)
        self.total_hashes += current_hashes
        self.hashrate_history.append(current_hashes)
        
        # 重置計數器
        for i in range(self.num_workers):
            self.stats_array[i] = 0
        
        avg_hashrate = sum(self.hashrate_history) / max(len(self.hashrate_history), 1)
        runtime = time.time() - self.start_time
        
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] 🌊 ⚡ {current_hashes:,} H/s (avg: {avg_hashrate:,.0f} H/s) | "
              f"Templates: {self.template_count} | Found: {self.blocks_found} | "
              f"Accepted: {self.blocks_accepted}", flush=True)
    
    def run(self):
        """主循環"""
        print(BANNER, flush=True)
        print(f"[Main] 🌊 ShioKaze v{__version__}", flush=True)
        print(f"[Main] 💰 Wallet: {self.wallet[:20]}...{self.wallet[-10:]}", flush=True)
        print(f"[Main] 👷 Workers: {self.num_workers}", flush=True)
        print("", flush=True)
        
        # 連接
        if not self.connect():
            return
        
        # 啟動 workers
        self.start_workers()
        self.start_time = time.time()
        
        # 當前 template
        current_template = None
        last_template_time = 0
        last_stats_time = time.time()
        
        try:
            while self.running.value:
                # 定期取得新 template（每 0.5 秒）
                now = time.time()
                if now - last_template_time >= 0.5:
                    new_template = self.get_block_template()
                    if new_template:
                        # 檢查是否需要更新
                        if (not current_template or 
                            new_template['pre_pow_hash'] != current_template['pre_pow_hash']):
                            
                            current_template = new_template
                            self.template_count += 1
                            
                            # 更新共享狀態
                            self.shared_state['template'] = {
                                'pre_pow_hash': new_template['pre_pow_hash'],
                                'timestamp': new_template['timestamp'],
                                'target': new_template['target'],
                                'matrix': new_template['matrix'],
                                'id': new_template['id']
                            }
                            
                            bits_hex = f"0x{new_template['bits']:08x}"
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌊 "
                                  f"Template #{self.template_count}: bits={bits_hex}", flush=True)
                    
                    last_template_time = now
                
                # 檢查結果
                while not self.result_queue.empty():
                    try:
                        result = self.result_queue.get_nowait()
                        if result['type'] == 'found':
                            self.blocks_found += 1
                            print(f"[Main] ✨ 💎 Found nonce: {result['nonce']}", flush=True)
                            
                            # 提交
                            if current_template and result['template_id'] == current_template['id']:
                                if self.submit_block(current_template, result['nonce']):
                                    self.blocks_accepted += 1
                    except:
                        break
                
                # 定期輸出統計（每秒）
                if now - last_stats_time >= 1.0:
                    self.print_stats()
                    last_stats_time = now
                
                time.sleep(0.05)
        
        except KeyboardInterrupt:
            print("\n[Main] 🛑 收到停止信號...", flush=True)
        
        finally:
            self.stop_workers()
            print(f"\n[Main] 📊 總結:", flush=True)
            print(f"       運行時間: {time.time() - self.start_time:.1f} 秒", flush=True)
            print(f"       總 Hash: {self.total_hashes:,}", flush=True)
            print(f"       發現: {self.blocks_found}", flush=True)
            print(f"       接受: {self.blocks_accepted}", flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ShioKaze v4 - Nami's Kaspa Miner")
    parser.add_argument('--testnet', action='store_true', help='Use testnet')
    parser.add_argument('--wallet', '-w', required=True, help='Kaspa wallet address')
    parser.add_argument('--workers', '-n', type=int, default=4, help='Number of workers')
    parser.add_argument('--address', '-a', help='gRPC address (auto-detect if not set)')
    
    args = parser.parse_args()
    
    # 決定地址
    if args.address:
        address = args.address
    elif args.testnet:
        address = "localhost:16210"
    else:
        address = "localhost:16110"
    
    # 創建礦工
    miner = ShioKazeMiner(
        address=address,
        wallet=args.wallet,
        num_workers=args.workers
    )
    
    # 運行
    miner.run()

if __name__ == "__main__":
    main()
