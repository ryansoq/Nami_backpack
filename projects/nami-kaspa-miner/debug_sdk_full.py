#!/usr/bin/env python3
"""
Debug SDK full - 使用 kaspa SDK 完整提交流程
"""
import asyncio
import sys
import os
import time
import random

from kaspa import RpcClient

# Cython PoW
sys.path.insert(0, os.path.expanduser("~/nami-backpack/projects/nami-kaspa-miner"))
try:
    import kaspa_pow_v2
    print("✅ Cython PoW loaded", flush=True)
except ImportError:
    print("❌ Cython PoW not available", flush=True)
    sys.exit(1)

# gRPC for pre_pow_hash calculation
sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc
import struct
import hashlib

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

def calculate_pre_pow_hash_from_dict(header: dict) -> bytes:
    """從 SDK 返回的字典計算 pre_pow_hash"""
    hasher = hashlib.blake2b(digest_size=32)
    hasher.update(struct.pack('<H', header.get('version', 1)))
    
    parents = header.get('parents', [])
    write_len(hasher, len(parents))
    
    for level in parents:
        parent_hashes = level.get('parentHashes', [])
        write_len(hasher, len(parent_hashes))
        for h in parent_hashes:
            hasher.update(hash_from_hex(h))
    
    hasher.update(hash_from_hex(header.get('hashMerkleRoot', '')))
    hasher.update(hash_from_hex(header.get('acceptedIdMerkleRoot', '')))
    hasher.update(hash_from_hex(header.get('utxoCommitment', '')))
    hasher.update(struct.pack('<Q', 0))  # timestamp = 0
    hasher.update(struct.pack('<I', header.get('bits', 0)))
    hasher.update(struct.pack('<Q', 0))  # nonce = 0
    hasher.update(struct.pack('<Q', header.get('daaScore', 0)))
    hasher.update(struct.pack('<Q', header.get('blueScore', 0)))
    write_blue_work(hasher, header.get('blueWork', ''))
    hasher.update(hash_from_hex(header.get('pruningPoint', '')))
    
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

async def main():
    print("🔗 連接到 testnet node...", flush=True)
    
    client = RpcClient(resolver=None, url='ws://127.0.0.1:17210', encoding='borsh')
    await client.connect()
    print("✅ 已連接！", flush=True)
    
    wallet = 'kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m'
    
    for round_num in range(1, 6):
        print(f"\n🔄 Round {round_num}:", flush=True)
        
        # 獲取 template
        template = await client.get_block_template({
            'payAddress': wallet,
            'extraData': list(b'ShioKaze SDK')
        })
        
        block = template.get('block')
        header = block.get('header', {})
        
        timestamp = header.get('timestamp')
        bits = header.get('bits')
        
        print(f"   bits=0x{bits:08x}, daaScore={header.get('daaScore')}", flush=True)
        
        # 計算 pre_pow_hash
        pre_pow_hash = calculate_pre_pow_hash_from_dict(header)
        target = bits_to_target(bits)
        matrix = kaspa_pow_v2.generate_matrix(pre_pow_hash)
        
        # 挖礦（最多 60 秒）
        start_time = time.time()
        found = False
        attempts = 0
        
        while not found and (time.time() - start_time) < 60:
            # 限制 nonce 範圍避免 overflow (用 signed i64 最大值)
            nonce = random.randint(0, 0x7FFFFFFFFFFFFFFF)
            pow_hash = kaspa_pow_v2.compute_pow(pre_pow_hash, timestamp, nonce, matrix)
            hash_int = hash_to_int(pow_hash)
            attempts += 1
            
            if hash_int < target:
                found = True
                elapsed = time.time() - start_time
                print(f"   💎 Found nonce in {elapsed:.2f}s ({attempts} attempts)", flush=True)
                print(f"      hash < target: {hash_int < target}", flush=True)
                
                # 更新 header 的 nonce
                header['nonce'] = nonce
                block['header'] = header
                
                # 用 SDK 提交
                print(f"   📤 用 SDK 提交區塊...", flush=True)
                try:
                    result = await client.submit_block({
                        'block': block,
                        'allowNonDaaBlocks': False  # 注意大小寫
                    })
                    print(f"   📬 結果: {result}", flush=True)
                    
                    if result.get('report') == 'Success':
                        print(f"\n🎉 BLOCK ACCEPTED!", flush=True)
                        await client.disconnect()
                        return
                    else:
                        print(f"   ❌ Rejected: {result}", flush=True)
                except Exception as e:
                    print(f"   ❌ Submit error: {e}", flush=True)
        
        if not found:
            elapsed = time.time() - start_time
            print(f"   ⏱️ Timeout ({elapsed:.1f}s, {attempts} attempts)", flush=True)
    
    await client.disconnect()
    print("\n⏱️ 完成 5 輪", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
