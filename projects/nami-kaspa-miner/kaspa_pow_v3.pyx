# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: initializedcheck=False
"""
═══════════════════════════════════════════════════════════════════════════════
  🌊 Kaspa PoW - Cython v3 (nogil + 純 C 陣列優化版)
═══════════════════════════════════════════════════════════════════════════════

  By Nami 🌊 - 2026

  v3 改進：
  - nogil 釋放 GIL（多線程更有效）
  - 純 C 陣列取代 NumPy（減少開銷）
  - 內層迴圈完全在 C 層執行

═══════════════════════════════════════════════════════════════════════════════
"""

from libc.stdint cimport uint8_t, uint16_t, uint32_t, uint64_t
from libc.string cimport memcpy, memset
from libc.stdlib cimport malloc, free

import numpy as np
cimport numpy as np
from Crypto.Hash import cSHAKE256

# ═══════════════════════════════════════════════════════════════════════════════
# Xoshiro256++ PRNG (nogil)
# ═══════════════════════════════════════════════════════════════════════════════

cdef inline uint64_t rotl(uint64_t x, int k) noexcept nogil:
    return (x << k) | (x >> (64 - k))

cdef inline uint64_t xoshiro_next(uint64_t* s) noexcept nogil:
    """xoshiro256++ - 完全在 C 層執行"""
    cdef uint64_t result = rotl(s[0] + s[3], 23) + s[0]
    cdef uint64_t t = s[1] << 17
    
    s[2] ^= s[0]
    s[3] ^= s[1]
    s[1] ^= s[2]
    s[0] ^= s[3]
    s[2] ^= t
    s[3] = rotl(s[3], 45)
    
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# Matrix Operations (nogil)
# ═══════════════════════════════════════════════════════════════════════════════

cdef int compute_rank_c(uint16_t* matrix) noexcept nogil:
    """計算 64x64 矩陣的秩（純 C）"""
    cdef int size = 64
    cdef double epsilon = 1e-9
    cdef double mat_float[64][64]
    cdef bint row_selected[64]
    cdef int rank = 0
    cdef int i, j, k, p
    cdef double temp
    
    # 複製到浮點數矩陣
    for i in range(size):
        row_selected[i] = False
        for j in range(size):
            mat_float[i][j] = <double>matrix[i * 64 + j]
    
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
            
            temp = mat_float[j][i]
            for p in range(i + 1, size):
                mat_float[j][p] /= temp
            
            for k in range(size):
                if k != j and (mat_float[k][i] > epsilon or mat_float[k][i] < -epsilon):
                    temp = mat_float[k][i]
                    for p in range(i + 1, size):
                        mat_float[k][p] -= mat_float[j][p] * temp
    
    return rank


cdef void generate_matrix_c(uint64_t* seeds, uint16_t* out_matrix) noexcept nogil:
    """生成 64x64 滿秩矩陣（純 C，nogil）"""
    cdef uint64_t state[4]
    cdef int i, j, k
    cdef uint64_t val
    
    state[0] = seeds[0]
    state[1] = seeds[1]
    state[2] = seeds[2]
    state[3] = seeds[3]
    
    while True:
        for i in range(64):
            for j in range(0, 64, 16):
                val = xoshiro_next(state)
                for k in range(16):
                    out_matrix[i * 64 + j + k] = (val >> (4 * k)) & 0x0F
        
        if compute_rank_c(out_matrix) == 64:
            return
        # 否則繼續用當前 state 重試


cdef void heavy_hash_core(uint16_t* matrix, uint8_t* pow_hash, uint8_t* digest) noexcept nogil:
    """HeavyHash 核心計算（純 C，nogil）
    
    只做矩陣乘法和 XOR，不做最後的 cSHAKE256
    """
    cdef uint16_t v[64]
    cdef uint64_t p[64]
    cdef uint64_t s
    cdef int i, j
    
    # 展開成 64 個 4-bit 值
    for i in range(32):
        v[i * 2] = (pow_hash[i] >> 4) & 0x0F      # 高 4 bits
        v[i * 2 + 1] = pow_hash[i] & 0x0F         # 低 4 bits
    
    # 矩陣乘法
    for i in range(64):
        s = 0
        for j in range(64):
            s += <uint64_t>matrix[i * 64 + j] * <uint64_t>v[j]
        p[i] = (s >> 10) & 0x0F
    
    # XOR 回原 hash
    for i in range(32):
        digest[i] = pow_hash[i] ^ (((<uint8_t>p[i * 2] & 0x0F) << 4) | (<uint8_t>p[i * 2 + 1] & 0x0F))


# ═══════════════════════════════════════════════════════════════════════════════
# Python 接口
# ═══════════════════════════════════════════════════════════════════════════════

