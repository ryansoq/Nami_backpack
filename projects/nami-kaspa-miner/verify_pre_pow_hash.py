#!/usr/bin/env python3
"""
驗證 pre_pow_hash 計算
比較我的實現和官方的 kaspa_pow 結果
"""
import sys
import os
import struct
import hashlib

sys.path.insert(0, os.path.expanduser("~/nami-backpack/projects/nami-kaspa-miner"))
sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc

def hash_from_hex(hex_str: str) -> bytes:
    if not hex_str:
        return b'\x00' * 32
    return bytes.fromhex(hex_str)

def write_len(hasher, length: int):
    hasher.update(struct.pack('<Q', length))

def write_blue_work(hasher, blue_work: str):
    if not blue_work:
        hasher.update(struct.pack('<Q', 0))
        return
    hex_str = blue_work
    if len(hex_str) % 2 == 1:
        hex_str = '0' + hex_str
    work_bytes = bytes.fromhex(hex_str)
    start = 0
    while start < len(work_bytes) and work_bytes[start] == 0:
        start += 1
    write_len(hasher, len(work_bytes) - start)
    hasher.update(work_bytes[start:])

def my_pre_pow_hash(header) -> bytes:
    """我的 pre_pow_hash 實現"""
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

# 連接並獲取 template
address = "localhost:16210"
wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

channel = grpc.insecure_channel(address)
stub = kaspa_pb2_grpc.RPCStub(channel)

request = kaspa_pb2.KaspadMessage(
    getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
        payAddress=wallet,
        extraData="verify"
    )
)

responses = stub.MessageStream(iter([request]))
response = next(responses)

if not response.HasField('getBlockTemplateResponse'):
    print("❌ No template response")
    sys.exit(1)

block = response.getBlockTemplateResponse.block
header = block.header

print(f"📋 Header from node:")
print(f"   version: {header.version}")
print(f"   timestamp: {header.timestamp}")
print(f"   bits: 0x{header.bits:08x}")
print(f"   nonce: {header.nonce}")
print(f"   daaScore: {header.daaScore}")
print(f"   blueScore: {header.blueScore}")
print(f"   blueWork: {header.blueWork}")

# 我的計算
my_hash = my_pre_pow_hash(header)
print(f"\n🔢 My pre_pow_hash: {my_hash.hex()}")

# 嘗試導入 Rust kaspa_pow_py 並比較
try:
    import kaspa_pow_py
    print("✅ kaspa_pow_py loaded")
    
    # 用我的 pre_pow_hash 生成矩陣
    matrix = kaspa_pow_py.gen_matrix(my_hash)
    print(f"   Matrix generated OK")
    
    # 計算一個測試 PoW
    test_pow = kaspa_pow_py.compute_pow(my_hash, header.timestamp, 12345, matrix)
    print(f"   Test PoW: {test_pow.hex()}")
    
except ImportError as e:
    print(f"❌ kaspa_pow_py not available: {e}")

# 驗證 header 序列化
print(f"\n📦 Header serialization check:")
print(f"   hashMerkleRoot: {header.hashMerkleRoot}")
print(f"   acceptedIdMerkleRoot: {header.acceptedIdMerkleRoot}")
print(f"   utxoCommitment: {header.utxoCommitment}")
print(f"   pruningPoint: {header.pruningPoint}")
print(f"   parents levels: {len(header.parents)}")
if header.parents:
    print(f"   parents[0] hashes: {len(header.parents[0].parentHashes)}")
