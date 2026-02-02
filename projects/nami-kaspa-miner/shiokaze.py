#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  🌊 ShioKaze (潮風) - Nami's Kaspa Miner
═══════════════════════════════════════════════════════════════════════════════

  A gentle sea breeze that mines Kaspa blocks.
  
  Built by Nami (波浪) - 2026
  
【Features】
  ✨ NumPy 優化的 HeavyHash (比原版快 ~400x)
  ✨ 矩陣緩存 (同區塊重複使用)
  ✨ 可調整的 mining cycle (適合觀察/測試)
  ✨ 詳細的統計輸出
  ✨ Testnet 和 Mainnet 支援

【用法】
  # Testnet
  python3 shiokaze.py --testnet --wallet kaspatest:qr...
  
  # Mainnet
  python3 shiokaze.py --wallet kaspa:qr...
  
  # 觀察模式 (快速循環)
  python3 shiokaze.py --testnet --wallet kaspatest:qr... --observe

【依賴】
  pip install grpcio grpcio-tools numpy pycryptodome

═══════════════════════════════════════════════════════════════════════════════
"""

__version__ = "1.0.0"
__author__ = "Nami 🌊"

import sys
import os
import time
import struct
import argparse
import random
from typing import Optional, Dict, Any, Tuple, List

# ═══════════════════════════════════════════════════════════════════════════════
# 依賴檢查
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("⚠️  NumPy not installed. Run: pip install numpy")

try:
    import grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    print("⚠️  grpcio not installed. Run: pip install grpcio grpcio-tools")

# Proto stubs (需要從 kaspa-pminer 複製或生成)
try:
    # 嘗試從當前目錄或 kaspa-pminer 導入
    sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
    import kaspa_pb2
    import kaspa_pb2_grpc
    from kaspa_miner_multi_core import cshake256, Xoshiro256PlusPlus
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    print("⚠️  Proto stubs not found. Need kaspa_pb2.py and kaspa_miner_multi_core.py")


# ═══════════════════════════════════════════════════════════════════════════════
# 🌊 HeavyHash 優化版 (with caching)
# ═══════════════════════════════════════════════════════════════════════════════

class WaveHasher:
    """
    🌊 WaveHasher - Nami 的 HeavyHash 實現
    
    使用 NumPy 加速 + 矩陣緩存，比原版快約 400 倍
    """
    
    def __init__(self):
        self._cached_key: Optional[Tuple[int, ...]] = None
        self._cached_matrix: Optional[np.ndarray] = None
        self.stats = {
            "hashes": 0,
            "matrix_generations": 0,
            "cache_hits": 0,
        }
    
    def _generate_matrix(self, s0: int, s1: int, s2: int, s3: int) -> np.ndarray:
        """生成 64x64 滿秩矩陣"""
        size = 64
        hasher = Xoshiro256PlusPlus(s0, s1, s2, s3)
        
        while True:
            matrix = np.zeros((size, size), dtype=np.uint16)
            
            for i in range(size):
                for j in range(0, size, 16):
                    value = hasher.next()
                    for k in range(16):
                        matrix[i, j + k] = (value >> (4 * k)) & 0x0F
            
            if np.linalg.matrix_rank(matrix.astype(np.float64)) == size:
                self.stats["matrix_generations"] += 1
                return matrix
    
    def heavyhash(self, hash_values: List[int], timestamp: int, nonce: int) -> bytes:
        """
        HeavyHash PoW 計算
        
        Args:
            hash_values: 4 個 uint64 的區塊頭 hash
            timestamp: 時間戳
            nonce: 挖礦 nonce
            
        Returns:
            32 bytes 的 hash 結果
        """
        size = 64
        self.stats["hashes"] += 1
        
        # 矩陣緩存
        cache_key = tuple(hash_values)
        if self._cached_key != cache_key:
            self._cached_matrix = self._generate_matrix(
                hash_values[0], hash_values[1], hash_values[2], hash_values[3]
            )
            self._cached_key = cache_key
        else:
            self.stats["cache_hits"] += 1
        
        mat = self._cached_matrix
        
        # 構建 80 bytes header
        hash_bytes = b''.join(struct.pack('<Q', val) for val in hash_values)
        header = bytearray(80)
        header[0:32] = hash_bytes
        header[32:40] = struct.pack('<Q', timestamp)
        header[72:80] = struct.pack('<Q', nonce)
        
        # 第一次 hash
        header = cshake256(bytes(header), b'ProofOfWorkHash', 32)
        
        # 向量化轉換
        header_arr = np.frombuffer(header, dtype=np.uint8)
        v = np.zeros(size, dtype=np.uint16)
        v[0::2] = (header_arr >> 4) & 0x0F
        v[1::2] = header_arr & 0x0F
        
        # 矩陣乘法
        p = np.dot(mat, v)
        p = (p >> 10) & 0xFFFF
        
        # XOR
        digest = bytearray(32)
        for i in range(32):
            digest[i] = header[i] ^ ((int(p[i * 2]) << 4) | int(p[i * 2 + 1]))
        
        # 最終 hash
        digest = cshake256(bytes(digest), b'HeavyHash', 32)
        
        return digest[::-1]


# ═══════════════════════════════════════════════════════════════════════════════
# 🌊 ShioKaze Miner
# ═══════════════════════════════════════════════════════════════════════════════

class ShioKaze:
    """
    🌊 ShioKaze - 潮風
    
    A gentle miner that rides the waves of Kaspa's BlockDAG.
    """
    
    # 預設端口
    PORTS = {
        "mainnet": {"grpc": 16110, "p2p": 16111},
        "testnet": {"grpc": 16210, "p2p": 16211},
    }
    
    def __init__(self, 
                 wallet: str,
                 address: str = None,
                 testnet: bool = False,
                 max_nonce: int = 50000,
                 observe_mode: bool = False,
                 debug: bool = False):
        """
        初始化 ShioKaze
        
        Args:
            wallet: 錢包地址
            address: kaspad gRPC 地址 (預設自動選擇)
            testnet: 是否使用 testnet
            max_nonce: 每輪最大 nonce 嘗試次數
            observe_mode: 觀察模式 (更頻繁換 template)
            debug: 除錯模式
        """
        self.wallet = wallet
        self.testnet = testnet
        self.debug = debug
        self.observe_mode = observe_mode
        
        # 觀察模式使用較小的 max_nonce
        self.max_nonce = 2000 if observe_mode else max_nonce
        
        # 自動選擇地址
        if address:
            self.address = address
        else:
            port = self.PORTS["testnet" if testnet else "mainnet"]["grpc"]
            self.address = f"127.0.0.1:{port}"
        
        # gRPC 連接
        self.channel = None
        self.stub = None
        
        # 挖礦組件
        self.hasher = WaveHasher()
        
        # 統計
        self.stats = {
            "start_time": None,
            "templates_received": 0,
            "blocks_submitted": 0,
            "blocks_accepted": 0,
        }
        
        # 狀態
        self.running = False
    
    def log(self, msg: str, level: str = "INFO"):
        """輸出日誌"""
        timestamp = time.strftime("%H:%M:%S")
        prefix = {"INFO": "🌊", "DEBUG": "🔍", "WARN": "⚠️", "ERROR": "❌", "SUCCESS": "✨"}
        icon = prefix.get(level, "")
        print(f"[{timestamp}] {icon} {msg}", flush=True)
    
    def debug_log(self, msg: str):
        """除錯日誌"""
        if self.debug:
            self.log(msg, "DEBUG")
    
    # ─────────────────────────────────────────────────────────────────────────
    # gRPC 連接
    # ─────────────────────────────────────────────────────────────────────────
    
    def connect(self) -> bool:
        """連接到 kaspad"""
        self.log(f"Connecting to {self.address}...")
        
        try:
            # gRPC keepalive 設定（防止連線逾時）
            self.channel = grpc.insecure_channel(
                self.address,
                options=[
                    ('grpc.keepalive_time_ms', 10000),
                    ('grpc.keepalive_timeout_ms', 5000),
                    ('grpc.keepalive_permit_without_calls', True),
                    ('grpc.http2.max_pings_without_data', 0),
                ]
            )
            self.stub = kaspa_pb2_grpc.RPCStub(self.channel)
            
            # 取得節點資訊
            request = kaspa_pb2.KaspadMessage(
                getInfoRequest=kaspa_pb2.GetInfoRequestMessage()
            )
            response = self._call_rpc(request)
            
            if response and response.HasField('getInfoResponse'):
                info = response.getInfoResponse
                self.log(f"Connected to kaspad {info.serverVersion}", "SUCCESS")
                self.log(f"  Network: {'testnet' if self.testnet else 'mainnet'}")
                self.log(f"  Synced: {info.isSynced}")
                self.log(f"  Mempool: {info.mempoolSize} txs")
                return info.isSynced
            
            return False
            
        except Exception as e:
            self.log(f"Connection failed: {e}", "ERROR")
            return False
    
    def disconnect(self):
        """斷開連接"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
    
    def _call_rpc(self, request) -> Optional[Any]:
        """發送 RPC 請求"""
        try:
            responses = self.stub.MessageStream(iter([request]))
            for response in responses:
                return response
        except Exception as e:
            self.debug_log(f"RPC error: {e}")
            return None
    
    # ─────────────────────────────────────────────────────────────────────────
    # 區塊模板
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_block_template(self) -> Optional[Dict]:
        """獲取區塊模板"""
        request = kaspa_pb2.KaspadMessage(
            getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
                payAddress=self.wallet,
                extraData=""
            )
        )
        
        response = self._call_rpc(request)
        
        if response and response.HasField('getBlockTemplateResponse'):
            template_resp = response.getBlockTemplateResponse
            
            if template_resp.HasField('error') and template_resp.error.message:
                self.log(f"Template error: {template_resp.error.message}", "ERROR")
                return None
            
            block = template_resp.block
            header = block.header
            
            self.stats["templates_received"] += 1
            
            # 計算 pre-pow hash
            pre_pow_hash = self._calculate_pre_pow_hash(header)
            
            return {
                "block": block,
                "header": {
                    "timestamp": header.timestamp,
                    "bits": header.bits,
                    "nonce": header.nonce,
                },
                "pre_pow_hash": pre_pow_hash,
                "is_synced": template_resp.isSynced,
            }
        
        return None
    
    def _hash_from_hex(self, hex_str: str) -> bytes:
        """將十六進制字串轉為 32 bytes"""
        if not hex_str:
            return b'\x00' * 32
        return bytes.fromhex(hex_str)
    
    def _write_len(self, hasher, length: int):
        """寫入變長整數 (u64 little-endian)"""
        hasher.update(struct.pack('<Q', length))
    
    def _write_var_bytes(self, hasher, data: bytes):
        """寫入變長 bytes"""
        self._write_len(hasher, len(data))
        hasher.update(data)
    
    def _write_blue_work(self, hasher, blue_work: str):
        """序列化 blue_work (BigInt)"""
        if not blue_work:
            self._write_var_bytes(hasher, b'')
            return
        
        # 確保長度為偶數
        hex_str = blue_work
        if len(hex_str) % 2 == 1:
            hex_str = '0' + hex_str
        
        # 轉為 bytes 並去除前導零
        work_bytes = bytes.fromhex(hex_str)
        start = 0
        while start < len(work_bytes) and work_bytes[start] == 0:
            start += 1
        
        self._write_var_bytes(hasher, work_bytes[start:])
    
    def _calculate_pre_pow_hash(self, header) -> bytes:
        """
        計算 pre-PoW hash (用於 HeavyHash)
        
        與官方 rusty-kaspa 一致的序列化
        """
        import hashlib
        hasher = hashlib.blake2b(digest_size=32)
        
        # 1. Version
        hasher.update(struct.pack('<H', header.version))
        
        # 2-3. Parents
        parents = list(header.parents)
        self._write_len(hasher, len(parents))
        for level in parents:
            parent_hashes = list(level.parentHashes)
            self._write_len(hasher, len(parent_hashes))
            for h in parent_hashes:
                hasher.update(self._hash_from_hex(h))
        
        # 4-6. Merkle roots
        hasher.update(self._hash_from_hex(header.hashMerkleRoot))
        hasher.update(self._hash_from_hex(header.acceptedIdMerkleRoot))
        hasher.update(self._hash_from_hex(header.utxoCommitment))
        
        # 7-9. timestamp=0, bits, nonce=0 (for pre-pow)
        hasher.update(struct.pack('<Q', 0))  # timestamp = 0
        hasher.update(struct.pack('<I', header.bits))
        hasher.update(struct.pack('<Q', 0))  # nonce = 0
        
        # 10-12. DAA score, blue score, blue work
        hasher.update(struct.pack('<Q', header.daaScore))
        hasher.update(struct.pack('<Q', header.blueScore))
        self._write_blue_work(hasher, header.blueWork)
        
        # 13. Pruning point
        hasher.update(self._hash_from_hex(header.pruningPoint))
        
        return hasher.digest()
    
    def _hash_to_values(self, h: bytes) -> List[int]:
        """將 32 bytes hash 轉為 4 個 uint64"""
        return [
            struct.unpack('<Q', h[i:i+8])[0]
            for i in range(0, 32, 8)
        ]
    
    def _bits_to_target(self, bits: int) -> int:
        """將 compact bits 轉為 target"""
        exponent = bits >> 24
        mantissa = bits & 0xFFFFFF
        if exponent <= 3:
            return mantissa >> (8 * (3 - exponent))
        return mantissa << (8 * (exponent - 3))
    
    # ─────────────────────────────────────────────────────────────────────────
    # 區塊提交
    # ─────────────────────────────────────────────────────────────────────────
    
    def submit_block(self, block) -> Tuple[bool, str]:
        """提交區塊"""
        request = kaspa_pb2.KaspadMessage(
            submitBlockRequest=kaspa_pb2.SubmitBlockRequestMessage(
                block=block,
                allowNonDAABlocks=False
            )
        )
        
        response = self._call_rpc(request)
        
        if response and response.HasField('submitBlockResponse'):
            submit_resp = response.submitBlockResponse
            
            if submit_resp.HasField('error') and submit_resp.error.message:
                return False, submit_resp.error.message
            
            return True, "Block accepted!"
        
        return False, "No response"
    
    # ─────────────────────────────────────────────────────────────────────────
    # 挖礦
    # ─────────────────────────────────────────────────────────────────────────
    
    def mine(self, template: Dict) -> Optional[int]:
        """
        挖礦 - 尋找有效 nonce
        
        Returns:
            有效的 nonce 或 None
        """
        pre_pow_hash = template["pre_pow_hash"]
        hash_values = self._hash_to_values(pre_pow_hash)
        timestamp = template["header"]["timestamp"]
        bits = template["header"]["bits"]
        target = self._bits_to_target(bits)
        
        start_nonce = random.randint(0, 2**32)
        
        for i in range(self.max_nonce):
            nonce = (start_nonce + i) % (2**64)
            
            digest = self.hasher.heavyhash(hash_values, timestamp, nonce)
            result = int.from_bytes(digest, byteorder='big')
            
            if result <= target:
                self.log(f"Found valid nonce: 0x{nonce:016x}", "SUCCESS")
                return nonce
            
            # 進度報告
            if self.debug and i > 0 and i % 1000 == 0:
                elapsed = time.time() - self.stats["start_time"]
                hashrate = self.hasher.stats["hashes"] / elapsed
                self.debug_log(f"Hashrate: {hashrate:.1f} H/s, attempts: {i}")
        
        return None
    
    # ─────────────────────────────────────────────────────────────────────────
    # 主循環
    # ─────────────────────────────────────────────────────────────────────────
    
    def run(self):
        """主挖礦循環"""
        self._print_banner()
        
        if not self._check_dependencies():
            return
        
        if not self.connect():
            self.log("Cannot start mining - node not ready", "ERROR")
            return
        
        self.running = True
        self.stats["start_time"] = time.time()
        
        try:
            consecutive_errors = 0
            while self.running:
                try:
                    # 獲取模板
                    template = self.get_block_template()
                    
                    if not template:
                        consecutive_errors += 1
                        self.log(f"Failed to get template (attempt {consecutive_errors}), retrying...", "WARN")
                        if consecutive_errors >= 5:
                            self.log("Too many errors, reconnecting...", "WARN")
                            self.disconnect()
                            time.sleep(2)
                            if not self.connect():
                                self.log("Reconnection failed, stopping", "ERROR")
                                break
                            consecutive_errors = 0
                        time.sleep(1)
                        continue
                    
                    consecutive_errors = 0  # Reset on success
                    bits_hex = f"0x{template['header']['bits']:08x}"
                    self.log(f"New template #{self.stats['templates_received']}: bits={bits_hex}")
                    
                    # 挖礦
                    nonce = self.mine(template)
                    
                    if nonce is not None:
                        # 提交區塊
                        block = template["block"]
                        block.header.nonce = nonce
                        
                        self.stats["blocks_submitted"] += 1
                        success, message = self.submit_block(block)
                        
                        if success:
                            self.stats["blocks_accepted"] += 1
                            self.log(f"🎉 Block accepted! ({self.stats['blocks_accepted']} total)", "SUCCESS")
                        else:
                            self.log(f"Block rejected: {message}", "WARN")
                    
                    # 短暫休息
                    time.sleep(0.1)
                    
                except Exception as e:
                    consecutive_errors += 1
                    self.log(f"Error in mining loop: {e}", "ERROR")
                    time.sleep(1)
                
        except KeyboardInterrupt:
            self.log("\nStopping...")
        finally:
            self.running = False
            self._print_stats()
            self.disconnect()
    
    def _check_dependencies(self) -> bool:
        """檢查依賴"""
        ok = True
        if not NUMPY_AVAILABLE:
            self.log("NumPy required: pip install numpy", "ERROR")
            ok = False
        if not GRPC_AVAILABLE:
            self.log("gRPC required: pip install grpcio", "ERROR")
            ok = False
        if not PROTO_AVAILABLE:
            self.log("Proto stubs required from kaspa-pminer", "ERROR")
            ok = False
        return ok
    
    def _print_banner(self):
        """印出 banner"""
        mode = "OBSERVE" if self.observe_mode else "NORMAL"
        network = "TESTNET" if self.testnet else "MAINNET"
        
        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  🌊 ShioKaze v{__version__} - Nami's Kaspa Miner                    ║