def generate_matrix(bytes pre_pow_hash):
    """
    生成 64x64 滿秩矩陣（Python 接口）
    
    參數:
        pre_pow_hash: 32 bytes pre-PoW hash
    
    返回:
        numpy.ndarray (64, 64) uint16
    """
    cdef uint64_t seeds[4]
    cdef uint16_t* matrix_c
    cdef int i, j
    
    # 提取種子
    seeds[0] = int.from_bytes(pre_pow_hash[0:8], 'little')
    seeds[1] = int.from_bytes(pre_pow_hash[8:16], 'little')
    seeds[2] = int.from_bytes(pre_pow_hash[16:24], 'little')
    seeds[3] = int.from_bytes(pre_pow_hash[24:32], 'little')
    
    # 分配 C 陣列
    matrix_c = <uint16_t*>malloc(64 * 64 * sizeof(uint16_t))
    if matrix_c == NULL:
        raise MemoryError("Failed to allocate matrix")
    
    try:
        # 在 nogil 區塊生成矩陣
        with nogil:
            generate_matrix_c(seeds, matrix_c)
        
        # 複製到 NumPy（給 Python 用）
        result = np.zeros((64, 64), dtype=np.uint16)
        for i in range(64):
            for j in range(64):
                result[i, j] = matrix_c[i * 64 + j]
        
        return result
    finally:
        free(matrix_c)


def compute_pow(bytes pre_pow_hash, uint64_t timestamp, uint64_t nonce, 
                np.ndarray[np.uint16_t, ndim=2] matrix):
    """
    計算完整 PoW hash
    
    參數:
        pre_pow_hash: 32 bytes
        timestamp: 時間戳
        nonce: 挖礦 nonce
        matrix: 預先生成的 64x64 矩陣
    
    返回:
        bytes(32) - PoW hash 結果
    """
    import struct
    
    cdef uint16_t* matrix_c
    cdef uint8_t pow_hash_c[32]
    cdef uint8_t digest_c[32]
    cdef int i, j
    
    # 構建 80 bytes header
    cdef bytes data = (
        pre_pow_hash + 
        struct.pack('<Q', timestamp) + 
        (b'\x00' * 32) + 
        struct.pack('<Q', nonce)
    )
    
    # 第一次 cSHAKE256（必須在 GIL 下）
    h = cSHAKE256.new(data=data, custom=b"ProofOfWorkHash")
    pow_hash = h.read(32)
    
    # 複製到 C 陣列
    matrix_c = <uint16_t*>malloc(64 * 64 * sizeof(uint16_t))
    if matrix_c == NULL:
        raise MemoryError("Failed to allocate matrix")
    
    try:
        for i in range(64):
            for j in range(64):
                matrix_c[i * 64 + j] = matrix[i, j]
        
        for i in range(32):
            pow_hash_c[i] = pow_hash[i]
        
        # 核心計算（nogil）
        with nogil:
            heavy_hash_core(matrix_c, pow_hash_c, digest_c)
        
        # 最終 cSHAKE256（必須在 GIL 下）
        digest = bytes(digest_c[i] for i in range(32))
        h2 = cSHAKE256.new(data=digest, custom=b"HeavyHash")
        return h2.read(32)
    
    finally:
        free(matrix_c)


def compute_pow_batch(bytes pre_pow_hash, uint64_t timestamp, 
                      list nonces, np.ndarray[np.uint16_t, ndim=2] matrix):
    """
    批次計算多個 nonce 的 PoW（減少 function call 開銷）
    
    返回:
        list of (nonce, pow_hash) tuples
    """
    import struct
    
    cdef uint16_t* matrix_c
    cdef uint8_t pow_hash_c[32]
    cdef uint8_t digest_c[32]
    cdef int i, j, n
    cdef uint64_t nonce
    
    results = []
    
    # 複製矩陣到 C
    matrix_c = <uint16_t*>malloc(64 * 64 * sizeof(uint16_t))
    if matrix_c == NULL:
        raise MemoryError("Failed to allocate matrix")
    
    try:
        for i in range(64):
            for j in range(64):
                matrix_c[i * 64 + j] = matrix[i, j]
        
        for nonce in nonces:
            # 構建 header
            data = (
                pre_pow_hash + 
                struct.pack('<Q', timestamp) + 
                (b'\x00' * 32) + 
                struct.pack('<Q', nonce)
            )
            
            # 第一次 hash
            h = cSHAKE256.new(data=data, custom=b"ProofOfWorkHash")
            pow_hash = h.read(32)
            
            for i in range(32):
                pow_hash_c[i] = pow_hash[i]
            
            # 核心計算（nogil）
            with nogil:
                heavy_hash_core(matrix_c, pow_hash_c, digest_c)
            
            # 最終 hash
            digest = bytes(digest_c[i] for i in range(32))
            h2 = cSHAKE256.new(data=digest, custom=b"HeavyHash")
            results.append((nonce, h2.read(32)))
        
        return results
    
    finally:
        free(matrix_c)
