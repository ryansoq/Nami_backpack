#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  🌊 ShioKaze v2.0 (潮風) - Nami's Kaspa Miner
═══════════════════════════════════════════════════════════════════════════════

  Multiprocessing edition - 多核心並行挖礦！
  
  Built by Nami (波浪) - 2026

═══════════════════════════════════════════════════════════════════════════════
  📍 執行流程 (Execution Flow)
═══════════════════════════════════════════════════════════════════════════════

  main()
    │
    ├─► 連接 gRPC (kaspad node)
    │
    └─► [主循環]
          ├─► get_block_template()
          ├─► calculate_pre_pow_hash()     # ⚠️ keyed blake2b!
          │     └─► blake2b(header, key=b"BlockHash")
          ├─► [挖礦] heavy_hash() + NumPy 矩陣緩存
          └─► submit_block()

═══════════════════════════════════════════════════════════════════════════════
"""

__version__ = "2.0.0"
__author__ = "Nami 🌊"

import sys
import os
import time
import struct
import argparse
import hashlib
import multiprocessing as mp
from multiprocessing import Process, Queue, Value, Manager
import ctypes
from typing import Optional, Dict, Any, Tuple, List

# ═══════════════════════════════════════════════════════════════════════════════
# 依賴
# ═══════════════════════════════════════════════════════════════════════════════

import numpy as np
from Crypto.Hash import cSHAKE256

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc

# ═══════════════════════════════════════════════════════════════════════════════
# HeavyHash 核心（獨立函數，可在 worker 中使用）
# ═══════════════════════════════════════════════════════════════════════════════

def xoshiro256_next(state: np.ndarray) -> int:
    """xoshiro256++ PRNG"""
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
    """生成 64x64 HeavyHash 矩陣（4-bit 值）"""
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
    """HeavyHash 計算"""
    # 把 32 bytes 擴展成 64 個 4-bit 值
    header_arr = np.frombuffer(hash_bytes, dtype=np.uint8)
    v = np.zeros(64, dtype=np.uint16)
    v[0::2] = (header_arr >> 4) & 0x0F
    v[1::2] = header_arr & 0x0F
    
    # 矩陣乘法
    p = np.dot(matrix.astype(np.uint64), v.astype(np.uint64))
    p = (p >> 10) & 0xFFFF
    
    # XOR 回原 hash
    digest = bytearray(32)
    for i in range(32):
        digest[i] = hash_bytes[i] ^ ((int(p[i * 2]) << 4) | int(p[i * 2 + 1]))
    
    # 最終 hash
    h = cSHAKE256.new(data=bytes(digest), custom=b"HeavyHash")
    return h.read(32)

def compute_pow(pre_pow_hash: bytes, timestamp: int, nonce: int, matrix: np.ndarray) -> bytes:
    """計算完整 PoW hash"""
    data = pre_pow_hash + struct.pack('<Q', timestamp) + (b'\x00' * 32) + struct.pack('<Q', nonce)
    h = cSHAKE256.new(data=data, custom=b"ProofOfWorkHash")
    pow_hash = h.read(32)
    return heavy_hash(matrix, pow_hash)

def check_target(hash_bytes: bytes, target: int) -> bool:
    """檢查 hash 是否小於 target"""
    hash_int = int.from_bytes(hash_bytes, 'little')
    return hash_int <= target

def bits_to_target(bits: int) -> int:
    """compact bits → target int"""
    exponent = bits >> 24
    mantissa = bits & 0xffffff
    shift = 8 * (exponent - 3)
    return mantissa << shift if shift >= 0 else mantissa >> (-shift)

# ═══════════════════════════════════════════════════════════════════════════════
# Worker 進程
# ═══════════════════════════════════════════════════════════════════════════════

def mine_worker(
    worker_id: int,
    task_queue: mp.Queue,
    result_queue: mp.Queue,
    hash_counter: mp.Value,
    stop_flag: mp.Value,
):
    """Worker: 從 task_queue 取任務，找到 nonce 放入 result_queue"""
    print(f"[Worker {worker_id}] Started", flush=True)
    
    while not stop_flag.value:
        try:
            task = task_queue.get(timeout=0.5)
        except:
            continue
        
        if task is None:  # Poison pill
            break
        
        pre_pow_hash = task['pre_pow_hash']
        timestamp = task['timestamp']
        bits = task['bits']
        nonce_start = task['nonce_start']
        nonce_end = task['nonce_end']
        template_id = task['template_id']
        
        target = bits_to_target(bits)
        matrix = generate_matrix(pre_pow_hash)
        
        local_hashes = 0
        for nonce in range(nonce_start, nonce_end):
            if stop_flag.value:
                break
            
            result_hash = compute_pow(pre_pow_hash, timestamp, nonce, matrix)
            local_hashes += 1
            
            if local_hashes % 500 == 0:
                with hash_counter.get_lock():
                    hash_counter.value += 500
            
            if check_target(result_hash, target):
                print(f"[Worker {worker_id}] 💎 FOUND nonce={nonce}", flush=True)
                result_queue.put({
                    'worker_id': worker_id,
                    'nonce': nonce,
                    'hash': result_hash.hex(),
                    'template_id': template_id,
                })
                break
        
        # 更新剩餘的 hash 計數
        remaining = local_hashes % 500
        if remaining:
            with hash_counter.get_lock():
                hash_counter.value += remaining

# ═══════════════════════════════════════════════════════════════════════════════
# 主礦工
# ═══════════════════════════════════════════════════════════════════════════════

class ShioKazeV2:
    def __init__(self, wallet: str, testnet: bool = False, num_workers: int = None):
        self.wallet = wallet
        self.testnet = testnet
        self.address = f"127.0.0.1:{16210 if testnet else 16110}"
        self.num_workers = num_workers or mp.cpu_count()
        
        self.channel = None
        self.stub = None
        self.current_block = None
        
        self.task_queue = mp.Queue()
        self.result_queue = mp.Queue()
        self.hash_counter = mp.Value(ctypes.c_uint64, 0)
        self.stop_flag = mp.Value(ctypes.c_int, 0)
        
        self.workers = []
        self.stats = {'templates': 0, 'submitted': 0, 'accepted': 0, 'start': None}
        self.template_id = 0
    
    def log(self, msg: str, level: str = "INFO"):
        ts = time.strftime("%H:%M:%S")
        prefix = {"INFO": "🌊", "WARN": "⚠️", "ERROR": "❌", "SUCCESS": "✨"}.get(level, "")
        print(f"[{ts}] {prefix} {msg}", flush=True)
    
    def connect(self) -> bool:
        try:
            self.channel = grpc.insecure_channel(self.address)
            self.stub = kaspa_pb2_grpc.RPCStub(self.channel)
            req = kaspa_pb2.KaspadMessage(getInfoRequest=kaspa_pb2.GetInfoRequestMessage())
            resp = next(self.stub.MessageStream(iter([req])))
            if resp.HasField('getInfoResponse'):
                info = resp.getInfoResponse
                self.log(f"Connected to kaspad {info.serverVersion}", "SUCCESS")
                self.log(f"  Synced: {info.isSynced}")
                return info.isSynced
        except Exception as e:
            self.log(f"Connection failed: {e}", "ERROR")
        return False
    
    def _hash_from_hex(self, h: str) -> bytes:
        return bytes.fromhex(h) if h else b'\x00' * 32
    
    def _compute_pre_pow_hash(self, header) -> bytes:
        hasher = hashlib.blake2b(digest_size=32, key=b"BlockHash")
        hasher.update(struct.pack('<H', header.version))
        parents = list(header.parents)
        hasher.update(struct.pack('<Q', len(parents)))
        for level in parents:
            hashes = list(level.parentHashes)
            hasher.update(struct.pack('<Q', len(hashes)))
            for h in hashes:
                hasher.update(self._hash_from_hex(h))
        hasher.update(self._hash_from_hex(header.hashMerkleRoot))
        hasher.update(self._hash_from_hex(header.acceptedIdMerkleRoot))
        hasher.update(self._hash_from_hex(header.utxoCommitment))
        hasher.update(struct.pack('<Q', 0))  # timestamp=0
        hasher.update(struct.pack('<I', header.bits))
        hasher.update(struct.pack('<Q', 0))  # nonce=0
        hasher.update(struct.pack('<Q', header.daaScore))
        hasher.update(struct.pack('<Q', header.blueScore))
        # blue_work
        bw = header.blueWork
        if bw:
            if len(bw) % 2: bw = '0' + bw
            bw_bytes = bytes.fromhex(bw)
            hasher.update(struct.pack('<Q', len(bw_bytes)))
            hasher.update(bw_bytes)
        else:
            hasher.update(struct.pack('<Q', 0))
        hasher.update(self._hash_from_hex(header.pruningPoint))
        return hasher.digest()
    
    def get_template(self) -> Optional[Dict]:
        try:
            req = kaspa_pb2.KaspadMessage(
                getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
                    payAddress=self.wallet, extraData=""
                )
            )
            resp = next(self.stub.MessageStream(iter([req])))
            if resp.HasField('getBlockTemplateResponse'):
                tmpl = resp.getBlockTemplateResponse
                if tmpl.HasField('error'):
                    return None
                self.current_block = tmpl.block
                header = tmpl.block.header
                return {
                    'pre_pow_hash': self._compute_pre_pow_hash(header),
                    'timestamp': header.timestamp,
                    'bits': header.bits,
                }
        except Exception as e:
            self.log(f"Template error: {e}", "ERROR")
        return None
    
    def submit_block(self, nonce: int) -> Tuple[bool, str]:
        if not self.current_block:
            return False, "No block"
        try:
            block = kaspa_pb2.RpcBlock()
            block.CopyFrom(self.current_block)
            block.header.nonce = nonce
            req = kaspa_pb2.KaspadMessage(
                submitBlockRequest=kaspa_pb2.SubmitBlockRequestMessage(
                    block=block, allowNonDAABlocks=True
                )
            )
            resp = next(self.stub.MessageStream(iter([req])))
            if resp.HasField('submitBlockResponse'):
                r = resp.submitBlockResponse
                if r.rejectReason:
                    return False, f"Rejected: {r.rejectReason}"
                return True, "Accepted!"
        except Exception as e:
            return False, str(e)
        return False, "Unknown"
    
    def start_workers(self):
        self.log(f"Starting {self.num_workers} workers...")
        for i in range(self.num_workers):
            p = Process(target=mine_worker, args=(
                i, self.task_queue, self.result_queue, 
                self.hash_counter, self.stop_flag
            ), daemon=True)
            p.start()
            self.workers.append(p)
        self.log(f"✨ {self.num_workers} workers started!")
    
    def dispatch_tasks(self, template: Dict):
        """分發挖礦任務給 workers"""
        self.template_id += 1
        nonces_per_worker = 100000
        
        for i in range(self.num_workers):
            task = {
                'pre_pow_hash': template['pre_pow_hash'],
                'timestamp': template['timestamp'],
                'bits': template['bits'],
                'nonce_start': i * nonces_per_worker,
                'nonce_end': (i + 1) * nonces_per_worker,
                'template_id': self.template_id,
            }
            self.task_queue.put(task)
    
    def run(self):
        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  🌊 ShioKaze v{__version__} - Multiprocessing Miner           ║
╠═══════════════════════════════════════════════════════════════╣
║  Network:    {'TESTNET' if self.testnet else 'MAINNET':<10}                                 ║
║  Workers:    {self.num_workers:<10}                                 ║
║  Address:    {self.address:<20}                   ║
╚═══════════════════════════════════════════════════════════════╝
""", flush=True)
        
        if not self.connect():
            return
        
        self.start_workers()
        self.stats['start'] = time.time()
        
        last_report = time.time()
        last_hashes = 0
        
        try:
            while True:
                # 取得新 template 並分發
                template = self.get_template()
                if template:
                    self.stats['templates'] += 1
                    bits_hex = f"0x{template['bits']:08x}"
                    self.log(f"Template #{self.stats['templates']}: bits={bits_hex}")
                    self.dispatch_tasks(template)
                
                # 檢查結果
                while not self.result_queue.empty():
                    try:
                        result = self.result_queue.get_nowait()
                        self.log(f"💎 Found nonce: {result['nonce']}", "SUCCESS")
                        self.stats['submitted'] += 1
                        ok, msg = self.submit_block(result['nonce'])
                        if ok:
                            self.stats['accepted'] += 1
                            self.log(f"🎉 Block accepted! (#{self.stats['accepted']})", "SUCCESS")
                        else:
                            self.log(f"Block rejected: {msg}", "WARN")
                    except:
                        break
                
                # Hashrate 報告
                now = time.time()
                if now - last_report >= 5:
                    current = self.hash_counter.value
                    rate = (current - last_hashes) / (now - last_report)
                    avg = current / (now - self.stats['start'])
                    self.log(f"⚡ Hashrate: {rate:,.0f} H/s (avg: {avg:,.0f} H/s)")
                    last_report = now
                    last_hashes = current
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            self.log("Shutting down...")
            self.stop_flag.value = 1
            for _ in self.workers:
                self.task_queue.put(None)

def main():
    parser = argparse.ArgumentParser(description='🌊 ShioKaze v2')
    parser.add_argument('--wallet', '-w', required=True)
    parser.add_argument('--testnet', '-t', action='store_true')
    parser.add_argument('--workers', '-n', type=int)
    args = parser.parse_args()
    
    miner = ShioKazeV2(wallet=args.wallet, testnet=args.testnet, num_workers=args.workers)
    miner.run()

if __name__ == '__main__':
    main()