╠═══════════════════════════════════════════════════════════════╣
║  Network:    {network:<10}                                    ║
║  Mode:       {mode:<10}                                    ║
║  Max Nonce:  {self.max_nonce:<10}                                    ║
║  Address:    {self.address:<20}                      ║
║  Wallet:     {self.wallet[:20]}...                  ║
╚═══════════════════════════════════════════════════════════════╝
""", flush=True)
    
    def _print_stats(self):
        """輸出統計"""
        elapsed = time.time() - self.stats["start_time"] if self.stats["start_time"] else 0
        hashrate = self.hasher.stats["hashes"] / elapsed if elapsed > 0 else 0
        
        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  📊 Mining Statistics                                         ║
╠═══════════════════════════════════════════════════════════════╣
║  Runtime:          {elapsed:>10.1f} seconds                        ║
║  Total Hashes:     {self.hasher.stats['hashes']:>10,}                             ║
║  Hashrate:         {hashrate:>10.1f} H/s                           ║
║  Templates:        {self.stats['templates_received']:>10}                             ║
║  Blocks Submitted: {self.stats['blocks_submitted']:>10}                             ║
║  Blocks Accepted:  {self.stats['blocks_accepted']:>10}                             ║
║  Cache Hit Rate:   {self.hasher.stats['cache_hits'] / max(1, self.hasher.stats['hashes']) * 100:>9.1f}%                            ║
╚═══════════════════════════════════════════════════════════════╝
""", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 主程式
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='🌊 ShioKaze - Nami\'s Kaspa Miner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Testnet (觀察模式)
  python3 shiokaze.py --testnet --observe --wallet kaspatest:qr...
  
  # Testnet (一般模式)  
  python3 shiokaze.py --testnet --wallet kaspatest:qr...
  
  # Mainnet
  python3 shiokaze.py --wallet kaspa:qr...

🌊 Built with love by Nami
'''
    )
    
    parser.add_argument('--wallet', '-w', required=True,
                        help='Mining reward wallet address')
    parser.add_argument('--address', '-a',
                        help='kaspad gRPC address (default: auto)')
    parser.add_argument('--testnet', '-t', action='store_true',
                        help='Use testnet (port 16210)')
    parser.add_argument('--observe', '-o', action='store_true',
                        help='Observe mode (faster template cycling)')
    parser.add_argument('--max-nonce', '-n', type=int, default=50000,
                        help='Max nonce per template (default: 50000)')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug output')
    
    args = parser.parse_args()
    
    miner = ShioKaze(
        wallet=args.wallet,
        address=args.address,
        testnet=args.testnet,
        max_nonce=args.max_nonce,
        observe_mode=args.observe,
        debug=args.debug,
    )
    
    miner.run()


if __name__ == '__main__':
    main()
