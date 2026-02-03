#!/usr/bin/env python3
"""
Debug fresh block submit - 用新 template 快速提交
策略：用低難度或已知 nonce 快速驗證提交流程
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
    print("✅ Cython loaded", flush=True)
except:
    USE_CYTHON = False
    print("❌ Cython not available", flush=True)
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

def submit_block(stub, block):
    """提交區塊"""
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
        reason_name = kaspa_pb2.SubmitBlockResponseMessage.RejectReason.Name(resp.rejectReason)
        error_msg = resp.error.message if resp.HasField('error') else ""
        return resp.rejectReason == 0, reason_name, error_msg
    return False, "NO_RESPONSE", ""

# 連接
address = "localhost:16210"
wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

channel = grpc.insecure_channel(address)
stub = kaspa_pb2_grpc.RPCStub(channel)

print(f"📡 連接到 {address}...", flush=True)
print(f"💡 策略：快速挖礦 + 立即提交（< 1秒）\n", flush=True)

import random

attempts_total = 0
start_total = time.time()

for round_num in range(1, 11):  # Try 10 rounds
    # 獲取新 template
    request = kaspa_pb2.KaspadMessage(
        getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
            payAddress=wallet,
            extraData="fresh_test"
        )
    )
    
    responses = stub.MessageStream(iter([request]))
    response = next(responses)
    
    if not response.HasField('getBlockTemplateResponse'):
        print(f"❌ Round {round_num}: No template response", flush=True)
        continue
    
    block = response.getBlockTemplateResponse.block
    header = block.header
    
    pre_pow_hash = calculate_pre_pow_hash(header)
    target = bits_to_target(header.bits)
    matrix = kaspa_pow_v2.generate_matrix(pre_pow_hash)
    
    template_time = time.time()
    
    print(f"🔄 Round {round_num}: template bits=0x{header.bits:08x}, daaScore={header.daaScore}", flush=True)
    
    # 快速搜索（最多 5 秒）
    found = False
    attempts = 0
    max_time = 5.0  # 最多 5 秒
    
    while not found and (time.time() - template_time) < max_time:
        nonce = random.randint(0, 0xFFFFFFFFFFFFFFFF)
        pow_hash = kaspa_pow_v2.compute_pow(pre_pow_hash, header.timestamp, nonce, matrix)
        hash_int = hash_to_int(pow_hash)
        attempts += 1
        attempts_total += 1
        
        if hash_int < target:
            found = True
            elapsed = time.time() - template_time
            
            print(f"   💎 Found nonce in {elapsed:.2f}s ({attempts} attempts)", flush=True)
            print(f"      hash < target: {hash_int < target}", flush=True)
            
            # 立即提交
            block.header.nonce = nonce
            
            success, reason, error_msg = submit_block(stub, block)
            
            if success:
                print(f"   ✅ 🎉 BLOCK ACCEPTED!", flush=True)
                elapsed_total = time.time() - start_total
                print(f"\n🏆 成功！總計 {attempts_total} attempts, {elapsed_total:.1f}s", flush=True)
                sys.exit(0)
            else:
                print(f"   ❌ Rejected: {reason}", flush=True)
                if error_msg:
                    print(f"      Error: {error_msg}", flush=True)
    
    if not found:
        elapsed = time.time() - template_time
        print(f"   ⏱️ Timeout ({elapsed:.1f}s, {attempts} attempts)", flush=True)
    
    # 短暫等待再試
    time.sleep(0.1)

elapsed_total = time.time() - start_total
print(f"\n⏱️ 完成 10 輪，總計 {attempts_total} attempts, {elapsed_total:.1f}s", flush=True)
print(f"   平均 {attempts_total/elapsed_total:.0f} H/s", flush=True)
