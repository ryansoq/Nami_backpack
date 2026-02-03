# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
"""
Kaspa PoW - Cython 高效能版本
kHeavyHash 算法核心
"""

import cython
from libc.stdint cimport uint8_t, uint16_t, uint64_t
from libc.string cimport memcpy, memset

import hashlib
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
    cdef double temp
    
    # 複製到浮點數矩陣
    for i in range(size):
        row_selected[i] = False
        for j in range(size):
            mat_float[i][j] = <double>matrix[i, j]
    
    # 高斯消去法
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


cdef void generate_matrix_internal(uint64_t s0, uint64_t s1, uint64_t s2, uint64_t s3, 
                                    uint16_t[:, :] out_matrix):
    """生成 64x64 滿秩矩陣"""
    cdef Xoshiro256PlusPlus rng
    cdef int i, j, k
    cdef uint64_t val
    
    while True:
        rng = Xoshiro256PlusPlus(s0, s1, s2, s3)
        
        for i in range(64):
            for j in range(0, 64, 16):
                val = rng.next_uint64()
                for k in range(16):
                    out_matrix[i, j + k] = (val >> (4 * k)) & 0x0F
        
        if compute_rank(out_matrix) == 64:
            return
        
        # 如果不是滿秩，用 rng 的新狀態重試
        s0 = rng.s0
        s1 = rng.s1
        s2 = rng.s2
        s3 = rng.s3


def generate_matrix(uint64_t s0, uint64_t s1, uint64_t s2, uint64_t s3):
    """Python 接口：生成滿秩矩陣"""
    import numpy as np
    cdef uint16_t[:, :] matrix = np.zeros((64, 64), dtype=np.uint16)
    generate_matrix_internal(s0, s1, s2, s3, matrix)
    return np.asarray(matrix)


# ═══════════════════════════════════════════════════════════════════════════════
# HeavyHash Core
# ═══════════════════════════════════════════════════════════════════════════════

cpdef bytes heavyhash(list hash_values, uint64_t timestamp, uint64_t nonce):
    """
    HeavyHash PoW 算法
    
    參數:
        hash_values: [uint64, uint64, uint64, uint64] - pre_pow_hash
        timestamp: uint64 - 時間戳
        nonce: uint64 - 挖礦 nonce
    
    返回:
        bytes(32) - PoW hash 結果
    """
    import numpy as np
    cdef int i, j
    cdef uint64_t s
    
    # 生成矩陣
    cdef uint16_t[:, :] mat = np.zeros((64, 64), dtype=np.uint16)
    generate_matrix_internal(hash_values[0], hash_values[1], hash_values[2], hash_values[3], mat)
    
    # 構建 header (80 bytes)
    cdef bytearray header = bytearray(80)
    cdef uint64_t val
    
    # [0:32] = hash_values
    for i in range(4):
        val = hash_values[i]
        for j in range(8):
            header[i * 8 + j] = (val >> (j * 8)) & 0xFF
    
    # [32:40] = timestamp
    for j in range(8):
        header[32 + j] = (timestamp >> (j * 8)) & 0xFF
    
    # [40:72] = padding (zeros)
    # [72:80] = nonce
    for j in range(8):
        header[72 + j] = (nonce >> (j * 8)) & 0xFF
    
    # 第一次 hash: cSHAKE256("ProofOfWorkHash")
    h = cSHAKE256.new(custom=b'ProofOfWorkHash')
    h.update(bytes(header))
    header = bytearray(h.read(32))
    
    # 轉換為向量 v (64 個 4-bit 值)
    cdef uint8_t[64] v
    for i in range(32):
        v[i * 2] = (header[i] >> 4) & 0x0F
        v[i * 2 + 1] = header[i] & 0x0F
    
    # 矩陣乘法
    cdef uint16_t[64] p
    for i in range(64):
        s = 0
        for j in range(64):
            s += mat[i, j] * v[j]
        p[i] = (s >> 10) & 0xFFFF
    
    # 組合並 XOR
    cdef bytearray digest = bytearray(32)
    for i in range(32):
        digest[i] = header[i] ^ (((p[i * 2] & 0x0F) << 4) | (p[i * 2 + 1] & 0x0F))
    
    # 最終 hash: cSHAKE256("HeavyHash")
    h2 = cSHAKE256.new(custom=b'HeavyHash')
    h2.update(bytes(digest))
    result = h2.read(32)
    
    # 反轉 bytes
    return result[::-1]


cpdef bytes calculate_pow(list hash_values, uint64_t timestamp, uint64_t nonce):
    """計算 PoW hash（供外部調用）"""
    return heavyhash(hash_values, timestamp, nonce)


cpdef bint check_pow(bytes pow_hash, bytes target):
    """檢查 PoW 是否小於目標"""
    return pow_hash < target
