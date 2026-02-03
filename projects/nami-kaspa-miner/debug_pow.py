#!/usr/bin/env python3
"""
Debug PoW 計算 - 比對官方和我們的結果
"""

import sys
import os
import struct
import hashlib

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc

# 嘗試載入 Cython
try:
    import kaspa_pow_v2
    USE_CYTHON = True
    print("✅ Cython loaded")
except:
    USE_CYTHON = False
    print("❌ Cython not available")

# ===== pre_pow_hash 計算 =====

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
    """計算 pre_pow_hash（timestamp 和 nonce 設為 0）"""
    hasher = hashlib.blake2b(digest_size=32)
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
    hasher.update(struct.pack('<Q', 0))  # timestamp = 0
    hasher.update(struct.pack('<I', header.bits))
    hasher.update(struct.pack('<Q', 0))  # nonce = 0
    hasher.update(struct.pack('<Q', header.daaScore))
    hasher.update(struct.pack('<Q', header.blueScore))
    write_blue_work(hasher, header.blueWork)
    hasher.update(hash_from_hex(header.pruningPoint))
    
    return hasher.digest()

def bits_to_target(bits: int) -> int:
    exponent = (bits >> 24) & 0xFF
    mantissa = bits & 0x00FFFFFF
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    return target

def hash_to_int(hash_bytes: bytes) -> int:
    return int.from_bytes(hash_bytes, 'little')

# ===== 主程式 =====

def main():
    address = "localhost:16210"  # testnet
    wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"
    
    channel = grpc.insecure_channel(address)
    stub = kaspa_pb2_grpc.RPCStub(channel)
    
    # 取得 template
    request = kaspa_pb2.KaspadMessage(
        getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
            payAddress=wallet,
            extraData="debug"
        )
    )
    
    responses = stub.MessageStream(iter([request]))
    response = next(responses)
    
    if not response.HasField('getBlockTemplateResponse'):
        print("❌ No template response")
        return
    
    block = response.getBlockTemplateResponse.block
    header = block.header
    
    print(f"\n📋 Block Template:")
    print(f"  version: {header.version}")
    print(f"  timestamp: {header.timestamp}")
    print(f"  bits: 0x{header.bits:08x}")
    print(f"  daaScore: {header.daaScore}")
    print(f"  blueScore: {header.blueScore}")
    print(f"  blueWork: {header.blueWork}")
    print(f"  hashMerkleRoot: {header.hashMerkleRoot[:32]}...")
    
    # 計算 pre_pow_hash
    pre_pow_hash = calculate_pre_pow_hash(header)
    print(f"\n🔢 Calculated pre_pow_hash: {pre_pow_hash.hex()}")
    
    # 計算 target
    target = bits_to_target(header.bits)
    print(f"🎯 Target: {target:064x}")
    
    if USE_CYTHON:
        # 生成矩陣
        matrix = kaspa_pow_v2.generate_matrix(pre_pow_hash)
        print(f"📐 Matrix generated")
        
        # 挖一會兒看看
        import random
        import time
        print(f"\n⛏️ Mining test (searching for valid nonce)...")
        
        found = 0
        start = time.time()
        total = 0
        for i in range(500000):  # 增加到 50 萬次
            total += 1
            nonce = random.randint(0, 0xFFFFFFFFFFFFFFFF)
            pow_hash = kaspa_pow_v2.compute_pow(pre_pow_hash, header.timestamp, nonce, matrix)
            hash_int = hash_to_int(pow_hash)
            
            if hash_int < target:
                found += 1
                print(f"\n💎 Found valid nonce: {nonce}")
                print(f"  pow_hash: {pow_hash.hex()}")
                print(f"  hash_int: {hash_int:064x}")
                print(f"  target:   {target:064x}")
                print(f"  hash < target: {hash_int < target}")
                
                # 嘗試提交
                print(f"\n📤 Attempting to submit...")
                block.header.nonce = nonce
                
                submit_req = kaspa_pb2.KaspadMessage(
                    submitBlockRequest=kaspa_pb2.SubmitBlockRequestMessage(
                        block=block,
                        allowNonDAABlocks=False
                    )
                )
                
                sub_responses = stub.MessageStream(iter([submit_req]))
                sub_response = next(sub_responses)
                
                if sub_response.HasField('submitBlockResponse'):
                    resp = sub_response.submitBlockResponse
                    if resp.error and resp.error.message:
                        print(f"  ❌ Error: {resp.error.message}")
                    elif resp.rejectReason:
                        print(f"  ❌ Rejected: {resp.rejectReason}")
                    else:
                        print(f"  ✅ ACCEPTED!")
                else:
                    print(f"  ❌ No submit response")
                
                # 只測試第一個找到的
                break
        
        if found == 0:
            print("  No valid nonce found in 100 tries (expected with low hashrate)")
    
    print("\n✅ Debug complete")

if __name__ == "__main__":
    main()
