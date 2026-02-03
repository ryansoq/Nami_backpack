#!/usr/bin/env python3
"""
Debug block structure - 詳細比較區塊結構
"""
import sys
import os
import json

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc
from google.protobuf import json_format

# 連接
address = "localhost:16210"
wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

channel = grpc.insecure_channel(address)
stub = kaspa_pb2_grpc.RPCStub(channel)

request = kaspa_pb2.KaspadMessage(
    getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
        payAddress=wallet,
        extraData="structure_debug"
    )
)

responses = stub.MessageStream(iter([request]))
response = next(responses)

if not response.HasField('getBlockTemplateResponse'):
    print("❌ No template response")
    sys.exit(1)

block = response.getBlockTemplateResponse.block
header = block.header

print("=" * 60)
print("📋 ORIGINAL BLOCK TEMPLATE (from node)")
print("=" * 60)

# 轉換為 JSON 查看完整結構
block_json = json_format.MessageToDict(block)
print(json.dumps(block_json, indent=2)[:5000])  # 只顯示前 5000 字

print("\n" + "=" * 60)
print("📋 HEADER DETAILS")
print("=" * 60)

print(f"version: {header.version}")
print(f"timestamp: {header.timestamp}")
print(f"bits: {header.bits} (0x{header.bits:08x})")
print(f"nonce: {header.nonce}")
print(f"daaScore: {header.daaScore}")
print(f"blueScore: {header.blueScore}")
print(f"blueWork: {header.blueWork}")
print(f"hashMerkleRoot: {header.hashMerkleRoot}")
print(f"acceptedIdMerkleRoot: {header.acceptedIdMerkleRoot}")
print(f"utxoCommitment: {header.utxoCommitment}")
print(f"pruningPoint: {header.pruningPoint}")

print(f"\nParents ({len(header.parents)} levels):")
for i, level in enumerate(header.parents[:3]):
    print(f"  Level {i}: {list(level.parentHashes)[:2]}{'...' if len(level.parentHashes) > 2 else ''}")
if len(header.parents) > 3:
    print(f"  ... ({len(header.parents)} total levels)")

print("\n" + "=" * 60)
print("📋 COINBASE TRANSACTION")
print("=" * 60)

if len(block.transactions) > 0:
    coinbase = block.transactions[0]
    print(f"version: {coinbase.version}")
    print(f"inputs: {len(coinbase.inputs)}")
    print(f"outputs: {len(coinbase.outputs)}")
    print(f"lockTime: {coinbase.lockTime}")
    print(f"subnetworkId: {coinbase.subnetworkId}")
    print(f"gas: {coinbase.gas}")
    print(f"payload (hex): {coinbase.payload}")
    print(f"payload length: {len(coinbase.payload) // 2} bytes")
    
    # 解析 payload
    if coinbase.payload:
        payload_bytes = bytes.fromhex(coinbase.payload)
        print(f"\nPayload breakdown:")
        # Kaspa coinbase payload 結構:
        # - blue_score (u64, 8 bytes)
        # - subsidy (u64, 8 bytes)
        # - miner_data (variable)
        if len(payload_bytes) >= 16:
            blue_score = int.from_bytes(payload_bytes[0:8], 'little')
            subsidy = int.from_bytes(payload_bytes[8:16], 'little')
            miner_data = payload_bytes[16:]
            print(f"  blue_score (from payload): {blue_score}")
            print(f"  subsidy (from payload): {subsidy} sompi = {subsidy / 1e8:.8f} KAS")
            print(f"  miner_data length: {len(miner_data)} bytes")
            print(f"  miner_data (hex): {miner_data.hex()[:64]}...")
            
            # 比較 blue_score
            if blue_score == header.blueScore:
                print(f"\n  ✅ blue_score matches header!")
            else:
                print(f"\n  ❌ blue_score MISMATCH!")
                print(f"     payload: {blue_score}")
                print(f"     header: {header.blueScore}")

print("\n" + "=" * 60)
print("📋 AFTER SETTING NONCE")
print("=" * 60)

# 設置 nonce
block.header.nonce = 12345678901234567890

print(f"nonce (after): {block.header.nonce}")

# 再次解析 coinbase payload 確認沒變
if len(block.transactions) > 0:
    coinbase = block.transactions[0]
    if coinbase.payload:
        payload_bytes = bytes.fromhex(coinbase.payload)
        if len(payload_bytes) >= 16:
            blue_score_after = int.from_bytes(payload_bytes[0:8], 'little')
            print(f"coinbase blue_score (after nonce set): {blue_score_after}")
            if blue_score_after == header.blueScore:
                print("✅ Still matches!")
            else:
                print("❌ MISMATCH after nonce set!")
