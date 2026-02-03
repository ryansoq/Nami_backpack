#!/usr/bin/env python3
"""
Debug block parents structure
"""
import sys
import os

sys.path.insert(0, os.path.expanduser("~/kaspa-pminer"))
import kaspa_pb2
import kaspa_pb2_grpc
import grpc

address = "localhost:16210"
wallet = "kaspatest:qqxhwz070a3tpmz57alnc3zp67uqrw8ll7rdws9nqp8nsvptarw3jl87m5j2m"

channel = grpc.insecure_channel(address)
stub = kaspa_pb2_grpc.RPCStub(channel)

request = kaspa_pb2.KaspadMessage(
    getBlockTemplateRequest=kaspa_pb2.GetBlockTemplateRequestMessage(
        payAddress=wallet,
        extraData="debug_parents"
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
print(f"  version: {header.version}")
print(f"  timestamp: {header.timestamp}")
print(f"  bits: 0x{header.bits:08x}")
print(f"  daaScore: {header.daaScore}")
print(f"  blueScore: {header.blueScore}")

print(f"\n📦 Parents structure:")
print(f"  Total levels: {len(header.parents)}")

for i, level in enumerate(header.parents):
    parent_hashes = list(level.parentHashes)
    if i < 5 or i >= len(header.parents) - 2:  # Show first 5 and last 2
        print(f"  Level {i}: {len(parent_hashes)} parents")
        for j, h in enumerate(parent_hashes[:3]):  # Show first 3 hashes
            print(f"    [{j}] {h}")
        if len(parent_hashes) > 3:
            print(f"    ... ({len(parent_hashes)} total)")
    elif i == 5:
        print(f"  ...")

print(f"\n📦 Transactions:")
print(f"  Count: {len(block.transactions)}")
for i, tx in enumerate(block.transactions):
    print(f"  TX {i}:")
    print(f"    version: {tx.version}")
    print(f"    inputs: {len(tx.inputs)}")
    print(f"    outputs: {len(tx.outputs)}")
    print(f"    subnetworkId: {tx.subnetworkId}")
    print(f"    payload: {tx.payload[:40] if tx.payload else 'empty'}...")

print(f"\n📋 Other header fields:")
print(f"  hashMerkleRoot: {header.hashMerkleRoot}")
print(f"  acceptedIdMerkleRoot: {header.acceptedIdMerkleRoot}")
print(f"  utxoCommitment: {header.utxoCommitment}")
print(f"  blueWork: {header.blueWork}")
print(f"  pruningPoint: {header.pruningPoint}")
