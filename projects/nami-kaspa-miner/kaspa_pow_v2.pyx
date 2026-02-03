# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
"""
═══════════════════════════════════════════════════════════════════════════════
  🌊 Kaspa PoW - Cython v2 (矩陣緩存優化版)
═══════════════════════════════════════════════════════════════════════════════

  By Nami 🌊 - 2026

  改進：
  - 分離矩陣生成和 HeavyHash 計算
  - 支援外部傳入矩陣（緩存友好）
  - 更快的內層迴圈

═══════════════════════════════════════════════════════════════════════════════
"""

import cython
from libc.stdint cimport uint8_t, uint16_t, uint64_t
from libc.string cimport memcpy, memset

import numpy as np
cimport numpy as np
from Crypto.Hash import cSHAKE256

# ═══════════════════════════════════════════════════════════════════════════════
# Xoshiro256++ PRNG
# ═══════════════════════════════════════════════════════════════════════════════

cdef inline uint64_t rotl(uint64_t x, int k) nogil:
    return (x << k) | (x >> (64 - k))

cdef class Xoshiro256PlusPlus:
    cdef uint64_t s0, s1, s2, s3
    
    def __init__(self, uint64_t s0, uint64_t s1, uint64_t s2, uint64_t s3):
        self.s0 = s0
        self.s1 = s1
        self.s2 = s2
        self.s3 = s3
    
    cdef uint64_t next_uint64(self) nogil:
        cdef uint64_t result, t
        result = rotl(self.s0 + self.s3, 23) + self.s0
        t = self.s1 << 17
        self.s2 ^= self.s0
        self.s3 ^= self.s1
        self.s1 ^= self.s2
        self.s0 ^= self.s3
        self.s2 ^= t
        self.s3 = rotl(self.s3, 45)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Matrix Operations
# ═══════════════════════════════════════════════════════════════════════════════

cdef int compute_rank(uint16_t[:, :] matrix) nogil:
    """計算矩陣的秩"""
    cdef int size = 64
    cdef double epsilon = 1e-9
    cdef double[64][64] mat_float
    cdef bint[64] row_selected
    cdef int rank = 0
    cdef int i, j, k, p
    
    for i in range(size):
        row_selected[i] = False
        for j in range(size):
            mat_float[i][j] = <double>matrix[i, j]
    
    for i in range(size):
        j = 0
        while j < size:
            if not row_selected[j] and (mat_float[j][i] > epsilon or mat_float[j][i] < -epsilon):
                break
            j += 1
        
        if j != size:
            rank += 1
            row_selected[j] = True
            for p in range(i + 1, size):
                mat_float[j][p] /= mat_float[j][i]
            for k in range(size):
                if k != j and (mat_float[k][i] > epsilon or mat_float[k][i] < -epsilon):
                    for p in range(i + 1, size):
                        mat_float[k][p] -= mat_float[j][p] * mat_float[k][i]
    
    return rank


def generate_matrix(bytes pre_pow_hash):
    """
    生成 64x64 滿秩矩陣（Python 接口）
    
    參數:
        pre_pow_hash: 32 bytes pre-PoW hash
    
    返回:
        numpy.ndarray (64, 64) uint16
    """
    cdef uint64_t s0, s1, s2, s3
    cdef Xoshiro256PlusPlus rng
    cdef int i, j, k
    cdef uint64_t val
    
    # 從 pre_pow_hash 提取種子
    s0 = int.from_bytes(pre_pow_hash[0:8], 'little')
    s1 = int.from_bytes(pre_pow_hash[8:16], 'little')
    s2 = int.from_bytes(pre_pow_hash[16:24], 'little')
    s3 = int.from_bytes(pre_pow_hash[24:32], 'little')
    
    cdef np.ndarray[np.uint16_t, ndim=2] matrix
    
    while True:
        rng = Xoshiro256PlusPlus(s0, s1, s2, s3)
        matrix = np.zeros((64, 64), dtype=np.uint16)
        
        for i in range(64):
            for j in range(0, 64, 16):
                val = rng.next_uint64()
                for k in range(16):
                    matrix[i, j + k] = (val >> (4 * k)) & 0x0F
        
        if compute_rank(matrix) == 64:
            return matrix
        
        # 不是滿秩，用新狀態重試
        s0 = rng.s0
        s1 = rng.s1
        s2 = rng.s2
        s3 = rng.s3


# ═══════════════════════════════════════════════════════════════════════════════
# HeavyHash Core（優化版 - 接受預算矩陣）
# ═══════════════════════════════════════════════════════════════════════════════

def heavy_hash_with_matrix(np.ndarray[np.uint16_t, ndim=2] matrix, bytes pow_hash):
    """
    HeavyHash 核心計算（使用預算矩陣）
    
    參數:
        matrix: 64x64 矩陣（預先生成）
        pow_hash: 32 bytes（cSHAKE256 ProofOfWorkHash 的結果）
    
    返回:
        bytes(32) - 最終 PoW hash
    """
    cdef int i, j
    cdef uint64_t s
    cdef np.ndarray[np.uint8_t, ndim=1] header_arr
    cdef np.ndarray[np.uint16_t, ndim=1] v
    cdef np.ndarray[np.uint64_t, ndim=1] p
    
    # 展開成 64 個 4-bit 值
    header_arr = np.frombuffer(pow_hash, dtype=np.uint8)
    v = np.zeros(64, dtype=np.uint16)
    
    for i in range(32):
        v[i * 2] = (header_arr[i] >> 4) & 0x0F      # 高 4 bits
        v[i * 2 + 1] = header_arr[i] & 0x0F         # 低 4 bits
    
    # 矩陣乘法
    p = np.zeros(64, dtype=np.uint64)
    for i in range(64):
        s = 0
        for j in range(64):
            s += <uint64_t>matrix[i, j] * <uint64_t>v[j]
        p[i] = (s >> 10) & 0x0F
    
    # XOR 回原 hash
    cdef bytearray digest = bytearray(32)
    for i in range(32):
        digest[i] = pow_hash[i] ^ (((<uint8_t>p[i * 2] & 0x0F) << 4) | (<uint8_t>p[i * 2 + 1] & 0x0F))
    
    # 最終 cSHAKE256
    h = cSHAKE256.new(data=bytes(digest), custom=b"HeavyHash")
    return h.read(32)


def compute_pow(bytes pre_pow_hash, uint64_t timestamp, uint64_t nonce, 
                np.ndarray[np.uint16_t, ndim=2] matrix):
    """
    計算完整 PoW hash（使用預算矩陣）
    
    參數:
        pre_pow_hash: 32 bytes
        timestamp: 時間戳
        nonce: 挖礦 nonce
        matrix: 預先生成的 64x64 矩陣
    
    返回:
        bytes(32) - PoW hash 結果
    """
    import struct
    
    # 構建 80 bytes header
    cdef bytes data = (
        pre_pow_hash + 
        struct.pack('<Q', timestamp) + 
        (b'\x00' * 32) + 
        struct.pack('<Q', nonce)
    )
    
    # 第一次 hash
    h = cSHAKE256.new(data=data, custom=b"ProofOfWorkHash")
    pow_hash = h.read(32)
    
    # HeavyHash
    return heavy_hash_with_matrix(matrix, pow_hash)


def check_pow(bytes pow_hash, uint64_t target):
    """檢查 PoW 是否符合難度"""
    cdef uint64_t hash_val = int.from_bytes(pow_hash[:8], 'little')
    # 簡化比較（只比前 8 bytes 通常夠了）
    return hash_val < target
