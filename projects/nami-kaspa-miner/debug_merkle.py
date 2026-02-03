#!/usr/bin/env python3
"""
Debug merkle root - 檢查區塊提交前後 merkle root 是否改變
"""
import sys
import os
import hashlib
import struct

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc

def hash_from_hex(hex_str: str) -> bytes:
    if not hex_str:
        return b'\x00' * 32
    return bytes.fromhex(hex_str)

def tx_id(tx) -> bytes:
    """計算交易 ID (hash)"""
    hasher = hashlib.blake2b(digest_size=32)
    
    # version
    hasher.update(struct.pack('<I', tx.version))
    
    # inputs
    hasher.update(struct.pack('<Q', len(tx.inputs)))
    for inp in tx.inputs:
        # previous outpoint
        hasher.update(hash_from_hex(inp.previousOutpoint.transactionId))
        hasher.update(struct.pack('<I', inp.previousOutpoint.index))
        # signature script
        script = bytes.fromhex(inp.signatureScript) if inp.signatureScript else b''
        hasher.update(struct.pack('<Q', len(script)))
        hasher.update(script)
        # sequence
        hasher.update(struct.pack('<Q', inp.sequence))
        # sigOpCount (only if inputs exist)
        hasher.update(struct.pack('<B', inp.sigOpCount))
    
    # outputs
    hasher.update(struct.pack('<Q', len(tx.outputs)))
    for out in tx.outputs:
        hasher.update(struct.pack('<Q', out.amount))
        # scriptPublicKey
        hasher.update(struct.pack('<H', out.scriptPublicKey.version))
        script = bytes.fromhex(out.scriptPublicKey.scriptPublicKey) if out.scriptPublicKey.scriptPublicKey else b''
        hasher.update(struct.pack('<Q', len(script)))
        hasher.update(script)
    
    # lockTime
    hasher.update(struct.pack('<Q', tx.lockTime))
    
    # subnetworkId
    subnet = bytes.fromhex(tx.subnetworkId) if tx.subnetworkId else b'\x00' * 20
    hasher.update(subnet)
    
    # gas
    hasher.update(struct.pack('<Q', tx.gas))
    
    # payload
    payload = bytes.fromhex(tx.payload) if tx.payload else b''
    hasher.update(struct.pack('<Q', len(payload)))
    hasher.update(payload)
    
    return hasher.digest()

def calc_merkle_root(hashes: list) -> bytes:
    """計算 Merkle Root"""
    if len(hashes) == 0:
        return b'\x00' * 32
    if len(hashes) == 1:
        return hashes[0]
    
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])  # duplicate last
        next_level = []
        for i in range(0, len(hashes), 2):
            hasher = hashlib.blake2b(digest_size=32)
            hasher.update(hashes[i])
            hasher.update(hashes[i+1])
            next_level.append(hasher.digest())
        hashes = next_level
    
    return hashes[0]

# 連接
address = "localhost:16210"
wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

channel = grpc.insecure_channel(address)
stub = kaspa_pb2_grpc.RPCStub(channel)

request = kaspa_pb2.KaspadMessage(
    getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
        payAddress=wallet,
        extraData="merkle_debug"
    )
)

responses = stub.MessageStream(iter([request]))
response = next(responses)

if not response.HasField('getBlockTemplateResponse'):
    print("❌ No template response")
    sys.exit(1)

block = response.getBlockTemplateResponse.block
header = block.header

print(f"📋 Block Header:")
print(f"  hashMerkleRoot (from node): {header.hashMerkleRoot}")
print(f"  transactions: {len(block.transactions)}")

# 計算每個交易的 hash
print(f"\n📦 Transaction IDs:")
tx_hashes = []
for i, tx in enumerate(block.transactions[:5]):  # 只顯示前 5 個
    # 注意：Kaspa 的 tx hash 可能有特殊計算方式
    print(f"  TX {i}: version={tx.version}, inputs={len(tx.inputs)}, outputs={len(tx.outputs)}")
    # tx_hash = tx_id(tx)
    # tx_hashes.append(tx_hash)
    # print(f"  TX {i}: {tx_hash.hex()}")

# 驗證修改 nonce 前後的區塊狀態
print(f"\n🔍 驗證區塊修改:")

# 保存原始值
original_nonce = header.nonce
original_merkle = header.hashMerkleRoot
original_timestamp = header.timestamp
original_bits = header.bits

print(f"  Before modification:")
print(f"    nonce: {original_nonce}")
print(f"    hashMerkleRoot: {original_merkle}")
print(f"    timestamp: {original_timestamp}")
print(f"    bits: 0x{original_bits:08x}")

# 修改 nonce
new_nonce = 123456789
block.header.nonce = new_nonce

print(f"\n  After setting nonce = {new_nonce}:")
print(f"    nonce: {header.nonce}")
print(f"    hashMerkleRoot: {header.hashMerkleRoot}")
print(f"    timestamp: {header.timestamp}")
print(f"    bits: 0x{header.bits:08x}")

# 檢查其他欄位是否改變
if header.hashMerkleRoot != original_merkle:
    print(f"\n  ⚠️ hashMerkleRoot CHANGED!")
else:
    print(f"\n  ✅ hashMerkleRoot unchanged")

if header.timestamp != original_timestamp:
    print(f"  ⚠️ timestamp CHANGED!")
else:
    print(f"  ✅ timestamp unchanged")

if header.bits != original_bits:
    print(f"  ⚠️ bits CHANGED!")
else:
    print(f"  ✅ bits unchanged")

# 序列化檢查
print(f"\n📦 Serialization check:")
serialized = block.SerializeToString()
print(f"  Block size: {len(serialized)} bytes")

# 反序列化驗證
new_block = kaspa_pb2.RpcBlock()
new_block.ParseFromString(serialized)
print(f"  After deserialize:")
print(f"    nonce: {new_block.header.nonce}")
print(f"    hashMerkleRoot: {new_block.header.hashMerkleRoot}")
print(f"    transactions: {len(new_block.transactions)}")
