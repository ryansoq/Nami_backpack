#!/usr/bin/env python3
"""
Debug block submit - 詳細檢查區塊提交
"""
import sys
import os
import struct
import hashlib
import time

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc

try:
    import kaspa_pow_v2
    USE_CYTHON = True
    print("✅ Cython loaded")
except:
    USE_CYTHON = False
    print("❌ Cython not available")
    sys.exit(1)

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

def calculate_pre_pow_hash(header) -> bytes:
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

# 連接
address = "localhost:16210"
wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

channel = grpc.insecure_channel(address)
stub = kaspa_pb2_grpc.RPCStub(channel)

# 獲取 template
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
    sys.exit(1)

block = response.getBlockTemplateResponse.block
header = block.header

print(f"\n📋 Block Header:")
print(f"  version: {header.version}")
print(f"  timestamp: {header.timestamp}")
print(f"  bits: 0x{header.bits:08x}")
print(f"  nonce: {header.nonce}")
print(f"  daaScore: {header.daaScore}")

# 計算 pre_pow_hash
pre_pow_hash = calculate_pre_pow_hash(header)
target = bits_to_target(header.bits)

print(f"\n🔢 pre_pow_hash: {pre_pow_hash.hex()}")
print(f"🎯 target: {target:064x}")

# 生成矩陣
matrix = kaspa_pow_v2.generate_matrix(pre_pow_hash)

# 挖礦找有效 nonce
print(f"\n⛏️ 搜索有效 nonce...")
import random
start_time = time.time()
found = False
attempts = 0

while not found and attempts < 1000000:
    nonce = random.randint(0, 0xFFFFFFFFFFFFFFFF)
    pow_hash = kaspa_pow_v2.compute_pow(pre_pow_hash, header.timestamp, nonce, matrix)
    hash_int = hash_to_int(pow_hash)
    attempts += 1
    
    if hash_int < target:
        found = True
        elapsed = time.time() - start_time
        print(f"\n💎 找到有效 nonce! ({attempts} attempts, {elapsed:.2f}s)")
        print(f"  nonce: {nonce}")
        print(f"  pow_hash: {pow_hash.hex()}")
        print(f"  hash_int: {hash_int:064x}")
        print(f"  target:   {target:064x}")
        print(f"  hash < target: {hash_int < target}")
        
        # 設置 nonce 並提交
        print(f"\n📤 提交區塊...")
        
        # 打印提交前的 header 狀態
        print(f"\n📋 提交前 header 狀態:")
        print(f"  nonce (before): {block.header.nonce}")
        
        # 設置 nonce
        block.header.nonce = nonce
        
        print(f"  nonce (after): {block.header.nonce}")
        
        # 檢查 protobuf 序列化
        serialized = block.SerializeToString()
        print(f"  serialized size: {len(serialized)} bytes")
        
        # 提交
        submit_req = kaspa_pb2.KaspadMessage(
            submitBlockRequest=kaspa_pb2.SubmitBlockRequestMessage(
                block=block,
                allowNonDAABlocks=False
            )
        )
        
        try:
            sub_responses = stub.MessageStream(iter([submit_req]))
            sub_response = next(sub_responses)
            
            if sub_response.HasField('submitBlockResponse'):
                resp = sub_response.submitBlockResponse
                print(f"\n📬 Response:")
                print(f"  report: {resp.report}")
                if resp.error and resp.error.message:
                    print(f"  error.message: {resp.error.message}")
                if resp.rejectReason:
                    print(f"  rejectReason: {resp.rejectReason}")
                    print(f"  rejectReason type: {type(resp.rejectReason)}")
                
                # 檢查是否成功
                if resp.report == 1:  # Success
                    print(f"\n✅ 🎉 BLOCK ACCEPTED!")
                else:
                    print(f"\n❌ Block rejected")
            else:
                print(f"❌ No submitBlockResponse field")
                print(f"  Available fields: {sub_response.ListFields()}")
        except Exception as e:
            print(f"❌ Submit error: {e}")
            import traceback
            traceback.print_exc()

if not found:
    print(f"\n⏱️ 超時，未找到有效 nonce ({attempts} attempts)")
