#!/usr/bin/env python3
"""
驗證 pre_pow_hash 計算 - 使用正確的 keyed blake2b
"""
import sys
import os
import struct
import hashlib

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

def old_pre_pow_hash(header) -> bytes:
    """舊的實現（沒有 key）"""
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

def new_pre_pow_hash(header) -> bytes:
    """新的實現（使用 key="BlockHash"）"""
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
        extraData="verify2"
    )
)

responses = stub.MessageStream(iter([request]))
response = next(responses)

if not response.HasField('getBlockTemplateResponse'):
    print("❌ No template response")
    sys.exit(1)

block = response.getBlockTemplateResponse.block
header = block.header

print(f"📋 Header:")
print(f"   version: {header.version}")
print(f"   timestamp: {header.timestamp}")
print(f"   bits: 0x{header.bits:08x}")

old_hash = old_pre_pow_hash(header)
new_hash = new_pre_pow_hash(header)

print(f"\n🔢 Pre-PoW Hash comparison:")
print(f"   Old (no key):    {old_hash.hex()}")
print(f"   New (key):       {new_hash.hex()}")
print(f"   Different:       {old_hash != new_hash}")

# 用新的 hash 測試 PoW
try:
    import kaspa_pow_v2
    matrix = kaspa_pow_v2.generate_matrix(new_hash)
    test_pow = kaspa_pow_v2.compute_pow(new_hash, header.timestamp, 12345, matrix)
    print(f"\n✅ New hash PoW test: {test_pow.hex()}")
except ImportError as e:
    print(f"\n❌ kaspa_pow_v2 not available: {e}")
